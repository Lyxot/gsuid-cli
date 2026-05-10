from __future__ import annotations

from collections.abc import Mapping

from gsuid_cli.renderers._text_helpers import _finish, _mapping, _mapping_list
from gsuid_cli.renderers.common import int_value, sequence, text_value


def render_guide_abyss_text(data: Mapping[str, object]) -> str:
    abyss = _mapping(data.get("abyss"))
    version = text_value(data.get("version")) or text_value(data.get("requested_version"))
    floor = text_value(abyss.get("floor")) or text_value(data.get("floor")) or "12"
    title = f"深渊攻略 - 第{floor}层"
    lines = [f"{title}（{version}）" if version else title]
    disorder = text_value(abyss.get("disorder"))
    if disorder:
        lines.extend(["", "地脉异常:", disorder])

    chambers = _mapping_list(abyss.get("chambers"))
    if not chambers:
        lines.extend(["", "暂无深渊怪物数据"])
        return _finish(lines)

    for chamber in chambers:
        name = text_value(chamber.get("name")) or "间"
        level = int_value(chamber.get("level"), 0)
        lines.append("")
        lines.append(f"{name} · 怪物等级 Lv{level}" if level else name)
        _append_abyss_side(lines, "上半", chamber.get("upper"))
        _append_abyss_side(lines, "下半", chamber.get("lower"))
    return _finish(lines)


def render_guide_theater_text(data: Mapping[str, object]) -> str:
    theater = _mapping(data.get("theater"))
    version = text_value(data.get("version")) or text_value(theater.get("event_id"))
    lines = [f"剧诗攻略 - {version}" if version else "剧诗攻略"]
    begin = text_value(theater.get("begin_time"))
    end = text_value(theater.get("end_time"))
    if begin or end:
        lines.append(f"时间: {_range_text(begin, end)}")
    buff = text_value(theater.get("buff_description"))
    if buff:
        lines.extend(["", "增益:", buff])
    _append_avatar_section(lines, "特邀角色", theater.get("buff_avatars"))
    _append_avatar_section(lines, "助演角色", theater.get("invite_avatars"))

    rooms = _mapping_list(theater.get("rooms"))
    if not rooms:
        lines.extend(["", "暂无剧诗房间数据"])
        return _finish(lines)
    lines.extend(["", "房间:"])
    for room in rooms:
        title = text_value(room.get("title"))
        room_id = text_value(room.get("id"))
        level = int_value(room.get("monster_level"), 0)
        heading = f"  - 第{room_id}幕" if room_id else "  - 房间"
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
            lines.append(f"    怪物: {'、'.join(monsters)}")
    return _finish(lines)


def render_recommend_build_text(data: Mapping[str, object]) -> str:
    character = text_value(data.get("character")) or "未知角色"
    lines = [f"养成推荐 - {character}"]
    weapon_lines = _build_weapon_lines(data.get("weapons"))
    if weapon_lines:
        lines.extend(["", "推荐武器:"])
        lines.extend(f"  - {line}" for line in weapon_lines)
    artifact_lines = _build_artifact_lines(data.get("artifacts"))
    if artifact_lines:
        lines.extend(["", "推荐圣遗物:"])
        lines.extend(f"  - {line}" for line in artifact_lines)
    remarks = _text_list(data.get("remarks"))
    if remarks:
        lines.extend(["", "备注:"])
        lines.extend(f"  - {remark}" for remark in remarks)
    if len(lines) == 1:
        lines.extend(["", "暂无可展示的推荐内容"])
    return _finish(lines)


def render_recommend_holder_text(data: Mapping[str, object]) -> str:
    item = text_value(data.get("item")) or "未知物品"
    lines = [f"适用角色推荐 - {item}"]
    matches = _mapping_list(data.get("matches"))
    if not matches:
        lines.extend(["", "暂无适用角色"])
        return _finish(lines)
    for match in matches:
        kind = "武器" if match.get("kind") == "weapon" else "圣遗物"
        name = text_value(match.get("match")) or kind
        holders = _text_list(match.get("holders"))
        lines.extend(["", f"{kind} - {name}"])
        if holders:
            lines.append(f"  适用角色: {'、'.join(holders)}")
    return _finish(lines)


def render_rerun_list_text(data: Mapping[str, object]) -> str:
    version = text_value(data.get("version")) or "当前版本"
    rows = _mapping_list(data.get("reruns"))
    lines = [
        f"未复刻列表 - {version}",
        f"数量: {data.get('count', len(rows))}",
    ]
    if data.get("total_count") not in (None, ""):
        lines.append(f"总数: {data['total_count']}")

    groups = _mapping_list(data.get("groups"))
    if not groups and rows:
        groups = [{"label": "未复刻", "items": rows}]
    if not groups:
        lines.extend(["", "暂无未复刻数据"])
        return _finish(lines)

    for group in groups:
        items = _mapping_list(group.get("items"))
        if not items:
            continue
        lines.append("")
        lines.append(text_value(group.get("label")) or "未复刻")
        for item in items:
            name = text_value(item.get("entity")) or "未知"
            days = int_value(item.get("days_since_last_banner"), 0)
            last = text_value(item.get("last_banner_version"))
            detail = f"{days}天未复刻" if days else "未复刻天数未知"
            if last:
                detail += f"，上次: {last}"
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
        text = f"    - 第{index}波"
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
            lines.append(f"{rarity}星: {'、'.join(items)}")
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
            labels.append(f"{name}{piece or '2'}件")
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
        name = text_value(monster.get("name")) or "未知怪物"
        count = int_value(monster.get("count"), 0)
        monsters.append(f"{name} x{count}" if with_count and count else name)
    return monsters


def _range_text(start: str | None, end: str | None) -> str:
    if start and end:
        return f"{start} 至 {end}"
    return start or end or "未知"


def _text_list(value: object) -> list[str]:
    return [text for item in sequence(value) if (text := text_value(item))]
