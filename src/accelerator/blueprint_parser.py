"""Minimal blueprint parser handling only [system] and [precision_shield] sections."""

from __future__ import annotations

import json
from typing import Any, Dict


def parse_blueprint(text: str) -> Dict[str, Dict[str, Any]]:
    """Parse a blueprint text and return only the ``system`` and ``precision_shield`` sections."""
    sections: Dict[str, Dict[str, Any]] = {}
    current: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip()
            if current in ("system", "precision_shield"):
                sections[current] = {}
            else:
                current = None
            continue
        if current is None or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        sections[current][key] = _parse_value(value)

    return sections


def _parse_value(value: str) -> Any:
    lowered = value.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    if (
        (value.startswith("[") and value.endswith("]"))
        or (value.startswith("{") and value.endswith("}"))
    ):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    try:
        if "." in value or "e" in value.lower():
            return float(value)
        return int(value)
    except ValueError:
        pass
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value
