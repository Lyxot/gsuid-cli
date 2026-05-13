"""Mihoyo (mys) panel data adapter.

Translates official mihoyo character/profile responses into the Enka
panel payload shape consumed by the panel renderer. Used when refreshing
panel data from the mys provider instead of Enka.
"""

from __future__ import annotations

import argparse
import json

from gsuid_cli.commands.auth import _credential
from gsuid_cli.commands.panel.cache import PANEL_DATA
from gsuid_cli.commands.panel.common import (
    _dict,
    _list_of_dicts,
    _number,
    _refresh_cache_policy,
)
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.providers import provider_for_region
from gsuid_cli.text import t as _t

MYS_PROP_IDS = {
    "1": "1",
    "2": "2",
    "3": "3",
    "4": "4",
    "5": "5",
    "6": "6",
    "7": "7",
    "8": "8",
    "9": "9",
    "20": "20",
    "22": "22",
    "23": "23",
    "26": "26",
    "28": "28",
    "30": "30",
    "40": "40",
    "41": "41",
    "42": "42",
    "43": "43",
    "44": "44",
    "45": "45",
    "46": "46",
    "50": "50",
    "51": "51",
    "52": "52",
    "53": "53",
    "54": "54",
    "55": "55",
    "56": "56",
    "2000": "2000",
    "2001": "2001",
    "2002": "2002",
}
MYS_PERCENT_PROP_IDS = {
    "3",
    "6",
    "9",
    "20",
    "22",
    "23",
    "26",
    "30",
    "40",
    "41",
    "42",
    "43",
    "44",
    "45",
    "46",
    "50",
    "51",
    "52",
    "53",
    "54",
    "55",
    "56",
}


