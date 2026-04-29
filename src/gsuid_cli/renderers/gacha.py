from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from functools import lru_cache
from urllib.parse import quote

from PIL import Image, ImageDraw, ImageFilter

from gsuid_cli.renderers.common import (
    asset_path,
    crop_center,
    font,
    image_from_bytes,
    int_value,
    open_rgba,
    png_bytes,
    text_value,
)

TEXTURE = asset_path("gacha", "textures")
DATA = asset_path("gacha", "data")
PUBLIC_TEXTURE = asset_path("public", "textures")
GENSHINUID_RESOURCE_BASE = "https://example.test/GenshinUID/resource"
FALLBACK_CHARACTER_ID = "10000007"
FALLBACK_CHARACTER_ICON_URL = f"{GENSHINUID_RESOURCE_BASE}/chars/{FALLBACK_CHARACTER_ID}.png"

FIRST_COLOR = (29, 29, 29)
BROWN_COLOR = (41, 25, 0)
RED_COLOR = (255, 66, 66)
GREEN_COLOR = (74, 189, 119)
WIDTH = 950
SINGLE_Y = 150
GROUP_SPACING = 300

GROUPS = (
    ("新手祈愿", ("100",)),
    ("常驻祈愿", ("200",)),
    ("角色祈愿", ("301", "400")),
    ("武器祈愿", ("302",)),
    ("集录祈愿", ("500",)),
)
CHANGE_MAP = {
    "新手祈愿": "new",
    "常驻祈愿": "normal",
    "角色祈愿": "char",
    "武器祈愿": "weapon",
    "集录祈愿": "mix",
}
HOMO_TAG = ["非到极致", "运气不好", "平稳保底", "小欧一把", "欧狗在此"]
STANDARD_FIVE = {
    "莫娜",
    "迪卢克",
    "七七",
    "琴",
    "提纳里",
    "迪希雅",
    "梦见月瑞希",
    "Mona",
    "Diluc",
    "Qiqi",
    "Jean",
    "Tighnari",
    "Dehya",
    "Yumemizuki Mizuki",
    "阿莫斯之弓",
    "天空之翼",
    "四风原典",
    "天空之卷",
    "和璞鸢",
    "天空之脊",
    "狼的末路",
    "天空之傲",
    "风鹰剑",
    "天空之刃",
}


def gacha_summary_item_urls(items: Sequence[Mapping[str, object]]) -> list[str]:
    urls: list[str] = []
    for item in items:
        if str(item.get("rank_type") or "") != "5":
            continue
        for url in _icon_candidate_urls(item):
            if url not in urls:
                urls.append(url)
    return urls


def gacha_summary_missing_icon_count(
    items: Sequence[Mapping[str, object]],
    asset_images: Mapping[str, bytes],
) -> int:
    missing = 0
    for item in items:
        if str(item.get("rank_type") or "") != "5":
            continue
        if not _available_icon_url(_item_icon_urls(item), asset_images):
            missing += 1
    return missing


