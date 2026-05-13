from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache

from gsuid_cli.renderers._text_helpers import _finish, _mapping, _number_text, _text
from gsuid_cli.renderers.common import asset_path
from gsuid_cli.renderers.utility_text import _sequence
from gsuid_cli.text import t as _t

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
    "FIGHT_PROP_ATTACK": _t("gsuid.renderers.panel.image.88_25.ef28aed2"),
    "FIGHT_PROP_ATTACK_PERCENT": _t("gsuid.providers.akasha.51_4.f60501c6"),
    "FIGHT_PROP_BASE_ATTACK": _t("gsuid.renderers.panel.image.90_30.1ad8495e"),
    "FIGHT_PROP_DEFENSE": _t("gsuid.renderers.panel.image.91_26.2557c107"),
    "FIGHT_PROP_DEFENSE_PERCENT": _t("gsuid.renderers.panel.image.92_34.7ecee44b"),
    "FIGHT_PROP_BASE_DEFENSE": _t("gsuid.renderers.panel.image.93_31.7da6b094"),
    "FIGHT_PROP_HP": _t("gsuid.renderers.panel.metrics.357_7.575ca7a8"),
    "FIGHT_PROP_HP_PERCENT": _t("gsuid.renderers.panel.text.45_29.79ca221e"),
    "FIGHT_PROP_BASE_HP": _t("gsuid.renderers.panel.text.46_26.1a15b7e5"),
    "FIGHT_PROP_ELEMENT_MASTERY": _t("gsuid.providers.akasha.66_4.af09dad1"),
    "FIGHT_PROP_CRITICAL": _t("gsuid.providers.akasha.70_4.33e0f20a"),
    "FIGHT_PROP_CRITICAL_HURT": _t("gsuid.providers.akasha.72_4.7c0dd18b"),
    "FIGHT_PROP_CHARGE_EFFICIENCY": _t("gsuid.providers.akasha.68_4.a7a24305"),
    "FIGHT_PROP_FIRE_ADD_HURT": _t("gsuid.renderers.panel.image.102_32.a7d92d8b"),
    "FIGHT_PROP_ELEC_ADD_HURT": _t("gsuid.renderers.panel.image.103_32.b05986fe"),
    "FIGHT_PROP_WATER_ADD_HURT": _t("gsuid.renderers.panel.image.104_33.0205a287"),
    "FIGHT_PROP_GRASS_ADD_HURT": _t("gsuid.renderers.panel.image.105_33.cfb22d08"),
    "FIGHT_PROP_WIND_ADD_HURT": _t("gsuid.renderers.panel.image.106_32.53069124"),
    "FIGHT_PROP_ROCK_ADD_HURT": _t("gsuid.renderers.panel.image.107_32.78be5ad7"),
    "FIGHT_PROP_ICE_ADD_HURT": _t("gsuid.renderers.panel.image.108_31.81e609f2"),
    "FIGHT_PROP_PHYSICAL_ADD_HURT": _t("gsuid.renderers.panel.image.109_36.be65271f"),
}
WEAPON_TYPE_LABELS = {
    "WEAPON_SWORD_ONE_HAND": _t("gsuid.renderers.panel.text.61_29.19c268b4"),
    "WEAPON_CLAYMORE": _t("gsuid.renderers.panel.text.62_23.1a1f46df"),
    "WEAPON_POLE": _t("gsuid.renderers.panel.text.63_19.5d4b74a8"),
    "WEAPON_CATALYST": _t("gsuid.renderers.panel.metrics.1053_22.4813ba67"),
    "WEAPON_BOW": _t("gsuid.renderers.panel.metrics.1055_24.a0ec11cd"),
}


def render_panel_refresh_text(data: Mapping[str, object]) -> str:
    player = _mapping(data.get("player"))
    lines = [_t("gsuid.renderers.panel.text.71_13.7d0f1eba"), f"UID: {_text(data.get('uid'))}"]
    _append_player(lines, player)
    lines.extend(
        [
            _t("gsuid.renderers.events.text.53_21.15097066", _source_label(data.get("source"))),
            _t("gsuid.renderers.panel.text.202_17.2e0aa7dd", _text(data.get("character_count"))),
            f"TTL: {_text(data.get('ttl'))}",
            _t("gsuid.renderers.panel.text.78_12.ea09f0ef", _text(data.get("cached_at"))),
        ]
    )
    failures = _sequence(data.get("failures"))
    if failures:
        lines.append(_t("gsuid.renderers.panel.text.83_21.e16780df"))
        for failure in failures:
            lines.append(f"  - {_text(failure)}")
    return _finish(lines)


