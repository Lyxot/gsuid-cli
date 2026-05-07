from __future__ import annotations

from collections.abc import Mapping, Sequence

from gsuid_cli.renderers.common import int_value, text_value
from gsuid_cli.renderers.utility_text import _finish, _mapping, _mapping_list

OCULUS_LABELS = {
    "anemoculus_number": "风神瞳",
    "geoculus_number": "岩神瞳",
    "electroculus_number": "雷神瞳",
    "dendroculus_number": "草神瞳",
    "hydroculus_number": "水神瞳",
    "pyroculus_number": "火神瞳",
    "cryoculus_number": "冰神瞳",
    "moono_culus_number": "月神瞳",
}
CHEST_LABELS = {
    "common_chest_number": "普通宝箱",
    "exquisite_chest_number": "精致宝箱",
    "precious_chest_number": "珍贵宝箱",
    "luxurious_chest_number": "华丽宝箱",
    "magic_chest_number": "奇馈宝箱",
}
POOL_LABELS = {
    "avatar_card_pool_list": "角色祈愿",
    "weapon_card_pool_list": "武器祈愿",
}
ACT_LABELS = {
    "act_list": "限时活动",
    "fixed_act_list": "常驻活动",
}
CATEGORY_LABELS = {
    "avatar_consume": "角色突破",
    "avatar_skill_consume": "角色天赋",
    "weapon_consume": "武器突破",
    "reliquary_consume": "圣遗物",
}
SOURCE_LABELS = {
    "mys_anniversary_game_data": "米游社周年庆数据",
}
CONFIDENCE_LABELS = {
    "provider": "来源数据",
}


def render_player_summary_text(
    *,
    uid: str,
    summary: Mapping[str, object],
    characters: Sequence[Mapping[str, object]],
) -> str:
    role = _mapping(summary.get("role"))
    stats = _mapping(summary.get("stats"))
    nickname = text_value(role.get("nickname")) or "旅行者"
    lines = [f"玩家概览 - {nickname}", f"UID: {uid}"]
    level = _optional_int_text(role.get("level"))
    if level:
        lines.append(f"冒险等阶: {level}")
    region_name = text_value(role.get("region_name")) or text_value(role.get("region"))
    if region_name:
        lines.append(f"服务器: {region_name}")

    lines.append("")
    _append_stat(lines, "活跃天数", stats.get("active_day_number"))
    _append_stat(lines, "成就数量", stats.get("achievement_number"))
    abyss = text_value(stats.get("spiral_abyss"))
    if abyss:
        lines.append(f"深境螺旋: {abyss}")
    avatar_count = _summary_avatar_count(summary, characters)
    if avatar_count:
        lines.append(f"拥有角色: {avatar_count}")

    _append_counter_section(lines, "神瞳", stats, OCULUS_LABELS)
    _append_counter_section(lines, "宝箱", stats, CHEST_LABELS)
    _append_worlds(lines, summary.get("world_explorations"))
    _append_character_lines(lines, "角色", characters or _mapping_list(summary.get("avatars")))
    return _finish(lines)


def render_player_characters_text(data: Mapping[str, object]) -> str:
    uid = text_value(data.get("uid")) or "未知"
    characters = _sorted_characters(_mapping_list(data.get("characters")))
    lines = ["角色列表", f"UID: {uid}", f"数量: {data.get('count', len(characters))}"]
    _append_character_lines(lines, "角色", characters)
    return _finish(lines)


