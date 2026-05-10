from __future__ import annotations

import argparse
import re

from gsuid_cli.core.errors import CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.providers.public import PublicDataProvider


def _panel_with_weapon_effect(
    args: argparse.Namespace,
    panel: dict[str, object],
    avatar: dict[str, object],
) -> dict[str, object]:
    weapon = panel.get("weapon")
    if not isinstance(weapon, dict) or weapon.get("effect"):
        return panel
    weapon_id = str(weapon.get("item_id") or "")
    if len(weapon_id) != 5 or not weapon_id.isdigit():
        return panel
    try:
        response = PublicDataProvider(
            HttpClient(
                timeout=args.timeout,
                cache_policy=args.cache,
                output_dir=args.output_dir,
                debug=args.debug,
            )
        ).weapon_detail(
            weapon_id=weapon_id,
            category="panel.weapon_effect",
        )
    except CliError:
        return panel
    data = response.payload.get("data")
    if not isinstance(data, dict):
        return panel
    effect = _weapon_effect_text(data.get("affix"), _weapon_affix(avatar))
    if not effect:
        return panel
    next_weapon = {**weapon, "effect": effect}
    return {**panel, "weapon": next_weapon}


def _with_avatar_names(
    args: argparse.Namespace,
    payload: dict[str, object],
) -> tuple[dict[str, object], list[str]]:
    raw_avatars = payload.get("avatarInfoList")
    if not isinstance(raw_avatars, list):
        return payload, []
    avatar_dicts = [avatar for avatar in raw_avatars if isinstance(avatar, dict)]
    if all(avatar.get("name") or avatar.get("route") for avatar in avatar_dicts):
        return payload, []
    try:
        names = _avatar_name_index(args)
    except CliError:
        return payload, ["character name enrichment failed; use avatar ids for panel lookup"]
    enriched = []
    changed = False
    for avatar in avatar_dicts:
        item = dict(avatar)
        info = names.get(str(item.get("avatarId") or item.get("id") or ""))
        if info:
            if not item.get("name") and info.get("name"):
                item["name"] = info["name"]
                changed = True
            if not item.get("route") and info.get("route"):
                item["route"] = info["route"]
                changed = True
        enriched.append(item)
    if not changed:
        return payload, []
    new_payload = dict(payload)
    new_payload["avatarInfoList"] = enriched
    return new_payload, []


def _weapon_affix(avatar: dict[str, object]) -> int:
    equips = avatar.get("equipList")
    if not isinstance(equips, list):
        return 1
    for equip in equips:
        if not isinstance(equip, dict):
            continue
        weapon = equip.get("weapon")
        if not isinstance(weapon, dict):
            continue
        affix_map = weapon.get("affixMap")
        if isinstance(affix_map, dict) and affix_map:
            return min(max(int(_number(next(iter(affix_map.values())))) + 1, 1), 5)
    return 1


def _weapon_effect_text(affix: object, rank: int) -> str | None:
    if not isinstance(affix, dict):
        return None
    first = next((item for item in affix.values() if isinstance(item, dict)), None)
    if not isinstance(first, dict):
        return None
    upgrade = first.get("upgrade")
    if not isinstance(upgrade, dict):
        return None
    text = upgrade.get(str(max(min(rank, 5), 1) - 1))
    if not isinstance(text, str):
        return None
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<.*?>", "", text)
    return text.replace("@", "").replace("#", "").strip()


def _avatar_name_index(args: argparse.Namespace) -> dict[str, dict[str, object]]:
    response = PublicDataProvider(
        HttpClient(
            timeout=args.timeout,
            cache_policy=args.cache,
            output_dir=args.output_dir,
            debug=args.debug,
        )
    ).avatar_index(
        category="panel.character_names",
    )
    data = response.payload.get("data")
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, dict):
        return {}
    index: dict[str, dict[str, object]] = {}
    for item in items.values():
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        if item_id:
            index[item_id] = item
    return index


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