def render_panel_list_text(data: Mapping[str, object]) -> str:
    lines = [_t("gsuid.renderers.panel.text.90_13.0fb25c4d"), f"UID: {_text(data.get('uid'))}"]
    _append_player(lines, _mapping(data.get("player")))
    _append_character_rows(lines, _sequence(data.get("characters")), count=data.get("count"))
    _append_cached_at(lines, data)
    return _finish(lines)


def render_panel_show_text(data: Mapping[str, object]) -> str:
    panel = _mapping(data.get("panel"))
    lines = [
        _t(
            "gsuid.renderers.panel.text.99_13.185d1143",
            _text(panel.get("name") or data.get("character")),
        )
    ]
    lines.append(f"UID: {_text(data.get('uid'))}")
    lines.append(
        _t(
            "gsuid.renderers.panel.text.102_8.c25d88de",
            _text(panel.get("level")),
            _text(panel.get("constellation")),
            _text(panel.get("friendship")),
        )
    )
    weapon = _mapping(panel.get("weapon"))
    _append_weapon(lines, weapon)
    lines.append(
        _t("gsuid.renderers.panel.text.109_17.dfd6b27d", _number_text(panel.get("artifact_score")))
    )
    _append_skill_levels(lines, _mapping(panel.get("skill_levels")))
    _append_fight_props(lines, _mapping(panel.get("fight_props")))
    _append_artifacts(lines, _sequence(panel.get("artifacts")), limit=5)
    _append_reference(lines, _mapping(data.get("reference")))
    overrides = _mapping(data.get("requested_overrides"))
    if overrides:
        lines.append(_t("gsuid.renderers.panel.text.116_21.c741835a"))
        for key, value in overrides.items():
            lines.append(f"  - {_override_label(key)}: {_text(value)}")
    _append_cached_at(lines, data)
    return _finish(lines)


def render_panel_compare_text(data: Mapping[str, object]) -> str:
    lines = [_t("gsuid.renderers.panel.text.124_13.0df7465d")]
    baseline = _mapping(data.get("baseline"))
    baseline_panel = _mapping(baseline.get("panel"))
    lines.append(_t("gsuid.renderers.panel.text.127_17.976d2ae2", _build_label(baseline)))
    lines.append(
        _t(
            "gsuid.renderers.panel.text.128_17.b8c4ec90",
            _number_text(baseline_panel.get("artifact_score")),
        )
    )
    builds = _sequence(data.get("builds"))
    if builds:
        lines.append("")
        lines.append(_t("gsuid.renderers.panel.text.132_21.d01fbc1c"))
        for build in builds:
            panel = _mapping(_mapping(build).get("panel"))
            lines.append(
                _t(
                    "gsuid.renderers.panel.text.136_16.067b6d80",
                    _build_label(_mapping(build)),
                    _number_text(panel.get("artifact_score")),
                )
            )
    deltas = _sequence(data.get("deltas"))
    if deltas:
        lines.append("")
        lines.append(_t("gsuid.renderers.panel.text.142_21.5e1bad82"))
        for delta in deltas:
            item = _mapping(delta)
            lines.append(
                _t(
                    "gsuid.renderers.panel.text.146_16.8723c0d1",
                    _text(item.get("character")),
                    _signed_number(item.get("artifact_score")),
                )
            )
            _append_fight_delta(lines, _mapping(item.get("fight_props")))
    return _finish(lines)


def render_panel_save_text(data: Mapping[str, object]) -> str:
    return _finish(
        [
            _t("gsuid.renderers.panel.text.156_12.cfadca9a"),
            f"UID: {_text(data.get('uid'))}",
            _t("gsuid.renderers.panel.text.158_12.df3b787c", _text(data.get("character"))),
            _t("gsuid.renderers.panel.text.159_12.b4ebd776", _text(data.get("name"))),
            _t(
                "gsuid.renderers.gacha.184_8.82609e71",
                _t("gsuid.common.saved") if data.get("saved") else _t("gsuid.common.not_saved"),
            ),
            _t("gsuid.renderers.gacha.188_21.1133624e", _text(data.get("path"))),
        ]
    )


