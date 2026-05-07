from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from functools import lru_cache
from urllib.parse import quote

from PIL import Image, ImageDraw

from gsuid_cli.renderers.common import (
    asset_path,
    font,
    image_from_bytes,
    int_value,
    open_rgba,
    png_bytes,
    text_value,
)
from gsuid_cli.renderers.player.summary import player_title_avatar_image
from gsuid_cli.renderers.progress.collection import _color_background

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
    ("新手祈愿", ("100",)),
    ("常驻祈愿", ("200",)),
    ("角色祈愿", ("301",)),
    ("武器祈愿", ("302",)),
    ("集录祈愿", ("500",)),
)
SUMMARY_GACHA_TYPE_BY_GACHA_TYPE = {"400": "301"}
BANNER_LABELS = {
    "all": "全部祈愿",
    "character": "角色祈愿",
    "weapon": "武器祈愿",
    "standard": "常驻祈愿",
    "chronicled": "集录祈愿",
    "novice": "新手祈愿",
}
GACHA_TYPE_LABELS = {
    gacha_type: label for label, gacha_types in GROUPS for gacha_type in gacha_types
}
GACHA_TYPE_LABELS["400"] = "角色祈愿"
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


def render_gacha_summary_text(
    *,
    uid: str,
    banner: str,
    items: Sequence[Mapping[str, object]],
    summary: Mapping[str, object],
) -> str:
    lines = [f"祈愿统计 - {_banner_label(banner)}", f"UID: {uid}"]
    lines.append(f"总抽数: {int_value(summary.get('total'), len(items))}")
    _append_counter_section(lines, "按星级", _rank_counts(summary))
    _append_counter_section(lines, "按类型", _item_type_counts(summary))

    groups = _gacha_groups(items)
    if not groups:
        lines.extend(["", "暂无祈愿数据"])
        return _finish(lines)

    lines.extend(["", "祈愿池:"])
    for group in groups:
        label = text_value(group.get("label")) or "未知祈愿"
        lines.append(
            f"  - {label}: {int_value(group.get('total_draws'))}抽，"
            f"距离五星 {int_value(group.get('remain'))}抽"
        )
        time_range = text_value(group.get("time_range"))
        if time_range and time_range != "暂未抽过卡!":
            lines.append(f"    时间: {time_range}")
        detail = _gacha_group_detail(group)
        if detail:
            lines.append(f"    {'，'.join(detail)}")
        five_stars = _mapping_list(group.get("five_stars"))
        if five_stars:
            lines.append("    五星记录:")
            for item in five_stars:
                lines.append(f"      - {_five_star_text(label, item)}")
    return _finish(lines)


def render_gacha_refresh_text(data: Mapping[str, object]) -> str:
    lines = ["祈愿记录刷新", f"UID: {data.get('uid', '-')}"]
    credential_source = text_value(data.get("credential_source"))
    if credential_source:
        lines.append(f"凭据来源: {_source_label(credential_source)}")
    storage_backend = text_value(data.get("storage_backend"))
    if storage_backend:
        lines.append(f"存储后端: {storage_backend}")
    lines.extend(
        [
            f"获取: {int_value(data.get('fetched'))}",
            f"新增: {int_value(data.get('inserted'))}",
            f"重复: {int_value(data.get('duplicates'))}",
        ]
    )
    rows = _mapping_list(data.get("types"))
    if rows:
        lines.extend(["", "分类型:"])
        for row in rows:
            lines.append(
                f"  - {_gacha_type_label(row.get('gacha_type'))}: "
                f"获取 {int_value(row.get('fetched'))}，"
                f"新增 {int_value(row.get('inserted'))}，"
                f"重复 {int_value(row.get('duplicates'))}"
            )
    return _finish(lines)


def render_gacha_import_text(data: Mapping[str, object]) -> str:
    return _finish(
        [
            "祈愿记录导入",
            f"UID: {data.get('uid', '-')}",
            f"格式: {text_value(data.get('format')) or '-'}",
            f"总数: {int_value(data.get('total'))}",
            f"新增: {int_value(data.get('inserted'))}",
            f"重复: {int_value(data.get('duplicates'))}",
        ]
    )


