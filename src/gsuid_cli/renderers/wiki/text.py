from __future__ import annotations

import re
from collections.abc import Mapping

from gsuid_cli.renderers.common import int_value, sequence, text_value
from gsuid_cli.renderers.utility_text import _finish, _mapping

KIND_LABELS = {
    "character": "角色资料",
    "weapon": "武器资料",
    "artifact": "圣遗物资料",
    "enemy": "原魔资料",
    "food": "食物资料",
}
ELEMENT_LABELS = {
    "Fire": "火",
    "Water": "水",
    "Wind": "风",
    "Electric": "雷",
    "Grass": "草",
    "Ice": "冰",
    "Rock": "岩",
}
WEAPON_TYPE_LABELS = {
    "WEAPON_SWORD_ONE_HAND": "单手剑",
    "WEAPON_CLAYMORE": "双手剑",
    "WEAPON_POLE": "长柄武器",
    "WEAPON_CATALYST": "法器",
    "WEAPON_BOW": "弓",
}
REGION_LABELS = {
    "MONDSTADT": "蒙德",
    "LIYUE": "璃月",
    "INAZUMA": "稻妻",
    "SUMERU": "须弥",
    "FONTAINE": "枫丹",
    "NATLAN": "纳塔",
    "NODKRAI": "挪德卡莱",
    "SNEZHNAYA": "至冬",
}
PROP_LABELS = {
    "FIGHT_PROP_BASE_ATTACK": "基础攻击力",
    "FIGHT_PROP_CHARGE_EFFICIENCY": "元素充能效率",
    "FIGHT_PROP_ATTACK_PERCENT": "攻击力",
    "FIGHT_PROP_CRITICAL": "暴击率",
    "FIGHT_PROP_CRITICAL_HURT": "暴击伤害",
    "FIGHT_PROP_ELEMENT_MASTERY": "元素精通",
    "FIGHT_PROP_HP_PERCENT": "生命值",
    "FIGHT_PROP_DEFENSE_PERCENT": "防御力",
    "FIGHT_PROP_PHYSICAL_ADD_HURT": "物理伤害加成",
}
TALENT_TYPE_LABELS = {
    "0": "普通攻击",
    "1": "元素战技",
    "2": "元素爆发",
}


def render_wiki_lookup_text(kind: str, item: Mapping[str, object]) -> str:
    title = f"{KIND_LABELS.get(kind, 'Wiki资料')} - {_name(item)}"
    lines = [title]
    if kind == "character":
        _append_character(lines, item)
    elif kind == "weapon":
        _append_weapon(lines, item)
    elif kind == "artifact":
        _append_artifact(lines, item)
    elif kind == "food":
        _append_food(lines, item)
    else:
        _append_enemy(lines, item)
    return _finish(lines)


def render_wiki_talent_text(data: Mapping[str, object]) -> str:
    character = text_value(data.get("character")) or "未知角色"
    talent = _mapping(data.get("talent"))
    index = _index_label(talent.get("index"), "天赋")
    name = text_value(talent.get("name"))
    lines = [f"角色天赋 - {character}", f"{index}: {name}" if name else index]

    talent_type = _talent_type(talent.get("type"))
    if talent_type:
        lines.append(f"类型: {talent_type}")
    desc = _clean_text(
        talent.get("description")
        or talent.get("desc")
        or talent.get("effect")
        or talent.get("nameHashMap")
    )
    if desc:
        lines.extend(["", desc])
    promote = _mapping(talent.get("promote"))
    named_promote = talent.get("promote_materials")
    if named_promote:
        lines.extend(["", "升级材料:"])
        _append_named_promote_materials(lines, named_promote)
    elif promote:
        lines.extend(["", "升级材料:"])
        _append_promote_summary(lines, promote)
    return _finish(lines)


def render_wiki_constellation_text(data: Mapping[str, object]) -> str:
    character = text_value(data.get("character")) or "未知角色"
    payload = data.get("constellation")
    lines = [f"角色命座 - {character}"]
    if isinstance(payload, Mapping):
        _append_constellation(lines, payload)
        return _finish(lines)
    rows = [row for row in sequence(payload) if isinstance(row, Mapping)]
    lines.append(f"数量: {len(rows)}")
    for row in rows:
        _append_constellation(lines, row, bullet=True)
    return _finish(lines)


def render_wiki_character_materials_text(data: Mapping[str, object]) -> str:
    character = text_value(data.get("character")) or "未知角色"
    lines = [f"角色材料 - {character}"]
    _append_material_section(
        lines,
        "材料汇总",
        data.get("ascension_materials") or data.get("ascension"),
    )
    talent_materials = [
        row for row in sequence(data.get("talent_materials")) if isinstance(row, Mapping)
    ]
    if talent_materials:
        lines.extend(["", "天赋升级材料:"])
        for talent in talent_materials:
            name = text_value(talent.get("name")) or _index_label(talent.get("index"), "天赋")
            lines.append(f"  - {name}")
            _append_named_promote_materials(lines, talent.get("promote_materials"), indent="    ")
    return _finish(lines)


