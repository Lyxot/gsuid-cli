from __future__ import annotations

import json
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

from gsuid_cli.core.errors import EXIT_NO_RESULT, CliError
from gsuid_cli.core.time import utc_now

JsonDict = dict[str, object]
PanelCache = dict[str, object]
PANEL_DATA = Path(__file__).resolve().parents[2] / "assets" / "panel" / "data"

LEVEL_PROP_KEYS = ("4001", "level")
FIGHT_PROP_LABELS = {
    "1": "base_hp",
    "2": "hp",
    "3": "hp_percent",
    "4": "base_atk",
    "5": "atk",
    "6": "atk_percent",
    "7": "base_def",
    "8": "def",
    "9": "def_percent",
    "20": "crit_rate",
    "22": "crit_damage",
    "23": "energy_recharge",
    "26": "healing_bonus",
    "28": "elemental_mastery",
    "30": "physical_bonus",
    "40": "pyro_bonus",
    "41": "electro_bonus",
    "42": "hydro_bonus",
    "43": "dendro_bonus",
    "44": "anemo_bonus",
    "45": "geo_bonus",
    "46": "cryo_bonus",
    "2000": "max_hp",
    "2001": "max_atk",
    "2002": "max_def",
}
CRIT_RATE_PROPS = {"FIGHT_PROP_CRITICAL", "crit_rate", "20"}
CRIT_DAMAGE_PROPS = {"FIGHT_PROP_CRITICAL_HURT", "crit_damage", "22"}
PERCENT_FIGHT_PROP_LABELS = {
    "hp_percent",
    "atk_percent",
    "def_percent",
    "crit_rate",
    "crit_damage",
    "energy_recharge",
    "healing_bonus",
    "physical_bonus",
    "pyro_bonus",
    "cryo_bonus",
    "hydro_bonus",
    "anemo_bonus",
    "geo_bonus",
    "electro_bonus",
    "dendro_bonus",
    "critical",
    "critical_hurt",
    "charge_efficiency",
    "heal_add",
    "physical_add_hurt",
    "fire_add_hurt",
    "ice_add_hurt",
    "water_add_hurt",
    "wind_add_hurt",
    "rock_add_hurt",
    "electric_add_hurt",
    "grass_add_hurt",
}


def save_panel_cache(
    conn: sqlite3.Connection,
    *,
    uid: str,
    payload: JsonDict,
    source: JsonDict | None,
) -> dict[str, object]:
    player_info = _dict_value(payload.get("playerInfo"))
    avatars = _list_of_dicts(payload.get("avatarInfoList"))
    fetched_at = str((source or {}).get("fetched_at") or utc_now())
    source_provider = str((source or {}).get("provider") or "enka")
    ttl = _optional_int(payload.get("ttl"))
    conn.execute(
        """
        INSERT INTO panel_cache(
            uid, source_provider, fetched_at, ttl,
            player_info_json, avatar_info_json, raw_json
        )
        VALUES(?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(uid) DO UPDATE SET
            source_provider = excluded.source_provider,
            fetched_at = excluded.fetched_at,
            ttl = excluded.ttl,
            player_info_json = excluded.player_info_json,
            avatar_info_json = excluded.avatar_info_json,
            raw_json = excluded.raw_json
        """,
        (
            uid,
            source_provider,
            fetched_at,
            ttl,
            _dump_json(player_info),
            _dump_json(avatars),
            _dump_json(payload),
        ),
    )
    return {
        "uid": uid,
        "source_provider": source_provider,
        "fetched_at": fetched_at,
        "ttl": ttl,
        "player_info": player_info,
        "avatars": avatars,
    }


