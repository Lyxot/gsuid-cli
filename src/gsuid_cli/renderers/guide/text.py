from __future__ import annotations

from collections.abc import Mapping

from gsuid_cli.renderers._text_helpers import _finish, _mapping, _mapping_list
from gsuid_cli.renderers.common import int_value, sequence, text_value
from gsuid_cli.text import t as _t


def render_guide_abyss_text(data: Mapping[str, object]) -> str:
    abyss = _mapping(data.get("abyss"))
    version = text_value(data.get("version")) or text_value(data.get("requested_version"))
    floor = text_value(abyss.get("floor")) or text_value(data.get("floor")) or "12"
    title = _t("gsuid.renderers.guide.text.13_12.a4a8c965", floor)
    lines = [f"{title}（{version}）" if version else title]
    disorder = text_value(abyss.get("disorder"))
    if disorder:
        lines.extend(["", _t("gsuid.renderers.guide.text.17_26.e28666b5"), disorder])

    chambers = _mapping_list(abyss.get("chambers"))
    if not chambers:
        lines.extend(["", _t("gsuid.renderers.guide.text.21_26.80327cd7")])
        return _finish(lines)

    for chamber in chambers:
        name = text_value(chamber.get("name")) or _t("gsuid.renderers.guide.text.25_50.01b221aa")
        level = int_value(chamber.get("level"), 0)
        lines.append("")
        lines.append(
            _t("gsuid.renderers.guide.image.124_8.901d983e", name, level) if level else name
        )
        _append_abyss_side(
            lines, _t("gsuid.renderers.guide.text.29_34.b648ea14"), chamber.get("upper")
        )
        _append_abyss_side(
            lines, _t("gsuid.renderers.guide.text.30_34.9c03bee7"), chamber.get("lower")
        )
    return _finish(lines)


def render_guide_theater_text(data: Mapping[str, object]) -> str:
    theater = _mapping(data.get("theater"))
    version = text_value(data.get("version")) or text_value(theater.get("event_id"))
    lines = [
        _t("gsuid.renderers.guide.text.37_13.e4ec7012", version)
        if version
        else _t("gsuid.renderers.guide.text.37_57.d644ae0e")
    ]
    begin = text_value(theater.get("begin_time"))
    end = text_value(theater.get("end_time"))
    if begin or end:
        lines.append(_t("gsuid.renderers.challenge.text.99_21.389c2b09", _range_text(begin, end)))
    buff = text_value(theater.get("buff_description"))
    if buff:
        lines.extend(["", _t("gsuid.renderers.guide.text.44_26.997232be"), buff])
    _append_avatar_section(
        lines, _t("gsuid.renderers.guide.text.45_34.f5457ce2"), theater.get("buff_avatars")
    )
    _append_avatar_section(
        lines, _t("gsuid.renderers.guide.text.46_34.6d53f460"), theater.get("invite_avatars")
    )

    rooms = _mapping_list(theater.get("rooms"))
    if not rooms:
        lines.extend(["", _t("gsuid.renderers.guide.text.50_26.b10bf243")])
        return _finish(lines)
    lines.extend(["", _t("gsuid.renderers.guide.text.52_22.76875bf1")])
    for room in rooms:
        title = text_value(room.get("title"))
        room_id = text_value(room.get("id"))
        level = int_value(room.get("monster_level"), 0)
        heading = (
            _t("gsuid.renderers.guide.text.57_18.12e5f4b0", room_id)
            if room_id
            else _t("gsuid.renderers.guide.text.57_57.638e555d")
        )
        if title:
            heading += f": {title}"
        if level:
            heading += f"（Lv{level}）"
        lines.append(heading)
        desc = text_value(room.get("description"))
        if desc:
            lines.append(f"    {desc}")
        monsters = _monster_texts(room.get("monsters"))
        if monsters:
            lines.append(_t("gsuid.renderers.guide.text.68_25.6cb6632e", "、".join(monsters)))
    return _finish(lines)


def render_recommend_build_text(data: Mapping[str, object]) -> str:
    character = text_value(data.get("character")) or _t(
        "gsuid.renderers.challenge.text.293_68.876cfbce"
    )
    lines = [_t("gsuid.renderers.guide.text.74_13.0df7e8f9", character)]
    weapon_lines = _build_weapon_lines(data.get("weapons"))
    if weapon_lines:
        lines.extend(["", _t("gsuid.renderers.guide.text.77_26.5eeeb8d2")])
        lines.extend(f"  - {line}" for line in weapon_lines)
    artifact_lines = _build_artifact_lines(data.get("artifacts"))
    if artifact_lines:
        lines.extend(["", _t("gsuid.renderers.guide.text.81_26.a762e753")])
        lines.extend(f"  - {line}" for line in artifact_lines)
    remarks = _text_list(data.get("remarks"))
    if remarks:
        lines.extend(["", _t("gsuid.renderers.guide.text.85_26.4000b231")])
        lines.extend(f"  - {remark}" for remark in remarks)
    if len(lines) == 1:
        lines.extend(["", _t("gsuid.renderers.guide.text.88_26.a429ffa1")])
    return _finish(lines)


