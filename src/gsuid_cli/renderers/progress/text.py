from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache

from gsuid_cli.renderers.common import asset_path, int_value, sequence, text_value
from gsuid_cli.renderers.utility_text import _finish, _first_mapping, _mapping, _mapping_list

GCG_CARD_NAME_PATH = asset_path("progress", "gcg", "data", "card_names.json")

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
OTHER_LABELS = {
    "avatar_number": "角色数量",
    "way_point_number": "传送点",
    "domain_number": "秘境",
}
GUIDE_LABELS = {
    "achievement": "成就攻略查询",
    "commission": "委托攻略查询",
}


def render_progress_completion_text(*, uid: str, completion: Mapping[str, object]) -> str:
    stats = _stats(completion)
    lines = ["完成进度", f"UID: {uid}"]
    _append_stat(lines, "活跃天数", stats.get("active_day_number"))
    _append_stat(lines, "成就数量", stats.get("achievement_number"))
    abyss = text_value(stats.get("spiral_abyss"))
    if abyss:
        lines.append(f"深境螺旋: {abyss}")
    exploration_count = completion.get("exploration_count")
    if exploration_count not in (None, ""):
        lines.append(f"探索区域: {exploration_count}")

    _append_worlds(lines, completion.get("world_explorations"))
    _append_counter_section(lines, "神瞳", stats, OCULUS_LABELS)
    _append_counter_section(lines, "收集", stats, {**CHEST_LABELS, **OTHER_LABELS})
    return _finish(lines)


def render_progress_exploration_text(*, uid: str, exploration: Mapping[str, object]) -> str:
    lines = ["探索进度", f"UID: {uid}"]
    worlds = _mapping_list(exploration.get("world_explorations"))
    if not worlds:
        lines.extend(["", "暂无探索数据"])
        return _finish(lines)
    _append_worlds(lines, worlds)
    return _finish(lines)


def render_progress_collection_text(*, uid: str, collection: Mapping[str, object]) -> str:
    stats = _stats(collection)
    lines = ["收集进度", f"UID: {uid}"]
    _append_stat(lines, "活跃天数", stats.get("active_day_number"))
    _append_stat(lines, "成就数量", stats.get("achievement_number"))
    _append_counter_section(lines, "神瞳", stats, OCULUS_LABELS)
    _append_counter_section(lines, "宝箱", stats, CHEST_LABELS)
    _append_counter_section(lines, "其他", stats, OTHER_LABELS)
    return _finish(lines)


def render_progress_achievements_text(
    *,
    uid: str,
    achievements: list[Mapping[str, object]],
    query: object = None,
) -> str:
    lines = ["成就进度", f"UID: {uid}"]
    query_text = text_value(query)
    if query_text:
        lines.append(f"查询: {query_text}")
    lines.append(f"数量: {len(achievements)}")
    if not achievements:
        lines.extend(["", "暂无成就记录"])
        return _finish(lines)
    lines.extend(["", "成就:"])
    for achievement in achievements:
        lines.append(f"  - {_achievement_text(achievement)}")
    return _finish(lines)


def render_progress_guide_status_text(data: Mapping[str, object]) -> str:
    kind = text_value(data.get("kind"))
    lines = [
        GUIDE_LABELS.get(kind, "攻略查询"),
        f"查询: {text_value(data.get('query')) or '-'}",
        f"可用: {'是' if data.get('available') else '否'}",
        f"数量: {data.get('count', 0)}",
    ]
    limitations = [
        text
        for text in (text_value(item) for item in sequence(data.get("source_limitations")))
        if text
    ]
    if limitations:
        lines.extend(["", "来源限制:"])
        lines.extend(f"  - {limitation}" for limitation in limitations)
    matches = _mapping_list(data.get("matches"))
    if matches:
        lines.extend(["", "结果:"])
        for match in matches:
            _append_guide_match(lines, kind, match)
    return _finish(lines)


def render_progress_gcg_text(*, uid: str, gcg: Mapping[str, object]) -> str:
    basic = _mapping(gcg.get("basic"))
    nickname = text_value(basic.get("nickname")) or "牌手"
    lines = [f"七圣召唤 - {nickname}", f"UID: {uid}"]
    _append_stat(lines, "牌手等级", basic.get("level"))
    _append_ratio(
        lines,
        "角色牌",
        basic.get("avatar_card_num_gained"),
        basic.get("avatar_card_num_total"),
    )
    _append_ratio(
        lines,
        "行动牌",
        basic.get("action_card_num_gained"),
        basic.get("action_card_num_total"),
    )
    if gcg.get("deck_count") not in (None, ""):
        lines.append(f"卡组数量: {gcg['deck_count']}")
    covers = _mapping_list(basic.get("covers"))
    if covers:
        lines.extend(["", "展示牌:"])
        lines.extend(f"  - {_card_name(card)}" for card in covers)
    return _finish(lines)


