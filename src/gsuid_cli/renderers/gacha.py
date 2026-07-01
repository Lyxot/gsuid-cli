from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from functools import lru_cache
from urllib.parse import quote

from PIL import Image, ImageDraw

from gsuid_cli.renderers._text_helpers import _finish, _mapping_list
from gsuid_cli.renderers.common import (
    asset_path,
    draw_text_fit,
    font,
    image_from_bytes,
    int_value,
    open_rgba,
    png_bytes,
    text_value,
)
from gsuid_cli.renderers.player.summary import player_title_avatar_image
from gsuid_cli.renderers.progress.collection import _color_background
from gsuid_cli.text import t as _t

TEXTURE = asset_path("gacha", "textures")
DATA = asset_path("panel", "data")
GENSHINUID_RESOURCE_BASE = "genshinuid://resource"
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
    (_t("gsuid.renderers.gacha.53_14.8cbeebe7"), ("100",)),
    (_t("gsuid.renderers.gacha.51_16.3da2c5c8"), ("200",)),
    (_t("gsuid.renderers.gacha.58_27.abe86e08"), ("301",)),
    (_t("gsuid.renderers.gacha.50_14.59d0c22d"), ("302",)),
    (_t("gsuid.renderers.gacha.52_18.d1a59dd3"), ("500",)),
)
SUMMARY_GACHA_TYPE_BY_GACHA_TYPE = {"400": "301"}
BANNER_LABELS = {
    "all": _t("gsuid.renderers.gacha.48_11.4ff74d72"),
    "character": _t("gsuid.renderers.gacha.58_27.abe86e08"),
    "weapon": _t("gsuid.renderers.gacha.50_14.59d0c22d"),
    "standard": _t("gsuid.renderers.gacha.51_16.3da2c5c8"),
    "chronicled": _t("gsuid.renderers.gacha.52_18.d1a59dd3"),
    "novice": _t("gsuid.renderers.gacha.53_14.8cbeebe7"),
}
GACHA_TYPE_LABELS = {
    gacha_type: label for label, gacha_types in GROUPS for gacha_type in gacha_types
}
GACHA_TYPE_LABELS["400"] = _t("gsuid.renderers.gacha.58_27.abe86e08")
CHANGE_MAP = {
    _t("gsuid.renderers.gacha.53_14.8cbeebe7"): "new",
    _t("gsuid.renderers.gacha.51_16.3da2c5c8"): "normal",
    _t("gsuid.renderers.gacha.58_27.abe86e08"): "char",
    _t("gsuid.renderers.gacha.50_14.59d0c22d"): "weapon",
    _t("gsuid.renderers.gacha.52_18.d1a59dd3"): "mix",
}
HOMO_TAG = [
    _t("gsuid.renderers.gacha.66_12.d05c6e47"),
    _t("gsuid.renderers.gacha.66_28.1fddfc30"),
    _t("gsuid.renderers.gacha.66_44.c261ca9e"),
    _t("gsuid.renderers.gacha.66_60.74efbd8a"),
    _t("gsuid.renderers.gacha.66_76.212d89df"),
]
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


