from __future__ import annotations

import re
from collections.abc import Mapping

from gsuid_cli.renderers._text_helpers import _finish, _mapping
from gsuid_cli.renderers.common import int_value, sequence, text_value
from gsuid_cli.text import t as _t

KIND_LABELS = {
    "character": _t("gsuid.renderers.wiki.text.10_17.692036b0"),
    "weapon": _t("gsuid.renderers.wiki.text.11_14.751d5bdc"),
    "artifact": _t("gsuid.renderers.wiki.text.12_16.c96f1da3"),
    "enemy": _t("gsuid.renderers.wiki.text.13_13.6a72f216"),
    "food": _t("gsuid.renderers.wiki.text.14_12.ff34115c"),
}
ELEMENT_LABELS = {
    "Fire": _t("gsuid.renderers.wiki.picwiki.41_12.efb26208"),
    "Water": _t("gsuid.renderers.wiki.picwiki.42_13.8ffbf192"),
    "Wind": _t("gsuid.renderers.wiki.picwiki.43_12.534418ad"),
    "Electric": _t("gsuid.renderers.wiki.picwiki.44_16.deaefde2"),
    "Grass": _t("gsuid.renderers.wiki.picwiki.45_13.67447716"),
    "Ice": _t("gsuid.renderers.wiki.picwiki.46_11.6c20967f"),
    "Rock": _t("gsuid.renderers.wiki.picwiki.47_12.9ba9dc86"),
}
WEAPON_TYPE_LABELS = {
    "WEAPON_SWORD_ONE_HAND": _t("gsuid.renderers.panel.text.61_29.19c268b4"),
    "WEAPON_CLAYMORE": _t("gsuid.renderers.panel.text.62_23.1a1f46df"),
    "WEAPON_POLE": _t("gsuid.renderers.panel.text.63_19.5d4b74a8"),
    "WEAPON_CATALYST": _t("gsuid.renderers.panel.metrics.1053_22.4813ba67"),
    "WEAPON_BOW": _t("gsuid.renderers.panel.metrics.1055_24.a0ec11cd"),
}
REGION_LABELS = {
    "MONDSTADT": _t("gsuid.renderers.daily.text.18_9.4e2f394b"),
    "LIYUE": _t("gsuid.renderers.daily.text.19_9.cf9effa7"),
    "INAZUMA": _t("gsuid.renderers.daily.text.20_9.60582a7f"),
    "SUMERU": _t("gsuid.renderers.daily.text.21_9.d6e52915"),
    "FONTAINE": _t("gsuid.renderers.daily.text.22_9.71f4594b"),
    "NATLAN": _t("gsuid.renderers.daily.text.23_9.3fd1306d"),
    "NODKRAI": _t("gsuid.renderers.daily.text.24_9.b6b55ca3"),
    "SNEZHNAYA": _t("gsuid.renderers.wiki.text.40_17.76e8c41b"),
}
PROP_LABELS = {
    "FIGHT_PROP_BASE_ATTACK": _t("gsuid.renderers.panel.image.90_30.1ad8495e"),
    "FIGHT_PROP_CHARGE_EFFICIENCY": _t("gsuid.providers.akasha.68_4.a7a24305"),
    "FIGHT_PROP_ATTACK_PERCENT": _t("gsuid.renderers.panel.image.88_25.ef28aed2"),
    "FIGHT_PROP_CRITICAL": _t("gsuid.providers.akasha.70_4.33e0f20a"),
    "FIGHT_PROP_CRITICAL_HURT": _t("gsuid.providers.akasha.72_4.7c0dd18b"),
    "FIGHT_PROP_ELEMENT_MASTERY": _t("gsuid.providers.akasha.66_4.af09dad1"),
    "FIGHT_PROP_HP_PERCENT": _t("gsuid.renderers.panel.metrics.357_7.575ca7a8"),
    "FIGHT_PROP_DEFENSE_PERCENT": _t("gsuid.renderers.panel.image.91_26.2557c107"),
    "FIGHT_PROP_PHYSICAL_ADD_HURT": _t("gsuid.renderers.panel.image.109_36.be65271f"),
}
TALENT_TYPE_LABELS = {
    "0": _t("gsuid.renderers.wiki.text.54_9.d599b837"),
    "1": _t("gsuid.renderers.wiki.text.55_9.8ed83fb0"),
    "2": _t("gsuid.renderers.challenge.abyss.128_9.4e5b3902"),
}