def load_panel_cache(conn: sqlite3.Connection, uid: str) -> PanelCache:
    row = conn.execute("SELECT * FROM panel_cache WHERE uid = ?", (uid,)).fetchone()
    if row is None:
        raise CliError(
            "NO_RESULT",
            "No cached panel data is available for this UID. Run panel refresh first.",
            EXIT_NO_RESULT,
            {"uid": uid},
        )
    return {
        "uid": str(row["uid"]),
        "source_provider": str(row["source_provider"]),
        "fetched_at": str(row["fetched_at"]),
        "ttl": row["ttl"],
        "player_info": _json_dict(row["player_info_json"]),
        "avatars": _json_list(row["avatar_info_json"]),
        "raw": _json_dict(row["raw_json"]),
    }


def cache_source(cache: PanelCache) -> JsonDict:
    return {
        "provider": str(cache["source_provider"]),
        "region": "cn",
        "cached": True,
        "fetched_at": str(cache["fetched_at"]),
    }


def player_summary(cache: PanelCache) -> JsonDict:
    player = _dict_value(cache.get("player_info"))
    return {
        "uid": str(cache["uid"]),
        "nickname": player.get("nickname"),
        "level": _optional_int(player.get("level")),
        "signature": player.get("signature"),
        "world_level": _optional_int(player.get("worldLevel")),
        "achievements": _optional_int(player.get("finishAchievementNum")),
        "abyss_floor": _optional_int(player.get("towerFloorIndex")),
        "abyss_chamber": _optional_int(player.get("towerLevelIndex")),
    }


def avatar_summaries(cache: PanelCache) -> list[JsonDict]:
    return [rank_entry(avatar) for avatar in avatars(cache)]


def avatars(cache: PanelCache) -> list[JsonDict]:
    return _list_of_dicts(cache.get("avatars"))


def find_avatar(cache: PanelCache, query: str) -> JsonDict:
    normalized_query = _normalize(query)
    avatar_list = avatars(cache)
    for avatar in avatar_list:
        if normalized_query in {_normalize(alias) for alias in avatar_aliases(avatar)}:
            return avatar
    for avatar in avatar_list:
        aliases = [_normalize(alias) for alias in avatar_aliases(avatar)]
        if normalized_query and any(normalized_query in alias for alias in aliases):
            return avatar
    raise CliError(
        "NO_RESULT",
        "No cached character panel matched the query.",
        EXIT_NO_RESULT,
        {"uid": cache["uid"], "query": query},
        source=cache_source(cache),
    )


def normalized_avatar(avatar: JsonDict) -> JsonDict:
    artifacts = artifact_list(avatar)
    return {
        "avatar_id": avatar_id(avatar),
        "name": avatar_name(avatar),
        "level": avatar_level(avatar),
        "constellation": constellation_count(avatar),
        "friendship": friendship_level(avatar),
        "weapon": weapon_summary(avatar),
        "artifacts": artifacts,
        "artifact_score": round(sum(_float_value(item.get("score")) for item in artifacts), 2),
        "fight_props": fight_props(avatar),
        "skill_levels": _dict_value(avatar.get("skillLevelMap")),
    }


def rank_entry(avatar: JsonDict) -> JsonDict:
    normalized = normalized_avatar(avatar)
    weapon = _dict_value(normalized.get("weapon"))
    return {
        "avatar_id": normalized["avatar_id"],
        "name": normalized["name"],
        "level": normalized["level"],
        "constellation": normalized["constellation"],
        "friendship": normalized["friendship"],
        "weapon": weapon.get("name"),
        "artifact_score": normalized["artifact_score"],
    }


def artifact_entries(cache: PanelCache, avatar: JsonDict | None = None) -> list[JsonDict]:
    selected = [avatar] if avatar is not None else avatars(cache)
    entries: list[JsonDict] = []
    for item in selected:
        if item is None:
            continue
        character = rank_entry(item)
        for artifact in artifact_list(item):
            entries.append(
                {
                    "character": character["name"],
                    "avatar_id": character["avatar_id"],
                    **artifact,
                }
            )
    return entries


def avatar_id(avatar: JsonDict) -> str:
    return str(avatar.get("avatarId") or avatar.get("id") or "")


