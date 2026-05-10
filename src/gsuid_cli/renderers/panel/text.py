from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache

from gsuid_cli.renderers._text_helpers import _finish, _mapping, _number_text, _text
from gsuid_cli.renderers.common import asset_path
from gsuid_cli.renderers.utility_text import _sequence

PERCENT_PROPS = {
    "FIGHT_PROP_ATTACK_PERCENT",
    "FIGHT_PROP_DEFENSE_PERCENT",
    "FIGHT_PROP_HP_PERCENT",
    "FIGHT_PROP_CRITICAL",
    "FIGHT_PROP_CRITICAL_HURT",
    "FIGHT_PROP_CHARGE_EFFICIENCY",
    "FIGHT_PROP_HEAL_ADD",
    "FIGHT_PROP_FIRE_ADD_HURT",
    "FIGHT_PROP_ELEC_ADD_HURT",
    "FIGHT_PROP_WATER_ADD_HURT",
    "FIGHT_PROP_GRASS_ADD_HURT",
    "FIGHT_PROP_WIND_ADD_HURT",
    "FIGHT_PROP_ROCK_ADD_HURT",
    "FIGHT_PROP_ICE_ADD_HURT",
    "FIGHT_PROP_PHYSICAL_ADD_HURT",
}
FIXED_VALUE_PROPS = {
    "FIGHT_PROP_ATTACK",
    "FIGHT_PROP_BASE_ATTACK",
    "FIGHT_PROP_DEFENSE",
    "FIGHT_PROP_BASE_DEFENSE",
    "FIGHT_PROP_HP",
    "FIGHT_PROP_BASE_HP",
    "FIGHT_PROP_ELEMENT_MASTERY",
}
PROP_LABEL_FALLBACKS = {
    "FIGHT_PROP_ATTACK": "攻击力",
    "FIGHT_PROP_ATTACK_PERCENT": "百分比攻击力",
    "FIGHT_PROP_BASE_ATTACK": "基础攻击力",
    "FIGHT_PROP_DEFENSE": "防御力",
    "FIGHT_PROP_DEFENSE_PERCENT": "百分比防御力",
    "FIGHT_PROP_BASE_DEFENSE": "基础防御力",
    "FIGHT_PROP_HP": "生命值",
    "FIGHT_PROP_HP_PERCENT": "百分比生命值",
    "FIGHT_PROP_BASE_HP": "基础生命值",
    "FIGHT_PROP_ELEMENT_MASTERY": "元素精通",
    "FIGHT_PROP_CRITICAL": "暴击率",
    "FIGHT_PROP_CRITICAL_HURT": "暴击伤害",
    "FIGHT_PROP_CHARGE_EFFICIENCY": "元素充能效率",
    "FIGHT_PROP_FIRE_ADD_HURT": "火元素伤害加成",
    "FIGHT_PROP_ELEC_ADD_HURT": "雷元素伤害加成",
    "FIGHT_PROP_WATER_ADD_HURT": "水元素伤害加成",
    "FIGHT_PROP_GRASS_ADD_HURT": "草元素伤害加成",
    "FIGHT_PROP_WIND_ADD_HURT": "风元素伤害加成",
    "FIGHT_PROP_ROCK_ADD_HURT": "岩元素伤害加成",
    "FIGHT_PROP_ICE_ADD_HURT": "冰元素伤害加成",
    "FIGHT_PROP_PHYSICAL_ADD_HURT": "物理伤害加成",
}
WEAPON_TYPE_LABELS = {
    "WEAPON_SWORD_ONE_HAND": "单手剑",
    "WEAPON_CLAYMORE": "双手剑",
    "WEAPON_POLE": "长柄武器",
    "WEAPON_CATALYST": "法器",
    "WEAPON_BOW": "弓",
}


