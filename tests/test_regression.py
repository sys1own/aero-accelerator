"""Regression tests for the three critical patches."""

from __future__ import annotations

import math
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
        cache = tmp / ".accelerate-cache"
        if cache.exists():
            shutil.rmtree(cache, ignore_errors=True)


def _write_source(tmp: Path, name: str, source: str) -> Path:
    entry = tmp / name
    entry.write_text(source, encoding="utf-8")
    return entry


def _run(args: list[str], cwd: Path):
    return subprocess.run(
        ACCELERATE + args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def _import_module(path: Path, name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_math_pi_constant_compiles(tmp_workspace: Path) -> None:
    """`math.pi` is lowered to a float literal and compiles to a working extension."""
    entry = _write_source(
        tmp_workspace,
        "circle.py",
        "import math\n" "\n" "def area(r):\n" "    return math.pi * r * r\n",
    )
    out = tmp_workspace / "libs"
    result = _run(
        [
            "build",
            "--entry",
            str(entry),
            "--function",
            "area",
            "--output",
            str(out),
            "--no-benchmark",
        ],
        cwd=tmp_workspace,
    )
    assert result.returncode == 0, result.stdout

    so = list(out.glob("circle*.so"))
    assert so, "Expected compiled extension"

    imported = _import_module(so[0], "circle")
    assert imported.area(2.0) == pytest.approx(4.0 * math.pi)


def test_print_is_rejected_without_fallback(tmp_workspace: Path) -> None:
    """A function containing `print()` aborts with the exact I/O error message."""
    entry = _write_source(
        tmp_workspace,
        "bad.py",
        "def bad(n):\n" '    print("hello")\n' "    return n + 1\n",
    )
    out = tmp_workspace / "libs"
    result = _run(
        ["build", "--entry", str(entry), "--function", "bad", "--output", str(out)],
        cwd=tmp_workspace,
    )
    assert result.returncode == 1
    assert "Unsupported I/O operation detected. Aborting." in result.stdout


def test_print_falls_back_with_fallback(tmp_workspace: Path, capsys) -> None:
    """`--fallback` produces a Python wrapper when the source contains `print()`."""
    entry = _write_source(
        tmp_workspace,
        "bad.py",
        "def bad(n):\n" '    print("hello")\n' "    return n + 1\n",
    )
    out = tmp_workspace / "libs"
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
    assert "Falling back to Python implementation" in result.stdout

    wrapper = out / "bad.py"
    assert wrapper.exists()

    sys.path.insert(0, str(out))
    try:
        import bad as fallback_module  # type: ignore[import-not-found]

        assert fallback_module.bad(5) == 6
    finally:
        sys.path.pop(0)

    captured = capsys.readouterr()
    assert "hello" in captured.out


def test_no_rug_unused_import_warning(tmp_workspace: Path) -> None:
    """A plain integer build no longer emits `unused import: rug::Integer`."""
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
            "--verbose",
            "--no-benchmark",
        ],
        cwd=tmp_workspace,
    )
    assert result.returncode == 0, result.stdout
    assert "unused import: rug::Integer" not in result.stdout
    assert "rug" not in result.stdout


def test_immutable_local_omits_mut(tmp_workspace: Path) -> None:
    """A local variable assigned only once does not receive an unnecessary `mut`."""
    entry = _write_source(
        tmp_workspace,
        "square.py",
        "def square(x):\n" "    y = x * x\n" "    return y\n",
    )
    out = tmp_workspace / "libs"
    result = _run(
        [
            "build",
            "--entry",
            str(entry),
            "--function",
            "square",
            "--output",
            str(out),
            "--verbose",
            "--no-benchmark",
        ],
        cwd=tmp_workspace,
    )
    assert result.returncode == 0, result.stdout
    assert "does not need to be mutable" not in result.stdout
    assert "warning" not in result.stdout.lower()

    so = list(out.glob("square*.so"))
    assert so, "Expected compiled extension"

    imported = _import_module(so[0], "square")
    assert imported.square(7) == 49
