from __future__ import annotations

from collections.abc import Mapping, Sequence

from gsuid_cli.renderers._text_helpers import _finish
from gsuid_cli.renderers.common import bool_value, int_value, sequence, text_value
from gsuid_cli.text import t as _t

WEEKDAY_LABELS = {
    "monday": _t("gsuid.renderers.daily.materials.146_18.792c34e7"),
    "tuesday": _t("gsuid.renderers.daily.materials.147_19.8f03441d"),
    "wednesday": _t("gsuid.renderers.daily.materials.148_21.25455673"),
    "thursday": _t("gsuid.renderers.daily.materials.149_20.18f1fd9e"),
    "friday": _t("gsuid.renderers.daily.materials.150_18.4344fc13"),
    "saturday": _t("gsuid.renderers.daily.materials.151_20.f0c6199a"),
    "sunday": _t("gsuid.renderers.daily.materials.152_18.c3405710"),
}
CITY_LABELS = {
    "1": _t("gsuid.renderers.daily.text.18_9.4e2f394b"),
    "2": _t("gsuid.renderers.daily.text.19_9.cf9effa7"),
    "3": _t("gsuid.renderers.daily.text.20_9.60582a7f"),
    "4": _t("gsuid.renderers.daily.text.21_9.d6e52915"),
    "5": _t("gsuid.renderers.daily.text.22_9.71f4594b"),
    "6": _t("gsuid.renderers.daily.text.23_9.3fd1306d"),
    "7": _t("gsuid.renderers.daily.text.24_9.b6b55ca3"),
}


def render_daily_materials_text(
    *,
    day: str,
    domains: Sequence[Mapping[str, object]],
    date: object | None = None,
) -> str:
    del date
    lines = [_t("gsuid.renderers.daily.text.35_13.ffe3b530", _weekday_label(day))]

    for domain in domains:
        lines.append("")
        lines.append(_material_domain_heading(domain))

        items = _items(domain)
        if not items:
            lines.append(_t("gsuid.renderers.daily.text.43_25.263187e3"))
            continue
        lines.append(_t("gsuid.renderers.daily.text.45_21.215ce1f0"))
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
    title = (
        _t("gsuid.renderers.daily.text.61_12.6d5654dc", nickname)
        if nickname
        else _t("gsuid.renderers.daily.text.61_58.0e22dc98")
    )
    lines = [
        title,
        f"UID: {uid}",
        _t("gsuid.renderers.daily.text.62_35.76d0123e", _signed_text(signed)),
    ]

    current_resin = int_value(note.get("current_resin"))
    max_resin = int_value(note.get("max_resin"), 200)
    resin_recovery = int_value(note.get("resin_recovery_time"))
    resin_line = f"{current_resin}/{max_resin}"
    if current_resin < max_resin and resin_recovery > 0:
        resin_line += _t(
            "gsuid.renderers.daily.text.69_22.8d62ff57", _seconds_to_hms(resin_recovery)
        )
    lines.extend(["", _t("gsuid.renderers.daily.text.70_22.c83a9fcf", resin_line)])

    finished_tasks = int_value(note.get("finished_task_num"))
    total_tasks = int_value(note.get("total_task_num"))
    reward = (
        _t("gsuid.renderers.daily.text.74_13.61933bfc")
        if bool_value(note.get("is_extra_task_reward_received"))
        else _t("gsuid.renderers.daily.text.74_87.98ba7709")
    )
    lines.append(
        _t("gsuid.renderers.daily.text.75_17.d9ac7203", finished_tasks, total_tasks, reward)
    )

    remaining_discount = int_value(note.get("remain_resin_discount_num"), -1)
    discount_limit = int_value(note.get("resin_discount_num_limit"))
    if remaining_discount >= 0:
        used_discount = max(discount_limit - remaining_discount, 0)
        discount_text = _t(
            "gsuid.renderers.daily.text.81_24.d7c380e7",
            used_discount,
            discount_limit,
            remaining_discount,
        )
    else:
        discount_text = _t("gsuid.renderers.daily.text.211_11.d9c32a4c")
    lines.append(_t("gsuid.renderers.daily.text.84_17.abc2823f", discount_text))

    current_coin = int_value(note.get("current_home_coin"))
    max_coin = int_value(note.get("max_home_coin"))
    coin_recovery = int_value(note.get("home_coin_recovery_time"))
    coin_line = f"{current_coin}/{max_coin}"
    if current_coin < max_coin and coin_recovery > 0:
        coin_line += _t("gsuid.renderers.daily.text.69_22.8d62ff57", _seconds_to_hms(coin_recovery))
    lines.append(_t("gsuid.renderers.daily.text.92_17.dffbd2ff", coin_line))

    lines.append(_t("gsuid.renderers.daily.text.94_17.f9c72f28", _transformer_text(note)))
    lines.append(_t("gsuid.renderers.daily.text.95_17.5dbc1e23", _archon_quest_text(note)))

    expeditions = _expeditions(note)
    finished = sum(1 for expedition in expeditions if expedition.get("status") == "Finished")
    current_expedition_num = int_value(note.get("current_expedition_num"), len(expeditions))
    max_expedition_num = int_value(note.get("max_expedition_num"), len(expeditions))
    lines.append(
        _t(
            "gsuid.renderers.daily.text.101_17.e61be7bc",
            current_expedition_num,
            max_expedition_num,
            finished,
        )
    )

    return _finish(lines)