def render_panel_artifacts_text(data: Mapping[str, object]) -> str:
    lines = [_t("gsuid.renderers.panel.text.167_13.ff913e8e"), f"UID: {_text(data.get('uid'))}"]
    lines.append(
        _t(
            "gsuid.renderers.panel.text.169_8.d0d34140",
            _text(data.get("page")),
            _text(data.get("total_pages")),
            _text(data.get("count")),
            _text(data.get("total_count")),
        )
    )
    artifacts = _sequence(data.get("artifacts"))
    if not artifacts:
        lines.extend(["", _t("gsuid.renderers.panel.text.174_26.a16c772f")])
        return _finish(lines)
    lines.append("")
    lines.append(_t("gsuid.renderers.panel.text.177_17.9818e2fa"))
    for artifact in artifacts:
        item = _mapping(artifact)
        lines.append(
            _t(
                "gsuid.renderers.panel.text.181_12.eaa3cc27",
                _text(item.get("character")),
                _slot_label(item.get("slot")),
                _text(item.get("name")),
                _text(item.get("level")),
                _stars(item.get("rank")),
                _number_text(item.get("score")),
            )
        )
        _append_artifact_detail(lines, item, indent="    ")
    return _finish(lines)


def render_panel_showcase_text(data: Mapping[str, object]) -> str:
    lines = [_t("gsuid.renderers.panel.text.192_13.660eb890"), f"UID: {_text(data.get('uid'))}"]
    _append_player(lines, _mapping(data.get("player")))
    _append_character_rows(lines, _sequence(data.get("showcase")), count=data.get("count"))
    _append_cached_at(lines, data)
    return _finish(lines)


def render_panel_graduation_text(data: Mapping[str, object]) -> str:
    lines = [_t("gsuid.renderers.panel.text.200_13.5a72a3df"), f"UID: {_text(data.get('uid'))}"]
    rows = _sequence(data.get("characters"))
    lines.append(_t("gsuid.renderers.panel.text.202_17.2e0aa7dd", _text(data.get("count"))))
    limitations = _sequence(data.get("source_limitations"))
    if limitations:
        lines.append(_t("gsuid.renderers.panel.text.205_21.03c89ca2"))
        for limitation in limitations:
            lines.append(f"  - {_text(limitation)}")
    if rows:
        lines.append("")
        lines.append(_t("gsuid.renderers.panel.text.248_17.ebc2e4bd"))
        for row in rows:
            item = _mapping(row)
            lines.append(
                _t(
                    "gsuid.renderers.panel.text.214_16.67de82fd",
                    _text(item.get("name")),
                    _text(item.get("level")),
                    _number_text(item.get("artifact_score")),
                    _nullable_number(item.get("graduation_score")),
                )
            )
    return _finish(lines)


def _append_player(lines: list[str], player: Mapping[str, object]) -> None:
    nickname = _text(player.get("nickname"))
    if nickname != "-":
        lines.append(_t("gsuid.renderers.panel.text.225_21.31880771", nickname))
    level = _text(player.get("level"))
    if level != "-":
        lines.append(_t("gsuid.renderers.panel.text.228_21.9655db21", level))
    world_level = _text(player.get("world_level"))
    if world_level != "-":
        lines.append(_t("gsuid.renderers.panel.text.231_21.dbde8c66", world_level))
    achievements = _text(player.get("achievements"))
    if achievements != "-":
        lines.append(_t("gsuid.renderers.panel.text.234_21.5ff84549", achievements))


