"""Regression test for the Mandelbrot float-promotion bug."""

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


def test_mandelbrot_compiles_cleanly(tmp_workspace: Path) -> None:
    """A classic Mandelbrot iteration compiles without float/bool type errors."""
    source = (
        "def mandelbrot(c, max_iter):\n"
        "    zr = 0.0\n"
        "    zi = 0.0\n"
        "    for i in range(0, max_iter):\n"
        "        if (zr * zr) + (zi * zi) > 4.0:\n"
        "            return i\n"
        "        zr_new = (zr * zr) - (zi * zi) + c\n"
        "        zi = 2.0 * zr * zi\n"
        "        zr = zr_new\n"
        "    return max_iter\n"
    )
    entry = tmp_workspace / "mandelbrot.py"
    entry.write_text(source, encoding="utf-8")
    out = tmp_workspace / "libs"

    result = _run(
        [
            "build",
            "--entry",
            str(entry),
            "--function",
            "mandelbrot",
            "--output",
            str(out),
            "--verbose",
            "--no-benchmark",
        ],
        cwd=tmp_workspace,
    )
    assert result.returncode == 0, result.stdout
    assert "warning" not in result.stdout.lower()

    so = list(out.glob("mandelbrot*.so"))
    assert so, "Expected compiled extension"

    imported = _import_module(so[0], "mandelbrot")
    assert imported.mandelbrot(0.0, 100) == 100.0
    assert imported.mandelbrot(1.0, 100) == 3.0
