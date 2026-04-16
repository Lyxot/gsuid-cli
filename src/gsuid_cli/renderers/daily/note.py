from __future__ import annotations

from collections.abc import Mapping

from PIL import Image, ImageDraw

from gsuid_cli.renderers.common import (
    asset_path,
    bool_value,
    font,
    image_from_bytes,
    int_value,
    open_rgba,
    png_bytes,
    sequence,
    text_value,
)

TEXTURE = asset_path("daily", "note", "textures")

FIRST_COLOR = (29, 29, 29)
SECOND_COLOR = (98, 98, 98)
GREEN_COLOR = (15, 196, 35)
RED_COLOR = (235, 61, 75)


def render_daily_note_card(
    *,
    uid: str,
    note: Mapping[str, object],
    nickname: str | None = None,
    level: object | None = None,
    signed: bool | None = None,
    expedition_avatar_images: Mapping[str, bytes] | None = None,
) -> bytes:
    """Render a GenshinUID-style daily note card as PNG bytes."""
    img = open_rgba(TEXTURE / "bg.png")
    draw = ImageDraw.Draw(img)

    current_resin = int_value(note.get("current_resin"))
    max_resin = max(int_value(note.get("max_resin"), 200), 1)
    resin_percent = min(max(current_resin / max_resin, 0), 1)
    resin_color = RED_COLOR if resin_percent > 0.8 else SECOND_COLOR
    resin_recovery_time = _seconds_to_hours(int_value(note.get("resin_recovery_time")))

    bars = [
        _home_coin_bar(note),
        _daily_task_bar(note),
        _weekly_discount_bar(note),
        _transformer_bar(note),
        _archon_quest_bar(note),
    ]

    expeditions = list(sequence(note.get("expeditions")))[:5]
    while len(expeditions) < 5:
        expeditions.append({})
    for index, expedition in enumerate(expeditions):
        task_img = _task_img(expedition, expedition_avatar_images or {})
        img.paste(task_img, (81 + index * 106, 1051), task_img)

    ring = Image.open(TEXTURE / "ring.apng")
    frame = min(round(resin_percent * 49), 49)
    try:
        ring.seek(frame)
    except EOFError:
        ring.seek(0)
    ring = ring.convert("RGBA")
    img.paste(ring, (0, -21), ring)

    draw.text(
        (350, 466),
        f"还剩{resin_recovery_time}",
        font=font(28),
        fill=resin_color,
        anchor="mm",
    )
    draw.text((350, 135), f"UID{uid}", fill=(38, 38, 38), font=font(26), anchor="mm")
    draw.text(
        (350, 354),
        _level_text(level),
        font=font(28),
        fill=SECOND_COLOR,
        anchor="mm",
    )
    draw.text(
        (350, 408),
        f"{current_resin}/{max_resin}",
        font=font(70),
        fill=FIRST_COLOR,
        anchor="mm",
    )
    draw.text((350, 89), nickname or "旅行者", fill=(13, 13, 13), font=font(58), anchor="mm")
    draw.text((350, 1235), "当前数据源：战绩", fill=(92, 92, 92), font=font(20), anchor="mm")

    for index, bar in enumerate(bars):
        img.paste(bar, (0, 642 + 78 * index), bar)

    sign_pic = open_rgba(TEXTURE / f"sign_{_sign_status(signed)}.png")
    img.paste(sign_pic, (275, 500), sign_pic)

    return png_bytes(img)


def _bar(status: str, text: str, data: str) -> Image.Image:
    bar = open_rgba(TEXTURE / "bar_bg.png")
    draw = ImageDraw.Draw(bar)
    draw.text((219, 50), text, fill=(31, 32, 26), font=font(32), anchor="lm")
    draw.text((367, 52), data, fill=(49, 49, 49), font=font(28), anchor="lm")
    icon = open_rgba(TEXTURE / f"{status}.png")
    bar.paste(icon, (151, 25), icon)
    return bar


