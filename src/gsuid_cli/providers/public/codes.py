from __future__ import annotations

import re


def parse_active_codes(wikitext: str) -> list[dict[str, object]]:
    start = wikitext.find("==Active Codes==")
    end = wikitext.find("{{Code Row/Footer}}", start)
    if start < 0 or end < 0:
        return []
    section = re.sub(r"<!--.*?-->", "", wikitext[start:end], flags=re.DOTALL)
    rows = re.findall(r"\{\{Code Row\|([^{}]+)\}\}", section)
    codes = []
    for row in rows:
        code = _code_row(row)
        if code is not None:
            codes.append(code)
    return codes


def _code_row(row: str) -> dict[str, object] | None:
    parts = [part.strip() for part in row.split("|")]
    if len(parts) < 5:
        return None
    return {
        "codes": [code.strip() for code in parts[0].split(";") if code.strip()],
        "servers": _servers(parts[1]),
        "rewards": _rewards(parts[2]),
        "discovered_at": parts[3] or None,
        "expires_at": None if parts[4] in {"unknown", "indef"} else parts[4],
        "expiry_status": parts[4] or "unknown",
        "notes": parts[5] if len(parts) > 5 and parts[5] else None,
    }


def _servers(value: str) -> list[str]:
    return {
        "G": ["America", "Europe", "Asia", "TW/HK/Macao"],
        "A": ["America", "Europe", "Asia", "TW/HK/Macao", "China"],
        "CN": ["China"],
    }.get(value, [value])


def _rewards(value: str) -> list[dict[str, object]]:
    rewards = []
    for part in value.split(";"):
        name, _separator, count = part.partition("*")
        if name.strip():
            rewards.append({"name": name.strip(), "count": int(count) if count.isdigit() else None})
    return rewards