def render_panel_refresh_text(data: Mapping[str, object]) -> str:
    player = _mapping(data.get("player"))
    lines = ["面板缓存刷新", f"UID: {_text(data.get('uid'))}"]
    _append_player(lines, player)
    lines.extend(
        [
            f"来源: {_source_label(data.get('source'))}",
            f"角色数量: {_text(data.get('character_count'))}",
            f"TTL: {_text(data.get('ttl'))}",
            f"缓存时间: {_text(data.get('cached_at'))}",
        ]
    )
    failures = _sequence(data.get("failures"))
    if failures:
        lines.append("失败:")
        for failure in failures:
            lines.append(f"  - {_text(failure)}")
    return _finish(lines)


def render_panel_list_text(data: Mapping[str, object]) -> str:
    lines = ["面板列表", f"UID: {_text(data.get('uid'))}"]
    _append_player(lines, _mapping(data.get("player")))
    _append_character_rows(lines, _sequence(data.get("characters")), count=data.get("count"))
    _append_cached_at(lines, data)
    return _finish(lines)


def render_panel_show_text(data: Mapping[str, object]) -> str:
    panel = _mapping(data.get("panel"))
    lines = [f"角色面板 - {_text(panel.get('name') or data.get('character'))}"]
    lines.append(f"UID: {_text(data.get('uid'))}")
    lines.append(
        "等级: "
        f"{_text(panel.get('level'))}，"
        f"命座: {_text(panel.get('constellation'))}，"
        f"好感: {_text(panel.get('friendship'))}"
    )
    weapon = _mapping(panel.get("weapon"))
    _append_weapon(lines, weapon)
    lines.append(f"圣遗物评分: {_number_text(panel.get('artifact_score'))}")
    _append_skill_levels(lines, _mapping(panel.get("skill_levels")))
    _append_fight_props(lines, _mapping(panel.get("fight_props")))
    _append_artifacts(lines, _sequence(panel.get("artifacts")), limit=5)
    _append_reference(lines, _mapping(data.get("reference")))
    overrides = _mapping(data.get("requested_overrides"))
    if overrides:
        lines.append("请求覆盖:")
        for key, value in overrides.items():
            lines.append(f"  - {_override_label(key)}: {_text(value)}")
    _append_cached_at(lines, data)
    return _finish(lines)


def render_panel_compare_text(data: Mapping[str, object]) -> str:
    lines = ["面板对比"]
    baseline = _mapping(data.get("baseline"))
    baseline_panel = _mapping(baseline.get("panel"))
    lines.append(f"基准: {_build_label(baseline)}")
    lines.append(f"基准评分: {_number_text(baseline_panel.get('artifact_score'))}")
    builds = _sequence(data.get("builds"))
    if builds:
        lines.append("")
        lines.append("构建:")
        for build in builds:
            panel = _mapping(_mapping(build).get("panel"))
            lines.append(
                f"  - {_build_label(_mapping(build))}: "
                f"评分 {_number_text(panel.get('artifact_score'))}"
            )
    deltas = _sequence(data.get("deltas"))
    if deltas:
        lines.append("")
        lines.append("差值:")
        for delta in deltas:
            item = _mapping(delta)
            lines.append(
                f"  - {_text(item.get('character'))}: "
                f"圣遗物评分 {_signed_number(item.get('artifact_score'))}"
            )
            _append_fight_delta(lines, _mapping(item.get("fight_props")))
    return _finish(lines)


def render_panel_save_text(data: Mapping[str, object]) -> str:
    return _finish(
        [
            "面板保存",
            f"UID: {_text(data.get('uid'))}",
            f"角色: {_text(data.get('character'))}",
            f"名称: {_text(data.get('name'))}",
            f"状态: {'已保存' if data.get('saved') else '未保存'}",
            f"文件: {_text(data.get('path'))}",
        ]
    )


