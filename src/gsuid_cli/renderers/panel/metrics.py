from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from functools import lru_cache

from gsuid_cli.renderers.common import asset_path, int_value, text_value
from gsuid_cli.text import t as _t

DATA = asset_path("panel", "data")

SCORE_MAP = {
    _t("gsuid.providers.akasha.70_4.33e0f20a"): 2.0,
    _t("gsuid.providers.akasha.72_4.7c0dd18b"): 1.0,
    _t("gsuid.providers.akasha.66_4.af09dad1"): 0.25,
    _t("gsuid.providers.akasha.68_4.a7a24305"): 0.65,
    _t("gsuid.providers.akasha.54_4.9a1c9ca9"): 0.86,
    _t("gsuid.providers.akasha.51_4.f60501c6"): 1.0,
    _t("gsuid.renderers.panel.image.92_34.7ecee44b"): 0.7,
    _t("gsuid.renderers.panel.image.94_21.c269f206"): 0.014,
    _t("gsuid.renderers.panel.image.88_25.ef28aed2"): 0.12,
    _t("gsuid.renderers.panel.image.91_26.2557c107"): 0.18,
}
VALUE_MAP = {
    _t("gsuid.renderers.panel.image.88_25.ef28aed2"): 4.975,
    _t("gsuid.renderers.panel.image.94_21.c269f206"): 4.975,
    _t("gsuid.renderers.panel.image.91_26.2557c107"): 6.2,
    _t("gsuid.providers.akasha.66_4.af09dad1"): 19.75,
    _t("gsuid.providers.akasha.68_4.a7a24305"): 5.5,
    _t("gsuid.providers.akasha.70_4.33e0f20a"): 3.3,
    _t("gsuid.providers.akasha.72_4.7c0dd18b"): 6.6,
}
DEFAULT_ATTRS = [
    _t("gsuid.renderers.panel.image.88_25.ef28aed2"),
    _t("gsuid.providers.akasha.70_4.33e0f20a"),
    _t("gsuid.providers.akasha.72_4.7c0dd18b"),
]
PERCENT_ATTRS = {"dmgBonus", "addAtk", "addDef", "addHp"}
ELEMENT_DAMAGE_PROP = {
    "Anemo": "44",
    "Cryo": "46",
    "Dendro": "43",
    "Electro": "41",
    "Geo": "45",
    "Hydro": "42",
    "Pyro": "40",
}
CHANGE_LIST = {
    _t("gsuid.renderers.panel.metrics.44_4.cea7bd0a"),
    _t("gsuid.renderers.panel.metrics.45_4.c962e3f3"),
    _t("gsuid.renderers.panel.metrics.46_4.367ecafc"),
    _t("gsuid.renderers.panel.metrics.47_4.7303c1b0"),
    _t("gsuid.renderers.panel.metrics.48_4.f6c02c43"),
    _t("gsuid.renderers.panel.metrics.49_4.fb88c811"),
    _t("gsuid.renderers.panel.metrics.50_4.c2546e54"),
    _t("gsuid.renderers.panel.metrics.51_4.a6da15e1"),
}
FIXED_STAT_NAMES = {
    _t("gsuid.renderers.panel.image.88_25.ef28aed2"),
    _t("gsuid.renderers.panel.image.94_21.c269f206"),
    _t("gsuid.renderers.panel.image.91_26.2557c107"),
    _t("gsuid.providers.akasha.66_4.af09dad1"),
}
MAIN_SEQUENCE_SLOTS = ("EQUIP_SHOES", "EQUIP_RING", "EQUIP_DRESS")
ATTACK_TYPES = ("A", "B", "C", "E", "Q")
INITIAL_EFFECT_ATTRS = (
    "shieldBonus",
    "addDmg",
    "addHeal",
    "ignoreDef",
    "d",
    "g",
    "a",
)
BASE_VALUE_LIST = [
    8.6,
    9.3,
    10.0,
    10.6,
    11.3,
    12.3,
    13.3,
    14.4,
    15.7,
    17.1,
    18.6,
    20.3,
    22.2,
    24.3,
    26.9,
    29.5,
    32.2,
    34.9,
    37.6,
    40.3,
    43.1,
    45.9,
    48.6,
    51.4,
    54.2,
    56.6,
    59.1,
    61.5,
    64.9,
    68.2,
    71.3,
    74.5,
    77.7,
    80.9,
    84.6,
    88.3,
    92.0,
    95.9,
    99.8,
    103.7,
    107.7,
    112.1,
    116.8,
    121.1,
    128.0,
    134.3,
    140.8,
    147.5,
    154.5,
    161.8,
    168.4,
    175.3,
    182.2,
    189.3,
    199.3,
    208.2,
    217.2,
    226.5,
    236.3,
    246.4,
    256.8,
    269.6,
    282.8,
    296.3,
    312.2,
    325.7,
    339.8,
    353.9,
    368.3,
    382.8,
    397.4,
    412.3,
    425.6,
    438.9,
    457.1,
    473.4,
    489.7,
    505.6,
    522.4,
    538.7,
    555.0,
    571.5,
    588.2,
    605.1,
    626.9,
    644.5,
    622.7,
    681.7,
    702.6,
    723.4,
    723.4,
    723.4,
    723.4,
    723.4,
    780.734,
    780.734,
    780.734,
    780.734,
    780.734,
    837.4046,
]


