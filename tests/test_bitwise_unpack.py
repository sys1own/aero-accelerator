"""Regression tests for bitwise operators and integer type stability."""

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


def test_bitwise_unpack_compiles_cleanly(tmp_workspace: Path) -> None:
    """A pure-integer bitwise unpack compiles without float promotion or warnings."""
    source = (
        "def unpack(x):\n"
        "    lo = x & 0x0F\n"
        "    hi = (x >> 4) & 0x0F\n"
        "    mask = ~(x) & 0xFF\n"
        "    return lo, hi, mask\n"
    )
    entry = _write_source(tmp_workspace, "unpack.py", source)
    out = tmp_workspace / "libs"

    result = _run(
        [
            "build",
            "--entry",
            str(entry),
            "--function",
            "unpack",
            "--output",
            str(out),
            "--verbose",
            "--no-benchmark",
        ],
        cwd=tmp_workspace,
    )
    assert result.returncode == 0, result.stdout
    assert "_f64" not in result.stdout
    assert "warning" not in result.stdout.lower()

    so = list(out.glob("unpack*.so"))
    assert so, "Expected compiled extension"

    imported = _import_module(so[0], "unpack")
    lo, hi, mask = imported.unpack(0xAB)
    assert lo == 0x0B
    assert hi == 0x0A
    assert mask == 0xFF & ~0xAB


def test_bitwise_ops_remain_i64(tmp_workspace: Path) -> None:
    """Integer literals and bitwise operators must not be promoted to f64."""
    source = (
        "def bitops(x):\n"
        "    a = x | 1\n"
        "    b = a ^ 3\n"
        "    c = b << 2\n"
        "    d = c >> 1\n"
        "    return d & 0xFF\n"
    )
    entry = _write_source(tmp_workspace, "bitops.py", source)
    out = tmp_workspace / "libs"

    result = _run(
        [
            "build",
            "--entry",
            str(entry),
            "--function",
            "bitops",
            "--output",
            str(out),
            "--verbose",
            "--no-benchmark",
        ],
        cwd=tmp_workspace,
    )
    assert result.returncode == 0, result.stdout
    assert "_f64" not in result.stdout
    assert "warning" not in result.stdout.lower()

    so = list(out.glob("bitops*.so"))
    assert so, "Expected compiled extension"

    imported = _import_module(so[0], "bitops")
    assert imported.bitops(0x10) == (((((0x10 | 1) ^ 3) << 2) >> 1) & 0xFF)


def test_float_bitwise_conflict_is_rejected(tmp_workspace: Path) -> None:
    """A float-typed variable used in a bitwise operation is rejected cleanly."""
    source = "def bad(x):\n" "    y = x * 1.0\n" "    return y & 1\n"
    entry = _write_source(tmp_workspace, "bad.py", source)
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
            "--verbose",
            "--no-benchmark",
        ],
        cwd=tmp_workspace,
    )
    assert result.returncode != 0
    assert (
        "Bitwise operations are only supported on integer-typed values" in result.stdout
    )