def render_progress_gcg_deck_text(*, uid: str, data: Mapping[str, object]) -> str:
    deck = _first_mapping(data.get("decks"))
    deck_name = text_value(deck.get("name")) or "未命名卡组"
    lines = [f"七圣召唤卡组 - {deck_name}", f"UID: {uid}"]
    deck_id = deck.get("id", data.get("deck_id"))
    if deck_id not in (None, ""):
        lines.append(f"卡组ID: {deck_id}")
    if not deck:
        lines.extend(["", "暂无匹配卡组"])
        return _finish(lines)
    avatar_cards = _mapping_list(deck.get("avatar_cards"))
    if avatar_cards:
        lines.extend(["", "角色牌:"])
        lines.extend(f"  - {_card_name(card)}" for card in avatar_cards)
    action_cards = _mapping_list(deck.get("action_cards"))
    if action_cards:
        lines.extend(["", "行动牌:"])
        lines.extend(f"  - {_action_card_text(card)}" for card in action_cards)
    return _finish(lines)


def _append_stat(lines: list[str], label: str, value: object) -> None:
    text = _optional_int_text(value)
    if text:
        lines.append(f"{label}: {text}")


def _append_ratio(lines: list[str], label: str, current: object, total: object) -> None:
    current_text = _optional_int_text(current)
    total_text = _optional_int_text(total)
    if current_text or total_text:
        lines.append(f"{label}: {current_text or 0}/{total_text or 0}")


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
        detail = f"{percent:.1f}%"
        level = _optional_int_text(world.get("level"))
        if level:
            detail += f"，等级 {level}"
        lines.append(f"  - {name}: {detail}")
        for offering in _mapping_list(world.get("offerings")):
            offering_name = text_value(offering.get("name")) or "供奉"
            offering_level = _optional_int_text(offering.get("level"))
            if offering_level:
                lines.append(f"    {offering_name}: {offering_level}级")


def _achievement_text(achievement: Mapping[str, object]) -> str:
    name = text_value(achievement.get("name")) or "未命名成就"
    finish = _optional_int_text(achievement.get("finish_num"))
    percent = _percent_text(achievement.get("percentage"))
    details = []
    if finish:
        details.append(f"{finish}项")
    if percent:
        details.append(percent)
    return f"{name}: {'，'.join(details)}" if details else name


def _action_card_text(card: Mapping[str, object]) -> str:
    name = _card_name(card)
    num = int_value(card.get("num"), 1)
    suffix = f" x{num}" if num > 1 else ""
    cost = _first_cost(card)
    cost_value = _optional_int_text(cost.get("cost_value"))
    if cost_value:
        suffix += f"，费用 {cost_value}"
    return f"{name}{suffix}"


def _append_guide_match(lines: list[str], kind: str, match: Mapping[str, object]) -> None:
    name = text_value(match.get("name")) or "未命名"
    lines.append(f"  - {name}")
    if kind == "achievement":
        book = text_value(match.get("book"))
        if book:
            lines.append(f"    分类: {book}")
    else:
        achievement = text_value(match.get("achievement"))
        if achievement:
            lines.append(f"    关联成就: {achievement}")
    description = text_value(match.get("description"))
    if description:
        lines.append(f"    描述: {description}")
    guide = text_value(match.get("guide"))
    if guide:
        lines.append(f"    攻略: {guide}")
    link = text_value(match.get("link"))
    if link:
        lines.append(f"    链接: {link}")


def _card_name(card: Mapping[str, object]) -> str:
    name = text_value(card.get("name"))
    if name:
        return name
    card_id = text_value(card.get("id")) or text_value(card.get("rank_id"))
    if card_id:
        mapped_name = _gcg_card_names().get(card_id)
        if mapped_name:
            return mapped_name
    return "未知卡牌"


def _first_cost(card: Mapping[str, object]) -> Mapping[str, object]:
    costs = _mapping_list(card.get("action_cost"))
    return costs[0] if costs else {}


def _stats(data: Mapping[str, object]) -> Mapping[str, object]:
    stats = data.get("raw_stats") or data.get("stats")
    return stats if isinstance(stats, Mapping) else {}


def _optional_int_text(value: object) -> str:
    if value in (None, ""):
        return ""
    return str(int_value(value))


def _percent_text(value: object) -> str:
    try:
        percent = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    if percent < 0:
        return ""
    return f"{percent:g}%"


@lru_cache(maxsize=1)
def _gcg_card_names() -> Mapping[str, str]:
    try:
        payload = json.loads(GCG_CARD_NAME_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, Mapping):
        return {}
    return {str(key): str(value) for key, value in payload.items() if text_value(value)}
