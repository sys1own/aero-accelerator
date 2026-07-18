"""Integration tests for the accelerate CLI."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ACCELERATE = [sys.executable, "-m", "accelerator.cli"]


@pytest.fixture
def tmp_workspace():
    tmp = Path(tempfile.mkdtemp(prefix="accelerate-test-"))
    try:
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        # Clean up any cache the test created.
        cache = tmp / ".accelerate-cache"
        if cache.exists():
            shutil.rmtree(cache, ignore_errors=True)


def _write_source(tmp: Path, name: str, source: str) -> Path:
    entry = tmp / name
    entry.write_text(source, encoding="utf-8")
    return entry


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ACCELERATE + args,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def test_name_collision(tmp_workspace: Path) -> None:
    """A file named ``fib.py`` containing ``def fib`` must compile."""
    entry = _write_source(
        tmp_workspace,
        "fib.py",
        "def fib(n):\n"
        "    if n <= 1:\n"
        "        return n\n"
        "    return fib(n - 1) + fib(n - 2)\n",
    )
    out = tmp_workspace / "libs"
    result = _run(
        [
            "build",
            "--entry",
            str(entry),
            "--function",
            "fib",
            "--output",
            str(out),
            "--no-benchmark",
        ],
        cwd=tmp_workspace,
    )
    assert result.returncode == 0, result.stdout

    so = list(out.glob("fib*.so"))
    assert so, "Expected compiled extension"

    imported = _import_module(so[0], "fib")
    assert imported.fib(10) == 55


def test_multi_function(tmp_workspace: Path) -> None:
    """--functions builds multiple functions in one module."""
    entry = _write_source(
        tmp_workspace,
        "multi.py",
        "def fib(n):\n"
        "    if n <= 1:\n"
        "        return n\n"
        "    return fib(n - 1) + fib(n - 2)\n"
        "\n"
        "def fact(n):\n"
        "    if n <= 1:\n"
        "        return 1\n"
        "    return n * fact(n - 1)\n",
    )
    out = tmp_workspace / "libs"
    result = _run(
        [
            "build",
            "--entry",
            str(entry),
            "--functions",
            "fib,fact",
            "--output",
            str(out),
            "--no-benchmark",
        ],
        cwd=tmp_workspace,
    )
    assert result.returncode == 0, result.stdout

    so = list(out.glob("multi*.so"))
    assert so
    imported = _import_module(so[0], "multi")
    assert imported.fib(10) == 55
    assert imported.fact(5) == 120


def test_cache_hit_is_fast(tmp_workspace: Path) -> None:
    """A second build of the same source should use the cache."""
    entry = _write_source(
        tmp_workspace,
        "fib.py",
        "def fib(n):\n"
        "    if n <= 1:\n"
        "        return n\n"
        "    return fib(n - 1) + fib(n - 2)\n",
    )
    out = tmp_workspace / "libs"
    _run(
        [
            "build",
            "--entry",
            str(entry),
            "--function",
            "fib",
            "--output",
            str(out),
            "--no-benchmark",
        ],
        cwd=tmp_workspace,
    )
    result = _run(
        [
            "build",
            "--entry",
            str(entry),
            "--function",
            "fib",
            "--output",
            str(out),
            "--no-benchmark",
        ],
        cwd=tmp_workspace,
    )
    assert result.returncode == 0, result.stdout
    assert "Cache hit" in result.stdout


def test_io_error(tmp_workspace: Path) -> None:
    """Functions with I/O abort with the exact required message."""
    entry = _write_source(
        tmp_workspace,
        "bad.py",
        "def bad(n):\n"
        "    with open('x.txt') as f:\n"
        "        return int(f.read())\n",
    )
    out = tmp_workspace / "libs"
    result = _run(
        ["build", "--entry", str(entry), "--function", "bad", "--output", str(out)],
        cwd=tmp_workspace,
    )
    assert result.returncode == 1
    assert "Unsupported I/O operation detected. Aborting." in result.stdout


def test_fallback(tmp_workspace: Path) -> None:
    """``--fallback`` writes a Python wrapper when compilation cannot proceed."""
    entry = _write_source(
        tmp_workspace,
        "bad.py",
        "def bad(n):\n" "    return n + 1\n",
    )
    out = tmp_workspace / "libs"
    # Use an unsupported statement to force fallback.
    entry.write_text(
        "def bad(n):\n" "    for _ in [1, 2, 3]:\n" "        n += 1\n" "    return n\n",
        encoding="utf-8",
    )
    result = _run(
        [
            "build",
            "--entry",
            str(entry),
            "--function",
            "bad",
            "--output",
            str(out),
            "--fallback",
            "--no-benchmark",
        ],
        cwd=tmp_workspace,
    )
    assert result.returncode == 0, result.stdout
    wrapper = out / "bad.py"
    assert wrapper.exists()
    assert "Falling back to Python implementation" in result.stdout


def test_no_clean_preserves_crate(tmp_workspace: Path) -> None:
    """``--no-clean`` leaves the temporary Rust crate behind."""
    entry = _write_source(
        tmp_workspace,
        "fib.py",
        "def fib(n):\n"
        "    if n <= 1:\n"
        "        return n\n"
        "    return fib(n - 1) + fib(n - 2)\n",
    )
    out = tmp_workspace / "libs"
    result = _run(
        [
            "build",
            "--entry",
            str(entry),
            "--function",
            "fib",
            "--output",
            str(out),
            "--no-clean",
            "--no-cache",
            "--no-benchmark",
        ],
        cwd=tmp_workspace,
    )
    assert result.returncode == 0, result.stdout
    assert "Temporary crate preserved at" in result.stdout


def test_config_file(tmp_workspace: Path) -> None:
    """accelerate.toml defaults are respected."""
    entry = _write_source(
        tmp_workspace,
        "fib.py",
        "def fib(n):\n"
        "    if n <= 1:\n"
        "        return n\n"
        "    return fib(n - 1) + fib(n - 2)\n",
    )
    config = tmp_workspace / "accelerate.toml"
    config.write_text('[build]\noutput = "./out"\n', encoding="utf-8")
    result = _run(
        ["build", "--entry", str(entry), "--function", "fib", "--no-benchmark"],
        cwd=tmp_workspace,
    )
    assert result.returncode == 0, result.stdout
    assert (tmp_workspace / "out").exists()
    so = list((tmp_workspace / "out").glob("fib*.so"))
    assert so


def _import_module(path: Path, name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