def render_wiki_lookup_text(kind: str, item: Mapping[str, object]) -> str:
    title = (
        f"{KIND_LABELS.get(kind, _t('gsuid.renderers.wiki.text.61_37.9857f12b'))} - {_name(item)}"
    )
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
    character = text_value(data.get("character")) or _t(
        "gsuid.renderers.challenge.text.293_68.876cfbce"
    )
    talent = _mapping(data.get("talent"))
    index = _index_label(talent.get("index"), _t("gsuid.renderers.wiki.text.79_46.d83d147c"))
    name = text_value(talent.get("name"))
    lines = [
        _t("gsuid.renderers.wiki.text.81_13.7fd8cd48", character),
        f"{index}: {name}" if name else index,
    ]

    talent_type = _talent_type(talent.get("type"))
    if talent_type:
        lines.append(_t("gsuid.renderers.wiki.text.85_21.d6c84180", talent_type))
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
        lines.extend(["", _t("gsuid.renderers.wiki.text.97_26.9a37bc85")])
        _append_named_promote_materials(lines, named_promote)
    elif promote:
        lines.extend(["", _t("gsuid.renderers.wiki.text.97_26.9a37bc85")])
        _append_promote_summary(lines, promote)
    return _finish(lines)


def render_wiki_constellation_text(data: Mapping[str, object]) -> str:
    character = text_value(data.get("character")) or _t(
        "gsuid.renderers.challenge.text.293_68.876cfbce"
    )
    payload = data.get("constellation")
    lines = [_t("gsuid.renderers.wiki.text.108_13.063354cb", character)]
    if isinstance(payload, Mapping):
        _append_constellation(lines, payload)
        return _finish(lines)
    rows = [row for row in sequence(payload) if isinstance(row, Mapping)]
    lines.append(_t("gsuid.renderers.challenge.text.186_8.a63927f2", len(rows)))
    for row in rows:
        _append_constellation(lines, row, bullet=True)
    return _finish(lines)


def render_wiki_character_materials_text(data: Mapping[str, object]) -> str:
    character = text_value(data.get("character")) or _t(
        "gsuid.renderers.challenge.text.293_68.876cfbce"
    )
    lines = [_t("gsuid.renderers.wiki.text.121_13.af63a93e", character)]
    _append_material_section(
        lines,
        _t("gsuid.renderers.wiki.text.124_8.ebdcf085"),
        data.get("ascension_materials") or data.get("ascension"),
    )
    talent_materials = [
        row for row in sequence(data.get("talent_materials")) if isinstance(row, Mapping)
    ]
    if talent_materials:
        lines.extend(["", _t("gsuid.renderers.wiki.text.131_26.2ce586d4")])
        for talent in talent_materials:
            name = text_value(talent.get("name")) or _index_label(
                talent.get("index"), _t("gsuid.renderers.wiki.text.79_46.d83d147c")
            )
            lines.append(f"  - {name}")
            _append_named_promote_materials(lines, talent.get("promote_materials"), indent="    ")
    return _finish(lines)


def render_wiki_weapon_materials_text(data: Mapping[str, object]) -> str:
    weapon = text_value(data.get("weapon")) or _t("gsuid.renderers.panel.image.1086_49.6eb8409d")
    lines = [_t("gsuid.renderers.wiki.text.141_13.ab988ad8", weapon)]
    _append_material_section(
        lines,
        _t("gsuid.renderers.wiki.picwiki.235_43.dcb7501d"),
        data.get("ascension_materials") or data.get("ascension"),
    )
    return _finish(lines)


