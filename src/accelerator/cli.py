"""accelerate CLI: graph-based Python to Rust JIT compiler."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from accelerator.aero_frontend import python_source_to_uast
from accelerator.config import find_config, get, load_config
from accelerator.errors import (
    IO_ERROR,
    UnsupportedError,
    UserError,
    check_toolchain,
    classify_cargo_error,
    format_unsupported_error,
)
from accelerator.precision_shield.shield import Shield
from accelerator.scaffold.engine import Engine
from accelerator.translator import UASTToHINTranslator

DEFAULT_BENCHMARK_ARG = 35


def _log(msg: str, args: argparse.Namespace) -> None:
    if not args.ci:
        print(msg)


def _verbose_log(msg: str, args: argparse.Namespace) -> None:
    if args.verbose and not args.ci:
        print(msg)


def _resolve_function_names(args: argparse.Namespace) -> List[str]:
    names: List[str] = []
    if args.function:
        names.append(args.function)
    if args.functions:
        names.extend(f.strip() for f in args.functions.split(",") if f.strip())
    if not names:
        raise UserError("No function specified. Use --function or --functions.")
    return names


def _resolve_output(args: argparse.Namespace, config: Dict[str, Any]) -> Path:
    path = args.output
    if not path:
        path = get(config, "build", "output", default="")
    if not path:
        path = "./libs"
    return Path(path)


def _parse_benchmark_args(raw: Optional[str]) -> Tuple[Any, ...]:
    if not raw:
        return ()
    try:
        value = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        raise UserError(f"Could not parse --benchmark-args: {raw!r}")
    if isinstance(value, tuple):
        return value
    return (value,)


def _default_benchmark_args(func: ast.FunctionDef) -> Tuple[Any, ...]:
    nargs = len(func.args.args)
    if nargs == 1:
        return (DEFAULT_BENCHMARK_ARG,)
    return (1,) * nargs


def _cache_key(
    source: str,
    function_names: List[str],
    target: Optional[str],
    shield_config: Dict[str, Any],
) -> str:
    hasher = hashlib.sha256()
    hasher.update(source.encode("utf-8"))
    hasher.update(",".join(sorted(function_names)).encode("utf-8"))
    if target:
        hasher.update(target.encode("utf-8"))
    hasher.update(repr(shield_config).encode("utf-8"))
    return hasher.hexdigest()


def _cache_path(key: str, args: argparse.Namespace) -> Path:
    cache_dir = Path.cwd() / ".accelerate-cache"
    if args.ci:
        # Avoid polluting workspace in CI; use a temporary cache.
        cache_dir = Path(tempfile.gettempdir()) / "accelerate-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{key}.so"


def _find_function(tree: ast.AST, name: str) -> Optional[ast.FunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _find_artifact(
    cargo_target_dir: Path,
    crate_name: str,
    target: Optional[str],
) -> Optional[Path]:
    search_roots = [cargo_target_dir]
    if target:
        search_roots.append(cargo_target_dir / target)

    candidates: List[Path] = []
    for root in search_roots:
        candidates.extend(root.rglob(f"lib{crate_name}.so"))
        candidates.extend(root.rglob(f"{crate_name}.dll"))
        candidates.extend(root.rglob(f"lib{crate_name}.dylib"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _extension_suffix() -> str:
    suffixes = importlib.machinery.EXTENSION_SUFFIXES
    return suffixes[0] if suffixes else ".so"


def _copy_artifact(src: Path, dest: Path) -> None:
    shutil.copy(src, dest)


def _write_fallback(
    output_dir: Path,
    module_name: str,
    entry: Path,
    function_names: List[str],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    wrapper = output_dir / f"{module_name}.py"
    safe_entry = str(entry.resolve())
    orig_module = f"_accel_orig_{module_name}"
    lines = [
        "import importlib.util",
        "import pathlib",
        f'_ENTRY = pathlib.Path(r"{safe_entry}")',
        f'_SPEC = importlib.util.spec_from_file_location("{orig_module}", _ENTRY)',
        f"_ORIG = importlib.util.module_from_spec(_SPEC)",
        f"_SPEC.loader.exec_module(_ORIG)",
    ]
    for name in function_names:
        lines.append(f"{name} = _ORIG.{name}")
    wrapper.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return wrapper


def _load_function_from_entry(entry: Path, function_name: str) -> Any:
    module_name = f"_accel_orig_{Path(entry).stem}"
    spec = importlib.util.spec_from_file_location(module_name, str(entry.resolve()))
    if spec is None or spec.loader is None:
        raise UserError(f"Could not load entry file {entry}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, function_name)


def _run_benchmark(
    output_dir: Path,
    module_name: str,
    entry: Path,
    function_name: str,
    benchmark_args: Tuple[Any, ...],
    args: argparse.Namespace,
) -> None:
    if not args.ci:
        print("Running benchmark...")

    py_func = _load_function_from_entry(entry, function_name)

    so_path = output_dir / f"{module_name}{_extension_suffix()}"
    if so_path.exists():
        rust_module = _load_module(so_path, module_name)
        rust_func = getattr(rust_module, function_name)
    else:
        # Fallback wrapper path.
        wrapper = output_dir / f"{module_name}.py"
        if wrapper.exists():
            rust_module = _load_module(wrapper, module_name)
            rust_func = getattr(rust_module, function_name)
        else:
            return

    # Warm up and run Python reference.
    try:
        py_func(*benchmark_args)
    except Exception as exc:
        if not args.ci:
            print(f"Python benchmark failed: {exc}")
        return

    t0 = time.perf_counter()
    py_result = py_func(*benchmark_args)
    py_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    rust_result = rust_func(*benchmark_args)
    rust_time = time.perf_counter() - t0

    if rust_result != py_result:
        if not args.ci:
            print("Warning: Rust result differs from Python result.")

    if rust_time == 0:
        rust_time = 1e-9
    speedup = py_time / rust_time
    if not args.ci:
        print(f"Rust:   {rust_time:.4f}s")
        print(f"Python: {py_time:.4f}s")
        print(f"Speedup: {speedup:.1f}x")


def _load_module(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise UserError(f"Could not load compiled module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _do_build(args: argparse.Namespace, config: Dict[str, Any]) -> int:
    entry = Path(args.entry)
    if not entry.is_file():
        raise UserError(f"Entry file not found: {args.entry}")

    source = entry.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise UserError(f"Syntax error in {entry}: {exc} (line {exc.lineno})")

    function_names = _resolve_function_names(args)
    for name in function_names:
        func = _find_function(tree, name)
        if func is None:
            raise UserError(f"Function {name!r} not found in {entry}")

    output_dir = _resolve_output(args, config)
    output_dir.mkdir(parents=True, exist_ok=True)
    module_name = entry.stem

    check_toolchain()

    shield_config: Dict[str, Any] = get(config, "precision_shield", default={}) or {}
    cache_key = _cache_key(
        source,
        function_names,
        args.target,
        shield_config,
    )
    cache_file = _cache_path(cache_key, args)

    use_cache = get(config, "build", "cache", default=True) and not args.no_cache
    if use_cache and cache_file.exists():
        _log("Cache hit: using previously compiled extension.", args)
        dest = output_dir / f"{module_name}{_extension_suffix()}"
        _copy_artifact(cache_file, dest)
        _log(f"Compiled extension: {dest}", args)
        if not args.no_benchmark:
            func = _find_function(tree, function_names[0])
            benchmark_args = _resolve_benchmark_args(args, config, func)
            _run_benchmark(
                output_dir, module_name, entry, function_names[0], benchmark_args, args
            )
        return 0

    _log("Parsing Python source...", args)
    uast = python_source_to_uast(source)
    _log("Building HIN graph...", args)
    graph = UASTToHINTranslator().translate(uast)

    _log("Running precision shield...", args)
    traits_by_name: Dict[str, Dict[str, Any]] = {}
    for name in function_names:
        traits = Shield(config=shield_config).analyze(
            graph, func_name=name, source=source
        )
        traits["function_name"] = name
        traits_by_name[name] = traits
    graph.traits = traits_by_name
    graph.traits_by_name = traits_by_name

    _log("Generating Rust crate...", args)
    engine = Engine()
    crate_root = engine.generate(
        graph,
        output_dir,
        module_name=module_name,
        function_names=function_names,
        source=source,
    )

    try:
        _format_and_build(
            crate_root,
            args,
            config,
            output_dir,
            module_name,
            cache_file,
            source,
            function_names,
            tree,
        )
    finally:
        if not args.no_clean:
            shutil.rmtree(crate_root, ignore_errors=True)
        else:
            _log(f"Temporary crate preserved at: {crate_root}", args)

    return 0


def _resolve_benchmark_args(
    args: argparse.Namespace,
    config: Dict[str, Any],
    func: ast.FunctionDef,
) -> Tuple[Any, ...]:
    raw = args.benchmark_args
    if not raw:
        raw = get(config, "benchmark", "args", default=None)
    if raw:
        return _parse_benchmark_args(raw)
    return _default_benchmark_args(func)


def _format_and_build(
    crate_root: Path,
    args: argparse.Namespace,
    config: Dict[str, Any],
    output_dir: Path,
    module_name: str,
    cache_file: Path,
    source: str,
    function_names: List[str],
    tree: ast.AST,
) -> None:
    _log("Formatting Rust source...", args)
    fmt_result = subprocess.run(
        ["cargo", "fmt"],
        cwd=crate_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if fmt_result.returncode != 0:
        raise UserError(
            f"Generated Rust code is not valid and cannot be formatted: {fmt_result.stdout}"
        )

    _log("Compiling Rust extension...", args)
    cargo_target = Path.home() / ".cache" / "accelerator" / "target"
    cargo_target.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["CARGO_TARGET_DIR"] = str(cargo_target)

    cmd = ["cargo", "build", "--release"]
    if args.target:
        cmd += ["--target", args.target]
    result = subprocess.run(
        cmd,
        cwd=crate_root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if args.verbose:
        print(result.stdout)
    if result.returncode != 0:
        raise UserError(classify_cargo_error(result.stdout))

    crate_name = _rust_identifier(module_name)
    artifact = _find_artifact(cargo_target, crate_name, args.target)
    if artifact is None:
        raise UserError("No compiled shared library found after cargo build.")

    use_cache = get(config, "build", "cache", default=True) and not args.no_cache
    if use_cache:
        _copy_artifact(artifact, cache_file)

    dest = output_dir / f"{module_name}{_extension_suffix()}"
    _copy_artifact(artifact, dest)
    _log(f"Compiled extension: {dest}", args)

    if not args.no_benchmark:
        func = _find_function(tree, function_names[0])
        benchmark_args = _resolve_benchmark_args(args, config, func)
        _run_benchmark(
            output_dir,
            module_name,
            Path(args.entry),
            function_names[0],
            benchmark_args,
            args,
        )


def _rust_identifier(name: str) -> str:
    """Best-effort Rust-safe identifier from the engine module."""
    import re

    _RUST_KEYWORDS = {
        "as",
        "break",
        "const",
        "continue",
        "crate",
        "else",
        "enum",
        "extern",
        "false",
        "fn",
        "for",
        "if",
        "impl",
        "in",
        "let",
        "loop",
        "match",
        "mod",
        "move",
        "mut",
        "pub",
        "ref",
        "return",
        "self",
        "Self",
        "static",
        "struct",
        "super",
        "trait",
        "true",
        "type",
        "unsafe",
        "use",
        "where",
        "while",
        "dyn",
        "async",
        "await",
        "abstract",
        "become",
        "box",
        "do",
        "final",
        "macro",
        "override",
        "priv",
        "typeof",
        "unsized",
        "virtual",
        "yield",
    }
    sanitized = re.sub(r"[^0-9a-zA-Z_]", "_", name)
    if not sanitized:
        sanitized = "module"
    if sanitized[0].isdigit() or sanitized in _RUST_KEYWORDS:
        sanitized = "a_" + sanitized
    return sanitized


def _build(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    verbose = get(config, "build", "verbose", default=False)
    if args.verbose:
        verbose = True
    args.verbose = verbose

    try:
        return _do_build(args, config)
    except (UserError, UnsupportedError) as exc:
        if args.fallback:
            _log("Compilation failed; falling back to Python implementation.", args)
            if not args.ci:
                print(
                    "Falling back to Python implementation; "
                    "consider fixing the issue for better performance.",
                    file=sys.stderr,
                )
            try:
                entry = Path(args.entry)
                source = entry.read_text(encoding="utf-8")
                tree = ast.parse(source)
                function_names = _resolve_function_names(args)
                for name in function_names:
                    if _find_function(tree, name) is None:
                        raise UserError(f"Function {name!r} not found in {entry}")
                wrapper = _write_fallback(
                    _resolve_output(args, config),
                    entry.stem,
                    entry,
                    function_names,
                )
                _log(f"Fallback module written: {wrapper}", args)
                return 0
            except Exception as wrap_exc:
                print(f"Fallback failed: {wrap_exc}", file=sys.stderr)
                return 1

        if isinstance(exc, UnsupportedError):
            print(
                format_unsupported_error(
                    exc,
                    source_path=Path(args.entry) if args.entry else None,
                    source=(
                        Path(args.entry).read_text(encoding="utf-8")
                        if args.entry and Path(args.entry).is_file()
                        else None
                    ),
                ),
                file=sys.stderr,
            )
        else:
            print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="accelerate",
        description="Graph-based Python to Rust JIT compiler.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--entry", required=True, help="Python source file")
    build_parser.add_argument(
        "--function",
        default=None,
        help="Function to compile",
    )
    build_parser.add_argument(
        "--functions",
        default=None,
        help="Comma-separated list of functions to compile",
    )
    build_parser.add_argument(
        "--output",
        default=None,
        help="Output directory",
    )
    build_parser.add_argument(
        "--fallback",
        action="store_true",
        help="On failure, write a Python wrapper module",
    )
    build_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Force a rebuild instead of using the cache",
    )
    build_parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Preserve the temporary Rust crate for debugging",
    )
    build_parser.add_argument(
        "--no-benchmark",
        action="store_true",
        help="Skip the benchmark after a successful build",
    )
    build_parser.add_argument(
        "--benchmark-args",
        default=None,
        help="Arguments to pass to the benchmark function",
    )
    build_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show full cargo output",
    )
    build_parser.add_argument(
        "--ci",
        action="store_true",
        help="Suppress non-essential output and return only exit codes",
    )
    build_parser.add_argument(
        "--target",
        default=None,
        help="Cargo target triple for cross-compilation",
    )
    build_parser.add_argument(
        "--config",
        default=None,
        help="Path to accelerate.toml config file",
    )
    build_parser.set_defaults(func=_build)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
