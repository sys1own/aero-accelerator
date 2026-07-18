"""Unit tests for error classification."""

from accelerator.errors import classify_cargo_error, format_unsupported_error
from accelerator.scaffold.engine import UnsupportedError


def test_classify_name_collision() -> None:
    assert "Name conflict" in classify_cargo_error(
        "error[E0428]: the name `fib` is defined multiple times"
    )


def test_classify_missing_m4() -> None:
    assert "m4" in classify_cargo_error("configure: error: No usable m4 in $PATH")


def test_format_io_error() -> None:
    err = UnsupportedError("io")
    assert "Unsupported I/O operation detected. Aborting." == format_unsupported_error(
        err
    )


def test_format_unsupported_with_line() -> None:
    import ast

    node = ast.parse("def f():\n    pass\n").body[0]
    err = UnsupportedError("Unsupported statement: Pass", node=node)
    text = format_unsupported_error(err, source_path=None, source=None)
    assert "Unsupported operation: Unsupported statement: Pass" in text
    assert "Line: 1" in text