def _append_character(lines: list[str], item: Mapping[str, object]) -> None:
    _append_field(lines, _t("gsuid.renderers.wiki.text.151_25.18e56cf0"), _stars(item.get("rank")))
    _append_field(
        lines, _t("gsuid.renderers.panel.image.1902_49.74f529b6"), _element(item.get("element"))
    )
    _append_field(
        lines,
        _t("gsuid.commands.panel.impl.988_24.6f0f16e0"),
        _weapon_type(item.get("weapon_type")),
    )
    _append_field(
        lines, _t("gsuid.renderers.wiki.text.154_25.e87af301"), _region(item.get("region"))
    )
    _append_field(
        lines, _t("gsuid.renderers.wiki.text.155_25.eb640387"), _birthday(item.get("birthday"))
    )
    _append_field(lines, _t("gsuid.renderers.wiki.text.156_25.5fc6336b"), item.get("title"))
    desc = _clean_text(item.get("description"))
    if desc:
        lines.extend(["", desc])
    _append_level_info(lines, item)


def _append_weapon(lines: list[str], item: Mapping[str, object]) -> None:
    _append_field(lines, _t("gsuid.renderers.wiki.text.151_25.18e56cf0"), _stars(item.get("rank")))
    _append_field(
        lines,
        _t("gsuid.renderers.wiki.text.165_25.e4e46c72"),
        _weapon_type(item.get("weapon_type")),
    )
    base_attack = _base_attack(item.get("upgrade"))
    if base_attack:
        lines.append(_t("gsuid.renderers.wiki.text.168_21.45e30a96", base_attack))
    _append_field(
        lines,
        _t("gsuid.renderers.wiki.text.169_25.c43be358"),
        _prop_label(item.get("special_prop")),
    )
    desc = _clean_text(item.get("description"))
    if desc:
        lines.extend(["", desc])
    effect_name, effect_desc = _weapon_effect(item)
    if effect_name or effect_desc:
        lines.extend(["", _t("gsuid.renderers.panel.text.285_21.de4dace2")])
        if effect_name:
            lines.append(f"  - {effect_name}")
        if effect_desc:
            lines.append(f"    {effect_desc}")
    _append_level_info(lines, item)


def _append_artifact(lines: list[str], item: Mapping[str, object]) -> None:
    levels = [str(level) for level in sequence(item.get("level_list")) if str(level).strip()]
    if levels:
        lines.append(_t("gsuid.renderers.wiki.text.186_21.308299a5", "/".join(levels)))
    bonuses = _mapping(item.get("bonuses"))
    if bonuses:
        lines.extend(["", _t("gsuid.renderers.wiki.text.189_26.960fe210")])
        for index, (count, bonus) in enumerate(bonuses.items()):
            text = _clean_text(bonus)
            if text:
                lines.append(
                    _t(
                        "gsuid.renderers.wiki.text.193_29.e10f67b3",
                        _artifact_bonus_count(count, index),
                        text,
                    )
                )
    parts = [part for part in sequence(item.get("suit")) if isinstance(part, Mapping)]
    if parts:
        lines.extend(["", _t("gsuid.renderers.wiki.text.196_26.7edf8ef8")])
        for part in parts:
            name = text_value(part.get("name")) or _t("gsuid.renderers.wiki.text.198_51.065f4aae")
            desc = _clean_text(part.get("description"))
            lines.append(f"  - {name}")
            if desc:
                lines.append(f"    {desc}")


def _append_food(lines: list[str], item: Mapping[str, object]) -> None:
    _append_field(lines, _t("gsuid.renderers.wiki.text.151_25.18e56cf0"), _stars(item.get("rank")))
    effect = _food_effect(item)
    if effect:
        lines.extend(["", _t("gsuid.renderers.wiki.text.209_26.da7cd8e1"), effect])
    desc = _clean_text(item.get("description"))
    if desc:
        lines.extend(["", _t("gsuid.renderers.wiki.text.212_26.988bc013"), desc])
    recipe = _food_recipe(item.get("recipe"))
    materials = [row for row in sequence(recipe.get("input")) if isinstance(row, Mapping)]
    if materials:
        lines.extend(["", _t("gsuid.renderers.wiki.text.216_26.40803133")])
        for index, material in enumerate(materials, start=1):
            lines.append(f"  - {_material_label(material, index)}")


