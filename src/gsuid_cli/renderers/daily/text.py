from __future__ import annotations

from collections.abc import Mapping, Sequence

from gsuid_cli.renderers._text_helpers import _finish
from gsuid_cli.renderers.common import bool_value, int_value, sequence, text_value

WEEKDAY_LABELS = {
    "monday": "周一",
    "tuesday": "周二",
    "wednesday": "周三",
    "thursday": "周四",
    "friday": "周五",
    "saturday": "周六",
    "sunday": "周日",
}
CITY_LABELS = {
    "1": "蒙德",
    "2": "璃月",
    "3": "稻妻",
    "4": "须弥",
    "5": "枫丹",
    "6": "纳塔",
    "7": "挪德卡莱",
}


def render_daily_materials_text(
    *,
    day: str,
    domains: Sequence[Mapping[str, object]],
    date: object | None = None,
) -> str:
    del date
    lines = [f"每日材料 - {_weekday_label(day)}"]

    for domain in domains:
        lines.append("")
        lines.append(_material_domain_heading(domain))

        items = _items(domain)
        if not items:
            lines.append("  适用对象: 暂无")
            continue
        lines.append("  适用对象:")
        for item in items:
            lines.append(f"    - {_material_item_text(item)}")

    return _finish(lines)


def render_daily_note_text(
    *,
    uid: str,
    note: Mapping[str, object],
    nickname: str | None = None,
    level: object | None = None,
    signed: bool | None = None,
) -> str:
    del level
    title = f"实时便笺 - {nickname}" if nickname else "实时便笺"
    lines = [title, f"UID: {uid}", f"米游社签到: {_signed_text(signed)}"]

    current_resin = int_value(note.get("current_resin"))
    max_resin = int_value(note.get("max_resin"), 200)
    resin_recovery = int_value(note.get("resin_recovery_time"))
    resin_line = f"{current_resin}/{max_resin}"
    if current_resin < max_resin and resin_recovery > 0:
        resin_line += f"（回满还需 {_seconds_to_hms(resin_recovery)}）"
    lines.extend(["", f"原粹树脂: {resin_line}"])

    finished_tasks = int_value(note.get("finished_task_num"))
    total_tasks = int_value(note.get("total_task_num"))
    reward = "已领取" if bool_value(note.get("is_extra_task_reward_received")) else "未领取"
    lines.append(f"每日委托: {finished_tasks}/{total_tasks}，奖励: {reward}")

    remaining_discount = int_value(note.get("remain_resin_discount_num"), -1)
    discount_limit = int_value(note.get("resin_discount_num_limit"))
    if remaining_discount >= 0:
        used_discount = max(discount_limit - remaining_discount, 0)
        discount_text = f"已用 {used_discount}/{discount_limit}（剩余 {remaining_discount}）"
    else:
        discount_text = "未知"
    lines.append(f"周本减半: {discount_text}")

    current_coin = int_value(note.get("current_home_coin"))
    max_coin = int_value(note.get("max_home_coin"))
    coin_recovery = int_value(note.get("home_coin_recovery_time"))
    coin_line = f"{current_coin}/{max_coin}"
    if current_coin < max_coin and coin_recovery > 0:
        coin_line += f"（回满还需 {_seconds_to_hms(coin_recovery)}）"
    lines.append(f"洞天宝钱: {coin_line}")

    lines.append(f"参量质变仪: {_transformer_text(note)}")
    lines.append(f"魔神任务: {_archon_quest_text(note)}")

    expeditions = _expeditions(note)
    finished = sum(1 for expedition in expeditions if expedition.get("status") == "Finished")
    current_expedition_num = int_value(note.get("current_expedition_num"), len(expeditions))
    max_expedition_num = int_value(note.get("max_expedition_num"), len(expeditions))
    lines.append(f"探索派遣: {current_expedition_num}/{max_expedition_num}，已完成: {finished}")

    return _finish(lines)


def render_daily_signin_text(data: Mapping[str, object]) -> str:
    lines = []
    if data.get("uid") not in (None, ""):
        lines.append(f"UID: {data['uid']}")

    already_signed = bool_value(data.get("already_signed"))
    signed = bool_value(data.get("signed"))
    if already_signed:
        status = "✓ 今日已签到"
    elif signed:
        status = "✓ 签到成功"
    else:
        status = "✗ 今日未签到"
    lines.append(status)
    return _finish(lines)


