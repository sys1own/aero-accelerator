"""Regression tests for bitwise-driven type inference."""

from __future__ import annotations

import re
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


def test_untyped_args_bitwise_with_default_float(tmp_workspace: Path) -> None:
    """Bitwise ops should drive arg inference to i64 even when default_float=f64."""
    (tmp_workspace / "accelerate.toml").write_text(
        '[precision_shield]\ndefault_float = "f64"\n', encoding="utf-8"
    )
    entry = _write_source(
        tmp_workspace,
        "func4.py",
        "def func(a, b):\n" "    return a & b\n",
    )
    out = tmp_workspace / "libs"

    result = _run(
        [
            "build",
            "--entry",
            str(entry),
            "--function",
            "func",
            "--output",
            str(out),
            "--verbose",
            "--no-clean",
            "--no-benchmark",
        ],
        cwd=tmp_workspace,
    )
    assert result.returncode == 0, result.stdout
    crate_match = re.search(r"Temporary crate preserved at: (.+)", result.stdout)
    assert crate_match, "Expected temporary crate path in verbose output"
    lib_rs = Path(crate_match.group(1)) / "src" / "lib.rs"
    source = lib_rs.read_text(encoding="utf-8")
    assert "fn _accel_func(a: i64, b: i64) -> i64" in source

    so = list(out.glob("func4*.so"))
    assert so, "Expected compiled extension"

    imported = _import_module(so[0], "func4")
    assert imported.func(5, 3) == (5 & 3)


def test_f64_operand_in_bitwise_is_rejected(tmp_workspace: Path) -> None:
    """A bitwise operand that resolves to f64 is still rejected cleanly."""
    (tmp_workspace / "accelerate.toml").write_text(
        '[precision_shield]\ndefault_float = "f64"\n', encoding="utf-8"
    )
    entry = _write_source(
        tmp_workspace,
        "bad4.py",
        "def bad(x):\n" "    y = x * 1.0\n" "    return y & 1\n",
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
            "--verbose",
            "--no-benchmark",
        ],
        cwd=tmp_workspace,
    )
    assert result.returncode != 0
    assert (
        "Bitwise operations are only supported on integer-typed values" in result.stdout
    )