def render_gacha_summary_text(
    *,
    uid: str,
    banner: str,
    items: Sequence[Mapping[str, object]],
    summary: Mapping[str, object],
) -> str:
    lines = [_t("gsuid.renderers.gacha.102_13.15819363", _banner_label(banner)), f"UID: {uid}"]
    lines.append(
        _t("gsuid.renderers.gacha.103_17.dd5d446e", int_value(summary.get("total"), len(items)))
    )
    _append_counter_section(
        lines, _t("gsuid.renderers.gacha.104_35.657bf466"), _rank_counts(summary)
    )
    _append_counter_section(
        lines, _t("gsuid.renderers.gacha.105_35.c0a9a356"), _item_type_counts(summary)
    )

    groups = _gacha_groups(items)
    if not groups:
        lines.extend(["", _t("gsuid.renderers.gacha.279_30.e6d8f951")])
        return _finish(lines)

    lines.extend(["", _t("gsuid.renderers.gacha.112_22.ab116054")])
    for group in groups:
        label = text_value(group.get("label")) or _t("gsuid.renderers.gacha.649_51.e9731505")
        lines.append(
            _t(
                "gsuid.renderers.gacha.116_12.a436b58e",
                label,
                int_value(group.get("total_draws")),
                int_value(group.get("remain")),
            )
        )
        time_range = text_value(group.get("time_range"))
        if time_range and time_range != _t("gsuid.renderers.gacha.526_15.d3e8dac3"):
            lines.append(_t("gsuid.renderers.events.text.112_29.acab63aa", time_range))
        detail = _gacha_group_detail(group)
        if detail:
            lines.append(f"    {'，'.join(detail)}")
        five_stars = _mapping_list(group.get("five_stars"))
        if five_stars:
            lines.append(_t("gsuid.renderers.gacha.127_25.274421fe"))
            for item in five_stars:
                lines.append(f"      - {_five_star_text(label, item)}")
    return _finish(lines)


def render_gacha_refresh_text(data: Mapping[str, object]) -> str:
    lines = [_t("gsuid.renderers.gacha.134_13.fe3ee11b"), f"UID: {data.get('uid', '-')}"]
    credential_source = text_value(data.get("credential_source"))
    if credential_source:
        lines.append(_t("gsuid.renderers.gacha.137_21.03d4aea9", _source_label(credential_source)))
    storage_backend = text_value(data.get("storage_backend"))
    if storage_backend:
        lines.append(_t("gsuid.renderers.gacha.140_21.5a046e87", storage_backend))
    lines.extend(
        [
            _t("gsuid.renderers.gacha.143_12.45b2a93f", int_value(data.get("fetched"))),
            _t("gsuid.renderers.gacha.144_12.ee12340d", int_value(data.get("inserted"))),
            _t("gsuid.renderers.gacha.145_12.7cffc60f", int_value(data.get("duplicates"))),
        ]
    )
    rows = _mapping_list(data.get("types"))
    if rows:
        lines.extend(["", _t("gsuid.renderers.gacha.150_26.2ce4de9c")])
        for row in rows:
            lines.append(
                _t(
                    "gsuid.renderers.gacha.153_16.20b70766",
                    _gacha_type_label(row.get("gacha_type")),
                    int_value(row.get("fetched")),
                    int_value(row.get("inserted")),
                    int_value(row.get("duplicates")),
                )
            )
    return _finish(lines)


def render_gacha_import_text(data: Mapping[str, object]) -> str:
    return _finish(
        [
            _t("gsuid.renderers.gacha.164_12.3f5f2e07"),
            f"UID: {data.get('uid', '-')}",
            _t("gsuid.renderers.gacha.182_8.3d8ab093", text_value(data.get("format")) or "-"),
            _t("gsuid.renderers.events.text.88_21.d282f3df", int_value(data.get("total"))),
            _t("gsuid.renderers.gacha.144_12.ee12340d", int_value(data.get("inserted"))),
            _t("gsuid.renderers.gacha.145_12.7cffc60f", int_value(data.get("duplicates"))),
        ]
    )


def render_gacha_export_text(
    data: Mapping[str, object],
    *,
    artifact_path: object = None,
) -> str:
    lines = [
        _t("gsuid.commands.gacha.1161_23.3ba080fb"),
        f"UID: {data.get('uid', '-')}",
        _t("gsuid.renderers.gacha.182_8.3d8ab093", text_value(data.get("format")) or "-"),
        _t("gsuid.renderers.challenge.text.186_8.a63927f2", int_value(data.get("count"))),
        _t(
            "gsuid.renderers.gacha.184_8.82609e71",
            _t("gsuid.common.exported")
            if data.get("exported")
            else _t("gsuid.common.not_exported"),
        ),
    ]
    path = text_value(artifact_path)
    if path:
        lines.append(_t("gsuid.renderers.gacha.188_21.1133624e", path))
    return _finish(lines)


