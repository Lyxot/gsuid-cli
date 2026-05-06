from __future__ import annotations

import json
import re
from collections.abc import Mapping
from functools import lru_cache

from gsuid_cli.renderers.common import asset_path

PANEL_DATA = asset_path("panel", "data")
STAT_LABELS = {
    "Flat ATK": "攻击力",
    "Flat HP": "生命值",
    "Flat DEF": "防御力",
    "ATK%": "攻击力",
    "HP%": "生命值",
    "DEF%": "防御力",
    "Elemental Mastery": "元素精通",
    "Energy Recharge": "元素充能效率",
    "Crit RATE": "暴击率",
    "Crit DMG": "暴击伤害",
    "Cryo DMG Bonus": "冰元素伤害加成",
    "Pyro DMG Bonus": "火元素伤害加成",
    "Hydro DMG Bonus": "水元素伤害加成",
    "Electro DMG Bonus": "雷元素伤害加成",
    "Anemo DMG Bonus": "风元素伤害加成",
    "Geo DMG Bonus": "岩元素伤害加成",
    "Dendro DMG Bonus": "草元素伤害加成",
    "Healing Bonus": "治疗加成",
    "Physical DMG Bonus": "物理伤害加成",
}
EQUIP_LABELS = {
    "EQUIP_BRACER": "生之花",
    "EQUIP_NECKLACE": "死之羽",
    "EQUIP_SHOES": "时之沙",
    "EQUIP_RING": "空之杯",
    "EQUIP_DRESS": "理之冠",
}
PERCENT_STATS = {
    "ATK%",
    "HP%",
    "DEF%",
    "Energy Recharge",
    "Crit RATE",
    "Crit DMG",
    "Cryo DMG Bonus",
    "Pyro DMG Bonus",
    "Hydro DMG Bonus",
    "Electro DMG Bonus",
    "Anemo DMG Bonus",
    "Geo DMG Bonus",
    "Dendro DMG Bonus",
    "Healing Bonus",
    "Physical DMG Bonus",
}


def render_rank_list_text(data: Mapping[str, object]) -> str:
    uid = _text(data.get("uid"))
    player = _mapping(data.get("player"))
    characters = [_mapping(item) for item in _sequence(data.get("characters"))]
    nickname = _text(player.get("nickname"))
    title = f"Akasha排行 - {nickname}" if nickname != "-" else "Akasha排行"
    lines = [title, f"UID: {uid}", f"角色数量: {_text(data.get('count'))}"]
    if not characters:
        lines.extend(["", "暂无排行角色"])
        return _finish(lines)
    lines.extend(["", "角色:"])
    for character in characters:
        stats = _mapping(character.get("stats"))
        weapon = _mapping(character.get("weapon"))
        character_label = _character_label(character)
        lines.append(
            f"  - {character_label}: "
            f"{_number_text(character.get('result'))}，"
            f"排名 {_rank_text(character.get('rank'), character.get('out_of'))}"
        )
        lines.append(
            "    "
            f"命座 {_text(character.get('constellation'))}，"
            f"武器 {_weapon_name(weapon)} 精{_text(weapon.get('refinement'))}，"
            f"双暴 {_percent_number(stats.get('critRate'))}/"
            f"{_percent_number(stats.get('critDMG'))}，"
            f"CV {_number_text(stats.get('critValue'))}"
        )
        lines.append(
            f"    生命 {_number_text(stats.get('maxHP'))}，攻击 {_number_text(stats.get('maxATK'))}"
        )
        set_text = _artifact_sets_text(_mapping(character.get("artifact_sets")))
        if set_text != "-":
            lines.append(f"    套装: {set_text}")
    return _finish(lines)


def render_rank_character_text(data: Mapping[str, object]) -> str:
    entries = [_mapping(item) for item in _sequence(data.get("entries"))]
    selected_uid = _text(data.get("selected_uid"))
    lines = [
        f"角色排行 - {_text(data.get('character'))}",
        f"范围: {_text(data.get('tag'))} / 总数据 {_text(data.get('total_count'))}条",
    ]
    if selected_uid != "-":
        lines.append(f"目标UID: {selected_uid}")
    if not entries:
        lines.extend(["", "暂无排行数据"])
        return _finish(lines)
    lines.append("")
    rank = 0
    for index, entry in enumerate(entries[:20]):
        raw_rank = entry.get("index")
        rank = _rank_number(raw_rank) if index == 0 else rank + 1
        owner = _mapping(entry.get("owner"))
        stats = _mapping(entry.get("stats"))
        weapon = _mapping(entry.get("weapon"))
        weapon_info = _mapping(weapon.get("weaponInfo"))
        refinement = int(_number(_mapping(weapon_info.get("refinementLevel")).get("value"))) + 1
        mark = (
            " ← 当前UID" if selected_uid != "-" and _text(entry.get("uid")) == selected_uid else ""
        )
        lines.append(
            f"#{rank} {_text(owner.get('nickname'))} "
            f"({_text(owner.get('region'))}) UID: {_text(entry.get('uid'))}{mark}"
        )
        lines.append(
            "  "
            f"命座 {_text(entry.get('constellation'))}，"
            f"精{refinement}，"
            f"双暴 {_percent_number(_stat(stats, 'critRate'))}/"
            f"{_percent_number(_stat(stats, 'critDamage'))}，"
            f"CV {_number_text(entry.get('critValue'))}"
        )
        lines.append(
            "  "
            f"生命 {_number_text(_stat(stats, 'maxHp'))}，"
            f"攻击 {_number_text(_stat(stats, 'atk'))}"
        )
        set_text = _artifact_sets_text(_mapping(entry.get("artifactSets")))
        if set_text != "-":
            lines.append(f"  套装: {set_text}")
    return _finish(lines)


