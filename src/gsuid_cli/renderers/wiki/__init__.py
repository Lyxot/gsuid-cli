"""GenshinUID-style wiki renderers."""

from __future__ import annotations

from collections.abc import Mapping


def enhanced_effect(row: Mapping[str, object]) -> tuple[str, bool]:
    """Return the added or replacement text from Ambr's enhanced description."""
    buff = row.get("descriptionBuff")
    if not isinstance(buff, str) or not buff.strip():
        return "", False
    base = row.get("description")
    if not isinstance(base, str):
        base = ""
    if buff == base:
        return "", False
    if base and buff.startswith(base):
        extra = buff[len(base) :]
        return (extra, False) if extra.strip() else ("", False)
    return buff, True
