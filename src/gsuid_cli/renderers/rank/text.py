from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache

from gsuid_cli.renderers._text_helpers import _finish, _mapping, _number, _number_text, _text
from gsuid_cli.renderers.common import asset_path
from gsuid_cli.renderers.utility_text import _sequence
from gsuid_cli.text import t as _t

PANEL_DATA = asset_path("panel", "data")
STAT_LABELS = {
    "Flat ATK": _t("gsuid.renderers.panel.image.88_25.ef28aed2"),
    "Flat HP": _t("gsuid.renderers.panel.metrics.357_7.575ca7a8"),
    "Flat DEF": _t("gsuid.renderers.panel.image.91_26.2557c107"),
    "ATK%": _t("gsuid.renderers.panel.image.88_25.ef28aed2"),
    "HP%": _t("gsuid.renderers.panel.metrics.357_7.575ca7a8"),
    "DEF%": _t("gsuid.renderers.panel.image.91_26.2557c107"),
    "Elemental Mastery": _t("gsuid.providers.akasha.66_4.af09dad1"),
    "Energy Recharge": _t("gsuid.providers.akasha.68_4.a7a24305"),
    "Crit RATE": _t("gsuid.providers.akasha.70_4.33e0f20a"),
    "Crit DMG": _t("gsuid.providers.akasha.72_4.7c0dd18b"),
    "Cryo DMG Bonus": _t("gsuid.renderers.panel.image.108_31.81e609f2"),
    "Pyro DMG Bonus": _t("gsuid.renderers.panel.image.102_32.a7d92d8b"),
    "Hydro DMG Bonus": _t("gsuid.renderers.panel.image.104_33.0205a287"),
    "Electro DMG Bonus": _t("gsuid.renderers.panel.image.103_32.b05986fe"),
    "Anemo DMG Bonus": _t("gsuid.renderers.panel.image.106_32.53069124"),
    "Geo DMG Bonus": _t("gsuid.renderers.panel.image.107_32.78be5ad7"),
    "Dendro DMG Bonus": _t("gsuid.renderers.panel.image.105_33.cfb22d08"),
    "Healing Bonus": _t("gsuid.renderers.panel.image.101_27.f1fcdb6f"),
    "Physical DMG Bonus": _t("gsuid.renderers.panel.image.109_36.be65271f"),
}
EQUIP_LABELS = {
    "EQUIP_BRACER": _t("gsuid.commands.panel.mys.317_8.5c8bb682"),
    "EQUIP_NECKLACE": _t("gsuid.commands.panel.mys.318_8.9eaf35fa"),
    "EQUIP_SHOES": _t("gsuid.commands.panel.mys.319_8.bc4a2cbb"),
    "EQUIP_RING": _t("gsuid.commands.panel.mys.320_8.c4347056"),
    "EQUIP_DRESS": _t("gsuid.commands.panel.mys.321_8.e5385dd2"),
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
    title = (
        _t("gsuid.renderers.rank.text.64_12.d2868f38", nickname)
        if nickname != "-"
        else _t("gsuid.renderers.rank.text.64_65.4b81c79a")
    )
    lines = [
        title,
        f"UID: {uid}",
        _t("gsuid.renderers.panel.text.202_17.2e0aa7dd", _text(data.get("count"))),
    ]
    if not characters:
        lines.extend(["", _t("gsuid.renderers.rank.text.67_26.7c77d819")])
        return _finish(lines)
    lines.extend(["", _t("gsuid.renderers.panel.text.248_17.ebc2e4bd")])
    for character in characters:
        stats = _mapping(character.get("stats"))
        weapon = _mapping(character.get("weapon"))
        character_label = _character_label(character)
        lines.append(
            _t(
                "gsuid.renderers.rank.text.75_12.ec0d3044",
                character_label,
                _number_text(character.get("result")),
                _rank_text(character.get("rank"), character.get("out_of")),
            )
        )
        lines.append(
            _t(
                "gsuid.renderers.rank.text.80_12.c21e6f7f",
                _text(character.get("constellation")),
                _weapon_name(weapon),
                _text(weapon.get("refinement")),
                _percent_number(stats.get("critRate")),
                _percent_number(stats.get("critDMG")),
                _number_text(stats.get("critValue")),
            )
        )
        lines.append(
            _t(
                "gsuid.renderers.rank.text.88_12.fa451708",
                _number_text(stats.get("maxHP")),
                _number_text(stats.get("maxATK")),
            )
        )
        set_text = _artifact_sets_text(_mapping(character.get("artifact_sets")))
        if set_text != "-":
            lines.append(_t("gsuid.renderers.rank.text.92_25.4be54ef5", set_text))
    return _finish(lines)


def render_rank_character_text(data: Mapping[str, object]) -> str:
    entries = [_mapping(item) for item in _sequence(data.get("entries"))]
    selected_uid = _text(data.get("selected_uid"))
    lines = [
        _t("gsuid.renderers.rank.text.100_8.a16a8fdb", _text(data.get("character"))),
        _t(
            "gsuid.renderers.rank.text.101_8.3eff2429",
            _text(data.get("tag")),
            _text(data.get("total_count")),
        ),
    ]
    if selected_uid != "-":
        lines.append(_t("gsuid.renderers.rank.text.104_21.b1e34f16", selected_uid))
    if not entries:
        lines.extend(["", _t("gsuid.renderers.rank.text.106_26.9fbf16c5")])
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
            _t("gsuid.renderers.rank.text.119_12.84cbd9ff")
            if selected_uid != "-" and _text(entry.get("uid")) == selected_uid
            else ""
        )
        lines.append(
            f"#{rank} {_text(owner.get('nickname'))} "
            f"({_text(owner.get('region'))}) UID: {_text(entry.get('uid'))}{mark}"
        )
        lines.append(
            _t(
                "gsuid.renderers.rank.text.126_12.06ab3f56",
                _text(entry.get("constellation")),
                refinement,
                _percent_number(_stat(stats, "critRate")),
                _percent_number(_stat(stats, "critDamage")),
                _number_text(entry.get("critValue")),
            )
        )
        lines.append(
            _t(
                "gsuid.renderers.rank.text.134_12.8bd1406b",
                _number_text(_stat(stats, "maxHp")),
                _number_text(_stat(stats, "atk")),
            )
        )
        set_text = _artifact_sets_text(_mapping(entry.get("artifactSets")))
        if set_text != "-":
            lines.append(_t("gsuid.renderers.rank.text.140_25.80eae690", set_text))
    return _finish(lines)


