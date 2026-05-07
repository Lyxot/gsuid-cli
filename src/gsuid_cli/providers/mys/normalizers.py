from __future__ import annotations

import json
from datetime import datetime

from gsuid_cli.core.errors import EXIT_UPSTREAM, CliError
from gsuid_cli.providers.mys.constants import CN_TIMEZONE, ELEMENT_ID_BY_NAME, PROVIDER


def _payload_data(
    payload: dict[str, object],
    category: str,
    source: dict[str, object],
) -> dict[str, object]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise CliError(
            "UPSTREAM_INVALID_RESPONSE",
            "Provider returned an unexpected response shape.",
            EXIT_UPSTREAM,
            {"provider": PROVIDER, "category": category},
            source=source,
        )
    return data


def _daily_note(data: dict[str, object]) -> dict[str, object]:
    keys = (
        "current_resin",
        "max_resin",
        "resin_recovery_time",
        "finished_task_num",
        "total_task_num",
        "is_extra_task_reward_received",
        "remain_resin_discount_num",
        "resin_discount_num_limit",
        "current_expedition_num",
        "max_expedition_num",
        "expeditions",
        "current_home_coin",
        "max_home_coin",
        "home_coin_recovery_time",
        "transformer",
        "daily_task",
        "archon_quest_progress",
    )
    return {key: data.get(key) for key in keys}


def _player_summary(data: dict[str, object]) -> dict[str, object]:
    stats = data.get("stats")
    avatars = data.get("avatars")
    explorations = data.get("world_explorations")
    homes = data.get("homes")
    if not isinstance(stats, dict):
        stats = {}
    if not isinstance(avatars, list):
        avatars = []
    if not isinstance(explorations, list):
        explorations = []
    if not isinstance(homes, list):
        homes = []

    return {
        "role": {
            "nickname": data.get("nickname"),
            "level": data.get("level"),
            "region": data.get("region"),
            "region_name": data.get("region_name"),
            "avatar_icon": data.get("avatar_icon"),
        },
        "stats": stats,
        "avatars": [_avatar_summary(avatar) for avatar in avatars if isinstance(avatar, dict)],
        "avatar_count": len([avatar for avatar in avatars if isinstance(avatar, dict)]),
        "world_explorations": [
            exploration for exploration in explorations if isinstance(exploration, dict)
        ],
        "homes": [home for home in homes if isinstance(home, dict)],
    }


def _role_needs_identity(role: object) -> bool:
    if not isinstance(role, dict):
        return False
    return role.get("nickname") in (None, "") or role.get("level") in (None, "")


def _merge_role_identity(summary: dict[str, object], role: dict[str, object]) -> None:
    summary_role = summary.get("role")
    if not isinstance(summary_role, dict):
        return
    for key in ("nickname", "level", "region", "region_name"):
        if summary_role.get(key) in (None, "") and role.get(key) not in (None, ""):
            summary_role[key] = role[key]


def _avatar_summary(avatar: dict[str, object]) -> dict[str, object]:
    return {
        "id": avatar.get("id"),
        "name": avatar.get("name"),
        "element": avatar.get("element"),
        "level": avatar.get("level"),
        "rarity": avatar.get("rarity"),
        "icon": avatar.get("icon"),
    }


def _character(character: dict[str, object]) -> dict[str, object]:
    weapon = character.get("weapon")
    reliquaries = character.get("reliquaries")
    constellations = character.get("constellations")
    costumes = character.get("costumes")
    if not isinstance(weapon, dict):
        weapon = {}
    if not isinstance(reliquaries, list):
        reliquaries = []
    if not isinstance(constellations, list):
        constellations = []
    if not isinstance(costumes, list):
        costumes = []

    return {
        "id": character.get("id"),
        "name": character.get("name"),
        "element": character.get("element"),
        "level": character.get("level"),
        "rarity": character.get("rarity"),
        "fetter": character.get("fetter"),
        "actived_constellation_num": character.get("actived_constellation_num"),
        "image": character.get("image"),
        "icon": character.get("icon"),
        "weapon": {
            "id": weapon.get("id"),
            "name": weapon.get("name"),
            "type": weapon.get("type"),
            "rarity": weapon.get("rarity"),
            "level": weapon.get("level"),
            "promote_level": weapon.get("promote_level"),
            "affix_level": weapon.get("affix_level"),
            "icon": weapon.get("icon"),
        },
        "reliquaries": [item for item in reliquaries if isinstance(item, dict)],
        "constellations": [item for item in constellations if isinstance(item, dict)],
        "costumes": [item for item in costumes if isinstance(item, dict)],
    }


def _inventory(data: dict[str, object]) -> dict[str, object]:
    overall = _inventory_items(data.get("overall_consume"))
    categories = {}
    material_consume = data.get("overall_material_consume")
    if not isinstance(material_consume, dict):
        material_consume = {}
    for key in (
        "avatar_consume",
        "avatar_skill_consume",
        "weapon_consume",
        "reliquary_consume",
    ):
        categories[key] = _inventory_items(material_consume.get(key))
    return {
        "has_user_info": data.get("has_user_info"),
        "overall": overall,
        "categories": categories,
        "count": len(overall),
        "raw_count": {
            key: len(value) for key, value in categories.items() if isinstance(value, list)
        },
    }


