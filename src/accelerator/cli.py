"""accelerate CLI: graph-based Python to Rust JIT compiler."""

from __future__ import annotations

import argparse
import ast
import glob
import importlib.machinery
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .aero_frontend import python_source_to_uast
from .precision_shield.shield import Shield
from .scaffold.engine import Engine, RustGenerator, UnsupportedError
from .translator import UASTToHINTranslator

IO_ERROR = "Unsupported I/O operation detected. Aborting."


def _find_function(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _contains_io(func: ast.FunctionDef) -> bool:
    for node in ast.walk(func):
        if isinstance(node, (ast.With, ast.AsyncWith)):
            return True
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in RustGenerator.IO_NAMES:
                return True
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in RustGenerator.IO_MODULES
            ):
                return True
    return False


def _build(args: argparse.Namespace) -> int:
    entry = Path(args.entry)
    if not entry.is_file():
        print(f"Error: entry file not found: {args.entry}", file=sys.stderr)
        return 1

    source = entry.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    func = _find_function(tree, args.function)
    if func is None:
        print(f"Error: function {args.function!r} not found", file=sys.stderr)
        return 1

    if _contains_io(func):
        print(IO_ERROR, file=sys.stderr)
        return 1

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Graph pipeline
    uast = python_source_to_uast(source)
    graph = UASTToHINTranslator().translate(uast)
    traits = Shield().analyze(graph, func_name=args.function, source=source)
    graph.traits = traits

    # Rust source generation
    engine = Engine()
    crate_root = engine.generate(
        graph,
        output_dir,
        module_name=entry.stem,
        function_name=args.function,
        source=source,
    )

    # Build with cargo, using a shared target directory so dependencies are cached.
    cargo_target = Path.home() / ".cache" / "accelerator" / "target"
    cargo_target.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["CARGO_TARGET_DIR"] = str(cargo_target)

    print("cargo: compiling Rust extension...")
    result = subprocess.run(
        ["cargo", "build", "--release"],
        cwd=crate_root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(result.stdout)
    if result.returncode != 0:
        print("Error: cargo build failed", file=sys.stderr)
        return 1

    # Locate the shared library.
    release_dir = cargo_target / "release"
    so_files = list(release_dir.glob("*.so")) + list(release_dir.glob("*.dylib")) + list(release_dir.glob("*.dll"))
    if not so_files:
        # Fallback: search within the crate target dir if CARGO_TARGET_DIR was ignored.
        so_files = list(Path(crate_root).rglob("*.so"))
    if not so_files:
        print("Error: no compiled shared library found", file=sys.stderr)
        return 1

    # Use the most recently built artifact.
    so_file = max(so_files, key=lambda p: p.stat().st_mtime)
    suffix = importlib.machinery.EXTENSION_SUFFIXES[0] if importlib.machinery.EXTENSION_SUFFIXES else ".so"
    dest_name = f"{entry.stem}{suffix}"
    dest = output_dir / dest_name
    shutil.copy(so_file, dest)

    # Clean up the temporary crate.
    shutil.rmtree(crate_root, ignore_errors=True)

    print(f"Compiled extension: {dest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="accelerate", description="Graph-based Python to Rust JIT compiler.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--entry", required=True, help="Python source file")
    build_parser.add_argument("--function", required=True, help="Function to compile")
    build_parser.add_argument("--output", required=True, help="Output directory")
    build_parser.set_defaults(func=_build)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except UnsupportedError as exc:
        msg = str(exc)
        if msg == "io":
            print(IO_ERROR, file=sys.stderr)
        else:
            print(f"Unsupported operation: {msg}. Aborting.", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