def render_daily_bbs_coin_text(data: Mapping[str, object]) -> str:
    lines = ["米游币任务"]
    if data.get("uid") not in (None, ""):
        lines.append(f"UID: {data['uid']}")
    if data.get("points_received") is not None:
        lines.append(f"已获取米游币: {data['points_received']}")

    tasks = sequence(data.get("tasks"))
    lines.append("")
    lines.append("任务")
    if tasks:
        for task in tasks:
            if isinstance(task, Mapping):
                lines.append(f"  - {_bbs_task_text(task)}")
            else:
                lines.append(f"  - {task}")
    else:
        lines.append("  暂无")

    failures = sequence(data.get("failures"))
    if failures:
        lines.append("")
        lines.append("失败项")
        for failure in failures:
            lines.append(f"  - {failure}")

    limitations = sequence(data.get("source_limitations"))
    if limitations:
        lines.append("")
        lines.append("来源限制")
        for limitation in limitations:
            lines.append(f"  - {limitation}")

    return _finish(lines)


def _bbs_task_text(task: Mapping[str, object]) -> str:
    label = text_value(task.get("label")) or text_value(task.get("key")) or "任务"
    status = "已完成" if bool_value(task.get("completed")) else "未完成"
    happened = int_value(task.get("happened_times"), -1)
    remaining = int_value(task.get("remaining"), -1)
    details = [status]
    if happened >= 0 and remaining >= 0:
        details.append(f"已做 {happened}，剩余 {remaining}")
    return f"{label}: {'，'.join(details)}"


def _items(domain: Mapping[str, object]) -> list[Mapping[str, object]]:
    value = domain.get("items")
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _material_item_text(item: Mapping[str, object]) -> str:
    name = text_value(item.get("name")) or "未知"
    stars = _rank_stars(item.get("rank"))
    return f"{name} {stars}" if stars else name


def _material_domain_heading(domain: Mapping[str, object]) -> str:
    domain_type, domain_name = _domain_parts(text_value(domain.get("name")) or "未知副本")
    city = _city_label(domain.get("city"))
    heading = f"{city} {domain_name}" if city else domain_name
    return f"{heading} - {domain_type}" if domain_type else heading


def _domain_parts(name: str) -> tuple[str, str]:
    left, separator, right = name.partition("：")
    if not separator:
        return "", name
    return left, right


def _weekday_label(day: str) -> str:
    label = WEEKDAY_LABELS.get(day, day)
    return label


def _city_label(value: object) -> str | None:
    if value in (None, ""):
        return None
    return CITY_LABELS.get(str(value))


def _signed_text(signed: bool | None) -> str:
    if signed is True:
        return "已签到"
    if signed is False:
        return "未签到"
    return "未知"


def _transformer_text(note: Mapping[str, object]) -> str:
    transformer = note.get("transformer")
    if not isinstance(transformer, Mapping):
        return "未知"
    recovery = transformer.get("recovery_time")
    if not isinstance(recovery, Mapping):
        return "未知"
    if bool_value(recovery.get("reached")):
        return "可用"
    day = int_value(recovery.get("Day"), -1)
    hour = int_value(recovery.get("Hour"))
    minute = int_value(recovery.get("Minute"))
    if day < 0:
        return "未知"
    return f"还需 {day}天{hour}小时{minute}分钟"


def _archon_quest_text(note: Mapping[str, object]) -> str:
    progress = note.get("archon_quest_progress")
    if not isinstance(progress, Mapping) or progress.get("wiki_url") == "False":
        return "未知"
    quests = sequence(progress.get("list"))
    done = (
        bool_value(progress.get("is_finish_all_interchapter"))
        and bool_value(progress.get("is_finish_all_mainline"))
        and bool_value(progress.get("is_open_archon_quest"))
        and not quests
    )
    if done:
        return "已全部完成"
    if quests and isinstance(quests[0], Mapping):
        chapter = quests[0].get("chapter_num") or quests[0].get("name") or "进行中"
        return str(chapter)
    return "未完成"


def _expeditions(note: Mapping[str, object]) -> list[Mapping[str, object]]:
    return [
        expedition
        for expedition in sequence(note.get("expeditions"))
        if isinstance(expedition, Mapping)
    ]


def _rank_stars(value: object) -> str:
    rank = int_value(value, -1)
    if rank <= 0:
        return ""
    rank = min(rank, 5)
    return "★" * rank + "☆" * (5 - rank)


def _seconds_to_hms(seconds: int) -> str:
    minutes, _seconds = divmod(max(seconds, 0), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{_seconds:02d}"
