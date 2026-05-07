from __future__ import annotations

from datetime import timedelta, timezone
from urllib.parse import quote

CN_TZ = timezone(timedelta(hours=8))
AMBR_UI_URL = "https://gi.yatta.moe/assets/UI"
AMBR_MONSTER_UI_URL = f"{AMBR_UI_URL}/monster"
GENSHINUID_RESOURCE_BASE = "https://example.test/GenshinUID"
HAKUSH_UI_URL = "https://api.hakush.in/gi/UI"


def sort_key(value: object) -> tuple[int, str]:
    text = str(value)
    return (int(text), text) if text.isdigit() else (0, text)


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := optional_text(item))]


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def dict_value(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def list_value(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def ambr_item_icon_url(item_id: object) -> str | None:
    if item_id is None:
        return None
    text = str(item_id).strip()
    return f"{AMBR_UI_URL}/UI_ItemIcon_{text}.png" if text else None


def ambr_ui_icon_url(icon: object) -> str | None:
    if not isinstance(icon, str) or not icon:
        return None
    if icon.startswith("UI_RelicIcon_"):
        return f"{AMBR_UI_URL}/reliquary/{icon}.png"
    return f"{AMBR_UI_URL}/{icon}.png"


def genshinuid_resource_url(endpoint: str, filename: str) -> str:
    return f"{GENSHINUID_RESOURCE_BASE}/{endpoint}/{quote(filename)}"


def monster_icon_url(icon: str | None) -> str | None:
    if not icon or not icon.startswith("UI_"):
        return None
    return f"{AMBR_MONSTER_UI_URL}/{quote(icon)}.png"


def hakush_ui_url(icon: str | None) -> str | None:
    return f"{HAKUSH_UI_URL}/{quote(icon)}.webp" if icon else None


def optional_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
