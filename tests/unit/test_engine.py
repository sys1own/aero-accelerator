"""Unit tests for the Rust code generator."""

from __future__ import annotations

import ast
import tempfile
from pathlib import Path

from accelerator.scaffold.engine import Engine, RustGenerator, UnsupportedError


def test_rust_generator_emits_function_block() -> None:
    source = "def fib(n):\n    if n <= 1:\n        return n\n    return fib(n - 1) + fib(n - 2)\n"
    func = ast.parse(source).body[0]
    assert isinstance(func, ast.FunctionDef)
    generator = RustGenerator(func, "fib", {"function_type": "i64"})
    code = generator.emit()
    assert '#[pyfunction(name = "fib")]' in code
    assert "fn _accel_fib(n: i64) -> i64" in code
    assert "return _accel_fib(n - 1_i64) + _accel_fib(n - 2_i64);" in code


def test_engine_generates_no_template_placeholders() -> None:
    source = "def fib(n):\n    if n <= 1:\n        return n\n    return fib(n - 1) + fib(n - 2)\n"
    engine = Engine()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        crate_root = engine.generate(
            object(),
            out,
            module_name="fib",
            function_names=["fib"],
            source=source,
        )
        lib_rs = (crate_root / "src" / "lib.rs").read_text(encoding="utf-8")
        assert "{functions}" not in lib_rs
        assert "{module_name}" not in lib_rs
        assert "#[pymodule]" in lib_rs
        assert "fn fib(" in lib_rs
        assert "_accel_fib" in lib_rs