def render_rank_artifact_text(data: Mapping[str, object]) -> str:
    artifacts = [_mapping(item) for item in _sequence(data.get("artifacts"))]
    lines = [
        _t("gsuid.renderers.rank.text.147_8.8b739138", _text(data.get("sort"))),
        _t("gsuid.renderers.rank.text.148_8.4f49205c", _text(data.get("akasha_sort"))),
        _t("gsuid.renderers.challenge.text.186_8.a63927f2", _text(data.get("count"))),
    ]
    if not artifacts:
        lines.extend(["", _t("gsuid.renderers.rank.text.152_26.1a56ce07")])
        return _finish(lines)
    lines.append("")
    for index, artifact in enumerate(artifacts[:20], start=1):
        owner = _mapping(artifact.get("owner"))
        lines.append(
            f"#{index} {_text(owner.get('nickname'))} "
            f"({_text(owner.get('region'))}) UID: {_text(artifact.get('uid'))}"
        )
        lines.append(
            _t(
                "gsuid.renderers.rank.text.162_12.18aa0ce7",
                _slot_label(artifact.get("equipType")),
                _artifact_name(artifact),
                _artifact_level(artifact),
                _stars(artifact.get("stars")),
                _number_text(artifact.get("critValue")),
            )
        )
        lines.append(
            _t(
                "gsuid.renderers.rank.text.170_12.4a7cffc6",
                _stat_label(artifact.get("mainStatKey")),
                _stat_value_text(artifact.get("mainStatValue"), artifact.get("mainStatKey")),
            )
        )
        substats = _mapping(artifact.get("substats"))
        if substats:
            lines.append(_t("gsuid.renderers.rank.text.176_25.9dd064ca"))
            for name, value in substats.items():
                lines.append(f"    - {_stat_label(name)}: {_stat_value_text(value, name)}")
    return _finish(lines)


def _character_name(character: Mapping[str, object]) -> str:
    avatar_id = str(character.get("avatar_id") or character.get("character_id") or "")
    mapped = _text_map("avatarId2Name_mapping_6.6.0.json").get(avatar_id)
    return _text(mapped or character.get("name") or avatar_id)


def _weapon_name(weapon: Mapping[str, object]) -> str:
    name = _text(weapon.get("name"))
    if name == "-":
        return name
    for item in _text_map("weaponList_6.6.0.json").values():
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
    return _t(
        "gsuid.renderers.rank.text.217_11.edc56e93",
        rank_prefix,
        rank_num,
        _number_text(out_num),
        percent,
    )


def _artifact_sets_text(sets: Mapping[str, object]) -> str:
    parts: list[str] = []
    for name, value in sets.items():
        item = _mapping(value)
        count = int(_number(item.get("count")))
        if count <= 0:
            continue
        label = _artifact_set_label(name, item)
        parts.append(_t("gsuid.renderers.guide.text.187_26.12201c09", label, count))
    return "，".join(parts) if parts else "-"


def _artifact_set_label(name: object, item: Mapping[str, object]) -> str:
    icon = _icon_key(item.get("icon"))
    artifact_name = _text_map("icon2Name_mapping_6.6.0.json").get(icon)
    if artifact_name:
        set_name = _text_map("artifact2attr_mapping_6.6.0.json").get(str(artifact_name))
        if set_name:
            return _text(set_name)
    return _text(name)


def _artifact_name(artifact: Mapping[str, object]) -> str:
    icon_key = _icon_key(artifact.get("icon"))
    mapped = _text_map("icon2Name_mapping_6.6.0.json").get(icon_key)
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


@lru_cache(maxsize=16)
def _text_map(filename: str) -> dict[str, object]:
    try:
        data = json.loads((PANEL_DATA / filename).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