def _append_enemy(lines: list[str], item: Mapping[str, object]) -> None:
    _append_field(lines, _t("gsuid.renderers.wiki.text.165_25.e4e46c72"), item.get("enemy_type"))
    _append_field(lines, _t("gsuid.renderers.wiki.text.156_25.5fc6336b"), item.get("title"))
    _append_field(lines, _t("gsuid.renderers.wiki.text.224_25.1c08c5fe"), item.get("special_name"))
    desc = _clean_text(item.get("description"))
    if desc:
        lines.extend(["", desc])
    tips = _clean_text(item.get("tips"))
    if tips:
        lines.extend(["", _t("gsuid.renderers.wiki.text.230_26.9f79c2c1"), tips])


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
            lines.append(
                _t("gsuid.renderers.wiki.text.257_25.e15709ae", indent, level, material_text)
            )
            appended = True
    if not appended:
        lines.append(_t("gsuid.renderers.wiki.text.260_21.f06607b3", indent))


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
            lines.append(
                _t("gsuid.renderers.wiki.text.257_25.e15709ae", indent, level, material_text)
            )
            appended = True
    if not appended:
        lines.append(_t("gsuid.renderers.wiki.text.260_21.f06607b3", indent))


def _append_constellation(
    lines: list[str],
    row: Mapping[str, object],
    *,
    bullet: bool = False,
) -> None:
    index = _index_label(row.get("index"), _t("gsuid.commands.panel.impl.987_26.096ace91"))
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
    return text_value(affix.get("name")) or _t(
        "gsuid.renderers.wiki.picwiki.630_44.037909eb"
    ), _clean_text(effect)


def _append_level_info(lines: list[str], item: Mapping[str, object]) -> None:
    level_info = _mapping(item.get("level_info"))
    if not level_info:
        return
    lines.extend(["", _t("gsuid.renderers.wiki.text.342_22.628282f5")])
    _append_field(lines, _t("gsuid.commands.panel.impl.986_18.5c42c048"), level_info.get("level"))
    _append_field(
        lines, _t("gsuid.renderers.wiki.text.344_25.dd15b4d4"), level_info.get("promote_level")
    )
    _append_field(
        lines, _t("gsuid.renderers.wiki.text.345_25.f815ed99"), level_info.get("unlock_max_level")
    )
    _append_field(
        lines,
        _t("gsuid.renderers.wiki.text.346_25.74f2c4d4"),
        level_info.get("required_player_level"),
    )
    add_props = _mapping(level_info.get("add_props"))
    if add_props:
        lines.append(_t("gsuid.renderers.wiki.text.349_21.c41b6b08"))
        for prop, value in add_props.items():
            lines.append(f"  - {_prop_label(prop) or prop}: {_stat_value(prop, value)}")


def _stat_value(prop: object, value: object) -> str:
    number_text = text_value(value) or "-"
    prop_text = text_value(prop) or ""
    if prop_text in PROP_LABELS and any(
        token in prop_text for token in ("PERCENT", "CRITICAL", "HURT", "EFFICIENCY")
    ):
        try:
            return f"{float(number_text) * 100:.1f}%"
        except ValueError:
            return number_text
    return number_text


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
    name = text_value(material.get("name")) or _t(
        "gsuid.renderers.wiki.text.393_47.bf580cf9", index
    )
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
            return _t("gsuid.renderers.wiki.text.424_19.fa0b40c0", month, day)
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
    return text_value(item.get("name")) or _t("gsuid.renderers.daily.text.211_11.d9c32a4c")


def _clean_text(value: object) -> str | None:
    text = text_value(value)
    if text is None:
        return None
    text = text.replace("\\n", "\n")
    text = re.sub(r"</?color[^>]*>", "", text)
    text = text.replace("**", "")
    return text.strip() or None
