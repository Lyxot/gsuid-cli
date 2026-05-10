"""Shared private text-rendering helpers used by renderer modules.

These helpers handle the recurring task of coercing raw provider data
(arbitrary `object` values) into normalized strings, mappings, and
sequences for human-readable text output. Each helper has identical
semantics to the previously-duplicated copies in individual renderer
modules.

The names retain the leading underscore so importing modules can keep
their existing call sites unchanged (`_text(x)`, `_mapping(x)`, etc.).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping


def _text(value: object) -> str:
    if value is None or value == "":
        return "-"
    text = "".join(
        " " if unicodedata.category(char).startswith("C") else char for char in str(value)
    )
    text = " ".join(text.split())
    return text or "-"


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _first_mapping(value: object) -> Mapping[str, object]:
    values = _mapping_list(value)
    return values[0] if values else {}


def _finish(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"


def _yes_no(value: object) -> str:
    return "是" if bool(value) else "否"


def _nullable(value: object) -> str:
    text = _text(value)
    return "未设置" if text == "-" else text


def _join(value: object) -> str:
    items = [_text(item) for item in (value if isinstance(value, list) else [])]
    return "、".join(items) if items else "-"


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _number_text(value: object) -> str:
    number = _number(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")
