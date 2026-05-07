from __future__ import annotations

from collections.abc import Mapping

from gsuid_cli.renderers.common import sequence, text_value
from gsuid_cli.renderers.utility_text import _finish

FILTER_LABELS = {
    "active": "进行中",
    "all": "全部",
}
REWARD_LABELS = {
    "Primogem": "原石",
    "Mora": "摩拉",
    "Hero's Wit": "大英雄的经验",
    "Adventurer's Experience": "冒险家的经验",
    "Fine Enhancement Ore": "精锻用良矿",
    "Mystic Enhancement Ore": "精锻用魔矿",
}


def render_events_text(data: Mapping[str, object], *, kind: str) -> str:
    key = "banners" if kind == "banners" else "events"
    title = "活动祈愿" if kind == "banners" else "活动列表"
    rows = [row for row in sequence(data.get(key)) if isinstance(row, Mapping)]
    lines = [
        f"{title} - {_filter_label(data.get('filter'))}",
        f"数量: {data.get('count', len(rows))}",
    ]

    if not rows:
        lines.extend(["", "暂无活动数据"])
        return _finish(lines)

    for row in rows:
        lines.append("")
        lines.append(_event_title(row))
        time_text = _time_range(row)
        if time_text:
            lines.append(f"时间: {time_text}")
        banner_url = text_value(row.get("banner_url"))
        if banner_url:
            lines.append(f"图片: {banner_url}")

    return _finish(lines)


def render_codes_text(data: Mapping[str, object]) -> str:
    rows = [row for row in sequence(data.get("codes")) if isinstance(row, Mapping)]
    lines = ["兑换码", f"数量: {data.get('count', len(rows))}"]
    source_url = text_value(data.get("source_url"))
    if source_url:
        lines.append(f"来源: {source_url}")

    if not rows:
        lines.extend(["", "暂无可用兑换码"])
        return _finish(lines)

    lines.extend(["", "可用兑换码"])
    for row in rows:
        codes = [str(code) for code in sequence(row.get("codes")) if str(code).strip()]
        lines.append(f"  - {'、'.join(codes) if codes else '未知兑换码'}")
        servers = [_server_label(server) for server in sequence(row.get("servers"))]
        if servers:
            lines.append(f"    服务器: {'、'.join(servers)}")
        rewards = _reward_texts(row)
        if rewards:
            lines.append(f"    奖励: {'、'.join(rewards)}")
        expires = text_value(row.get("expires_at"))
        expiry_status = text_value(row.get("expiry_status"))
        if expires:
            lines.append(f"    过期时间: {expires}")
        elif expiry_status == "indef":
            lines.append("    过期时间: 长期有效")
        elif expiry_status:
            lines.append(f"    过期时间: {_expiry_status_label(expiry_status)}")

    return _finish(lines)


def render_announcements_list_text(data: Mapping[str, object]) -> str:
    rows = [row for row in sequence(data.get("announcements")) if isinstance(row, Mapping)]
    lines = [
        "公告列表",
        f"数量: {data.get('count', len(rows))}",
    ]
    if data.get("total") not in (None, ""):
        lines.append(f"总数: {data['total']}")

    sections = [
        section for section in sequence(data.get("sections")) if isinstance(section, Mapping)
    ]
    if not sections and rows:
        sections = [{"type_label": "公告", "items": rows}]
    if not sections:
        lines.extend(["", "暂无公告"])
        return _finish(lines)

    for section in sections:
        items = [item for item in sequence(section.get("items")) if isinstance(item, Mapping)]
        if not items:
            continue
        lines.append("")
        lines.append(text_value(section.get("type_label")) or "公告")
        for item in items:
            lines.append(f"  - {_announcement_list_title(item)}")
            ann_id = text_value(item.get("id") or item.get("ann_id"))
            if ann_id:
                lines.append(f"    公告ID: {ann_id}")
            time_text = _time_range(item)
            if time_text:
                lines.append(f"    时间: {time_text}")
            tag = text_value(item.get("tag"))
            if tag:
                lines.append(f"    标签: {tag}")

    return _finish(lines)


def render_announcement_detail_text(announcement: Mapping[str, object]) -> str:
    lines = ["公告详情", _announcement_title(announcement)]
    time_text = _time_range(announcement)
    if time_text:
        lines.append(f"时间: {time_text}")

    body = text_value(announcement.get("text")) or text_value(announcement.get("summary"))
    if body:
        lines.extend(["", "正文:", body])

    image_urls = _announcement_image_urls(announcement)
    if image_urls:
        lines.extend(["", "图片:"])
        for url in image_urls:
            lines.append(f"  - {url}")

    return _finish(lines)


def _event_title(row: Mapping[str, object]) -> str:
    return text_value(row.get("name_full")) or text_value(row.get("name")) or "未知活动"


def _announcement_title(row: Mapping[str, object]) -> str:
    subtitle = text_value(row.get("subtitle"))
    title = text_value(row.get("title"))
    if title and subtitle and title != subtitle:
        return f"{title} - {subtitle}"
    return subtitle or title or "公告"


def _announcement_list_title(row: Mapping[str, object]) -> str:
    return text_value(row.get("title")) or text_value(row.get("subtitle")) or "公告"


def _time_range(row: Mapping[str, object]) -> str | None:
    start = text_value(row.get("start_at"))
    end = text_value(row.get("end_at"))
    if start and end:
        return f"{start} 至 {end}"
    return start or end


def _reward_texts(row: Mapping[str, object]) -> list[str]:
    rewards = []
    for reward in sequence(row.get("rewards")):
        if not isinstance(reward, Mapping):
            continue
        name = text_value(reward.get("name"))
        if not name:
            continue
        name = REWARD_LABELS.get(name, name)
        count = reward.get("count")
        rewards.append(f"{name} x{count}" if count not in (None, "") else name)
    return rewards


def _server_label(value: object) -> str:
    text = str(value).strip()
    return {
        "America": "美服",
        "Europe": "欧服",
        "Asia": "亚服",
        "TW/HK/Macao": "港澳台服",
        "China": "国服",
    }.get(text, text)


def _expiry_status_label(value: str) -> str:
    return {
        "unknown": "未知",
        "indef": "长期有效",
    }.get(value, value)


def _announcement_image_urls(announcement: Mapping[str, object]) -> list[str]:
    urls: list[str] = []
    banner_url = text_value(announcement.get("banner_url"))
    if banner_url:
        urls.append(banner_url)
    for url in sequence(announcement.get("image_urls")):
        text = text_value(url)
        if text and text not in urls:
            urls.append(text)
    return urls


def _filter_label(value: object) -> str:
    text = text_value(value)
    if text is None:
        return "未知"
    return FILTER_LABELS.get(text, text)