def render_recommend_holder_text(data: Mapping[str, object]) -> str:
    item = text_value(data.get("item")) or _t("gsuid.renderers.gacha.630_43.988a9ca3")
    lines = [_t("gsuid.renderers.guide.text.94_13.924c036d", item)]
    matches = _mapping_list(data.get("matches"))
    if not matches:
        lines.extend(["", _t("gsuid.renderers.guide.text.97_26.b6d81b0e")])
        return _finish(lines)
    for match in matches:
        kind = (
            _t("gsuid.commands.panel.impl.988_24.6f0f16e0")
            if match.get("kind") == "weapon"
            else _t("gsuid.renderers.guide.text.100_62.619c6618")
        )
        name = text_value(match.get("match")) or kind
        holders = _text_list(match.get("holders"))
        lines.extend(["", f"{kind} - {name}"])
        if holders:
            lines.append(_t("gsuid.renderers.guide.text.105_25.0aee44ba", "、".join(holders)))
    return _finish(lines)


def render_rerun_list_text(data: Mapping[str, object]) -> str:
    version = text_value(data.get("version")) or _t("gsuid.renderers.guide.text.110_49.46e66f63")
    rows = _mapping_list(data.get("reruns"))
    lines = [
        _t("gsuid.renderers.guide.text.113_8.515245f3", version),
        _t("gsuid.renderers.challenge.text.186_8.a63927f2", data.get("count", len(rows))),
    ]
    if data.get("total_count") not in (None, ""):
        lines.append(_t("gsuid.renderers.events.text.88_21.d282f3df", data["total_count"]))

    groups = _mapping_list(data.get("groups"))
    if not groups and rows:
        groups = [{"label": _t("gsuid.renderers.guide.text.121_28.cb1029a4"), "items": rows}]
    if not groups:
        lines.extend(["", _t("gsuid.renderers.guide.text.123_26.1e08c732")])
        return _finish(lines)

    for group in groups:
        items = _mapping_list(group.get("items"))
        if not items:
            continue
        lines.append("")
        lines.append(
            text_value(group.get("label")) or _t("gsuid.renderers.guide.text.121_28.cb1029a4")
        )
        for item in items:
            name = text_value(item.get("entity")) or _t(
                "gsuid.renderers.daily.text.211_11.d9c32a4c"
            )
            days = int_value(item.get("days_since_last_banner"), 0)
            last = text_value(item.get("last_banner_version"))
            detail = (
                _t("gsuid.renderers.guide.text.136_21.af9b5991", days)
                if days
                else _t("gsuid.renderers.guide.text.136_56.60a50aaa")
            )
            if last:
                detail += _t("gsuid.renderers.guide.text.138_26.ec8c3e76", last)
            lines.append(f"  - {name}: {detail}")
    return _finish(lines)


def _append_abyss_side(lines: list[str], label: str, value: object) -> None:
    waves = _mapping_list(value)
    if not waves:
        return
    lines.append(f"  {label}:")
    for index, wave in enumerate(waves, start=1):
        extra = text_value(wave.get("extra_desc"))
        monsters = _monster_texts(wave.get("monsters"), with_count=True)
        text = _t("gsuid.renderers.guide.text.151_15.d422bdfa", index)
        if monsters:
            text += f": {'、'.join(monsters)}"
        lines.append(text)
        if extra:
            lines.append(f"      {extra}")


def _append_avatar_section(lines: list[str], label: str, value: object) -> None:
    names = _avatar_names(value)
    if names:
        lines.extend(["", f"{label}:"])
        for name in names:
            lines.append(f"  - {name}")


def _build_weapon_lines(value: object) -> list[str]:
    lines = []
    for group in _mapping_list(value):
        rarity = text_value(group.get("rarity")) or "?"
        items = _text_list(group.get("items"))
        if items:
            lines.append(_t("gsuid.renderers.guide.text.173_25.724b8b99", rarity, "、".join(items)))
    return lines


def _build_artifact_lines(value: object) -> list[str]:
    lines = []
    for group in _mapping_list(value):
        sets = _text_list(group.get("sets"))
        pieces = sequence(group.get("pieces"))
        if not sets:
            continue
        labels = []
        for index, name in enumerate(sets):
            piece = text_value(pieces[index]) if index < len(pieces) else "2"
            labels.append(_t("gsuid.renderers.guide.text.187_26.12201c09", name, piece or "2"))
        lines.append(" + ".join(labels))
    return lines


def _avatar_names(value: object) -> list[str]:
    names = []
    for avatar in _mapping_list(value):
        name = text_value(avatar.get("name"))
        if name:
            names.append(name)
    return names


def _monster_texts(value: object, *, with_count: bool = False) -> list[str]:
    monsters = []
    for monster in _mapping_list(value):
        name = text_value(monster.get("name")) or _t("gsuid.providers.public.guide.274_83.9f6cb1a9")
        count = int_value(monster.get("count"), 0)
        monsters.append(f"{name} x{count}" if with_count and count else name)
    return monsters


def _range_text(start: str | None, end: str | None) -> str:
    if start and end:
        return _t("gsuid.renderers.challenge.text.269_15.5881d084", start, end)
    return start or end or _t("gsuid.renderers.daily.text.211_11.d9c32a4c")


def _text_list(value: object) -> list[str]:
    return [text for item in sequence(value) if (text := text_value(item))]