def render_gacha_export_text(
    data: Mapping[str, object],
    *,
    artifact_path: object = None,
) -> str:
    lines = [
        "祈愿记录导出",
        f"UID: {data.get('uid', '-')}",
        f"格式: {text_value(data.get('format')) or '-'}",
        f"数量: {int_value(data.get('count'))}",
        f"状态: {'已导出' if data.get('exported') else '未导出'}",
    ]
    path = text_value(artifact_path)
    if path:
        lines.append(f"文件: {path}")
    return _finish(lines)


def render_gacha_authkey_text(
    data: Mapping[str, object],
    *,
    refreshed: bool = False,
) -> str:
    lines = ["祈愿链接凭据" if not refreshed else "祈愿链接凭据刷新"]
    if data.get("uid") not in (None, ""):
        lines.append(f"UID: {data['uid']}")
    lines.append(f"状态: {'可用' if data.get('available') else '不可用'}")
    if refreshed:
        lines.append(f"保存: {'已保存' if data.get('stored') else '未保存'}")
    credential_source = text_value(data.get("source"))
    if credential_source:
        lines.append(f"凭据来源: {_source_label(credential_source)}")
    storage_backend = text_value(data.get("storage_backend"))
    if storage_backend:
        lines.append(f"存储后端: {storage_backend}")
    sources = data.get("credential_sources")
    if isinstance(sources, Mapping):
        cookie = text_value(sources.get("cookie"))
        stoken = text_value(sources.get("stoken"))
        if cookie or stoken:
            lines.append(
                "生成凭据: "
                f"Cookie {_source_label(cookie) if cookie else '-'}，"
                f"Stoken {_source_label(stoken) if stoken else '-'}"
            )
    lines.append("内容: 已隐藏")
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
            rows.append((f"{rank_text}星", int_value(count)))
    return sorted(rows, key=lambda row: int_value(row[0].removesuffix("星")), reverse=True)


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
        detail.append(f"五星平均 {_number_text(avg)}抽")
    avg_up = group.get("avg_up")
    if group.get("label") != "常驻祈愿" and avg_up not in (None, "", 0):
        detail.append(f"限定平均 {_number_text(avg_up)}抽")
    style = text_value(group.get("type"))
    if style:
        detail.append(f"类型 {style}")
    return detail


def _five_star_text(group_label: str, item: Mapping[str, object]) -> str:
    name = text_value(item.get("name")) or "未知物品"
    parts = [
        name,
        f"{int_value(item.get('gacha_num'))}抽",
        _item_type_label(item.get("item_type")),
    ]
    time_text = text_value(item.get("time"))
    if time_text:
        parts.append(time_text)
    if group_label != "常驻祈愿":
        parts.append("限定" if item.get("is_up") else "常驻")
    return "，".join(part for part in parts if part)


def _banner_label(value: object) -> str:
    return BANNER_LABELS.get(str(value or ""), "全部祈愿")


def _gacha_type_label(value: object) -> str:
    return GACHA_TYPE_LABELS.get(str(value or ""), "未知祈愿")


def _summary_gacha_type(item: Mapping[str, object]) -> str:
    uigf_gacha_type = text_value(item.get("uigf_gacha_type"))
    if uigf_gacha_type:
        return uigf_gacha_type
    gacha_type = text_value(item.get("gacha_type")) or ""
    return SUMMARY_GACHA_TYPE_BY_GACHA_TYPE.get(gacha_type, gacha_type)


def _item_type_label(value: object) -> str:
    text = text_value(value)
    if text in {"Character", "角色"}:
        return "角色"
    if text in {"Weapon", "武器"}:
        return "武器"
    return text or ""


def _source_label(value: object) -> str:
    text = text_value(value)
    if text == "keyring":
        return "钥匙串"
    if text == "profile":
        return "配置"
    if text == "environment":
        return "环境变量"
    return text or "-"


def _mapping_list(value: object) -> list[Mapping[str, object]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _finish(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"