def render_panel_artifacts_text(data: Mapping[str, object]) -> str:
    lines = ["圣遗物仓库", f"UID: {_text(data.get('uid'))}"]
    lines.append(
        f"页码: {_text(data.get('page'))}/{_text(data.get('total_pages'))}，"
        f"当前: {_text(data.get('count'))}，总数: {_text(data.get('total_count'))}"
    )
    artifacts = _sequence(data.get("artifacts"))
    if not artifacts:
        lines.extend(["", "暂无圣遗物"])
        return _finish(lines)
    lines.append("")
    lines.append("圣遗物:")
    for artifact in artifacts:
        item = _mapping(artifact)
        lines.append(
            f"  - {_text(item.get('character'))}: "
            f"{_slot_label(item.get('slot'))} "
            f"{_text(item.get('name'))} "
            f"+{_text(item.get('level'))} "
            f"{_stars(item.get('rank'))}，评分 {_number_text(item.get('score'))}"
        )
        _append_artifact_detail(lines, item, indent="    ")
    return _finish(lines)


def render_panel_showcase_text(data: Mapping[str, object]) -> str:
    lines = ["角色展柜", f"UID: {_text(data.get('uid'))}"]
    _append_player(lines, _mapping(data.get("player")))
    _append_character_rows(lines, _sequence(data.get("showcase")), count=data.get("count"))
    _append_cached_at(lines, data)
    return _finish(lines)


def render_panel_graduation_text(data: Mapping[str, object]) -> str:
    lines = ["练度统计", f"UID: {_text(data.get('uid'))}"]
    rows = _sequence(data.get("characters"))
    lines.append(f"角色数量: {_text(data.get('count'))}")
    limitations = _sequence(data.get("source_limitations"))
    if limitations:
        lines.append("限制:")
        for limitation in limitations:
            lines.append(f"  - {_text(limitation)}")
    if rows:
        lines.append("")
        lines.append("角色:")
        for row in rows:
            item = _mapping(row)
            lines.append(
                f"  - {_text(item.get('name'))} "
                f"Lv.{_text(item.get('level'))}: "
                f"圣遗物评分 {_number_text(item.get('artifact_score'))}，"
                f"毕业分 {_nullable_number(item.get('graduation_score'))}"
            )
    return _finish(lines)


def _append_player(lines: list[str], player: Mapping[str, object]) -> None:
    nickname = _text(player.get("nickname"))
    if nickname != "-":
        lines.append(f"玩家: {nickname}")
    level = _text(player.get("level"))
    if level != "-":
        lines.append(f"冒险等阶: {level}")
    world_level = _text(player.get("world_level"))
    if world_level != "-":
        lines.append(f"世界等级: {world_level}")
    achievements = _text(player.get("achievements"))
    if achievements != "-":
        lines.append(f"成就: {achievements}")


def _append_character_rows(
    lines: list[str],
    rows: list[object],
    *,
    count: object,
) -> None:
    lines.append(f"角色数量: {_text(count)}")
    if not rows:
        lines.extend(["", "暂无角色"])
        return
    lines.append("")
    lines.append("角色:")
    for row in rows:
        item = _mapping(row)
        lines.append(
            f"  - {_text(item.get('name'))} "
            f"Lv.{_text(item.get('level'))} "
            f"{_constellation_text(item.get('constellation'))}，"
            f"武器: {_text(item.get('weapon'))}，"
            f"圣遗物评分: {_number_text(item.get('artifact_score'))}"
        )


def _append_weapon(lines: list[str], weapon: Mapping[str, object]) -> None:
    if not weapon:
        return
    suffix = []
    weapon_type = _weapon_type_label(weapon.get("type"))
    if weapon_type != "-":
        suffix.append(weapon_type)
    affix = _text(weapon.get("affix"))
    if affix != "-":
        suffix.append(f"精{affix}")
    lines.append(
        "武器: "
        f"{_text(weapon.get('name'))} "
        f"Lv.{_text(weapon.get('level'))} "
        f"{_stars(weapon.get('rank'))}"
        f"{'，' + '，'.join(suffix) if suffix else ''}"
    )
    stats = _sequence(weapon.get("stats"))
    if stats:
        lines.append("武器属性:")
        for stat in stats[:2]:
            item = _mapping(stat)
            lines.append(f"  - {_stat_name(item)}: {_stat_text(item)}")
    effect = _text(weapon.get("effect"))
    if effect != "-":
        lines.append("武器特效:")
        for line in effect.splitlines():
            lines.append(f"  {line}")