def avatar_name(avatar: JsonDict) -> str:
    mapped = _mapped_text("avatarId2Name_mapping_6.5.0.json", avatar_id(avatar))
    if mapped:
        return mapped
    value = (
        avatar.get("name")
        or avatar.get("route")
        or avatar.get("avatarName")
        or avatar.get("character_name")
    )
    if value:
        return str(value)
    return avatar_id(avatar)


def avatar_aliases(avatar: JsonDict) -> list[str]:
    values = [
        avatar_id(avatar),
        _mapped_text("avatarId2Name_mapping_6.5.0.json", avatar_id(avatar)),
        avatar.get("name"),
        avatar.get("route"),
        avatar.get("avatarName"),
        avatar.get("character_name"),
    ]
    return list(dict.fromkeys(str(value) for value in values if value))


def avatar_level(avatar: JsonDict) -> int | None:
    level = _optional_int(avatar.get("level"))
    if level is not None:
        return level
    prop_map = _dict_value(avatar.get("propMap"))
    for key in LEVEL_PROP_KEYS:
        value = prop_map.get(key)
        if isinstance(value, dict):
            level = _optional_int(value.get("val") or value.get("ival"))
        else:
            level = _optional_int(value)
        if level is not None:
            return level
    return None


def constellation_count(avatar: JsonDict) -> int:
    value = avatar.get("constellation")
    if value is not None:
        return _optional_int(value) or 0
    talents = avatar.get("talentIdList")
    return len(talents) if isinstance(talents, list) else 0


def friendship_level(avatar: JsonDict) -> int | None:
    fetter = _dict_value(avatar.get("fetterInfo"))
    return _optional_int(fetter.get("expLevel"))


def weapon_summary(avatar: JsonDict) -> JsonDict | None:
    for equip in _list_of_dicts(avatar.get("equipList")):
        flat = _dict_value(equip.get("flat"))
        if flat.get("itemType") == "ITEM_WEAPON" or isinstance(equip.get("weapon"), dict):
            weapon = _dict_value(equip.get("weapon"))
            name = _weapon_name(equip, flat)
            return {
                "item_id": str(equip.get("itemId") or equip.get("id") or ""),
                "name": str(name),
                "level": _optional_int(weapon.get("level") or equip.get("level")),
                "rank": _optional_int(flat.get("rankLevel") or equip.get("rank")),
                "type": _weapon_type(equip, flat),
                "affix": _weapon_affix(weapon),
                "stats": _list_of_dicts(flat.get("weaponStats") or equip.get("stats")),
            }
    return None


def artifact_list(avatar: JsonDict) -> list[JsonDict]:
    artifacts: list[JsonDict] = []
    for equip in _list_of_dicts(avatar.get("equipList")):
        flat = _dict_value(equip.get("flat"))
        if flat.get("itemType") != "ITEM_RELIQUARY" and not isinstance(
            equip.get("reliquary"), dict
        ):
            continue
        substats = _list_of_dicts(flat.get("reliquarySubstats") or equip.get("substats"))
        main_stat = _dict_value(flat.get("reliquaryMainstat") or equip.get("main_stat"))
        mapped_name = _mapped_text("icon2Name_mapping_6.5.0.json", flat.get("icon"))
        name = mapped_name or flat.get("name") or ""
        artifact = {
            "item_id": str(equip.get("itemId") or equip.get("id") or ""),
            "name": str(name or equip.get("name") or ""),
            "slot": flat.get("equipType") or equip.get("slot"),
            "set_name": _mapped_text("artifact2attr_mapping_6.5.0.json", name)
            or flat.get("setName")
            or equip.get("set_name"),
            "rank": _optional_int(flat.get("rankLevel") or equip.get("rank")),
            "level": _artifact_level(equip),
            "main_stat": main_stat,
            "substats": substats,
            "score": round(artifact_score(substats), 2),
        }
        artifacts.append(artifact)
    return artifacts