def _mys_panel_profile(args: argparse.Namespace, *, uid: str, region: str) -> CommandResult:
    credential_args = argparse.Namespace(**vars(args))
    credential_args.credential_kind = "cookie"
    cookie, credential_source, storage_backend = _credential(credential_args, uid)
    provider = provider_for_region(
        region,
        HttpClient(
            timeout=args.timeout,
            cache_policy=_refresh_cache_policy(args),
            output_dir=args.output_dir,
            debug=args.debug,
        ),
    )
    summary_result = provider.player_summary(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    character_ids = _summary_character_ids(summary_result.data)
    if not character_ids:
        characters_result = provider.player_characters(
            uid=uid,
            cookie=cookie,
            region=region,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )
        character_ids = _character_ids(characters_result.data.get("characters"))
    details_result = provider.character_details(
        uid=uid,
        cookie=cookie,
        region=region,
        character_ids=character_ids,
        category="panel.refresh.mys",
    )
    return CommandResult(
        data=_mys_panel_payload(uid, summary_result.data, details_result.data),
        source=details_result.source,
        warnings=[*summary_result.warnings, *details_result.warnings],
    )


def _summary_character_ids(data: dict[str, object]) -> list[int]:
    summary = _dict(data.get("summary"))
    return _character_ids(summary.get("avatars"))


def _character_ids(value: object) -> list[int]:
    ids: list[int] = []
    if not isinstance(value, list):
        return ids
    for item in value:
        if not isinstance(item, dict):
            continue
        character_id = _int(item.get("id") or item.get("avatar_id") or item.get("avatarId"))
        if character_id is not None:
            ids.append(character_id)
    return ids


def _mys_panel_payload(
    uid: str,
    summary_data: dict[str, object],
    details_data: dict[str, object],
) -> dict[str, object]:
    summary = _dict(summary_data.get("summary"))
    details = details_data.get("details")
    return {
        "uid": uid,
        "ttl": 300,
        "playerInfo": _mys_player_info(uid, summary),
        "avatarInfoList": [_mys_avatar(detail) for detail in details if isinstance(detail, dict)]
        if isinstance(details, list)
        else [],
    }


def _mys_player_info(uid: str, summary: dict[str, object]) -> dict[str, object]:
    role = _dict(summary.get("role"))
    stats = _dict(summary.get("stats"))
    return {
        "uid": uid,
        "nickname": role.get("nickname"),
        "level": role.get("level"),
        "region": role.get("region"),
        "worldLevel": stats.get("world_level") or stats.get("worldLevel"),
        "finishAchievementNum": stats.get("achievement_number") or stats.get("achievements"),
    }


def _mys_avatar(detail: dict[str, object]) -> dict[str, object]:
    base = _dict(detail.get("base")) or detail
    avatar_id = base.get("id") or detail.get("id") or detail.get("avatarId")
    return {
        "avatarId": avatar_id,
        "name": base.get("name") or detail.get("name"),
        "level": base.get("level") or detail.get("level"),
        "talentIdList": _active_talent_ids(detail.get("constellations")),
        "fetterInfo": {"expLevel": base.get("fetter") or detail.get("fetter")},
        "skillLevelMap": _skill_level_map(detail.get("skills")),
        "fightPropMap": _mys_fight_props(detail),
        "equipList": [_mys_weapon(detail.get("weapon")), *_mys_artifacts(detail.get("relics"))],
    }


def _active_talent_ids(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    return [
        talent_id
        for item in value
        if isinstance(item, dict) and item.get("is_actived") and (talent_id := _int(item.get("id")))
    ]


def _skill_level_map(value: object) -> dict[str, int]:
    levels: dict[str, int] = {}
    if not isinstance(value, list):
        return levels
    for item in value:
        if not isinstance(item, dict):
            continue
        skill_id = item.get("skill_id") or item.get("id")
        level = _int(item.get("level"))
        if skill_id not in (None, "") and level is not None:
            levels[str(skill_id)] = level
    return levels


def _mys_fight_props(detail: dict[str, object]) -> dict[str, object]:
    props: dict[str, object] = {}
    for group in ("base_properties", "extra_properties", "element_properties"):
        value = detail.get(group)
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            prop_id = MYS_PROP_IDS.get(str(item.get("property_type") or ""))
            if not prop_id:
                continue
            props[prop_id] = _mys_prop_value(item.get("final"), prop_id, fight_prop=True)
    return props


def _mys_weapon(value: object) -> dict[str, object]:
    weapon = _dict(value)
    main = _dict(weapon.get("main_property"))
    sub = _dict(weapon.get("sub_property"))
    stats = [_mys_stat(main, value_key="final")]
    if sub:
        stats.append(_mys_stat(sub, value_key="final"))
    return {
        "itemId": weapon.get("id"),
        "weapon": {"level": weapon.get("level"), "affixMap": {"1": _weapon_affix(weapon)}},
        "flat": {
            "itemType": "ITEM_WEAPON",
            "name": weapon.get("name"),
            "rankLevel": weapon.get("rarity"),
            "weaponStats": [stat for stat in stats if stat],
        },
    }


def _mys_artifacts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [_mys_artifact(item) for item in value if isinstance(item, dict)]


def _mys_artifact(relic: dict[str, object]) -> dict[str, object]:
    main = _dict(relic.get("main_property"))
    return {
        "itemId": relic.get("id"),
        "reliquary": {"level": (_int(relic.get("level")) or 0) + 1},
        "flat": {
            "itemType": "ITEM_RELIQUARY",
            "name": relic.get("name"),
            "icon": relic.get("icon") or _artifact_icon(relic.get("name")),
            "equipType": _artifact_slot(relic.get("pos_name")),
            "rankLevel": relic.get("rarity"),
            "setName": _dict(relic.get("set")).get("name"),
            "reliquaryMainstat": _mys_stat(main, value_key="value", main=True),
            "reliquarySubstats": [
                stat
                for stat in (
                    _mys_stat(item, value_key="value")
                    for item in _list_of_dicts(relic.get("sub_property_list"))
                )
                if stat
            ],
        },
    }


def _mys_stat(
    item: dict[str, object],
    *,
    value_key: str,
    main: bool = False,
) -> dict[str, object] | None:
    prop_id = MYS_PROP_IDS.get(str(item.get("property_type") or ""))
    if not prop_id:
        return None
    key = "mainPropId" if main else "appendPropId"
    return {
        key: prop_id,
        "statName": _prop_name(prop_id),
        "statValue": _mys_prop_value(item.get(value_key), prop_id, fight_prop=False),
    }


def _mys_prop_value(value: object, prop_id: str, *, fight_prop: bool) -> float:
    text = str(value or "").strip()
    is_percent = text.endswith("%")
    number = _number(text.removesuffix("%"))
    if fight_prop and (is_percent or prop_id in MYS_PERCENT_PROP_IDS):
        return round(number / 100, 6)
    return number


def _weapon_affix(weapon: dict[str, object]) -> int:
    affix = _int(weapon.get("affix_level"))
    if affix is None:
        return 0
    return max(affix - 1, 0)


def _artifact_slot(value: object) -> object:
    return {
        _t("gsuid.commands.panel.mys.317_8.5c8bb682"): "EQUIP_BRACER",
        _t("gsuid.commands.panel.mys.318_8.9eaf35fa"): "EQUIP_NECKLACE",
        _t("gsuid.commands.panel.mys.319_8.bc4a2cbb"): "EQUIP_SHOES",
        _t("gsuid.commands.panel.mys.320_8.c4347056"): "EQUIP_RING",
        _t("gsuid.commands.panel.mys.321_8.e5385dd2"): "EQUIP_DRESS",
    }.get(str(value), value)


def _artifact_icon(name: object) -> str | None:
    if name in (None, ""):
        return None
    names = _text_map("icon2Name_mapping_6.5.0.json")
    for icon, mapped_name in names.items():
        if mapped_name == name:
            return str(icon)
    return None


def _prop_name(prop_id: str) -> str | None:
    value = _text_map("propId2Name_mapping.json").get(prop_id)
    return str(value) if value not in (None, "") else None


def _text_map(filename: str) -> dict[str, object]:
    path = PANEL_DATA / filename
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