def _append_skill_levels(lines: list[str], skill_levels: Mapping[str, object]) -> None:
    if not skill_levels:
        return
    values = [_text(value) for _key, value in skill_levels.items()]
    if len(values) > 3:
        values = [values[0], values[1], values[-1]]
    lines.append(f"技能: {'/'.join(values)}")


def _append_fight_props(lines: list[str], props: Mapping[str, object]) -> None:
    selected = [
        ("max_hp", "生命值"),
        ("max_atk", "攻击力"),
        ("max_def", "防御力"),
        ("base_hp", "基础生命"),
        ("base_atk", "基础攻击"),
        ("base_def", "基础防御"),
        ("elemental_mastery", "元素精通"),
        ("crit_rate", "暴击率"),
        ("crit_damage", "暴击伤害"),
        ("energy_recharge", "元素充能"),
        ("pyro_bonus", "火伤加成"),
        ("hydro_bonus", "水伤加成"),
        ("cryo_bonus", "冰伤加成"),
        ("electro_bonus", "雷伤加成"),
        ("anemo_bonus", "风伤加成"),
        ("geo_bonus", "岩伤加成"),
        ("dendro_bonus", "草伤加成"),
        ("physical_bonus", "物伤加成"),
    ]
    available = [(key, label) for key, label in selected if key in props]
    if not available:
        return
    lines.append("属性:")
    for key, label in available:
        lines.append(f"  - {label}: {_stat_value(key, props.get(key))}")


def _append_fight_delta(lines: list[str], props: Mapping[str, object]) -> None:
    interesting = [
        ("base_hp", "基础生命"),
        ("base_atk", "基础攻击"),
        ("base_def", "基础防御"),
        ("elemental_mastery", "元素精通"),
        ("crit_rate", "暴击率"),
        ("crit_damage", "暴击伤害"),
        ("energy_recharge", "元素充能"),
        ("pyro_bonus", "火伤加成"),
        ("hydro_bonus", "水伤加成"),
        ("cryo_bonus", "冰伤加成"),
        ("electro_bonus", "雷伤加成"),
        ("anemo_bonus", "风伤加成"),
        ("geo_bonus", "岩伤加成"),
        ("dendro_bonus", "草伤加成"),
        ("physical_bonus", "物伤加成"),
    ]
    for key, label in interesting:
        if key in props:
            lines.append(f"    {label}: {_signed_number(props.get(key))}")


def _append_artifacts(lines: list[str], artifacts: list[object], *, limit: int) -> None:
    if not artifacts:
        return
    lines.append("圣遗物:")
    for artifact in artifacts[:limit]:
        item = _mapping(artifact)
        lines.append(
            f"  - {_slot_label(item.get('slot'))}: "
            f"{_text(item.get('name'))} "
            f"+{_text(item.get('level'))} "
            f"{_stars(item.get('rank'))}，评分 {_number_text(item.get('score'))}"
        )
        _append_artifact_detail(lines, item, indent="    ")


def _append_artifact_detail(
    lines: list[str],
    artifact: Mapping[str, object],
    *,
    indent: str,
) -> None:
    set_name = _text(artifact.get("set_name"))
    if set_name != "-":
        lines.append(f"{indent}套装: {set_name}")
    main_stat = _mapping(artifact.get("main_stat"))
    if main_stat:
        lines.append(f"{indent}主词条: {_stat_name(main_stat)} {_stat_text(main_stat)}")
    substats = [_mapping(item) for item in _sequence(artifact.get("substats"))]
    if substats:
        lines.append(f"{indent}副词条:")
        for substat in substats:
            lines.append(f"{indent}  - {_stat_name(substat)}: {_stat_text(substat)}")