def panel_reference_metrics(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> dict[str, object]:
    artifact_scores: dict[str, float] = {}
    total = 0.0
    for raw_artifact, normalized in _artifact_pairs(avatar, panel):
        score = artifact_effective_score(raw_artifact, normalized, avatar, panel)
        item_id = str(normalized.get("item_id") or raw_artifact.get("itemId") or "")
        if item_id:
            artifact_scores[item_id] = score
        total += score

    damage_rows = _damage_rows(avatar, panel)
    standard = _matched_standard(panel)
    return {
        "artifact_effective_scores": artifact_scores,
        "effective_stat_count": round(total, 2),
        "sequence_label": _sequence_label(standard),
        "graduation_percent": _graduation_percent(panel, damage_rows, standard),
        "damage_rows": damage_rows,
    }


def artifact_effective_score(
    raw_artifact: Mapping[str, object],
    normalized: Mapping[str, object],
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> float:
    char_name = _avatar_name(avatar, panel)
    attrs = _string_list(_map("value_attr.json").get(char_name)) or DEFAULT_ATTRS
    raw = _fight_props(avatar, panel)
    base_hp = _raw_float(raw, "1", _raw_float(raw, "base_hp"))
    base_atk = _raw_float(raw, "4", _raw_float(raw, "base_atk"))
    base_def = _raw_float(raw, "7", _raw_float(raw, "base_def"))
    score = 0.0
    for substat in _artifact_substats(raw_artifact, normalized):
        name = _stat_name(substat)
        value = _float_value(substat.get("statValue"))
        score += _substat_effective_value(name, value, base_hp, base_atk, base_def, attrs)
    return round(score, 2)


def _substat_effective_value(
    name: str,
    value: float,
    base_hp: float,
    base_atk: float,
    base_def: float,
    attrs: Sequence[str],
) -> float:
    if name in attrs and name in {
        _t("gsuid.renderers.panel.image.94_21.c269f206"),
        _t("gsuid.renderers.panel.image.91_26.2557c107"),
        _t("gsuid.renderers.panel.image.88_25.ef28aed2"),
    }:
        base = {
            _t("gsuid.renderers.panel.image.94_21.c269f206"): base_hp,
            _t("gsuid.renderers.panel.image.91_26.2557c107"): base_def,
            _t("gsuid.renderers.panel.image.88_25.ef28aed2"): base_atk,
        }[name]
        if base <= 0:
            return 0.0
        return round(((value / base) * 100) / VALUE_MAP[name], 2)
    if name in {
        _t("gsuid.providers.akasha.54_4.9a1c9ca9"),
        _t("gsuid.renderers.panel.image.92_34.7ecee44b"),
        _t("gsuid.providers.akasha.51_4.f60501c6"),
    }:
        preferred = name.replace(_t("gsuid.renderers.panel.image.1902_24.4ce634c4"), "")
        return round(value / VALUE_MAP[preferred], 2) if preferred in attrs else 0.0
    return round(value / VALUE_MAP[name], 2) if name in attrs and name in VALUE_MAP else 0.0


def _damage_rows(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> list[dict[str, object]]:
    char_name = _avatar_name(avatar, panel)
    action_map = _map("char_action.json").get(char_name)
    if not isinstance(action_map, Mapping):
        return []
    fight_prop = _effective_fight_prop(avatar, panel)
    enemy = _enemy_state()
    _apply_enemy_debuffs(enemy, _buff_effects(avatar, panel, "fight"))
    rows: list[dict[str, object]] = []
    for action_name, action in action_map.items():
        if not isinstance(action_name, str) or not isinstance(action, Mapping):
            continue
        normal, avg, crit = _action_damage(action_name, action, avatar, panel, fight_prop, enemy)
        rows.append({"action": action_name, "normal": normal, "avg": avg, "crit": crit})
    return rows


def _action_damage(
    action_name: str,
    action: Mapping[str, object],
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
    fight_prop: Mapping[str, object],
    enemy: dict[str, object],
) -> tuple[float, float, float]:
    attack_type = _attack_type(action_name, _avatar_name(avatar, panel))
    sp = _sp_bonus(fight_prop, action_name)
    real_prop = _real_prop_for_action(fight_prop, action_name, attack_type)
    if (
        _t("gsuid.renderers.panel.metrics.331_7.b6adc0f5") in action_name
        or _t("gsuid.renderers.panel.metrics.322_7.3ba2689a") in action_name
        or _t("gsuid.renderers.panel.metrics.266_11.d91d1ab7") in action_name
        or _t("gsuid.renderers.panel.metrics.267_11.2fc49f94") in action_name
    ):
        return _transform_damage(action_name, avatar, panel, attack_type, real_prop, enemy)
    if (
        _t("gsuid.renderers.panel.metrics.270_7.7d81885c") in action_name
        or _t("gsuid.renderers.panel.metrics.270_34.ffc78509") in action_name
    ):
        normal = (
            _base_area(action_name, action, avatar, panel, attack_type, real_prop, sp)
            + _prefixed_prop(real_prop, attack_type, "addHeal")
        ) * (1 + _float_value(real_prop.get("healBonus")))
        return normal, normal, 0.0
    if _t("gsuid.renderers.panel.metrics.276_7.50f66b03") in action_name:
        normal = _base_area(action_name, action, avatar, panel, attack_type, real_prop, sp) * (
            1 + _float_value(real_prop.get("shieldBonus"))
        )
        return normal, 0.0, 0.0

    element = _damage_type(action_name, attack_type, avatar, panel)
    base = _base_area(action_name, action, avatar, panel, attack_type, real_prop, sp)
    base += _quicken_bonus(action_name, avatar, panel, attack_type, real_prop)
    base *= 1 + _float_value(real_prop.get("extraBonus"))
    base_area_plus = _prefixed_prop(real_prop, attack_type, "baseArea")
    if base_area_plus != 1:
        base *= base_area_plus - 1
    normal = (
        base
        * (1 + _damage_bonus(element, attack_type, real_prop) + sp["dmgBonus"])
        * _reaction_multiplier(action_name, avatar, panel, attack_type, real_prop)
        * _damage_proof(
            enemy,
            element,
            _float_value(real_prop.get(f"{attack_type}_d")),
            _float_value(real_prop.get(f"{attack_type}_ignoreDef")),
        )
    )
    crit_rate = _prefixed_prop(real_prop, attack_type, "critRate")
    crit_damage = _prefixed_prop(real_prop, attack_type, "critDmg")
    crit = normal * (1 + crit_damage)
    if crit_rate < 0:
        avg = normal
    elif crit_rate > 1:
        avg = crit
    else:
        avg = crit * crit_rate + normal * (1 - crit_rate)
    return normal, avg, crit


def _transform_damage(
    action_name: str,
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
    attack_type: str,
    real_prop: Mapping[str, object],
    enemy: Mapping[str, object],
) -> tuple[float, float, float]:
    level = max(min(_avatar_level(avatar, panel), len(BASE_VALUE_LIST)), 1)
    em = _prefixed_prop(real_prop, attack_type, "elementalMastery")
    if _t("gsuid.renderers.panel.metrics.322_7.3ba2689a") in action_name:
        base_time = (
            6
            if _t("gsuid.renderers.panel.metrics.323_25.e3b4d04b") in action_name
            or _t("gsuid.renderers.panel.metrics.323_55.94068a27") in action_name
            else 4
        )
        normal = (
            BASE_VALUE_LIST[level - 1]
            * base_time
            * (1 + (16.0 * em) / (em + 2000) + _float_value(real_prop.get("a")))
            * _resist_proof(enemy, "Dendro")
        )
        return normal, normal * 1.2, normal * 2
    if _t("gsuid.renderers.panel.metrics.331_7.b6adc0f5") in action_name:
        normal = (
            BASE_VALUE_LIST[level - 1]
            * 1.2
            * (1 + (16.0 * em) / (em + 2000) + _float_value(real_prop.get("a")))
            * (1 + _float_value(real_prop.get("g")) / 100)
            * _resist_proof(enemy, "Anemo")
        )
        return normal, 0.0, 0.0
    return 0.0, 0.0, 0.0


def _base_area(
    action_name: str,
    action: Mapping[str, object],
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
    attack_type: str,
    real_prop: Mapping[str, object],
    sp: Mapping[str, float],
) -> float:
    sp_base = _sp_base_area(action_name, action, avatar, panel, attack_type, real_prop, sp)
    if sp_base is not None:
        return sp_base
    percent, fixed = _power_value(action, attack_type, real_prop)
    action_type = text_value(action.get("type")) or ""
    if _t("gsuid.renderers.panel.metrics.357_7.575ca7a8") in action_type:
        prop = _prefixed_prop(real_prop, attack_type, "hp")
    elif _t("gsuid.renderers.panel.metrics.359_9.2029e612") in action_type:
        prop = _prefixed_prop(real_prop, attack_type, "def")
    else:
        prop = _prefixed_prop(real_prop, attack_type, "atk")
    return prop * percent + fixed + sp["addDmg"]


def _sp_base_area(
    action_name: str,
    action: Mapping[str, object],
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
    attack_type: str,
    real_prop: Mapping[str, object],
    sp: Mapping[str, float],
) -> float | None:
    char_name = _avatar_name(avatar, panel)
    if not (
        (
            _t("gsuid.renderers.panel.metrics.377_9.3b163307") in action_name
            or _t("gsuid.renderers.panel.metrics.377_42.57d3e726") in action_name
        )
        or (
            char_name == _t("gsuid.renderers.panel.metrics.378_25.8e5d5a05")
            and action_name.startswith("E")
        )
    ):
        return None
    values = action.get("value")
    if not isinstance(values, list) or not values:
        return 0.0
    level = int_value(real_prop.get(f"{attack_type}_skill_level"), 1)
    power = str(values[min(max(level, 1), len(values)) - 1])
    power_parts = [float(part.replace("%", "")) / 100 for part in power.split("+")]
    if len(power_parts) < 2:
        return None
    plus = (
        _float_value(action.get("plus"), 1.0)
        + _prefixed_prop(real_prop, attack_type, "powerPlus")
        - 1
    )
    atk = _float_value(real_prop.get("E_atk")) + sp["attack"]
    em = _prefixed_prop(real_prop, attack_type, "elementalMastery")
    return (power_parts[0] * atk + power_parts[1] * em) * plus + sp["addDmg"]


def _power_value(
    action: Mapping[str, object],
    attack_type: str,
    real_prop: Mapping[str, object],
) -> tuple[float, float]:
    values = action.get("value")
    if not isinstance(values, list) or not values:
        return 0.0, 0.0
    level = int_value(real_prop.get(f"{attack_type}_skill_level"), 1)
    power = str(values[min(max(level, 1), len(values)) - 1])
    plus = (
        _float_value(action.get("plus"), 1.0)
        + _prefixed_prop(real_prop, attack_type, "powerPlus")
        - 1
    )
    return _p2v(power, plus)


def _p2v(power: str, plus: float) -> tuple[float, float]:
    if "+" in power:
        first, second = power.split("+", 1)
        percent = (float(first.replace("%", "")) / 100) * plus if "%" in first else 0.0
        if "%" in second:
            return percent + (float(second.replace("%", "")) / 100) * plus, 0.0
        return percent, float(second)
    if "%" in power:
        return float(power.replace("%", "")) / 100 * plus, 0.0
    return 0.0, float(power)


def _quicken_bonus(
    action_name: str,
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
    attack_type: str,
    real_prop: Mapping[str, object],
) -> float:
    if (
        _t("gsuid.renderers.panel.metrics.436_7.50c40fe7") not in action_name
        and _t("gsuid.renderers.panel.metrics.436_42.c0605a74") not in action_name
    ):
        return 0.0
    level = max(min(_avatar_level(avatar, panel), len(BASE_VALUE_LIST)), 1)
    k = 2.3 if _t("gsuid.renderers.panel.metrics.436_7.50c40fe7") in action_name else 2.5
    em = _prefixed_prop(real_prop, attack_type, "elementalMastery")
    times = 1.0
    if "*" in action_name:
        try:
            times = float(action_name.split("*")[-1].replace(")", ""))
        except ValueError:
            times = 1.0
    return k * BASE_VALUE_LIST[level - 1] * (1 + (5 * em) / (em + 1200)) * times


def _reaction_multiplier(
    action_name: str,
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
    attack_type: str,
    real_prop: Mapping[str, object],
) -> float:
    if (
        _t("gsuid.renderers.panel.metrics.460_7.89fd5c6c") not in action_name
        and _t("gsuid.renderers.panel.metrics.457_39.465f09cb") not in action_name
    ):
        return 1.0
    element = _avatar_element(avatar, panel)
    if _t("gsuid.renderers.panel.metrics.460_7.89fd5c6c") in action_name:
        base = 1.5 if element == "Pyro" else 2.0
    else:
        base = 2.0 if element == "Pyro" else 1.5
    em = _prefixed_prop(real_prop, attack_type, "elementalMastery")
    return base * (1 + (2.78 * em) / (em + 1400) + _float_value(real_prop.get("a")))


def _matched_standard(panel: Mapping[str, object]) -> Mapping[str, object] | None:
    char_name = text_value(panel.get("name")) or ""
    standards = _map("dmg_map.json").get(char_name)
    if not isinstance(standards, list) or not standards:
        return None
    seq = _panel_sequence(panel)
    weapon_match = None
    cup_match = None
    for item in standards:
        if not isinstance(item, Mapping):
            continue
        standard_seq = text_value(item.get("seq")) or ""
        if standard_seq == seq:
            return item
        if len(seq) >= 2 and len(standard_seq) >= 2:
            if standard_seq[:2] == seq[:2] and weapon_match is None:
                weapon_match = item
            if standard_seq[-2] == seq[-2] and cup_match is None:
                cup_match = item
    return (
        weapon_match
        or cup_match
        or next((item for item in standards if isinstance(item, Mapping)), None)
    )


def _panel_sequence(panel: Mapping[str, object]) -> str:
    weapon = panel.get("weapon")
    weapon_name = text_value(weapon.get("name")) if isinstance(weapon, Mapping) else ""
    set_type, set_name = _equip_set(panel)
    if set_type in {"2", ""}:
        return ""
    return f"{weapon_name}|{set_name}|{_main_stat_sequence(panel)}"


def _equip_set(panel: Mapping[str, object]) -> tuple[str, str]:
    artifacts = panel.get("artifacts")
    if not isinstance(artifacts, list):
        return "", ""
    counts: dict[str, int] = {}
    order: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            continue
        set_name = text_value(artifact.get("set_name"))
        if not set_name:
            continue
        if set_name not in counts:
            order.append(set_name)
        counts[set_name] = counts.get(set_name, 0) + 1
    for set_name in order:
        if counts[set_name] >= 4:
            return "4", set_name
    two_piece = [set_name for set_name in order if counts[set_name] >= 2]
    return "2" * len(two_piece), "|".join(two_piece)


def _main_stat_sequence(panel: Mapping[str, object]) -> str:
    artifacts = panel.get("artifacts")
    if not isinstance(artifacts, list):
        return ""
    by_slot = {
        str(artifact.get("slot")): artifact
        for artifact in artifacts
        if isinstance(artifact, Mapping)
    }
    text = ""
    for slot in MAIN_SEQUENCE_SLOTS:
        artifact = by_slot.get(slot)
        main_stat = artifact.get("main_stat") if isinstance(artifact, Mapping) else None
        if isinstance(main_stat, Mapping):
            text += _first_main(_stat_name(main_stat))
    return text


def _first_main(name: str) -> str:
    if not name:
        return ""
    if _t("gsuid.renderers.panel.image.1371_17.bf42cc55") in name:
        return name[0]
    if _t("gsuid.renderers.panel.image.1902_49.74f529b6") in name and len(name) >= 3:
        return name[2]
    if _t("gsuid.renderers.panel.image.1902_24.4ce634c4") in name:
        return (
            _t("gsuid.renderers.panel.metrics.551_15.3eb31f88")
            if _t("gsuid.renderers.panel.image.94_21.c269f206") in name
            else name[3:4]
        )
    return name[0]


def _sequence_label(standard: Mapping[str, object] | None) -> str:
    if standard is None:
        return _t("gsuid.renderers.panel.image.1413_53.cd8c79d5")
    seq = text_value(standard.get("seq")) or ""
    if not seq:
        return _t("gsuid.renderers.panel.image.1413_53.cd8c79d5")
    return "|".join(part[:2] for part in seq.split("|")) + seq[-1]


def _graduation_percent(
    panel: Mapping[str, object],
    rows: Sequence[Mapping[str, object]],
    standard: Mapping[str, object] | None,
) -> float | None:
    if standard is None:
        return None
    skill = text_value(standard.get("skill")) or ""
    std_value = _float_value(standard.get("value"))
    if not skill or std_value == 0:
        return None
    if skill == "atk":
        value = _fight_prop_display(panel, "atk")
    elif skill == "def":
        value = _fight_prop_display(panel, "def")
    else:
        row = next((item for item in rows if item.get("action") == skill), None)
        if not isinstance(row, Mapping):
            return None
        value = (
            _float_value(row.get("normal"))
            if _float_value(row.get("crit")) == 0
            else _float_value(row.get("avg"))
        )
    char_name = text_value(panel.get("name")) or ""
    if char_name == _t("gsuid.renderers.panel.metrics.589_20.b0d83f63"):
        std_value *= 3
    elif char_name == _t("gsuid.renderers.panel.metrics.45_4.c962e3f3"):
        std_value *= 2
    return round((value / std_value) * 100, 2)


def _fight_prop_display(panel: Mapping[str, object], key: str) -> float:
    props = panel.get("fight_props")
    if isinstance(props, Mapping):
        return _float_value(props.get(key))
    return 0.0


def _effective_fight_prop(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> dict[str, object]:
    prop = _base_fight_prop(avatar, panel)
    prop.update(
        {f"{key}_skill_level": value for key, value in _skill_levels(avatar, panel).items()}
    )
    prop = _apply_effects(prop, [], avatar, panel)
    prop = _apply_effects(prop, _buff_effects(avatar, panel, "fight"), avatar, panel)
    return prop


def _base_fight_prop(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> dict[str, object]:
    raw = _fight_props(avatar, panel)
    element = _avatar_element(avatar, panel)
    hp = _raw_float(raw, "2000")
    atk = _raw_float(raw, "2001")
    defense = _raw_float(raw, "2002")
    base_hp = _raw_float(raw, "1")
    base_atk = _raw_float(raw, "4")
    base_def = _raw_float(raw, "7")
    return {
        "hp": hp,
        "baseHp": base_hp,
        "addHp": hp - base_hp,
        "exHp": 0.0,
        "atk": atk,
        "baseAtk": base_atk,
        "addAtk": atk - base_atk,
        "exAtk": 0.0,
        "def": defense,
        "baseDef": base_def,
        "addDef": defense - base_def,
        "exDef": 0.0,
        "elementalMastery": _raw_float(raw, "28"),
        "critRate": _raw_float(raw, "20"),
        "critDmg": _raw_float(raw, "22"),
        "energyRecharge": _raw_float(raw, "23"),
        "healBonus": _raw_float(raw, "26"),
        "healedBonus": _raw_float(raw, "27"),
        "physicalDmgSub": _raw_float(raw, "29"),
        "physicalDmgBonus": _raw_float(raw, "30"),
        "dmgBonus": _raw_float(raw, ELEMENT_DAMAGE_PROP.get(element, "")),
    }


def _apply_effects(
    prop: Mapping[str, object],
    effects: Sequence[str],
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> dict[str, object]:
    result = dict(prop)
    if "A_d" not in result:
        for attr in INITIAL_EFFECT_ATTRS:
            result[attr] = 0.0
        result.update(
            {
                "k": 1.0,
                "sp": [],
                "baseArea": 1.0,
                "powerPlus": 1.0,
                "extraBonus": 0.0,
                "moonDmgBonus": 0.0,
                "moonExDmgBonus": 0.0,
            }
        )
        if _float_value(result.get("baseHp")) + _float_value(result.get("addHp")) == _float_value(
            result.get("hp")
        ):
            result["exHp"] = result["addHp"]
            result["exAtk"] = result["addAtk"]
            result["exDef"] = result["addDef"]
            result["addHp"] = 0.0
            result["addAtk"] = 0.0
            result["addDef"] = 0.0
        for key, value in list(result.items()):
            for prefix in ATTACK_TYPES:
                result[f"{prefix}_{key}"] = value
        _set_attack_damage_bonuses(result, avatar, panel)

    base_effects: list[tuple[str, str, float, str]] = []
    for effect in _split_effects(effects):
        if "Resist" in effect:
            continue
        effect_limit = ""
        if ":" in effect:
            effect_limit, effect = effect.split(":", 1)
        if "+" not in effect:
            continue
        effect_attr, effect_value = effect.split("+", 1)
        parsed = _parse_effect_value(result, effect_attr, effect_value, avatar, panel)
        if parsed is None:
            continue
        effect_attr, value, effect_base, base_check = parsed
        if base_check and effect_base in {"hp", "atk", "def"}:
            base_effects.append((effect_limit, effect_attr, value, effect_base))
            continue
        _apply_effect_value(result, effect_limit, effect_attr, value)

    result = _get_base_values(result)
    for effect_limit, effect_attr, value, effect_base in base_effects:
        _apply_effect_value(
            result,
            effect_limit,
            effect_attr,
            _float_value(result.get(effect_base)) * value,
        )
    return _get_base_values(result)


def _set_attack_damage_bonuses(
    prop: dict[str, object],
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> None:
    char_name = _avatar_name(avatar, panel)
    weapon_type = str(_map("avatarName2Weapon_mapping_6.6.0.json").get(char_name) or "")
    for prefix in ATTACK_TYPES:
        if (
            weapon_type == _t("gsuid.renderers.panel.metrics.1053_22.4813ba67")
            or char_name in CHANGE_LIST
        ):
            prop[f"{prefix}_dmgBonus"] = prop["dmgBonus"]
        elif weapon_type == _t("gsuid.renderers.panel.metrics.1055_24.a0ec11cd"):
            prop[f"{prefix}_dmgBonus"] = (
                prop["physicalDmgBonus"] if prefix in {"A", "C"} else prop["dmgBonus"]
            )
        else:
            prop[f"{prefix}_dmgBonus"] = (
                prop["physicalDmgBonus"] if prefix in {"A", "B", "C"} else prop["dmgBonus"]
            )


def _parse_effect_value(
    prop: Mapping[str, object],
    effect_attr: str,
    raw_value: str,
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> tuple[str, float, str, bool] | None:
    if effect_attr == "extraDmg":
        return None
    effect_max = 9999999.0
    effect_base = ""
    p_count = raw_value.count("%")
    base_check = True
    if p_count >= 2:
        raw_max, raw_value, effect_base = raw_value.split("%", 2)
        effect_max = float(raw_max) / 100
    elif p_count == 1:
        raw_value, effect_base = raw_value.split("%", 1)
    else:
        base_check = False

    if effect_attr not in {"exHp", "exAtk", "exDef", "elementalMastery"}:
        value = float(raw_value) / 100
    elif effect_base in {"hp", "elementalMastery", "def"}:
        value = float(raw_value) / 100
    else:
        value = float(raw_value)

    if base_check and effect_base not in {"hp", "atk", "def"}:
        base_value = _effect_base_value(prop, effect_attr, effect_base, avatar, panel)
        value *= base_value
    if value >= effect_max:
        value = effect_max

    if "DmgBonus" in effect_attr:
        char_element = _avatar_element(avatar, panel)
        if effect_attr.replace("DmgBonus", "") == char_element:
            effect_attr = "dmgBonus"
        elif effect_attr != "physicalDmgBonus":
            # Match GenshinUID's convention: generic damage bonuses use lowercase
            # dmgBonus, while uppercase DmgBonus entries are element-prefixed.
            return None
    return effect_attr, value, effect_base, base_check


def _effect_base_value(
    prop: Mapping[str, object],
    effect_attr: str,
    effect_base: str,
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> float:
    if effect_base == "energyRecharge":
        value = _float_value(prop.get(effect_base))
        return value - 1 if effect_attr in PERCENT_ATTRS else (value - 1) / 100
    if effect_base == "energyrecharge":
        value = _float_value(prop.get("energyRecharge"))
        return value if effect_attr in PERCENT_ATTRS else value / 100
    if effect_base == "elementalMastery":
        value = _float_value(prop.get(effect_base))
        if (
            _avatar_name(avatar, panel) == _t("gsuid.renderers.panel.metrics.798_42.e4a3fbc3")
            and effect_attr == "dmgBonus"
        ):
            return (value - 200) / 100
        return value
    return _float_value(prop.get(effect_base))


def _apply_effect_value(
    prop: dict[str, object],
    effect_limit: str,
    effect_attr: str,
    value: float,
) -> None:
    if effect_limit:
        if (
            _t("gsuid.renderers.panel.metrics.811_11.d274eee8")
            <= effect_limit[-1]
            <= _t("gsuid.renderers.panel.metrics.811_43.5e62e292")
        ):
            sp = prop.get("sp")
            if isinstance(sp, list):
                sp.append(
                    {
                        "effect_name": effect_limit,
                        "effect_attr": effect_attr,
                        "effect_value": value,
                    }
                )
            return
        for prefix in effect_limit:
            key = f"{prefix}_{effect_attr}"
            prop[key] = _float_value(prop.get(key)) + value
        return
    if effect_attr not in {"a", "addDmg"}:
        for prefix in ATTACK_TYPES:
            key = f"{prefix}_{effect_attr}"
            prop[key] = _float_value(prop.get(key)) + value
    prop[effect_attr] = _float_value(prop.get(effect_attr)) + value


def _get_base_values(prop: dict[str, object]) -> dict[str, object]:
    prop["hp"] = (_float_value(prop.get("addHp")) + 1) * _float_value(
        prop.get("baseHp")
    ) + _float_value(prop.get("exHp"))
    prop["atk"] = (_float_value(prop.get("addAtk")) + 1) * _float_value(
        prop.get("baseAtk")
    ) + _float_value(prop.get("exAtk"))
    prop["def"] = (_float_value(prop.get("addDef")) + 1) * _float_value(
        prop.get("baseDef")
    ) + _float_value(prop.get("exDef"))
    for prefix in ATTACK_TYPES:
        for attr in ("hp", "atk", "def"):
            attr_title = attr[0].upper() + attr[1:]
            prop[f"{prefix}_{attr}"] = (
                _float_value(prop.get(f"{prefix}_add{attr_title}")) + 1
            ) * _float_value(prop.get(f"base{attr_title}")) + _float_value(
                prop.get(f"ex{attr_title}")
            )
    return prop


def _real_prop_for_action(
    fight_prop: Mapping[str, object],
    action_name: str,
    attack_type: str,
) -> Mapping[str, object]:
    _ = action_name, attack_type
    return fight_prop


def _sp_bonus(prop: Mapping[str, object], action_name: str) -> dict[str, float]:
    bonus = {"dmgBonus": 0.0, "addDmg": 0.0, "attack": 0.0}
    sp = prop.get("sp")
    if not isinstance(sp, list):
        return bonus
    for item in sp:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("effect_name") or "") not in action_name:
            continue
        attr = str(item.get("effect_attr") or "")
        value = _float_value(item.get("effect_value"))
        if attr == "dmgBonus":
            bonus["dmgBonus"] += value
        elif attr == "addDmg":
            bonus["addDmg"] += value
        else:
            bonus["attack"] += value
    return bonus


def _prefixed_prop(prop: Mapping[str, object], attack_type: str, attr: str) -> float:
    return _float_value(prop.get(f"{attack_type}_{attr}"), _float_value(prop.get(attr)))


def _buff_effects(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
    kind: str,
) -> list[str]:
    effects: list[str] = []
    char_name = _avatar_name(avatar, panel)
    weapon_name = _weapon_name(panel)
    affix = _weapon_affix(avatar)
    weapon_effect = _nested_effect(
        "weapon_effect.json", weapon_name, "fight", f"{kind}_effect", str(affix)
    )
    if weapon_effect is not None:
        effects.append(weapon_effect)
    effects.extend(_artifact_set_effects(panel, kind))
    effects.extend(_character_effects(avatar, panel, kind, char_name))
    return effects


def _artifact_set_effects(panel: Mapping[str, object], kind: str) -> list[str]:
    effects: list[str] = []
    set_type, set_name = _equip_set(panel)
    if set_type == "4":
        for piece in ("2", "4"):
            effect = _nested_effect("artifact_effect.json", set_name, f"{kind}_effect", piece)
            if effect is not None:
                effects.append(effect)
    elif set_type == "2":
        effect = _nested_effect("artifact_effect.json", set_name, f"{kind}_effect", "2")
        if effect is not None:
            effects.append(effect)
    elif set_type == "22":
        names = set_name.split("|")
        for name in names:
            effect = _nested_effect("artifact_effect.json", name, f"{kind}_effect", "2")
            if effect is not None:
                effects.append(effect)
    return effects


def _character_effects(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
    kind: str,
    char_name: str,
) -> list[str]:
    effects: list[str] = []
    effect_map = _map("char_effect.json").get(char_name)
    if not isinstance(effect_map, Mapping):
        return effects
    main = "fight" if kind == "group" else kind
    main_map = effect_map.get(main)
    if not isinstance(main_map, Mapping):
        return effects
    talent_count = (
        len(avatar.get("talentIdList")) if isinstance(avatar.get("talentIdList"), list) else 0
    )
    talent_effects = main_map.get(f"{kind}_talent")
    if isinstance(talent_effects, Mapping):
        for key, effect in talent_effects.items():
            if talent_count >= int_value(key):
                effects.append(str(effect))
    skill_effects = main_map.get(f"{kind}_skill")
    if isinstance(skill_effects, Mapping):
        level = _avatar_level(avatar, panel)
        for key, effect in skill_effects.items():
            if level >= int_value(key):
                effects.append(str(effect))
    return effects


def _split_effects(effects: Sequence[str]) -> list[str]:
    result: list[str] = []
    for effect in effects:
        for item in str(effect).split(";"):
            if item:
                result.append(item)
    return result


def _enemy_state() -> dict[str, object]:
    return {
        "PhysicalResist": 0.1,
        "AnemoResist": 0.1,
        "CryoResist": 0.1,
        "DendroResist": 0.1,
        "ElectroResist": 0.1,
        "GeoResist": 0.1,
        "HydroResist": 0.1,
        "PyroResist": 0.1,
    }


def _apply_enemy_debuffs(enemy: dict[str, object], effects: Sequence[str]) -> None:
    for effect in _split_effects(effects):
        if "Resist" not in effect or "+" not in effect:
            continue
        name, raw_value = effect.split("+", 1)
        value = _float_value(raw_value) / 100
        if name != "Resist":
            # GenshinUID's single-character panel path has no tracked enemy aura,
            # so the generic "Resist" shorthand has no target here.
            enemy[name] = _float_value(enemy.get(name), 0.1) + value


def _nested_effect(filename: str, *keys: str) -> str | None:
    current: object = _map(filename)
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return str(current) if current is not None else None


def _weapon_name(panel: Mapping[str, object]) -> str:
    weapon = panel.get("weapon")
    return text_value(weapon.get("name")) if isinstance(weapon, Mapping) else ""


def _weapon_affix(avatar: Mapping[str, object]) -> int:
    for equip in _equip_list(avatar):
        flat = _flat(equip)
        if flat.get("itemType") == "ITEM_WEAPON" or isinstance(equip.get("weapon"), Mapping):
            raw_weapon = equip.get("weapon")
            if isinstance(raw_weapon, Mapping):
                affix_map = raw_weapon.get("affixMap")
                if isinstance(affix_map, Mapping) and affix_map:
                    return min(max(int_value(next(iter(affix_map.values()))) + 1, 1), 5)
    return 1


def _equip_list(avatar: Mapping[str, object]) -> list[Mapping[str, object]]:
    equips = avatar.get("equipList")
    return (
        [item for item in equips if isinstance(item, Mapping)] if isinstance(equips, list) else []
    )


def _attack_type(action_name: str, char_name: str) -> str:
    attack_type = action_name[:1]
    if char_name == _t("gsuid.renderers.panel.metrics.1028_20.bb768ff8"):
        return attack_type
    if (
        _t("gsuid.renderers.panel.metrics.1030_7.23d356e2") in action_name
        or _t("gsuid.renderers.panel.metrics.1030_34.d96b0d32") in action_name
    ):
        return "B"
    if any(
        token in action_name
        for token in (
            _t("gsuid.renderers.panel.metrics.1032_46.29f46ceb"),
            _t("gsuid.renderers.panel.metrics.1032_59.61ddee72"),
            _t("gsuid.renderers.panel.metrics.1032_72.13915bf4"),
            _t("gsuid.renderers.panel.metrics.1032_88.2a0a5f81"),
            _t("gsuid.renderers.panel.metrics.1032_101.b415fa98"),
        )
    ):
        return "B"
    if _t("gsuid.renderers.panel.metrics.1034_7.4bb42b5a") in action_name:
        return "C"
    if (
        _t("gsuid.renderers.panel.metrics.1036_7.c865b5b0") in action_name
        and _t("gsuid.renderers.panel.metrics.1036_32.69ace645") in action_name
    ):
        return "A"
    if _t("gsuid.renderers.panel.metrics.1038_7.990b4459") in action_name:
        return "A"
    return attack_type


def _damage_type(
    action_name: str,
    attack_type: str,
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> str:
    char_name = _avatar_name(avatar, panel)
    element = _avatar_element(avatar, panel)
    weapon_type = str(_map("avatarName2Weapon_mapping_6.6.0.json").get(char_name) or "")
    damage_type = "Physical"
    if (
        weapon_type == _t("gsuid.renderers.panel.metrics.1053_22.4813ba67")
        or char_name in CHANGE_LIST
    ):
        damage_type = element
    elif weapon_type == _t("gsuid.renderers.panel.metrics.1055_24.a0ec11cd"):
        if attack_type in {"B", "E", "Q"}:
            damage_type = element
    elif attack_type in {"E", "Q"}:
        damage_type = element
    if action_name in {
        _t("gsuid.renderers.panel.metrics.1061_8.df6dc283"),
        _t("gsuid.renderers.panel.metrics.1062_8.a42274ab"),
        _t("gsuid.renderers.panel.metrics.1063_8.1c2a8b98"),
        _t("gsuid.renderers.panel.metrics.1064_8.04686d9b"),
    }:
        damage_type = "Physical"
    if (
        _t("gsuid.renderers.panel.metrics.1036_7.c865b5b0") in action_name
        and "A" not in action_name
    ):
        damage_type = element
    if char_name == _t("gsuid.renderers.panel.metrics.1069_20.484baf23") and action_name == _t(
        "gsuid.renderers.panel.metrics.1069_48.3e97c81e"
    ):
        damage_type = "Physical"
    return damage_type


def _damage_bonus(
    element: str,
    attack_type: str,
    real_prop: Mapping[str, object],
) -> float:
    if element == "Physical":
        return _prefixed_prop(real_prop, attack_type, "physicalDmgBonus")
    return _prefixed_prop(real_prop, attack_type, "dmgBonus")


def _damage_proof(
    enemy: Mapping[str, object], element: str, extra_d: float, ignore_def: float
) -> float:
    d_up = 190.0
    d_down = 190.0 + (1 - extra_d) * (1 - ignore_def) * 190.0
    return _resist_proof(enemy, element) * (d_up / d_down)


def _resist_proof(enemy: Mapping[str, object], element: str) -> float:
    resist = _float_value(enemy.get(f"{element}Resist"), 0.1)
    if resist > 0.75:
        return 1 / (1 + 4 * resist)
    if resist > 0:
        return 1 - resist
    return 1 - resist / 2


def _skill_levels(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> dict[str, int]:
    skill_map = avatar.get("skillLevelMap")
    values = (
        [int_value(value, 1) for value in skill_map.values()]
        if isinstance(skill_map, Mapping)
        else []
    )
    if len(values) > 3:
        values = [values[0], values[1], values[-1]]
    while len(values) < 3:
        values.append(1)
    levels = {"A": values[0], "E": values[1], "Q": values[-1]}
    skill_add = _string_list(_map("skill_add.json").get(_avatar_name(avatar, panel))) or ["E", "Q"]
    talent_count = (
        len(avatar.get("talentIdList")) if isinstance(avatar.get("talentIdList"), list) else 0
    )
    for index, target in enumerate(skill_add[:2]):
        if target in levels and talent_count >= 3 + index * 2:
            levels[target] += 3
    return levels


def _artifact_pairs(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> list[tuple[Mapping[str, object], Mapping[str, object]]]:
    normalized_artifacts = panel.get("artifacts")
    normalized_by_id: dict[str, Mapping[str, object]] = {}
    if isinstance(normalized_artifacts, list):
        for artifact in normalized_artifacts:
            if isinstance(artifact, Mapping):
                normalized_by_id[str(artifact.get("item_id") or "")] = artifact
    pairs = []
    equips = avatar.get("equipList")
    for equip in equips if isinstance(equips, list) else []:
        if not isinstance(equip, Mapping):
            continue
        flat = _flat(equip)
        if flat.get("itemType") != "ITEM_RELIQUARY" and not isinstance(
            equip.get("reliquary"), Mapping
        ):
            continue
        normalized = normalized_by_id.get(str(equip.get("itemId") or ""), {})
        pairs.append((equip, normalized))
    return pairs


def _artifact_substats(
    raw_artifact: Mapping[str, object],
    normalized: Mapping[str, object],
) -> list[Mapping[str, object]]:
    raw = _flat(raw_artifact).get("reliquarySubstats")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, Mapping)]
    normalized_stats = normalized.get("substats")
    if isinstance(normalized_stats, list):
        return [item for item in normalized_stats if isinstance(item, Mapping)]
    return []


def _stat_name(stat: Mapping[str, object]) -> str:
    prop = text_value(stat.get("appendPropId") or stat.get("mainPropId")) or ""
    return str(_map("propId2Name_mapping.json").get(prop) or prop)


def _avatar_name(avatar: Mapping[str, object], panel: Mapping[str, object]) -> str:
    value = text_value(panel.get("name")) or text_value(avatar.get("name")) or ""
    if value:
        return value
    avatar_id = str(panel.get("avatar_id") or avatar.get("avatarId") or "")
    return str(_map("avatarId2Name_mapping_6.6.0.json").get(avatar_id) or avatar_id)


def _avatar_level(avatar: Mapping[str, object], panel: Mapping[str, object]) -> int:
    level = int_value(panel.get("level") or avatar.get("level"))
    if level:
        return level
    prop_map = avatar.get("propMap")
    if isinstance(prop_map, Mapping):
        level_prop = prop_map.get("4001")
        if isinstance(level_prop, Mapping):
            return int_value(level_prop.get("val") or level_prop.get("ival"))
    return 1


def _avatar_element(avatar: Mapping[str, object], panel: Mapping[str, object]) -> str:
    return str(
        _map("avatarName2Element_mapping_6.6.0.json").get(_avatar_name(avatar, panel)) or "Anemo"
    )


def _fight_props(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> Mapping[str, object]:
    raw = avatar.get("fightPropMap")
    if isinstance(raw, Mapping):
        return raw
    normalized = panel.get("fight_props")
    return normalized if isinstance(normalized, Mapping) else {}


def _prop(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
    key: str,
) -> float:
    raw = _fight_props(avatar, panel)
    value = _raw_float(raw, key)
    return (
        value / 100
        if abs(value) > 2 and key not in {"1", "4", "7", "28", "2000", "2001", "2002"}
        else value
    )


def _raw_float(raw: Mapping[str, object], key: str, default: float = 0.0) -> float:
    return _float_value(raw.get(key), default)


def _float_value(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _flat(equip: Mapping[str, object]) -> Mapping[str, object]:
    flat = equip.get("flat")
    return flat if isinstance(flat, Mapping) else {}


def _string_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


@lru_cache(maxsize=32)
def _map(filename: str) -> Mapping[str, object]:
    with (DATA / filename).open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data if isinstance(data, dict) else {}