def _inventory_items(value: object) -> list[dict[str, object]]:
    items = []
    for item in _dict_list(value):
        if item.get("id") in (None, "") and item.get("name") in (None, ""):
            continue
        items.append(_inventory_item(item))
    return items


def _inventory_item(item: dict[str, object]) -> dict[str, object]:
    required = _int_value(item.get("num"))
    missing = _int_value(item.get("lack_num"))
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "level": item.get("level"),
        "required": required,
        "missing": missing,
        "owned": max(required - missing, 0),
        "icon": item.get("icon") or item.get("icon_url"),
        "wiki_url": item.get("wiki_url"),
    }


def _inventory_compute_item(character: dict[str, object]) -> dict[str, object] | None:
    avatar_id = _int_value(character.get("id"))
    name = character.get("name")
    if avatar_id <= 0 or not isinstance(name, str) or not name:
        return None
    item: dict[str, object] = {
        "avatar_id": avatar_id,
        "avatar_level_current": 1,
        "avatar_level_target": 90,
        "element_attr_id": ELEMENT_ID_BY_NAME.get(str(character.get("element")), 0),
        "level": _int_value(character.get("rarity"), 5),
        "name": name,
    }
    weapon = _inventory_compute_weapon(character.get("weapon"))
    if weapon is not None:
        item["weapon"] = weapon
    return item