def render_player_inventory_text(
    *,
    uid: str,
    summary: Mapping[str, object],
    inventory: Mapping[str, object],
) -> str:
    nickname = _nickname(summary)
    lines = [f"养成素材 - {nickname}", f"UID: {uid}", f"数量: {inventory.get('count', 0)}"]
    items = _mapping_list(inventory.get("overall"))
    if items:
        lines.extend(["", "总览:"])
        for item in items:
            lines.append(f"  - {_inventory_item_text(item)}")
    else:
        lines.extend(["", "暂无养成素材"])

    categories = _mapping(inventory.get("categories"))
    category_lines = []
    for key, label in CATEGORY_LABELS.items():
        category_items = _mapping_list(categories.get(key))
        if category_items:
            category_lines.append(f"  - {label}: {len(category_items)}")
    if category_lines:
        lines.extend(["", "分类:"])
        lines.extend(category_lines)
    return _finish(lines)


def render_player_calendar_text(
    *,
    uid: str,
    summary: Mapping[str, object],
    calendar: Mapping[str, object],
) -> str:
    nickname = _nickname(summary)
    counts = _mapping(calendar.get("counts"))
    lines = [f"活动日历 - {nickname}", f"UID: {uid}"]
    for key, label in (
        ("avatar_card_pool_list", "角色祈愿"),
        ("weapon_card_pool_list", "武器祈愿"),
        ("act_list", "限时活动"),
        ("fixed_act_list", "常驻活动"),
    ):
        count = counts.get(key)
        if count not in (None, ""):
            lines.append(f"{label}: {count}")

    pool_lines: list[str] = []
    for key, label in POOL_LABELS.items():
        for pool in _mapping_list(calendar.get(key)):
            pool_lines.extend(_pool_lines(label, pool))
    if pool_lines:
        lines.extend(["", "祈愿:"])
        lines.extend(pool_lines)

    for key, label in ACT_LABELS.items():
        acts = _mapping_list(calendar.get(key))
        if not acts:
            continue
        lines.extend(["", f"{label}:"])
        for act in acts:
            lines.extend(_activity_lines(act))
    return _finish(lines)


def render_player_diary_text(
    *,
    uid: str,
    summary: Mapping[str, object],
    diary: Mapping[str, object],
) -> str:
    nickname = _nickname(summary)
    month = text_value(diary.get("data_month")) or text_value(diary.get("month")) or "未知"
    day_data = _mapping(diary.get("day_data"))
    month_data = _mapping(diary.get("month_data"))
    lines = [f"旅行札记 - {nickname}", f"UID: {uid}", f"月份: {month}"]

    lines.extend(
        [
            "",
            (
                "今日: "
                f"原石 {_num(day_data.get('current_primogems'))}，"
                f"摩拉 {_num(day_data.get('current_mora'))}"
            ),
            (
                "昨日: "
                f"原石 {_num(day_data.get('last_primogems'))}，"
                f"摩拉 {_num(day_data.get('last_mora'))}"
            ),
            (
                "本月: "
                f"原石 {_num(month_data.get('current_primogems'))}，"
                f"摩拉 {_num(month_data.get('current_mora'))}"
            ),
            (
                "上月: "
                f"原石 {_num(month_data.get('last_primogems'))}，"
                f"摩拉 {_num(month_data.get('last_mora'))}"
            ),
        ]
    )

    groups = _mapping_list(month_data.get("group_by"))
    if groups:
        lines.extend(["", "本月来源:"])
        for group in groups:
            action = text_value(group.get("action")) or "其他"
            num = _num(group.get("num"))
            percent = _optional_int_text(group.get("percent"))
            suffix = f"（{percent}%）" if percent else ""
            lines.append(f"  - {action}: {num}{suffix}")
    return _finish(lines)


def render_player_register_time_text(data: Mapping[str, object]) -> str:
    uid = text_value(data.get("uid")) or "未知"
    register_time = _mapping(data.get("register_time"))
    lines = ["注册时间", f"UID: {uid}"]
    registered_at = text_value(register_time.get("registered_at"))
    if registered_at:
        lines.append(f"注册时间: {registered_at}")
    timezone = text_value(register_time.get("timezone"))
    if timezone:
        lines.append(f"时区: {timezone}")
    source = text_value(register_time.get("source"))
    if source:
        lines.append(f"来源: {SOURCE_LABELS.get(source, source)}")
    confidence = text_value(register_time.get("confidence"))
    if confidence:
        lines.append(f"可信度: {CONFIDENCE_LABELS.get(confidence, confidence)}")
    return _finish(lines)