def render_gacha_authkey_text(
    data: Mapping[str, object],
    *,
    refreshed: bool = False,
) -> str:
    lines = [
        _t("gsuid.renderers.gacha.197_13.c039e0ea")
        if not refreshed
        else _t("gsuid.renderers.gacha.197_56.94c980b5")
    ]
    if data.get("uid") not in (None, ""):
        lines.append(f"UID: {data['uid']}")
    lines.append(
        _t(
            "gsuid.renderers.gacha.184_8.82609e71",
            _t("gsuid.common.available")
            if data.get("available")
            else _t("gsuid.common.not_available"),
        )
    )
    if refreshed:
        lines.append(
            _t(
                "gsuid.renderers.gacha.202_21.cf53b8f1",
                _t("gsuid.common.saved") if data.get("stored") else _t("gsuid.common.not_saved"),
            )
        )
    credential_source = text_value(data.get("source"))
    if credential_source:
        lines.append(_t("gsuid.renderers.gacha.137_21.03d4aea9", _source_label(credential_source)))
    storage_backend = text_value(data.get("storage_backend"))
    if storage_backend:
        lines.append(_t("gsuid.renderers.gacha.140_21.5a046e87", storage_backend))
    sources = data.get("credential_sources")
    if isinstance(sources, Mapping):
        cookie = text_value(sources.get("cookie"))
        stoken = text_value(sources.get("stoken"))
        if cookie or stoken:
            lines.append(
                _t(
                    "gsuid.renderers.gacha.215_16.f7a58d47",
                    _source_label(cookie) if cookie else "-",
                    _source_label(stoken) if stoken else "-",
                )
            )
    lines.append(_t("gsuid.renderers.gacha.219_17.9cfef6ee"))
    return _finish(lines)


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
    summary: Mapping[str, object] | None = None,
    title_avatar_url: str | None = None,
) -> bytes:
    asset_images = asset_images or {}
    summary = summary or {}
    groups = _gacha_groups(items)
    height = max(
        700,
        530
        + len(groups) * GROUP_SPACING
        + sum(_five_star_rows(group["five_stars"]) * SINGLE_Y for group in groups),
    )
    image = _color_background(WIDTH, height)
    avatar_title = open_rgba(TEXTURE / "avatar_title.png")
    image.paste(avatar_title, (0, 0), avatar_title)
    avatar = player_title_avatar_image(
        summary=_profile_avatar_summary(summary, title_avatar_url),
        asset_images=asset_images,
        size=264,
        title_avatar_url=title_avatar_url,
        with_ring=True,
    )
    image.paste(avatar, (343, 68), avatar)
    draw = ImageDraw.Draw(image)
    draw.text((475, 454), f"UID {uid}", FIRST_COLOR, font(36), "mm")

    if not groups:
        draw.text(
            (475, 610), _t("gsuid.renderers.gacha.279_30.e6d8f951"), FIRST_COLOR, font(42), "mm"
        )
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
        group_items = [item for item in items if _summary_gacha_type(item) in types]
        if not group_items:
            continue
        groups.append(_group_summary(label, group_items))
    return groups


def _profile_avatar_summary(
    summary: Mapping[str, object],
    title_avatar_url: str | None,
) -> Mapping[str, object]:
    if not title_avatar_url:
        return summary
    role = summary.get("role")
    if not isinstance(role, Mapping) or "avatar_icon" not in role:
        return summary
    role_without_avatar = dict(role)
    role_without_avatar.pop("avatar_icon", None)
    return {**dict(summary), "role": role_without_avatar}


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
    title = _title_panel_background()
    level = _luck_level(group)
    emotion = _emotion_image(uid, str(group["label"]), level)
    title.paste(emotion, (703, 28), emotion)
    draw = ImageDraw.Draw(title)
    draw.text((778, 207), HOMO_TAG[level - 1], FIRST_COLOR, font(36), "mm")
    draw.text((69, 72), str(group["label"]), FIRST_COLOR, font(62), "lm")
    draw.text((68, 122), str(group["time_range"]), BROWN_COLOR, font(28), "lm")
    draw_text_fit(
        draw,
        (500, 85),
        _t("gsuid.renderers.gacha.summary.pity", group["remain"]),
        fill=RED_COLOR,
        size=28,
        max_width=300,
        min_size=20,
    )
    value_positions = (
        (123, _number_text(group["avg"]), _t("gsuid.renderers.gacha.summary.avg")),
        (272, _number_text(group["avg_up"]), _t("gsuid.renderers.gacha.summary.avg_up")),
        (424, str(group["total_draws"]), _t("gsuid.renderers.gacha.summary.total")),
        (585, str(group["type"]), _t("gsuid.renderers.gacha.summary.type")),
    )
    for x, value, label in value_positions:
        draw.text((x, 176), value, FIRST_COLOR, font(40), "mm")
        draw_text_fit(
            draw,
            (x, 210),
            label,
            fill=FIRST_COLOR,
            size=24,
            max_width=130,
            min_size=16,
        )
    return title