def _home_coin_bar(note: Mapping[str, object]) -> Image.Image:
    current = int_value(note.get("current_home_coin"))
    maximum = int_value(note.get("max_home_coin"))
    status = "no" if maximum - current < 200 else "ok"
    return _bar(status, "洞天宝钱", f"{current} / {maximum}")


def _daily_task_bar(note: Mapping[str, object]) -> Image.Image:
    finished = int_value(note.get("finished_task_num"))
    total = int_value(note.get("total_task_num"))
    status = "ok" if bool_value(note.get("is_extra_task_reward_received")) else "no"
    return _bar(status, "完成委托", f"{finished} / {total}")


def _weekly_discount_bar(note: Mapping[str, object]) -> Image.Image:
    remaining = int_value(note.get("remain_resin_discount_num"), -99)
    limit = int_value(note.get("resin_discount_num_limit"))
    if remaining == -99:
        return _bar("un", "周本减半", "未知情况")
    return _bar("ok" if remaining == 0 else "no", "周本减半", f"{remaining} / {limit}")


def _transformer_bar(note: Mapping[str, object]) -> Image.Image:
    transformer = note.get("transformer")
    if not isinstance(transformer, Mapping):
        return _bar("un", "参量质变", "未知情况")
    recovery = transformer.get("recovery_time")
    if not isinstance(recovery, Mapping):
        return _bar("un", "参量质变", "未知情况")
    day = int_value(recovery.get("Day"), -99)
    hour = int_value(recovery.get("Hour"))
    if day == -99:
        return _bar("un", "参量质变", "未知情况")
    status = "no" if bool_value(recovery.get("reached")) else "ok"
    return _bar(status, "参量质变", f"还剩{day}天{hour}小时")


def _archon_quest_bar(note: Mapping[str, object]) -> Image.Image:
    progress = note.get("archon_quest_progress")
    if not isinstance(progress, Mapping) or progress.get("wiki_url") == "False":
        return _bar("un", "魔神任务", "数据未知...")
    quests = list(sequence(progress.get("list")))
    done = (
        bool_value(progress.get("is_finish_all_interchapter"))
        and bool_value(progress.get("is_finish_all_mainline"))
        and bool_value(progress.get("is_open_archon_quest"))
        and not quests
    )
    if done:
        return _bar("ok", "魔神任务", "已全部完成")
    if quests and isinstance(quests[0], Mapping):
        return _bar("no", "魔神任务", str(quests[0].get("chapter_num") or "暂未开启..."))
    return _bar("no", "魔神任务", "暂未开启...")


def _task_img(expedition: object, avatar_images: Mapping[str, bytes]) -> Image.Image:
    go_img = open_rgba(TEXTURE / "go_bg.png")
    avatar_url = _expedition_avatar_url(expedition)
    if not avatar_url:
        return go_img
    avatar_data = avatar_images.get(avatar_url)
    if avatar_data:
        avatar = image_from_bytes(avatar_data, (115, 115))
        if avatar is not None:
            go_img.paste(avatar, (0, -12), avatar)

    draw = ImageDraw.Draw(go_img)
    status = expedition.get("status") if isinstance(expedition, Mapping) else None
    if status == "Finished":
        text = "待收取"
        color = RED_COLOR
    else:
        text = "已派遣"
        color = GREEN_COLOR
    draw.text((60, 125), text, font=font(20), fill=color, anchor="mm")
    return go_img


def _expedition_avatar_url(expedition: object) -> str | None:
    if not isinstance(expedition, Mapping):
        return None
    return text_value(expedition.get("avatar_side_icon"))


def _seconds_to_hours(seconds: int) -> str:
    minutes, _seconds = divmod(max(seconds, 0), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}小时{minutes:02d}分"


def _level_text(level: object | None) -> str:
    if level is None:
        return "暂无数据"
    return f"探索等级{level}"


def _sign_status(signed: bool | None) -> str:
    if signed is True:
        return "ok"
    if signed is False:
        return "no"
    return "un"
