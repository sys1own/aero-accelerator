"""Precision shield: selects Rust types and traits from an analyzed graph."""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Set

from ..errors import UnsupportedError

_FLOAT_MATH_FUNCS: Set[str] = {
    "sqrt",
    "sin",
    "cos",
    "tan",
    "exp",
    "log",
    "log10",
    "pow",
    "ceil",
    "floor",
    "trunc",
}
_BITWISE_OPS: Set[type] = {
    ast.LShift,
    ast.RShift,
    ast.BitOr,
    ast.BitXor,
    ast.BitAnd,
    ast.Invert,
}


class Shield:
    """Inspect a function/HIN graph and decide which Rust types/traits are needed."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}

    def analyze(
        self,
        graph: Any,
        func_name: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return required Rust traits/types for the function represented by ``graph``.

        The graph is accepted because the CLI flow passes the HIN network here,
        but concrete type decisions are made from the original Python AST.
        """
        func = None
        if source:
            try:
                tree = ast.parse(source)
            except SyntaxError as exc:
                raise ValueError(f"Could not parse source: {exc}") from exc
            func = _find_function(tree, func_name)

        if func is None:
            # Fallback to graph-level hints if the AST is unavailable.
            return {
                "function_name": func_name,
                "arg_types": ["i64"],
                "return_type": "i64",
                "function_type": "i64",
                "recursive": False,
                "traits": self._traits(["Integer"]),
            }

        arg_names = [a.arg for a in func.args.args]
        function_type = _infer_number_type(func)

        if (
            self.config.get("default_float") in ("double", "f64")
            and function_type == "i64"
        ):
            function_type = "f64"

        if function_type == "f64" and _uses_bitwise(func):
            raise UnsupportedError(
                "Bitwise operations are only supported on integer-typed values",
                node=func,
            )

        uses_float = function_type == "f64"
        recursive = _is_recursive(func)

        traits = ["Integer"]
        if uses_float:
            traits.append("Float")

        return {
            "function_name": func_name,
            "arg_types": [function_type] * len(arg_names),
            "return_type": function_type,
            "function_type": function_type,
            "arg_names": arg_names,
            "recursive": recursive,
            "traits": self._traits(traits),
        }

    def _traits(self, traits: List[str]) -> List[str]:
        if self.config.get("enable_rug") is False:
            return []
        return traits


def _find_function(tree: ast.AST, name: Optional[str]) -> Optional[ast.FunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if name is None or node.name == name:
                return node
    return None


def _infer_number_type(func: ast.FunctionDef) -> str:
    """Pick i64 or f64 for the whole function based on its literals/operators."""
    for node in ast.walk(func):
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            return "f64"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return "f64"
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id == "math"
                and node.attr in ("pi", "e", "tau")
            ):
                return "f64"
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                base = node.func.value
                attr = node.func.attr
                if (
                    isinstance(base, ast.Name)
                    and base.id == "math"
                    and attr in _FLOAT_MATH_FUNCS
                ):
                    return "f64"
    return "i64"


def _is_recursive(func: ast.FunctionDef) -> bool:
    name = func.name
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            if _call_name(node) == name:
                return True
    return False


def _uses_bitwise(func: ast.FunctionDef) -> bool:
    """Return True if the function uses any bitwise operators or inversion."""
    for node in ast.walk(func):
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Invert):
            return True
        if isinstance(node, ast.BinOp) and type(node.op) in _BITWISE_OPS:
            return True
    return False


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""