def _title_panel_background() -> Image.Image:
    image = Image.new("RGBA", (950, 260), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((32, 15, 912, 245), radius=42, fill=(255, 255, 255, 250))
    return image


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
    draw.text(
        (55, 124),
        _t("gsuid.renderers.gacha.412_25.b3cd15c5", gacha_num),
        text_color,
        font(24),
        "mm",
    )
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
    if item_type in {_t("gsuid.renderers.gacha.663_15.6b26695e"), "Character"}:
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


def _emotion_image(uid: str, label: str, level: int) -> Image.Image:
    folder = TEXTURE / str(level)
    options = sorted(folder.glob("*.png"))
    if not options:
        return Image.new("RGBA", (154, 154))
    digest = hashlib.sha256(f"{uid}:{label}:{level}".encode()).digest()
    source = open_rgba(options[digest[0] % len(options)])
    return source.resize((154, 154), Image.Resampling.LANCZOS)


def _luck_level(group: Mapping[str, object]) -> int:
    label = str(group["label"])
    value = float(
        group["avg_up"] if label != _t("gsuid.renderers.gacha.51_16.3da2c5c8") else group["avg"]
    )
    if label == _t("gsuid.renderers.gacha.51_16.3da2c5c8"):
        thresholds = [54, 61, 67, 73, 80]
    elif label == _t("gsuid.renderers.gacha.50_14.59d0c22d"):
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
        return _t("gsuid.renderers.gacha.512_15.75698459")
    if long_count / total >= 0.7:
        return _t("gsuid.renderers.gacha.514_15.769530ea")
    if short_count / total >= 0.7:
        return _t("gsuid.renderers.gacha.516_15.1454a819")
    if total_gap_seconds / 30000 <= total:
        return (
            _t("gsuid.renderers.gacha.516_15.1454a819")
            if long_count >= short_count
            else _t("gsuid.renderers.gacha.518_61.9be7913b")
        )
    if total_gap_seconds / 32000 >= total * 2:
        return _t("gsuid.renderers.gacha.520_15.f22fdf07")
    return _t("gsuid.renderers.gacha.521_11.73da0e4f")


def _time_range(items: Sequence[Mapping[str, object]]) -> str:
    if not items:
        return _t("gsuid.renderers.gacha.526_15.d3e8dac3")
    first = text_value(items[0].get("time")) or ""
    last = text_value(items[-1].get("time")) or ""
    return f"{first}~{last}" if first and last else _t("gsuid.renderers.gacha.526_15.d3e8dac3")


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
    zh = json.loads((DATA / "avatarId2Name_mapping_6.7.0.json").read_text(encoding="utf-8"))
    mapping: dict[str, list[str]] = {}
    if isinstance(zh, dict):
        for avatar_id, name in zh.items():
            if isinstance(name, str):
                mapping.setdefault(name, []).append(str(avatar_id))
    return mapping


def _append_counter_section(
    lines: list[str],
    title: str,
    values: Sequence[tuple[str, int]],
) -> None:
    rows = [f"  - {label}: {count}" for label, count in values if count]
    if rows:
        lines.extend(["", f"{title}:"])
        lines.extend(rows)


def _rank_counts(summary: Mapping[str, object]) -> list[tuple[str, int]]:
    value = summary.get("by_rank")
    if not isinstance(value, Mapping):
        return []
    rows = []
    for rank, count in value.items():
        rank_text = text_value(rank)
        if rank_text:
            rows.append((_t("gsuid.renderers.gacha.599_25.931af952", rank_text), int_value(count)))
    return sorted(
        rows,
        key=lambda row: int_value(row[0].removesuffix(_t("gsuid.renderers.gacha.600_70.92ae747c"))),
        reverse=True,
    )


def _item_type_counts(summary: Mapping[str, object]) -> list[tuple[str, int]]:
    value = summary.get("by_item_type")
    if not isinstance(value, Mapping):
        return []
    rows = []
    for item_type, count in value.items():
        label = _item_type_label(item_type)
        if label:
            rows.append((label, int_value(count)))
    return rows


def _gacha_group_detail(group: Mapping[str, object]) -> list[str]:
    detail = []
    avg = group.get("avg")
    if avg not in (None, "", 0):
        detail.append(_t("gsuid.renderers.gacha.619_22.14349c5c", _number_text(avg)))
    avg_up = group.get("avg_up")
    if group.get("label") != _t("gsuid.renderers.gacha.51_16.3da2c5c8") and avg_up not in (
        None,
        "",
        0,
    ):
        detail.append(_t("gsuid.renderers.gacha.622_22.a370ca55", _number_text(avg_up)))
    style = text_value(group.get("type"))
    if style:
        detail.append(_t("gsuid.renderers.gacha.625_22.9a18408b", style))
    return detail


def _five_star_text(group_label: str, item: Mapping[str, object]) -> str:
    name = text_value(item.get("name")) or _t("gsuid.renderers.gacha.630_43.988a9ca3")
    parts = [
        name,
        _t("gsuid.renderers.gacha.412_25.b3cd15c5", int_value(item.get("gacha_num"))),
        _item_type_label(item.get("item_type")),
    ]
    time_text = text_value(item.get("time"))
    if time_text:
        parts.append(time_text)
    if group_label != _t("gsuid.renderers.gacha.51_16.3da2c5c8"):
        parts.append(
            _t("gsuid.renderers.gacha.640_21.70c31580")
            if item.get("is_up")
            else _t("gsuid.renderers.gacha.640_56.08a4dc38")
        )
    return "，".join(part for part in parts if part)


def _banner_label(value: object) -> str:
    return BANNER_LABELS.get(str(value or ""), _t("gsuid.renderers.gacha.48_11.4ff74d72"))


def _gacha_type_label(value: object) -> str:
    return GACHA_TYPE_LABELS.get(str(value or ""), _t("gsuid.renderers.gacha.649_51.e9731505"))


def _summary_gacha_type(item: Mapping[str, object]) -> str:
    uigf_gacha_type = text_value(item.get("uigf_gacha_type"))
    if uigf_gacha_type:
        return uigf_gacha_type
    gacha_type = text_value(item.get("gacha_type")) or ""
    return SUMMARY_GACHA_TYPE_BY_GACHA_TYPE.get(gacha_type, gacha_type)


def _item_type_label(value: object) -> str:
    text = text_value(value)
    if text in {"Character", _t("gsuid.renderers.gacha.663_15.6b26695e")}:
        return _t("gsuid.renderers.gacha.663_15.6b26695e")
    if text in {"Weapon", _t("gsuid.commands.panel.impl.988_24.6f0f16e0")}:
        return _t("gsuid.commands.panel.impl.988_24.6f0f16e0")
    return text or ""


def _source_label(value: object) -> str:
    text = text_value(value)
    if text == "keyring":
        return _t("gsuid.renderers.gacha.672_15.8209f138")
    if text == "profile":
        return _t("gsuid.renderers.gacha.674_15.d7d7ce79")
    if text == "environment":
        return _t("gsuid.renderers.gacha.676_15.8da07705")
    return text or "-"