def artifact_score(substats: list[JsonDict]) -> float:
    score = 0.0
    for stat in substats:
        prop = str(stat.get("appendPropId") or stat.get("prop") or "")
        value = _float_value(stat.get("statValue") or stat.get("value"))
        if prop in CRIT_RATE_PROPS:
            score += value * 2
        elif prop in CRIT_DAMAGE_PROPS:
            score += value
    return score


def fight_props(avatar: JsonDict) -> JsonDict:
    raw = _dict_value(avatar.get("fightPropMap"))
    props: JsonDict = {}
    for key, value in raw.items():
        label = FIGHT_PROP_LABELS.get(str(key), _normalize_fight_prop(str(key)))
        props[label] = _fight_prop_value(label, value)
    return props


def sort_rank_entries(entries: list[JsonDict], sort_key: str) -> list[JsonDict]:
    key = "level" if sort_key == "level" else "artifact_score"
    return sorted(entries, key=lambda item: _float_value(item.get(key)), reverse=True)


def _json_dict(value: str) -> JsonDict:
    data = json.loads(value)
    return data if isinstance(data, dict) else {}


def _json_list(value: str) -> list[JsonDict]:
    data = json.loads(value)
    return _list_of_dicts(data)


def _dump_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _dict_value(value: object) -> JsonDict:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[JsonDict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _optional_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _float_value(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _normalize(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def _normalize_fight_prop(value: str) -> str:
    if value.startswith("FIGHT_PROP_"):
        return value.removeprefix("FIGHT_PROP_").lower()
    return value


def _fight_prop_value(label: str, value: object) -> object:
    if label not in PERCENT_FIGHT_PROP_LABELS or isinstance(value, bool):
        return value
    try:
        return round(float(value) * 100, 4)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return value


def _weapon_name(equip: JsonDict, flat: JsonDict) -> str:
    return str(
        _mapped_text("weaponId2Name_mapping_6.5.0.json", equip.get("itemId") or equip.get("id"))
        or _mapped_text("weaponHash2Name_mapping_6.5.0.json", flat.get("nameTextMapHash"))
        or _weapon_name_by_route(flat.get("name") or equip.get("name") or equip.get("itemName"))
        or flat.get("name")
        or equip.get("name")
        or equip.get("itemName")
        or ""
    )


def _weapon_type(equip: JsonDict, flat: JsonDict) -> str | None:
    weapon_id = str(equip.get("itemId") or equip.get("id") or "")
    weapon_data = _weapon_list().get(weapon_id)
    if isinstance(weapon_data, dict):
        value = weapon_data.get("type")
        if value:
            return str(value)
    return _mapped_text("weaponHash2Type_mapping_6.5.0.json", flat.get("nameTextMapHash"))


def _weapon_affix(weapon: JsonDict) -> int:
    affix_map = weapon.get("affixMap")
    if isinstance(affix_map, dict) and affix_map:
        return min(max((_optional_int(next(iter(affix_map.values()))) or 0) + 1, 1), 5)
    return 1


def _artifact_level(equip: JsonDict) -> int | None:
    reliquary_level = _optional_int(_dict_value(equip.get("reliquary")).get("level"))
    if reliquary_level is not None:
        return max(reliquary_level - 1, 0)
    level = _optional_int(equip.get("level"))
    if level is None:
        return None
    return max(level - 1, 0) if level > 20 else level


def _weapon_name_by_route(value: object) -> str | None:
    if value in (None, ""):
        return None
    route = str(value)
    for item in _weapon_list().values():
        if isinstance(item, dict) and item.get("route") == route:
            name = item.get("name")
            return str(name) if name not in (None, "") else None
    return None


def _mapped_text(filename: str, key: object) -> str | None:
    if key in (None, ""):
        return None
    value = _text_map(filename).get(str(key))
    return str(value) if value not in (None, "") else None


@lru_cache(maxsize=1)
def _weapon_list() -> dict[str, object]:
    return _text_map("weaponList_6.5.0.json")


@lru_cache(maxsize=16)
def _text_map(filename: str) -> dict[str, object]:
    path = PANEL_DATA / filename
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
