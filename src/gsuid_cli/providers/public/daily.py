from __future__ import annotations

from datetime import datetime, timedelta

from gsuid_cli.core.errors import EXIT_INVALID_INPUT, CliError
from gsuid_cli.providers.public.common import (
    CN_TZ,
    ambr_item_icon_url,
    ambr_ui_icon_url,
    optional_int,
)

DAY_NAMES = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
DAILY_RESET_OFFSET = timedelta(hours=4)
WEAPON_DOMAIN_MARKER = "炼武"


def daily_domain(value: dict[str, object], upgrades: dict[str, object]) -> dict[str, object]:
    reward_ids = value.get("reward") if isinstance(value.get("reward"), list) else []
    name = value.get("name")
    material_id = reward_ids[-1] if reward_ids else None
    item_type = "weapon" if WEAPON_DOMAIN_MARKER in str(name or "") else "avatar"
    return {
        "id": str(value.get("id") or ""),
        "name": name,
        "city": value.get("city"),
        "reward_item_ids": reward_ids,
        "domain_icon_url": ambr_item_icon_url(material_id),
        "items": _daily_domain_items(reward_ids, upgrades, item_type),
    }


def day_from_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%A").lower()
    except ValueError as exc:
        raise CliError(
            "INVALID_ARGUMENT",
            "date must use YYYY-MM-DD format",
            EXIT_INVALID_INPUT,
            {"date": value},
        ) from exc


def current_daily_day() -> str:
    return (datetime.now(CN_TZ) - DAILY_RESET_OFFSET).strftime("%A").lower()


def _daily_domain_items(
    reward_ids: list[object],
    upgrades: dict[str, object],
    item_type: str,
) -> list[dict[str, object]]:
    data = upgrades.get(item_type)
    if not isinstance(data, dict):
        return []
    reward_ints = {optional_int(item_id) for item_id in reward_ids}
    reward_ints.discard(None)

    items: list[dict[str, object]] = []
    seen: set[str] = set()
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        costs = value.get("items")
        if not isinstance(costs, dict):
            continue
        if not any(optional_int(cost_id) in reward_ints for cost_id in costs):
            continue
        item_id = str(value.get("id") or key)
        if item_id in seen:
            continue
        seen.add(item_id)
        icon = value.get("icon")
        items.append(
            {
                "id": item_id,
                "type": item_type,
                "name": value.get("name"),
                "rank": value.get("rank"),
                "icon": icon,
                "icon_url": ambr_ui_icon_url(icon),
            }
        )
    return items