def render_rank_artifact_text(data: Mapping[str, object]) -> str:
    artifacts = [_mapping(item) for item in _sequence(data.get("artifacts"))]
    lines = [
        f"圣遗物排行 - {_text(data.get('sort'))}",
        f"排序字段: {_text(data.get('akasha_sort'))}",
        f"数量: {_text(data.get('count'))}",
    ]
    if not artifacts:
        lines.extend(["", "暂无圣遗物排行数据"])
        return _finish(lines)
    lines.append("")
    for index, artifact in enumerate(artifacts[:20], start=1):
        owner = _mapping(artifact.get("owner"))
        lines.append(
            f"#{index} {_text(owner.get('nickname'))} "
            f"({_text(owner.get('region'))}) UID: {_text(artifact.get('uid'))}"
        )
        lines.append(
            "  "
            f"{_slot_label(artifact.get('equipType'))}: "
            f"{_artifact_name(artifact)} "
            f"+{_artifact_level(artifact)} "
            f"{_stars(artifact.get('stars'))}，"
            f"双爆分 {_number_text(artifact.get('critValue'))}"
        )
        lines.append(
            "  "
            f"主词条: {_stat_label(artifact.get('mainStatKey'))} "
            f"{_stat_value_text(artifact.get('mainStatValue'), artifact.get('mainStatKey'))}"
        )
        substats = _mapping(artifact.get("substats"))
        if substats:
            lines.append("  副词条:")
            for name, value in substats.items():
                lines.append(f"    - {_stat_label(name)}: {_stat_value_text(value, name)}")
    return _finish(lines)


def _character_name(character: Mapping[str, object]) -> str:
    avatar_id = str(character.get("avatar_id") or character.get("character_id") or "")
    mapped = _text_map("avatarId2Name_mapping_6.5.0.json").get(avatar_id)
    return _text(mapped or character.get("name") or avatar_id)


def _weapon_name(weapon: Mapping[str, object]) -> str:
    name = _text(weapon.get("name"))
    if name == "-":
        return name
    for item in _text_map("weaponList_6.5.0.json").values():
        if isinstance(item, Mapping) and item.get("route") == name:
            return _text(item.get("name"))
    return name


def _variant_label(character: Mapping[str, object]) -> str:
    variant = _mapping(character.get("variant"))
    label = _text(variant.get("displayName") or character.get("short"))
    return "" if label == "-" else label


def _character_label(character: Mapping[str, object]) -> str:
    name = _character_name(character)
    variant = _variant_label(character)
    return f"{name} {variant}" if variant else name


def _rank_text(rank: object, out_of: object) -> str:
    rank_num = _rank_number(rank)
    out_num = _number(out_of)
    if out_num <= 0:
        return f"{_text(rank)}"
    percent = _number_text(rank_num / out_num * 100)
    rank_prefix = "~" if str(rank).startswith("~") else ""
    return f"{rank_prefix}{rank_num}/{_number_text(out_num)}（前{percent}%）"


def _artifact_sets_text(sets: Mapping[str, object]) -> str:
    parts: list[str] = []
    for name, value in sets.items():
        item = _mapping(value)
        count = int(_number(item.get("count")))
        if count <= 0:
            continue
        label = _artifact_set_label(name, item)
        parts.append(f"{label}{count}件")
    return "，".join(parts) if parts else "-"


def _artifact_set_label(name: object, item: Mapping[str, object]) -> str:
    icon = _icon_key(item.get("icon"))
    artifact_name = _text_map("icon2Name_mapping_6.5.0.json").get(icon)
    if artifact_name:
        set_name = _text_map("artifact2attr_mapping_6.5.0.json").get(str(artifact_name))
        if set_name:
            return _text(set_name)
    return _text(name)


def _artifact_name(artifact: Mapping[str, object]) -> str:
    icon_key = _icon_key(artifact.get("icon"))
    mapped = _text_map("icon2Name_mapping_6.5.0.json").get(icon_key)
    return _text(mapped or artifact.get("name"))


def _icon_key(value: object) -> str:
    text = _text(value)
    return text.rsplit("/", 1)[-1].split(".", 1)[0] if text != "-" else ""


def _artifact_level(artifact: Mapping[str, object]) -> str:
    level = int(_number(artifact.get("level")))
    return str(max(level - 1, 0))


def _slot_label(value: object) -> str:
    return EQUIP_LABELS.get(str(value), _text(value))


def _stat_label(value: object) -> str:
    return STAT_LABELS.get(str(value), _text(value))


def _stat_value_text(value: object, stat_name: object) -> str:
    suffix = "%" if str(stat_name) in PERCENT_STATS else ""
    return f"{_number_text(value)}{suffix}"


def _stat(stats: Mapping[str, object], key: str) -> object:
    value = stats.get(key)
    return _mapping(value).get("value") if isinstance(value, Mapping) else value


def _rank_number(value: object) -> int:
    text = str(value)
    if text.startswith("~"):
        text = text[1:]
    return int(_number(text))


def _percent_number(value: object) -> str:
    number = _number(value)
    if abs(number) <= 2:
        number *= 100
    return _number_text(number)


def _stars(value: object) -> str:
    count = int(_number(value))
    return "★" * count if count > 0 else ""


def _number_text(value: object) -> str:
    number = _number(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _text(value: object) -> str:
    if value is None or value == "":
        return "-"
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value))
    text = " ".join(text.split())
    return text or "-"


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _finish(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"


@lru_cache(maxsize=16)
def _text_map(filename: str) -> dict[str, object]:
    try:
        data = json.loads((PANEL_DATA / filename).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
