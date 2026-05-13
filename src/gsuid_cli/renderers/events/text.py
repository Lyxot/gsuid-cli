from __future__ import annotations

from collections.abc import Mapping

from gsuid_cli.renderers._text_helpers import _finish
from gsuid_cli.renderers.common import sequence, text_value
from gsuid_cli.text import t as _t

FILTER_LABELS = {
    "active": _t("gsuid.renderers.daily.text.245_75.6f1972e4"),
    "all": _t("gsuid.renderers.events.text.10_11.778fc8f9"),
}
REWARD_LABELS = {
    "Primogem": _t("gsuid.renderers.events.text.13_16.2a2b2bee"),
    "Mora": _t("gsuid.renderers.events.text.14_12.3806be48"),
    "Hero's Wit": _t("gsuid.renderers.events.text.15_18.dab70214"),
    "Adventurer's Experience": _t("gsuid.renderers.events.text.16_31.adb4b122"),
    "Fine Enhancement Ore": _t("gsuid.renderers.events.text.17_28.a3650487"),
    "Mystic Enhancement Ore": _t("gsuid.renderers.events.text.18_30.dc546f8a"),
}


def render_events_text(data: Mapping[str, object], *, kind: str) -> str:
    key = "banners" if kind == "banners" else "events"
    title = (
        _t("gsuid.renderers.events.text.24_12.881f1b72")
        if kind == "banners"
        else _t("gsuid.renderers.events.text.24_53.c81adb6a")
    )
    rows = [row for row in sequence(data.get(key)) if isinstance(row, Mapping)]
    lines = [
        f"{title} - {_filter_label(data.get('filter'))}",
        _t("gsuid.renderers.challenge.text.186_8.a63927f2", data.get("count", len(rows))),
    ]

    if not rows:
        lines.extend(["", _t("gsuid.renderers.events.image.63_38.9b22e30f")])
        return _finish(lines)

    for row in rows:
        lines.append("")
        lines.append(_event_title(row))
        time_text = _time_range(row)
        if time_text:
            lines.append(_t("gsuid.renderers.challenge.text.99_21.389c2b09", time_text))
        banner_url = text_value(row.get("banner_url"))
        if banner_url:
            lines.append(_t("gsuid.renderers.events.text.43_25.0bca765a", banner_url))

    return _finish(lines)


def render_codes_text(data: Mapping[str, object]) -> str:
    rows = [row for row in sequence(data.get("codes")) if isinstance(row, Mapping)]
    lines = [
        _t("gsuid.renderers.events.text.50_13.7ebc000c"),
        _t("gsuid.renderers.challenge.text.186_8.a63927f2", data.get("count", len(rows))),
    ]
    source_url = text_value(data.get("source_url"))
    if source_url:
        lines.append(_t("gsuid.renderers.events.text.53_21.15097066", source_url))

    if not rows:
        lines.extend(["", _t("gsuid.renderers.events.text.56_26.b956c996")])
        return _finish(lines)

    lines.extend(["", _t("gsuid.renderers.events.text.59_22.1102597f")])
    for row in rows:
        codes = [str(code) for code in sequence(row.get("codes")) if str(code).strip()]
        lines.append(
            f"  - {'、'.join(codes) if codes else _t('gsuid.renderers.events.text.62_60.47c17115')}"
        )
        servers = [_server_label(server) for server in sequence(row.get("servers"))]
        if servers:
            lines.append(_t("gsuid.renderers.events.text.65_25.573329f9", "、".join(servers)))
        rewards = _reward_texts(row)
        if rewards:
            lines.append(_t("gsuid.renderers.events.text.68_25.87cab234", "、".join(rewards)))
        expires = text_value(row.get("expires_at"))
        expiry_status = text_value(row.get("expiry_status"))
        if expires:
            lines.append(_t("gsuid.renderers.events.text.72_25.f6a51cab", expires))
        elif expiry_status == "indef":
            lines.append(_t("gsuid.renderers.events.text.74_25.0fbb9aa4"))
        elif expiry_status:
            lines.append(
                _t(
                    "gsuid.renderers.events.text.72_25.f6a51cab",
                    _expiry_status_label(expiry_status),
                )
            )

    return _finish(lines)