def render_daily_signin_text(data: Mapping[str, object]) -> str:
    lines = []
    if data.get("uid") not in (None, ""):
        lines.append(f"UID: {data['uid']}")

    already_signed = bool_value(data.get("already_signed"))
    signed = bool_value(data.get("signed"))
    if already_signed:
        status = _t("gsuid.renderers.daily.text.114_17.05ef4d80")
    elif signed:
        status = _t("gsuid.renderers.daily.text.116_17.d7ecc42e")
    else:
        status = _t("gsuid.renderers.daily.text.118_17.4e5a58e1")
    lines.append(status)
    return _finish(lines)


def render_daily_bbs_coin_text(data: Mapping[str, object]) -> str:
    lines = [_t("gsuid.renderers.daily.text.124_13.f84856c6")]
    if data.get("uid") not in (None, ""):
        lines.append(f"UID: {data['uid']}")
    if data.get("points_received") is not None:
        lines.append(_t("gsuid.renderers.daily.text.128_21.057bef1b", data["points_received"]))

    tasks = sequence(data.get("tasks"))
    lines.append("")
    lines.append(_t("gsuid.renderers.daily.text.132_17.3172b317"))
    if tasks:
        for task in tasks:
            if isinstance(task, Mapping):
                lines.append(f"  - {_bbs_task_text(task)}")
            else:
                lines.append(f"  - {task}")
    else:
        lines.append(_t("gsuid.renderers.daily.text.140_21.1bbd41ae"))

    failures = sequence(data.get("failures"))
    if failures:
        lines.append("")
        lines.append(_t("gsuid.renderers.daily.text.145_21.204db865"))
        for failure in failures:
            lines.append(f"  - {failure}")

    limitations = sequence(data.get("source_limitations"))
    if limitations:
        lines.append("")
        lines.append(_t("gsuid.renderers.daily.text.152_21.317f24d3"))
        for limitation in limitations:
            lines.append(f"  - {limitation}")

    return _finish(lines)


def _bbs_task_text(task: Mapping[str, object]) -> str:
    label = (
        text_value(task.get("label"))
        or text_value(task.get("key"))
        or _t("gsuid.renderers.daily.text.132_17.3172b317")
    )
    status = (
        _t("gsuid.renderers.daily.text.161_13.e99b48a2")
        if bool_value(task.get("completed"))
        else _t("gsuid.renderers.daily.text.247_11.b61b08ae")
    )
    happened = int_value(task.get("happened_times"), -1)
    remaining = int_value(task.get("remaining"), -1)
    details = [status]
    if happened >= 0 and remaining >= 0:
        details.append(_t("gsuid.renderers.daily.text.166_23.9ba1dc1c", happened, remaining))
    return f"{label}: {'，'.join(details)}"


def _items(domain: Mapping[str, object]) -> list[Mapping[str, object]]:
    value = domain.get("items")
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _material_item_text(item: Mapping[str, object]) -> str:
    name = text_value(item.get("name")) or _t("gsuid.renderers.daily.text.211_11.d9c32a4c")
    stars = _rank_stars(item.get("rank"))
    return f"{name} {stars}" if stars else name


def _material_domain_heading(domain: Mapping[str, object]) -> str:
    domain_type, domain_name = _domain_parts(
        text_value(domain.get("name")) or _t("gsuid.renderers.daily.text.182_79.e07dca5d")
    )
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
        return _t("gsuid.renderers.daily.text.208_15.26cc11aa")
    if signed is False:
        return _t("gsuid.renderers.daily.text.210_15.48ab7a95")
    return _t("gsuid.renderers.daily.text.211_11.d9c32a4c")


def _transformer_text(note: Mapping[str, object]) -> str:
    transformer = note.get("transformer")
    if not isinstance(transformer, Mapping):
        return _t("gsuid.renderers.daily.text.211_11.d9c32a4c")
    recovery = transformer.get("recovery_time")
    if not isinstance(recovery, Mapping):
        return _t("gsuid.renderers.daily.text.211_11.d9c32a4c")
    if bool_value(recovery.get("reached")):
        return _t("gsuid.renderers.daily.text.222_15.e91365cf")
    day = int_value(recovery.get("Day"), -1)
    hour = int_value(recovery.get("Hour"))
    minute = int_value(recovery.get("Minute"))
    if day < 0:
        return _t("gsuid.renderers.daily.text.211_11.d9c32a4c")
    return _t("gsuid.renderers.daily.text.228_11.bc4b965b", day, hour, minute)


def _archon_quest_text(note: Mapping[str, object]) -> str:
    progress = note.get("archon_quest_progress")
    if not isinstance(progress, Mapping) or progress.get("wiki_url") == "False":
        return _t("gsuid.renderers.daily.text.211_11.d9c32a4c")
    quests = sequence(progress.get("list"))
    done = (
        bool_value(progress.get("is_finish_all_interchapter"))
        and bool_value(progress.get("is_finish_all_mainline"))
        and bool_value(progress.get("is_open_archon_quest"))
        and not quests
    )
    if done:
        return _t("gsuid.renderers.daily.note.163_42.1f8000f4")
    if quests and isinstance(quests[0], Mapping):
        chapter = (
            quests[0].get("chapter_num")
            or quests[0].get("name")
            or _t("gsuid.renderers.daily.text.245_75.6f1972e4")
        )
        return str(chapter)
    return _t("gsuid.renderers.daily.text.247_11.b61b08ae")


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
