from __future__ import annotations

from gsuid_cli.providers.public.common import ambr_ui_icon_url, dict_value


def normalize_wiki_item(kind: str, item: dict[str, object]) -> dict[str, object]:
    common = {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or ""),
        "rank": item.get("rank"),
        "icon": item.get("icon"),
        "icon_url": ambr_ui_icon_url(item.get("icon")),
        "route": item.get("route"),
    }
    if kind == "character":
        return {
            **common,
            "element": item.get("element"),
            "weapon_type": item.get("weaponType"),
            "region": item.get("region"),
            "birthday": item.get("birthday"),
            "release": item.get("release"),
            "title": _nested(item, "fetter", "title"),
            "description": _nested(item, "fetter", "detail"),
            "ascension": item.get("ascension"),
            "upgrade": item.get("upgrade"),
            "talent": item.get("talent"),
            "constellation": item.get("constellation"),
        }
    if kind == "weapon":
        return {
            **common,
            "weapon_type": item.get("type"),
            "description": item.get("description"),
            "special_prop": item.get("specialProp"),
            "affixes": _affixes(item.get("affix")),
            "ascension": item.get("ascension"),
            "upgrade": item.get("upgrade"),
        }
    if kind == "artifact":
        return {
            **common,
            "level_list": item.get("levelList"),
            "bonuses": item.get("affixList") or item.get("setBonus"),
            "suit": _artifact_suit(item.get("suit")),
            "source": item.get("source"),
        }
    if kind == "food":
        return {
            **common,
            "description": item.get("description"),
            "effect": item.get("effect"),
            "recipe": item.get("recipe"),
        }
    return {
        **common,
        "enemy_type": item.get("type"),
        "title": item.get("title"),
        "special_name": item.get("specialName"),
        "description": item.get("description"),
        "tips": item.get("tips"),
    }


def ordered_dict_items(value: dict[str, object]) -> list[dict[str, object]]:
    return [item for item in value.values() if isinstance(item, dict)]


def indexed_item(value: dict[str, object], index: int) -> dict[str, object] | None:
    rows = ordered_dict_items(value)
    if index < 1 or index > len(rows):
        return None
    return rows[index - 1]


def upgrade_materials(value: object) -> dict[str, object]:
    upgrade = dict_value(value)
    return {
        "promote": upgrade.get("promote") or [],
        "prop": upgrade.get("prop") or [],
        "awaken_cost": upgrade.get("awakenCost") or [],
    }


def talent_materials(value: object) -> list[dict[str, object]]:
    talents = dict_value(value)
    rows = []
    for index, talent in enumerate(ordered_dict_items(talents), start=1):
        promote = dict_value(talent.get("promote"))
        rows.append(
            {
                "index": index,
                "name": talent.get("name"),
                "type": talent.get("type"),
                "promote": promote,
            }
        )
    return rows


def _nested(item: dict[str, object], key: str, nested_key: str) -> object | None:
    value = item.get(key)
    if not isinstance(value, dict):
        return None
    return value.get(nested_key)


def _affixes(value: object) -> list[dict[str, object]]:
    if not isinstance(value, dict):
        return []
    return [
        {
            "id": str(key),
            "name": affix.get("name"),
            "upgrade": affix.get("upgrade"),
        }
        for key, affix in value.items()
        if isinstance(affix, dict)
    ]


def _artifact_suit(value: object) -> list[dict[str, object]]:
    if not isinstance(value, dict):
        return []
    slot_names = {
        "EQUIP_BRACER": "flower",
        "EQUIP_NECKLACE": "plume",
        "EQUIP_SHOES": "sands",
        "EQUIP_RING": "goblet",
        "EQUIP_DRESS": "circlet",
    }
    parts: list[dict[str, object]] = []
    for key in ("EQUIP_BRACER", "EQUIP_NECKLACE", "EQUIP_SHOES", "EQUIP_RING", "EQUIP_DRESS"):
        part = value.get(key)
        if not isinstance(part, dict):
            continue
        icon = part.get("icon")
        parts.append(
            {
                "slot": slot_names[key],
                "name": part.get("name"),
                "description": part.get("description"),
                "max_level": part.get("maxLevel"),
                "icon": icon,
                "icon_url": ambr_ui_icon_url(icon),
            }
        )
    return parts