def _inventory_compute_weapon(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    weapon_id = _int_value(value.get("id"))
    name = value.get("name")
    rarity = _int_value(value.get("rarity"))
    if weapon_id <= 0 or not isinstance(name, str) or not name or rarity <= 0:
        return None
    target = 70 if rarity <= 2 else 90
    return {
        "id": weapon_id,
        "name": name,
        "weapon_cat_id": _int_value(value.get("type"), 1),
        "weapon_level": rarity,
        "max_level": target,
        "is_recommend": False,
        "levelRange": [1, target],
        "level_current": 1,
        "level_target": target,
    }


def _inventory_compute_item_summary(item: dict[str, object]) -> dict[str, object]:
    return {
        "avatar_id": item.get("avatar_id"),
        "name": item.get("name"),
    }


def _retcode_ok(payload: dict[str, object]) -> bool:
    return payload.get("retcode") in (0, "0", None)


def _is_calculator_row_rejection(error: CliError) -> bool:
    return error.code == "UPSTREAM_REJECTED" and str(error.details.get("retcode")) == "-500001"


def _is_calculator_payload_rejection(payload: dict[str, object]) -> bool:
    return str(payload.get("retcode")) == "-500001"


def _calendar(data: dict[str, object]) -> dict[str, object]:
    keys = (
        "avatar_card_pool_list",
        "weapon_card_pool_list",
        "mixed_card_pool_list",
        "selected_avatar_card_pool_list",
        "selected_mixed_card_pool_list",
        "act_list",
        "fixed_act_list",
        "selected_act_list",
    )
    lists = {key: _dict_list(data.get(key)) for key in keys}
    return {
        **lists,
        "counts": {key: len(value) for key, value in lists.items()},
    }


def _register_time(
    uid: str,
    data: dict[str, object],
    source: dict[str, object],
) -> dict[str, object]:
    raw_data = data.get("data")
    if isinstance(raw_data, str):
        try:
            parsed = json.loads(raw_data)
        except ValueError as exc:
            raise _invalid_provider_data("player.register-time", source) from exc
    elif isinstance(raw_data, dict):
        parsed = raw_data
    else:
        raise _invalid_provider_data("player.register-time", source)
    timestamp = _int_value(parsed.get("1"))
    if timestamp <= 0:
        raise _invalid_provider_data("player.register-time", source)
    registered_at = datetime.fromtimestamp(timestamp, CN_TIMEZONE)
    return {
        "uid": uid,
        "timestamp": timestamp,
        "registered_at": registered_at.isoformat(),
        "timezone": "Asia/Shanghai",
        "confidence": "provider",
        "source": "mys_anniversary_game_data",
    }


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _int_value(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _invalid_provider_data(category: str, source: dict[str, object]) -> CliError:
    return CliError(
        "UPSTREAM_INVALID_RESPONSE",
        "Provider returned an unexpected response shape.",
        EXIT_UPSTREAM,
        {"provider": PROVIDER, "category": category},
        source=source,
    )


def _diary(data: dict[str, object]) -> dict[str, object]:
    day_data = data.get("day_data")
    month_data = data.get("month_data")
    optional_month = data.get("optional_month")
    lantern = data.get("lantern")
    if not isinstance(day_data, dict):
        day_data = {}
    if not isinstance(month_data, dict):
        month_data = {}
    if not isinstance(optional_month, list):
        optional_month = []
    if not isinstance(lantern, dict):
        lantern = {}

    return {
        "uid": data.get("uid"),
        "region": data.get("region"),
        "account_id": data.get("account_id"),
        "nickname": data.get("nickname"),
        "date": data.get("date"),
        "month": data.get("month"),
        "data_month": data.get("data_month"),
        "data_last_month": data.get("data_last_month"),
        "day_data": day_data,
        "month_data": month_data,
        "optional_month": [item for item in optional_month if isinstance(item, dict)],
        "lantern": lantern,
    }


def _abyss(data: dict[str, object], floor: int | None) -> dict[str, object]:
    floors_value = data.get("floors")
    if not isinstance(floors_value, list):
        floors_value = []
    floors = [item for item in floors_value if isinstance(item, dict)]
    if floor is not None:
        floors = [item for item in floors if _floor_index(item) == floor]

    return {
        "schedule_id": data.get("schedule_id"),
        "start_time": data.get("start_time"),
        "end_time": data.get("end_time"),
        "total_battle_times": data.get("total_battle_times"),
        "total_win_times": data.get("total_win_times"),
        "max_floor": data.get("max_floor"),
        "total_star": data.get("total_star"),
        "is_unlock": data.get("is_unlock"),
        "rankings": _abyss_rankings(data),
        "floors": floors,
        "floor_count": len(floors),
    }


def _floor_index(floor: dict[str, object]) -> int | None:
    value = floor.get("index")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _abyss_rankings(data: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    rankings = {}
    for key in (
        "reveal_rank",
        "defeat_rank",
        "damage_rank",
        "take_damage_rank",
        "normal_skill_rank",
        "energy_skill_rank",
    ):
        value = data.get(key)
        rankings[key] = (
            [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
        )
    return rankings


def _theater(data: dict[str, object], _season: str) -> dict[str, object]:
    sessions_value = data.get("data")
    if not isinstance(sessions_value, list):
        sessions_value = []
    sessions = [item for item in sessions_value if isinstance(item, dict)]
    selected = sessions[0] if sessions else None
    links = data.get("links")
    if not isinstance(links, dict):
        links = {}
    return {
        "selected": selected,
        "sessions": sessions,
        "count": len(sessions),
        "links": links,
    }


def _hard_challenge(data: dict[str, object]) -> dict[str, object]:
    sessions = data.get("data")
    if isinstance(sessions, list):
        session_items = [item for item in sessions if isinstance(item, dict)]
        return {
            "selected": session_items[0] if session_items else None,
            "data": session_items,
            "count": len(session_items),
        }

    hard = data.get("hard_challenge")
    role_combat = data.get("role_combat")
    return {
        "hard_challenge": hard if isinstance(hard, dict) else {},
        "role_combat": role_combat if isinstance(role_combat, dict) else {},
    }


def _completion(data: dict[str, object]) -> dict[str, object]:
    stats = data.get("stats")
    explorations = data.get("world_explorations")
    if not isinstance(stats, dict):
        stats = {}
    if not isinstance(explorations, list):
        explorations = []
    return {
        "role": {
            "nickname": data.get("nickname"),
            "level": data.get("level"),
            "region": data.get("region"),
            "region_name": data.get("region_name"),
        },
        "stats": stats,
        "exploration_count": len([item for item in explorations if isinstance(item, dict)]),
        "world_explorations": [item for item in explorations if isinstance(item, dict)],
        "challenge": _hard_challenge(data),
    }


def _exploration(data: dict[str, object]) -> dict[str, object]:
    explorations = data.get("world_explorations")
    homes = data.get("homes")
    if not isinstance(explorations, list):
        explorations = []
    if not isinstance(homes, list):
        homes = []
    return {
        "world_explorations": [item for item in explorations if isinstance(item, dict)],
        "homes": [item for item in homes if isinstance(item, dict)],
    }


def _collection(data: dict[str, object]) -> dict[str, object]:
    stats = data.get("stats")
    if not isinstance(stats, dict):
        stats = {}
    return {
        "avatars": stats.get("avatar_number"),
        "achievements": stats.get("achievement_number"),
        "spiral_abyss": stats.get("spiral_abyss"),
        "oculi": {key: value for key, value in stats.items() if "oculus" in key},
        "chests": {key: value for key, value in stats.items() if key.endswith("_chest_number")},
        "waypoints": stats.get("way_point_number"),
        "domains": stats.get("domain_number"),
        "raw_stats": stats,
    }


def _gcg(basic: dict[str, object], decks: dict[str, object]) -> dict[str, object]:
    deck_list = _gcg_decks(decks)
    return {
        "basic": basic,
        "deck_data": decks,
        "decks": deck_list,
        "deck_count": len(deck_list),
    }


def _gcg_decks(decks: dict[str, object]) -> list[dict[str, object]]:
    deck_list = (
        decks.get("deck_list") or decks.get("card_list") or decks.get("list") or decks.get("decks")
    )
    if not isinstance(deck_list, list):
        return []
    return [item for item in deck_list if isinstance(item, dict)]


def _schedule_type(season: str) -> str:
    return "2" if season == "previous" else "1"