def render_wiki_weapon_materials_text(data: Mapping[str, object]) -> str:
    weapon = text_value(data.get("weapon")) or "未知武器"
    lines = [f"武器材料 - {weapon}"]
    _append_material_section(
        lines,
        "突破素材",
        data.get("ascension_materials") or data.get("ascension"),
    )
    return _finish(lines)


def _append_character(lines: list[str], item: Mapping[str, object]) -> None:
    _append_field(lines, "稀有度", _stars(item.get("rank")))
    _append_field(lines, "元素", _element(item.get("element")))
    _append_field(lines, "武器", _weapon_type(item.get("weapon_type")))
    _append_field(lines, "地区", _region(item.get("region")))
    _append_field(lines, "生日", _birthday(item.get("birthday")))
    _append_field(lines, "称号", item.get("title"))
    desc = _clean_text(item.get("description"))
    if desc:
        lines.extend(["", desc])


def _append_weapon(lines: list[str], item: Mapping[str, object]) -> None:
    _append_field(lines, "稀有度", _stars(item.get("rank")))
    _append_field(lines, "类型", _weapon_type(item.get("weapon_type")))
    base_attack = _base_attack(item.get("upgrade"))
    if base_attack:
        lines.append(f"基础攻击力: {base_attack}")
    _append_field(lines, "副属性", _prop_label(item.get("special_prop")))
    desc = _clean_text(item.get("description"))
    if desc:
        lines.extend(["", desc])
    effect_name, effect_desc = _weapon_effect(item)
    if effect_name or effect_desc:
        lines.extend(["", "武器特效:"])
        if effect_name:
            lines.append(f"  - {effect_name}")
        if effect_desc:
            lines.append(f"    {effect_desc}")


def _append_artifact(lines: list[str], item: Mapping[str, object]) -> None:
    levels = [str(level) for level in sequence(item.get("level_list")) if str(level).strip()]
    if levels:
        lines.append(f"稀有度: {'/'.join(levels)}星")
    bonuses = _mapping(item.get("bonuses"))
    if bonuses:
        lines.extend(["", "套装效果:"])
        for index, (count, bonus) in enumerate(bonuses.items()):
            text = _clean_text(bonus)
            if text:
                lines.append(f"  - {_artifact_bonus_count(count, index)}件: {text}")
    parts = [part for part in sequence(item.get("suit")) if isinstance(part, Mapping)]
    if parts:
        lines.extend(["", "部件:"])
        for part in parts:
            name = text_value(part.get("name")) or "未命名部件"
            desc = _clean_text(part.get("description"))
            lines.append(f"  - {name}")
            if desc:
                lines.append(f"    {desc}")


def _append_food(lines: list[str], item: Mapping[str, object]) -> None:
    _append_field(lines, "稀有度", _stars(item.get("rank")))
    effect = _food_effect(item)
    if effect:
        lines.extend(["", "效果:", effect])
    desc = _clean_text(item.get("description"))
    if desc:
        lines.extend(["", "描述:", desc])
    recipe = _food_recipe(item.get("recipe"))
    materials = [row for row in sequence(recipe.get("input")) if isinstance(row, Mapping)]
    if materials:
        lines.extend(["", "所需材料:"])
        for index, material in enumerate(materials, start=1):
            lines.append(f"  - {_material_label(material, index)}")


def _append_enemy(lines: list[str], item: Mapping[str, object]) -> None:
    _append_field(lines, "类型", item.get("enemy_type"))
    _append_field(lines, "称号", item.get("title"))
    _append_field(lines, "特殊名称", item.get("special_name"))
    desc = _clean_text(item.get("description"))
    if desc:
        lines.extend(["", desc])
    tips = _clean_text(item.get("tips"))
    if tips:
        lines.extend(["", "攻略提示:", tips])


def _append_material_section(lines: list[str], title: str, value: object) -> None:
    entries = _material_entries(value)
    if not entries:
        return
    lines.extend(["", f"{title}:"])
    for index, entry in enumerate(entries, start=1):
        lines.append(f"  - {_material_label(entry, index)}")


def _append_promote_summary(
    lines: list[str],
    promote: Mapping[str, object],
    *,
    indent: str = "  ",
) -> None:
    appended = False
    for level, row in promote.items():
        if not isinstance(row, Mapping):
            continue
        cost_items = _material_entries(row.get("costItems"))
        if cost_items:
            material_text = "、".join(
                _material_label(entry, index) for index, entry in enumerate(cost_items, start=1)
            )
            lines.append(f"{indent}- 等级 {level}: {material_text}")
            appended = True
    if not appended:
        lines.append(f"{indent}- 暂无可读材料明细")


def _append_named_promote_materials(
    lines: list[str],
    value: object,
    *,
    indent: str = "  ",
) -> None:
    promote = _mapping(value)
    appended = False
    for level, materials in promote.items():
        entries = _material_entries(materials)
        if entries:
            material_text = "、".join(
                _material_label(entry, index) for index, entry in enumerate(entries, start=1)
            )
            lines.append(f"{indent}- 等级 {level}: {material_text}")
            appended = True
    if not appended:
        lines.append(f"{indent}- 暂无可读材料明细")