def _append_stat(lines: list[str], label: str, value: object) -> None:
    text = _optional_int_text(value)
    if text:
        lines.append(f"{label}: {text}")


def _append_counter_section(
    lines: list[str],
    title: str,
    stats: Mapping[str, object],
    labels: Mapping[str, str],
) -> None:
    values = []
    for key, label in labels.items():
        value = int_value(stats.get(key), 0)
        if value:
            values.append(f"  - {label}: {value}")
    if values:
        lines.extend(["", f"{title}:"])
        lines.extend(values)


def _append_worlds(lines: list[str], value: object) -> None:
    worlds = _mapping_list(value)
    if not worlds:
        return
    lines.extend(["", "世界探索:"])
    for world in sorted(worlds, key=lambda item: int_value(item.get("id"))):
        name = text_value(world.get("name")) or "未知区域"
        percent = int_value(world.get("exploration_percentage"), 0) / 10
        level = _optional_int_text(world.get("level"))
        detail = f"{percent:.1f}%"
        if level:
            detail += f"，等级 {level}"
        lines.append(f"  - {name}: {detail}")
        for offering in _mapping_list(world.get("offerings")):
            offering_name = text_value(offering.get("name")) or "供奉"
            offering_level = _optional_int_text(offering.get("level"))
            if offering_level:
                lines.append(f"    {offering_name}: 等级 {offering_level}")


def _append_character_lines(
    lines: list[str],
    title: str,
    characters: Sequence[Mapping[str, object]],
) -> None:
    if not characters:
        lines.extend(["", f"{title}: 暂无角色数据"])
        return
    lines.extend(["", f"{title}:"])
    for character in _sorted_characters(characters):
        lines.append(f"  - {_character_text(character)}")
        weapon = character.get("weapon")
        if isinstance(weapon, Mapping) and weapon:
            lines.append(f"    武器: {_weapon_text(weapon)}")


def _character_text(character: Mapping[str, object]) -> str:
    name = text_value(character.get("name")) or "未知角色"
    parts = [name]
    rarity = _stars(character.get("rarity"))
    if rarity:
        parts.append(rarity)
    level = _optional_int_text(character.get("level"))
    if level:
        parts.append(f"Lv{level}")
    fetter = _optional_int_text(character.get("fetter"))
    if fetter:
        parts.append(f"好感{fetter}")
    constellation = _optional_int_text(character.get("actived_constellation_num"))
    if constellation:
        parts.append(f"{constellation}命")
    return " ".join(parts)


def _weapon_text(weapon: Mapping[str, object]) -> str:
    name = text_value(weapon.get("name")) or "未知武器"
    parts = [name]
    rarity = _stars(weapon.get("rarity"))
    if rarity:
        parts.append(rarity)
    level = _optional_int_text(weapon.get("level"))
    if level:
        parts.append(f"Lv{level}")
    refinement = _optional_int_text(weapon.get("affix_level"))
    if refinement:
        parts.append(f"精{refinement}")
    return " ".join(parts)


def _inventory_item_text(item: Mapping[str, object]) -> str:
    name = text_value(item.get("name")) or "未知素材"
    owned = int_value(item.get("owned"), 0)
    required = int_value(item.get("required"), 0)
    missing = int_value(item.get("missing"), 0)
    detail = f"拥有 {owned}"
    if required:
        detail += f"，需求 {required}"
    if missing:
        detail += f"，缺少 {missing}"
    return f"{name}: {detail}"