def _append_reference(lines: list[str], reference: Mapping[str, object]) -> None:
    if not reference:
        return
    effective = _number_text(reference.get("effective_stat_count"))
    sequence = _text(reference.get("sequence_label"))
    percent = reference.get("graduation_percent")
    lines.append("参考:")
    lines.append(f"  - 有效词条: {effective}")
    lines.append(f"  - 参考轴: {sequence if sequence != '-' else '无匹配'}")
    percent_text = _percent_text(percent) if percent not in (None, 0, 0.0) else "暂无匹配"
    lines.append(f"  - 毕业度: {percent_text}")
    rows = _sequence(reference.get("damage_rows"))
    if rows:
        lines.append("伤害参考:")
        for row in rows:
            item = _mapping(row)
            lines.append(
                f"  - {_text(item.get('action'))}: "
                f"暴击 {_rounded_number(item.get('crit'))}，"
                f"期望 {_rounded_number(item.get('avg'))}，"
                f"普通 {_rounded_number(item.get('normal'))}"
            )


def _append_cached_at(lines: list[str], data: Mapping[str, object]) -> None:
    cached_at = _text(data.get("cached_at"))
    if cached_at != "-":
        lines.append(f"缓存时间: {cached_at}")


def _build_label(build: Mapping[str, object]) -> str:
    panel = _mapping(build.get("panel"))
    character = panel.get("name") or build.get("character")
    return f"{_text(build.get('uid'))}/{_text(character)}"


def _stat_value(key: str, value: object) -> str:
    if key in {
        "crit_rate",
        "crit_damage",
        "energy_recharge",
        "pyro_bonus",
        "hydro_bonus",
        "cryo_bonus",
        "electro_bonus",
        "anemo_bonus",
        "geo_bonus",
        "dendro_bonus",
        "physical_bonus",
    }:
        return f"{_number_text(value)}%"
    return _number_text(value)


def _stat_name(stat: Mapping[str, object]) -> str:
    prop = _text(stat.get("appendPropId") or stat.get("mainPropId") or stat.get("prop"))
    return _prop_name(prop)


def _stat_text(stat: Mapping[str, object]) -> str:
    prop = _text(stat.get("appendPropId") or stat.get("mainPropId") or stat.get("prop"))
    value = stat.get("statValue")
    if value is None:
        value = stat.get("value")
    suffix = "%" if prop in PERCENT_PROPS and prop not in FIXED_VALUE_PROPS else ""
    return f"{_number_text(value)}{suffix}"


def _prop_name(prop: str) -> str:
    return str(
        _text_map("propId2Name_mapping.json").get(prop) or PROP_LABEL_FALLBACKS.get(prop) or prop
    )


def _weapon_type_label(value: object) -> str:
    text = _text(value)
    if text == "-":
        return text
    return WEAPON_TYPE_LABELS.get(text, text)


def _slot_label(value: object) -> str:
    return {
        "EQUIP_BRACER": "生之花",
        "EQUIP_NECKLACE": "死之羽",
        "EQUIP_SHOES": "时之沙",
        "EQUIP_RING": "空之杯",
        "EQUIP_DRESS": "理之冠",
    }.get(str(value), _text(value))


def _override_label(value: object) -> str:
    return {
        "constellation": "命座",
        "weapon": "武器",
        "artifact_source_character": "圣遗物来源角色",
    }.get(str(value), _text(value))


def _source_label(value: object) -> str:
    return {"enka": "Enka", "mys": "米游社", "enka+mys": "Enka + 米游社", "auto": "自动"}.get(
        str(value), _text(value)
    )


def _constellation_text(value: object) -> str:
    return f"{_text(value)}命"


def _stars(value: object) -> str:
    try:
        count = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    if count <= 0:
        return ""
    return "★" * count


def _nullable_number(value: object) -> str:
    if value is None:
        return "未配置"
    return _number_text(value)


def _signed_number(value: object) -> str:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "0"
    sign = "+" if number > 0 else ""
    return f"{sign}{_number_text(number)}"


def _rounded_number(value: object) -> str:
    try:
        return str(round(float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "0"


def _percent_text(value: object) -> str:
    return f"{_number_text(value)}%"


@lru_cache(maxsize=16)
def _text_map(filename: str) -> dict[str, object]:
    path = asset_path("panel", "data", filename)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