def _append_character_rows(
    lines: list[str],
    rows: list[object],
    *,
    count: object,
) -> None:
    lines.append(_t("gsuid.renderers.panel.text.202_17.2e0aa7dd", _text(count)))
    if not rows:
        lines.extend(["", _t("gsuid.renderers.panel.text.245_26.61033763")])
        return
    lines.append("")
    lines.append(_t("gsuid.renderers.panel.text.248_17.ebc2e4bd"))
    for row in rows:
        item = _mapping(row)
        lines.append(
            _t(
                "gsuid.renderers.panel.text.252_12.a59a4d3b",
                _text(item.get("name")),
                _text(item.get("level")),
                _constellation_text(item.get("constellation")),
                _text(item.get("weapon")),
                _number_text(item.get("artifact_score")),
            )
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
        suffix.append(_t("gsuid.renderers.panel.image.1101_25.071fef7c", affix))
    lines.append(
        _t(
            "gsuid.renderers.panel.text.271_8.532970cf",
            _text(weapon.get("name")),
            _text(weapon.get("level")),
            _stars(weapon.get("rank")),
            "，" + "，".join(suffix) if suffix else "",
        )
    )
    stats = _sequence(weapon.get("stats"))
    if stats:
        lines.append(_t("gsuid.renderers.panel.text.279_21.6a26ede3"))
        for stat in stats[:2]:
            item = _mapping(stat)
            lines.append(f"  - {_stat_name(item)}: {_stat_text(item)}")
    effect = _text(weapon.get("effect"))
    if effect != "-":
        lines.append(_t("gsuid.renderers.panel.text.285_21.de4dace2"))
        for line in effect.splitlines():
            lines.append(f"  {line}")


def _append_skill_levels(lines: list[str], skill_levels: Mapping[str, object]) -> None:
    if not skill_levels:
        return
    values = [_text(value) for _key, value in skill_levels.items()]
    if len(values) > 3:
        values = [values[0], values[1], values[-1]]
    lines.append(_t("gsuid.renderers.panel.text.296_17.dca991c5", "/".join(values)))


def _append_fight_props(lines: list[str], props: Mapping[str, object]) -> None:
    selected = [
        ("max_hp", _t("gsuid.renderers.panel.metrics.357_7.575ca7a8")),
        ("max_atk", _t("gsuid.renderers.panel.image.88_25.ef28aed2")),
        ("max_def", _t("gsuid.renderers.panel.image.91_26.2557c107")),
        ("base_hp", _t("gsuid.renderers.panel.text.304_20.d1b0a1e5")),
        ("base_atk", _t("gsuid.renderers.panel.text.305_21.08b2cb62")),
        ("base_def", _t("gsuid.renderers.panel.text.306_21.547b82b5")),
        ("elemental_mastery", _t("gsuid.providers.akasha.66_4.af09dad1")),
        ("crit_rate", _t("gsuid.providers.akasha.70_4.33e0f20a")),
        ("crit_damage", _t("gsuid.providers.akasha.72_4.7c0dd18b")),
        ("energy_recharge", _t("gsuid.renderers.panel.text.310_28.fa9ecf1b")),
        ("pyro_bonus", _t("gsuid.renderers.panel.text.311_23.9192e854")),
        ("hydro_bonus", _t("gsuid.renderers.panel.text.312_24.f5923d74")),
        ("cryo_bonus", _t("gsuid.renderers.panel.text.313_23.1c3e26f7")),
        ("electro_bonus", _t("gsuid.renderers.panel.text.314_26.18a2bfe6")),
        ("anemo_bonus", _t("gsuid.renderers.panel.text.315_24.9fa7395e")),
        ("geo_bonus", _t("gsuid.renderers.panel.text.316_22.2a4b98ab")),
        ("dendro_bonus", _t("gsuid.renderers.panel.text.317_25.6846c48c")),
        ("physical_bonus", _t("gsuid.renderers.panel.text.318_27.ca6ed688")),
    ]
    available = [(key, label) for key, label in selected if key in props]
    if not available:
        return
    lines.append(_t("gsuid.renderers.panel.text.323_17.f14e455e"))
    for key, label in available:
        lines.append(f"  - {label}: {_stat_value(key, props.get(key))}")


def _append_fight_delta(lines: list[str], props: Mapping[str, object]) -> None:
    interesting = [
        ("base_hp", _t("gsuid.renderers.panel.text.304_20.d1b0a1e5")),
        ("base_atk", _t("gsuid.renderers.panel.text.305_21.08b2cb62")),
        ("base_def", _t("gsuid.renderers.panel.text.306_21.547b82b5")),
        ("elemental_mastery", _t("gsuid.providers.akasha.66_4.af09dad1")),
        ("crit_rate", _t("gsuid.providers.akasha.70_4.33e0f20a")),
        ("crit_damage", _t("gsuid.providers.akasha.72_4.7c0dd18b")),
        ("energy_recharge", _t("gsuid.renderers.panel.text.310_28.fa9ecf1b")),
        ("pyro_bonus", _t("gsuid.renderers.panel.text.311_23.9192e854")),
        ("hydro_bonus", _t("gsuid.renderers.panel.text.312_24.f5923d74")),
        ("cryo_bonus", _t("gsuid.renderers.panel.text.313_23.1c3e26f7")),
        ("electro_bonus", _t("gsuid.renderers.panel.text.314_26.18a2bfe6")),
        ("anemo_bonus", _t("gsuid.renderers.panel.text.315_24.9fa7395e")),
        ("geo_bonus", _t("gsuid.renderers.panel.text.316_22.2a4b98ab")),
        ("dendro_bonus", _t("gsuid.renderers.panel.text.317_25.6846c48c")),
        ("physical_bonus", _t("gsuid.renderers.panel.text.318_27.ca6ed688")),
    ]
    for key, label in interesting:
        if key in props:
            lines.append(f"    {label}: {_signed_number(props.get(key))}")


def _append_artifacts(lines: list[str], artifacts: list[object], *, limit: int) -> None:
    if not artifacts:
        return
    lines.append(_t("gsuid.renderers.panel.text.177_17.9818e2fa"))
    for artifact in artifacts[:limit]:
        item = _mapping(artifact)
        lines.append(
            _t(
                "gsuid.renderers.panel.text.358_12.26d3aebb",
                _slot_label(item.get("slot")),
                _text(item.get("name")),
                _text(item.get("level")),
                _stars(item.get("rank")),
                _number_text(item.get("score")),
            )
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
        lines.append(_t("gsuid.renderers.panel.text.374_21.1a190ef3", indent, set_name))
    main_stat = _mapping(artifact.get("main_stat"))
    if main_stat:
        lines.append(
            _t(
                "gsuid.renderers.panel.text.377_21.87dc72f1",
                indent,
                _stat_name(main_stat),
                _stat_text(main_stat),
            )
        )
    substats = [_mapping(item) for item in _sequence(artifact.get("substats"))]
    if substats:
        lines.append(_t("gsuid.renderers.panel.text.380_21.8c0ec9c1", indent))
        for substat in substats:
            lines.append(f"{indent}  - {_stat_name(substat)}: {_stat_text(substat)}")


def _append_reference(lines: list[str], reference: Mapping[str, object]) -> None:
    if not reference:
        return
    effective = _number_text(reference.get("effective_stat_count"))
    sequence = _text(reference.get("sequence_label"))
    percent = reference.get("graduation_percent")
    lines.append(_t("gsuid.renderers.panel.text.391_17.720a9385"))
    lines.append(_t("gsuid.renderers.panel.text.392_17.090fa1ce", effective))
    lines.append(
        _t(
            "gsuid.renderers.panel.text.393_17.50589d4a",
            sequence if sequence != "-" else _t("gsuid.common.matched_none"),
        )
    )
    percent_text = (
        _percent_text(percent)
        if percent not in (None, 0, 0.0)
        else _t("gsuid.renderers.panel.image.964_19.b5da4ade")
    )
    lines.append(_t("gsuid.renderers.panel.text.395_17.f72beb98", percent_text))
    rows = _sequence(reference.get("damage_rows"))
    if rows:
        lines.append(_t("gsuid.renderers.panel.text.398_21.53c3f87c"))
        for row in rows:
            item = _mapping(row)
            lines.append(
                _t(
                    "gsuid.renderers.panel.text.402_16.2e79c963",
                    _text(item.get("action")),
                    _rounded_number(item.get("crit")),
                    _rounded_number(item.get("avg")),
                    _rounded_number(item.get("normal")),
                )
            )


def _append_cached_at(lines: list[str], data: Mapping[str, object]) -> None:
    cached_at = _text(data.get("cached_at"))
    if cached_at != "-":
        lines.append(_t("gsuid.renderers.panel.text.78_12.ea09f0ef", cached_at))


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
        "EQUIP_BRACER": _t("gsuid.commands.panel.mys.317_8.5c8bb682"),
        "EQUIP_NECKLACE": _t("gsuid.commands.panel.mys.318_8.9eaf35fa"),
        "EQUIP_SHOES": _t("gsuid.commands.panel.mys.319_8.bc4a2cbb"),
        "EQUIP_RING": _t("gsuid.commands.panel.mys.320_8.c4347056"),
        "EQUIP_DRESS": _t("gsuid.commands.panel.mys.321_8.e5385dd2"),
    }.get(str(value), _text(value))


def _override_label(value: object) -> str:
    return {
        "constellation": _t("gsuid.commands.panel.impl.987_26.096ace91"),
        "weapon": _t("gsuid.commands.panel.impl.988_24.6f0f16e0"),
        "artifact_source_character": _t("gsuid.renderers.panel.text.480_37.87f0d3f6"),
    }.get(str(value), _text(value))


def _source_label(value: object) -> str:
    return {
        "enka": "Enka",
        "mys": _t("gsuid.renderers.panel.text.485_35.fc432ca2"),
        "enka+mys": _t("gsuid.renderers.panel.text.485_60.a540e3a7"),
        "auto": _t("gsuid.renderers.local_auth.288_20.4afad877"),
    }.get(str(value), _text(value))


def _constellation_text(value: object) -> str:
    return _t("gsuid.renderers.challenge.common.119_45.fd9e8859", _text(value))


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
        return _t("gsuid.renderers.panel.text.506_15.63595e95")
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