def _pool_lines(label: str, pool: Mapping[str, object]) -> list[str]:
    name = text_value(pool.get("pool_name")) or "未命名祈愿"
    version = text_value(pool.get("version_name"))
    duration = _duration_text(pool.get("countdown_seconds"))
    suffixes = []
    if version:
        suffixes.append(f"版本 {version}")
    if duration:
        suffixes.append(f"剩余 {duration}")
    heading = f"  - [{label}] {name}"
    if suffixes:
        heading += f"（{'，'.join(suffixes)}）"
    lines = [heading]
    for item_key, item_label in (("avatars", "角色"), ("weapon", "武器")):
        item_names = [_pool_item_text(item) for item in _mapping_list(pool.get(item_key))]
        if item_names:
            lines.append(f"    {item_label}: {'、'.join(item_names)}")
    return lines


def _pool_item_text(item: Mapping[str, object]) -> str:
    name = text_value(item.get("name")) or "未知"
    rarity = _stars(item.get("rarity"))
    return f"{name} {rarity}".rstrip()


def _activity_lines(act: Mapping[str, object]) -> list[str]:
    name = text_value(act.get("name")) or "未命名活动"
    status, extra = _activity_status_text(act)
    duration = _duration_text(act.get("countdown_seconds"))
    details = [status]
    if duration:
        details.append(f"剩余 {duration}")
    if extra:
        details.append(extra)
    lines = [f"  - {name}: {'，'.join(details)}"]
    rewards = [
        reward_text
        for reward in _mapping_list(act.get("reward_list"))
        if (reward_text := _reward_text(reward)) is not None
    ]
    if rewards:
        lines.append(f"    奖励: {'、'.join(rewards)}")
    return lines


def _activity_status_text(act: Mapping[str, object]) -> tuple[str, str | None]:
    if int_value(act.get("status")) != 2:
        return "未开始", None
    if act.get("type") == "ActTypeHardChallenge":
        detail = _mapping(act.get("hard_challenge_detail"))
        seconds = int_value(detail.get("second"), 0)
        if seconds:
            return f"困难{int_value(detail.get('difficulty'))}", f"{seconds}秒"
    if act.get("type") == "ActTypeExplore":
        detail = _mapping(act.get("explore_detail"))
        percent = int_value(detail.get("explore_percent"), 0)
        if percent:
            return f"{percent}%", None
    return ("已完成" if act.get("is_finished") else "未完成"), None


def _reward_text(reward: Mapping[str, object]) -> str | None:
    name = text_value(reward.get("name")) or "奖励"
    count = reward.get("num")
    if int_value(count, 0) == 0:
        return None
    return f"{name} x{count}" if count not in (None, "") else name


def _summary_avatar_count(
    summary: Mapping[str, object],
    characters: Sequence[Mapping[str, object]],
) -> int:
    count = int_value(summary.get("avatar_count"), 0)
    if count:
        return count
    avatars = _mapping_list(summary.get("avatars"))
    return len(characters) or len(avatars)


def _nickname(summary: Mapping[str, object]) -> str:
    role = _mapping(summary.get("role"))
    return text_value(role.get("nickname")) or "旅行者"


def _sorted_characters(
    characters: Sequence[Mapping[str, object]],
) -> list[Mapping[str, object]]:
    return sorted(
        characters,
        key=lambda character: (
            -int_value(character.get("rarity"), 0),
            -int_value(character.get("level"), 0),
            -int_value(character.get("fetter"), 0),
            text_value(character.get("name")) or "",
        ),
    )


def _stars(value: object) -> str:
    rarity = int_value(value, 0)
    if rarity <= 0:
        return ""
    return "★" * min(rarity, 5)


def _duration_text(value: object) -> str | None:
    seconds = int_value(value, 0)
    if seconds <= 0:
        return None
    days = seconds // (24 * 3600)
    hours = (seconds % (24 * 3600)) // 3600
    minutes = (seconds % 3600) // 60
    return f"{days}天{hours}时{minutes}分"


def _num(value: object) -> str:
    return str(int_value(value, 0))


def _optional_int_text(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(int_value(value))