def render_gacha_summary_card(
    *,
    uid: str,
    items: Sequence[Mapping[str, object]],
    asset_images: Mapping[str, bytes] | None = None,
) -> bytes:
    asset_images = asset_images or {}
    groups = _gacha_groups(items)
    height = max(
        700,
        530
        + len(groups) * GROUP_SPACING
        + sum(_five_star_rows(group["five_stars"]) * SINGLE_Y for group in groups),
    )
    image = _light_background(WIDTH, height)
    avatar_title = open_rgba(TEXTURE / "avatar_title.png")
    image.paste(avatar_title, (0, 0), avatar_title)
    avatar = _fallback_avatar(uid)
    image.paste(avatar, (318, 83), avatar)
    draw = ImageDraw.Draw(image)
    draw.text((475, 454), f"UID {uid}", FIRST_COLOR, font(36), "mm")

    if not groups:
        draw.text((475, 610), "暂无祈愿数据", FIRST_COLOR, font(42), "mm")
        return png_bytes(image, rgb=True)

    y = 540
    for group in groups:
        title = _title_panel(uid, group)
        image.paste(title, (0, y), title)
        for index, item in enumerate(group["five_stars"]):
            card = _item_card(item, asset_images)
            x = (index % 6) * 138 + 60
            card_y = (index // 6) * SINGLE_Y + y + 275
            image.paste(card, (x, card_y), card)
        y += GROUP_SPACING + _five_star_rows(group["five_stars"]) * SINGLE_Y

    return png_bytes(image, rgb=True)


def _gacha_groups(items: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    for label, types in GROUPS:
        group_items = [item for item in items if str(item.get("gacha_type") or "") in types]
        if not group_items:
            continue
        groups.append(_group_summary(label, group_items))
    return groups


def _group_summary(
    label: str,
    items: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    ordered = sorted(items, key=lambda item: (_time_key(item), int_value(item.get("id"))))
    five_stars: list[dict[str, object]] = []
    interval_without_first: list[int] = []
    up_items_without_first: list[dict[str, object]] = []
    pity = 1
    seen_five = False
    short_count = 0
    long_count = 0
    total_gap_seconds = 0.0
    previous_time: datetime | None = None

    for item in ordered:
        current_time = _parse_time(item.get("time"))
        if previous_time is not None and current_time is not None:
            gap = (current_time - previous_time).total_seconds()
            total_gap_seconds += max(gap, 0)
            if gap <= 5000:
                short_count += 1
            elif gap >= 86400:
                long_count += 1
        if current_time is not None:
            previous_time = current_time

        if str(item.get("rank_type") or "") == "5":
            five_star = {**dict(item), "gacha_num": pity, "is_up": _is_up(item)}
            five_stars.append(five_star)
            if seen_five:
                interval_without_first.append(pity)
                if five_star["is_up"]:
                    up_items_without_first.append(five_star)
            seen_five = True
            pity = 1
        else:
            pity += 1

    total = len(ordered)
    avg = _average(interval_without_first)
    avg_up = (
        round(sum(interval_without_first) / len(up_items_without_first), 2)
        if up_items_without_first
        else 0
    )
    return {
        "label": label,
        "total_draws": total,
        "five_stars": five_stars,
        "remain": pity - 1,
        "avg": avg,
        "avg_up": avg_up,
        "time_range": _time_range(ordered),
        "type": _gacha_style(total, short_count, long_count, total_gap_seconds),
    }


def _title_panel(uid: str, group: Mapping[str, object]) -> Image.Image:
    title = open_rgba(TEXTURE / "gahca_title.png")
    level = _luck_level(group)
    emotion = _emotion_image(uid, str(group["label"]), level)
    title.paste(emotion, (703, 28), emotion)
    draw = ImageDraw.Draw(title)
    draw.text((778, 207), HOMO_TAG[level - 1], FIRST_COLOR, font(36), "mm")
    draw.text((69, 72), str(group["label"]), FIRST_COLOR, font(62), "lm")
    draw.text((68, 122), str(group["time_range"]), BROWN_COLOR, font(28), "lm")
    draw.text((123, 176), _number_text(group["avg"]), FIRST_COLOR, font(40), "mm")
    draw.text((272, 176), _number_text(group["avg_up"]), FIRST_COLOR, font(40), "mm")
    draw.text((424, 176), str(group["total_draws"]), FIRST_COLOR, font(40), "mm")
    draw.text((585, 176), str(group["type"]), FIRST_COLOR, font(40), "mm")
    draw.text((383, 85), str(group["remain"]), RED_COLOR, font(28), "mm")
    return title


def _item_card(
    item: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    card = open_rgba(TEXTURE / "item_bg.png")
    icon = _first_remote_icon(_icon_candidate_urls(item), asset_images)
    if icon is None:
        icon = _placeholder_icon()
    card.paste(icon, (1, 0), icon)
    draw = ImageDraw.Draw(card)
    gacha_num = int_value(item.get("gacha_num"))
    if gacha_num >= 81:
        text_color = RED_COLOR
    elif gacha_num <= 55:
        text_color = GREEN_COLOR
    else:
        text_color = BROWN_COLOR
    draw.text((55, 124), f"{gacha_num}抽", text_color, font(24), "mm")
    if item.get("is_up"):
        up = open_rgba(TEXTURE / "up.png")
        card.paste(up, (47, -2), up)
    return card


def _icon_candidate_urls(item: Mapping[str, object]) -> list[str]:
    urls = _item_icon_urls(item)
    if FALLBACK_CHARACTER_ICON_URL not in urls:
        urls.append(FALLBACK_CHARACTER_ICON_URL)
    return urls


def _item_icon_urls(item: Mapping[str, object]) -> list[str]:
    item_type = str(item.get("item_type") or "")
    if item_type in {"角色", "Character"}:
        item_ids = _character_ids(item)
        if not item_ids:
            return [FALLBACK_CHARACTER_ICON_URL]
        return [f"{GENSHINUID_RESOURCE_BASE}/chars/{item_id}.png" for item_id in item_ids]
    name = text_value(item.get("name"))
    if not name:
        return [FALLBACK_CHARACTER_ICON_URL]
    return [f"{GENSHINUID_RESOURCE_BASE}/weapon/{quote(name, safe='')}.png"]


def _available_icon_url(urls: Sequence[str], asset_images: Mapping[str, bytes]) -> str | None:
    for url in urls:
        if url in asset_images:
            return url
    return None


def _first_remote_icon(
    urls: Sequence[str],
    asset_images: Mapping[str, bytes],
) -> Image.Image | None:
    for url in urls:
        icon = _remote_icon(url, asset_images)
        if icon is not None:
            return icon
    return None


def _remote_icon(url: str | None, asset_images: Mapping[str, bytes]) -> Image.Image | None:
    if not url or url not in asset_images:
        return None
    return image_from_bytes(asset_images[url], (108, 108))


def _placeholder_icon() -> Image.Image:
    image = Image.new("RGBA", (108, 108), (219, 202, 170, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((3, 3, 105, 105), radius=16, outline=(255, 255, 255, 180), width=3)
    draw.text((54, 54), "?", fill=FIRST_COLOR, font=font(36), anchor="mm")
    return image


def _fallback_avatar(uid: str) -> Image.Image:
    avatar = Image.new("RGBA", (320, 320))
    draw = ImageDraw.Draw(avatar)
    draw.ellipse((10, 10, 310, 310), fill=(218, 205, 179, 255), outline="white", width=10)
    draw.text((160, 138), "UID", fill=FIRST_COLOR, font=font(54), anchor="mm")
    draw.text((160, 198), uid[-4:], fill=FIRST_COLOR, font=font(44), anchor="mm")
    return avatar


def _emotion_image(uid: str, label: str, level: int) -> Image.Image:
    folder = TEXTURE / str(level)
    options = sorted(folder.glob("*.png"))
    if not options:
        return Image.new("RGBA", (154, 154))
    digest = hashlib.sha256(f"{uid}:{label}:{level}".encode()).digest()
    source = open_rgba(options[digest[0] % len(options)])
    return source.resize((154, 154), Image.Resampling.LANCZOS)


def _light_background(width: int, height: int) -> Image.Image:
    source = Image.open(PUBLIC_TEXTURE / "bg.jpg")
    image = crop_center(source, width, height).filter(ImageFilter.GaussianBlur(radius=12))
    overlay = Image.new("RGBA", (width, height), (238, 231, 216, 185))
    image = image.convert("RGBA")
    image.paste(overlay, (0, 0), overlay)
    return image


def _luck_level(group: Mapping[str, object]) -> int:
    label = str(group["label"])
    value = float(group["avg_up"] if label != "常驻祈愿" else group["avg"])
    if label == "常驻祈愿":
        thresholds = [54, 61, 67, 73, 80]
    elif label == "武器祈愿":
        thresholds = [62, 75, 88, 99, 111]
    else:
        thresholds = [74, 87, 99, 105, 120]
    if value == 0:
        return 3
    for index, threshold in enumerate(thresholds):
        if value <= threshold:
            return 5 - index
    return 1


def _average(values: Sequence[int]) -> float | int:
    if not values:
        return 0
    return round(sum(values) / len(values), 2)


def _number_text(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _gacha_style(total: int, short_count: int, long_count: int, total_gap_seconds: float) -> str:
    if total <= 40:
        return "佛系型"
    if long_count / total >= 0.7:
        return "随缘型"
    if short_count / total >= 0.7:
        return "规划型"
    if total_gap_seconds / 30000 <= total:
        return "规划型" if long_count >= short_count else "氪金型"
    if total_gap_seconds / 32000 >= total * 2:
        return "仓鼠型"
    return "一般型"


def _time_range(items: Sequence[Mapping[str, object]]) -> str:
    if not items:
        return "暂未抽过卡!"
    first = text_value(items[0].get("time")) or ""
    last = text_value(items[-1].get("time")) or ""
    return f"{first}~{last}" if first and last else "暂未抽过卡!"


def _time_key(item: Mapping[str, object]) -> str:
    return text_value(item.get("time")) or ""


def _parse_time(value: object) -> datetime | None:
    text = text_value(value)
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _is_up(item: Mapping[str, object]) -> bool:
    return (text_value(item.get("name")) or "") not in STANDARD_FIVE


def _five_star_rows(items: object) -> int:
    if not isinstance(items, list) or not items:
        return 0
    return (len(items) + 5) // 6


def _character_ids(item: Mapping[str, object]) -> list[str]:
    ids: list[str] = []
    item_id = int_value(item.get("item_id"))
    if item_id >= 100000:
        ids.append(str(item_id))
    name = text_value(item.get("name"))
    if name:
        for avatar_id in _character_name_map().get(name, []):
            if avatar_id not in ids:
                ids.append(avatar_id)
    return ids


@lru_cache(maxsize=1)
def _character_name_map() -> dict[str, list[str]]:
    zh = json.loads((DATA / "avatarId2Name_mapping_6.5.0.json").read_text(encoding="utf-8"))
    mapping: dict[str, list[str]] = {}
    if isinstance(zh, dict):
        for avatar_id, name in zh.items():
            if isinstance(name, str):
                mapping.setdefault(name, []).append(str(avatar_id))
    return mapping
