"""Tiny helpers shared between panel impl and its sibling submodules.

Lives in the ``panel`` package to break the import cycle between
``panel.impl`` and ``panel.mys``: both need value-coercion helpers and the
cache-policy resolver, and ``panel.mys`` is imported by ``panel.impl``.
"""

from __future__ import annotations

import argparse


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _number(value: object) -> float:
    return float(value) if _is_number(value) else 0.0


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _refresh_cache_policy(args: argparse.Namespace) -> str:
    if args.cache in {"only", "off"}:
        return str(args.cache)
    if args.force or args.cache == "use":
        return "refresh"
    return str(args.cache)


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