def render_announcements_list_text(data: Mapping[str, object]) -> str:
    rows = [row for row in sequence(data.get("announcements")) if isinstance(row, Mapping)]
    lines = [
        _t("gsuid.renderers.events.text.84_8.e7019331"),
        _t("gsuid.renderers.challenge.text.186_8.a63927f2", data.get("count", len(rows))),
    ]
    if data.get("total") not in (None, ""):
        lines.append(_t("gsuid.renderers.events.text.88_21.d282f3df", data["total"]))

    sections = [
        section for section in sequence(data.get("sections")) if isinstance(section, Mapping)
    ]
    if not sections and rows:
        sections = [
            {"type_label": _t("gsuid.renderers.events.image.224_79.3f956953"), "items": rows}
        ]
    if not sections:
        lines.extend(["", _t("gsuid.renderers.events.text.96_26.17b836f3")])
        return _finish(lines)

    for section in sections:
        items = [item for item in sequence(section.get("items")) if isinstance(item, Mapping)]
        if not items:
            continue
        lines.append("")
        lines.append(
            text_value(section.get("type_label"))
            or _t("gsuid.renderers.events.image.224_79.3f956953")
        )
        for item in items:
            lines.append(f"  - {_announcement_list_title(item)}")
            ann_id = text_value(item.get("id") or item.get("ann_id"))
            if ann_id:
                lines.append(_t("gsuid.renderers.events.text.109_29.6b4f1d84", ann_id))
            time_text = _time_range(item)
            if time_text:
                lines.append(_t("gsuid.renderers.events.text.112_29.acab63aa", time_text))
            tag = text_value(item.get("tag"))
            if tag:
                lines.append(_t("gsuid.renderers.events.text.115_29.187bdb7d", tag))

    return _finish(lines)


def render_announcement_detail_text(announcement: Mapping[str, object]) -> str:
    lines = [_t("gsuid.renderers.events.image.148_78.7dfb9873"), _announcement_title(announcement)]
    time_text = _time_range(announcement)
    if time_text:
        lines.append(_t("gsuid.renderers.challenge.text.99_21.389c2b09", time_text))

    body = text_value(announcement.get("text")) or text_value(announcement.get("summary"))
    if body:
        lines.extend(["", _t("gsuid.renderers.events.text.128_26.01bd2acd"), body])

    image_urls = _announcement_image_urls(announcement)
    if image_urls:
        lines.extend(["", _t("gsuid.renderers.events.text.132_26.0358b127")])
        for url in image_urls:
            lines.append(f"  - {url}")

    return _finish(lines)


def _event_title(row: Mapping[str, object]) -> str:
    return (
        text_value(row.get("name_full"))
        or text_value(row.get("name"))
        or _t("gsuid.renderers.events.image.73_87.9150e696")
    )


def _announcement_title(row: Mapping[str, object]) -> str:
    subtitle = text_value(row.get("subtitle"))
    title = text_value(row.get("title"))
    if title and subtitle and title != subtitle:
        return f"{title} - {subtitle}"
    return subtitle or title or _t("gsuid.renderers.events.image.224_79.3f956953")


def _announcement_list_title(row: Mapping[str, object]) -> str:
    return (
        text_value(row.get("title"))
        or text_value(row.get("subtitle"))
        or _t("gsuid.renderers.events.image.224_79.3f956953")
    )


def _time_range(row: Mapping[str, object]) -> str | None:
    start = text_value(row.get("start_at"))
    end = text_value(row.get("end_at"))
    if start and end:
        return _t("gsuid.renderers.challenge.text.269_15.5881d084", start, end)
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
        "America": _t("gsuid.renderers.events.text.180_19.62642448"),
        "Europe": _t("gsuid.renderers.events.text.181_18.88a2fc46"),
        "Asia": _t("gsuid.renderers.events.text.182_16.0c202d26"),
        "TW/HK/Macao": _t("gsuid.renderers.events.text.183_23.1c76ddc3"),
        "China": _t("gsuid.renderers.events.text.184_17.ca2c0218"),
    }.get(text, text)


def _expiry_status_label(value: str) -> str:
    return {
        "unknown": _t("gsuid.renderers.daily.text.211_11.d9c32a4c"),
        "indef": _t("gsuid.renderers.events.text.191_17.9554d6fb"),
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
        return _t("gsuid.renderers.daily.text.211_11.d9c32a4c")
    return FILTER_LABELS.get(text, text)