def _append_constellation(
    lines: list[str],
    row: Mapping[str, object],
    *,
    bullet: bool = False,
) -> None:
    index = _index_label(row.get("index"), "命座")
    name = text_value(row.get("name"))
    prefix = "  - " if bullet else ""
    lines.append(f"{prefix}{index}: {name}" if name else f"{prefix}{index}")
    desc = _clean_text(row.get("description") or row.get("desc"))
    if desc:
        lines.append(("    " if bullet else "") + desc)


def _append_field(lines: list[str], label: str, value: object) -> None:
    text = text_value(value)
    if text:
        lines.append(f"{label}: {text}")


def _food_effect(item: Mapping[str, object]) -> str | None:
    recipe = _food_recipe(item.get("recipe"))
    effect = recipe.get("effect")
    if isinstance(effect, Mapping):
        for value in effect.values():
            text = _clean_text(value)
            if text:
                return text
    return _clean_text(item.get("effect"))


def _food_recipe(value: object) -> Mapping[str, object]:
    recipe = _mapping(value)
    inputs = recipe.get("input")
    if isinstance(inputs, list):
        return {**recipe, "input": inputs}
    normalized_inputs: list[dict[str, object]] = []
    if isinstance(inputs, Mapping):
        for item in inputs.values():
            if isinstance(item, Mapping):
                normalized_inputs.append(dict(item))
    return {**recipe, "input": normalized_inputs}


def _weapon_effect(item: Mapping[str, object]) -> tuple[str | None, str | None]:
    affixes = [affix for affix in sequence(item.get("affixes")) if isinstance(affix, Mapping)]
    if not affixes:
        return None, None
    affix = affixes[0]
    upgrade = _mapping(affix.get("upgrade"))
    effect = text_value(upgrade.get("0")) or text_value(next(iter(upgrade.values()), ""))
    return text_value(affix.get("name")) or "武器特效", _clean_text(effect)


def _base_attack(value: object) -> int | None:
    upgrade = _mapping(value)
    for prop in sequence(upgrade.get("prop")):
        if not isinstance(prop, Mapping) or prop.get("propType") != "FIGHT_PROP_BASE_ATTACK":
            continue
        try:
            return round(float(prop.get("initValue") or 0))
        except (TypeError, ValueError):
            return None
    return None


def _material_entries(value: object) -> list[Mapping[str, object]]:
    if isinstance(value, Mapping):
        entries = []
        for key, item in value.items():
            if isinstance(item, Mapping):
                entries.append(item)
            else:
                entries.append({"count": item, "_sort": str(key)})
        entries.sort(key=lambda entry: str(entry.get("name") or entry.get("_sort") or ""))
        return entries
    return [item for item in sequence(value) if isinstance(item, Mapping)]


def _material_label(material: Mapping[str, object], index: int) -> str:
    name = text_value(material.get("name")) or f"未解析素材 {index}"
    count = material.get("count")
    return f"{name} x{count}" if count not in (None, "") else name


def _element(value: object) -> str | None:
    text = text_value(value)
    if text is None:
        return None
    return ELEMENT_LABELS.get(text, text)


def _weapon_type(value: object) -> str | None:
    text = text_value(value)
    if text is None:
        return None
    return WEAPON_TYPE_LABELS.get(text, text)


def _region(value: object) -> str | None:
    text = text_value(value)
    if text is None:
        return None
    return REGION_LABELS.get(text, text)


def _birthday(value: object) -> str | None:
    if isinstance(value, list) and len(value) >= 2:
        month = int_value(value[0], 0)
        day = int_value(value[1], 0)
        if month > 0 and day > 0:
            return f"{month}月{day}日"
    return text_value(value)


def _prop_label(value: object) -> str | None:
    text = text_value(value)
    if text is None or text.lower() in {"none", "null"}:
        return None
    return PROP_LABELS.get(text, text)


def _artifact_bonus_count(value: object, index: int) -> str:
    text = text_value(value)
    if text in {"1", "2", "3", "4", "5"}:
        return text
    return "2" if index == 0 else "4"


def _talent_type(value: object) -> str | None:
    text = text_value(value)
    if text is None:
        return None
    return TALENT_TYPE_LABELS.get(text, text)


def _stars(value: object) -> str | None:
    rank = int_value(value, 0)
    if rank <= 0:
        return None
    return "★" * rank


def _index_label(value: object, label: str) -> str:
    index = int_value(value, 0)
    return f"{label} {index}" if index > 0 else label


def _name(item: Mapping[str, object]) -> str:
    return text_value(item.get("name")) or "未知"


def _clean_text(value: object) -> str | None:
    text = text_value(value)
    if text is None:
        return None
    text = text.replace("\\n", "\n")
    text = re.sub(r"</?color[^>]*>", "", text)
    text = text.replace("**", "")
    return text.strip() or None
