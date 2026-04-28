from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from html import unescape
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter

from gsuid_cli.renderers.common import (
    asset_path,
    crop_center,
    font,
    image_from_bytes,
    open_rgba,
    png_bytes,
    sequence,
    text_value,
)

EVENT_TEXTURE = asset_path("events", "textures")
ANN_TEXTURE = asset_path("announcements", "textures")
PUBLIC_TEXTURE = asset_path("public", "textures")
TEXT_COLOR = (60, 59, 64)
ANN_BG = "#f9f6f2"
ANN_TEXT = "#3b4354"
ANN_MUTED = "#767779"


def event_image_urls(data: Mapping[str, object], key: str) -> list[str]:
    urls: list[str] = []
    for event in _mapping_list(data.get(key)):
        _append_url(urls, event.get("banner_url"))
    return urls


def render_events_card(
    data: Mapping[str, object],
    *,
    kind: str,
    asset_images: Mapping[str, bytes] | None = None,
) -> bytes:
    asset_images = asset_images or {}
    rows = _event_rows(data, kind)
    is_gacha = kind == "banners"
    slot_h = 480 if is_gacha else 380
    card_name = "gacha_event_bg.png" if is_gacha else "normal_event_bg.png"
    cover_name = "gacha_event_cover.png" if is_gacha else "normal_event_cover.png"
    banner_size = (576, 284) if is_gacha else (576, 208)
    banner_pos = (315, 130) if is_gacha else (315, 118)
    start_y = 199 if is_gacha else 149
    arrow_y = 274 if is_gacha else 224
    end_y = 325 if is_gacha else 275

    height = max(100 + len(rows) * slot_h, slot_h + 100)
    image = _light_background(950, height)
    cover = open_rgba(EVENT_TEXTURE / cover_name)

    if not rows:
        draw = ImageDraw.Draw(image)
        draw.text((475, height // 2), "暂无活动数据", TEXT_COLOR, font(36), "mm")
        return png_bytes(image, rgb=True)

    for index, event in enumerate(rows):
        card = open_rgba(EVENT_TEXTURE / card_name)
        banner = _remote_image(event.get("banner_url"), asset_images, banner_size)
        if banner is None:
            banner = _placeholder_banner(banner_size, text_value(event.get("name_full")) or "活动")
        card.paste(banner, banner_pos, banner)
        draw = ImageDraw.Draw(card)
        title = text_value(event.get("name_full")) or text_value(event.get("name")) or "未知活动"
        draw.text((475, 47), title[:26], TEXT_COLOR, font(26), "mm")
        start = _month_and_time(event.get("start_at"))
        end = _month_and_time(event.get("end_at"))
        draw.polygon([(98, arrow_y - 13), (98, arrow_y + 13), (121, arrow_y)], fill=(243, 110, 110))
        draw.text((74, start_y), start[0], TEXT_COLOR, font(62), anchor="lm")
        draw.text((74, start_y + 42), start[1], TEXT_COLOR, font(26), anchor="lm")
        draw.text((115, end_y), end[0], TEXT_COLOR, font(62), anchor="lm")
        draw.text((115, end_y + 43), end[1], TEXT_COLOR, font(26), anchor="lm")
        card.paste(cover, (0, 0), cover)
        image.paste(card, (0, 50 + slot_h * index), card)

    return png_bytes(image, rgb=True)


def render_announcements_list_card(data: Mapping[str, object]) -> bytes:
    sections = _announcement_sections(data)
    head = open_rgba(ANN_TEXTURE / "list.png")
    item = open_rgba(ANN_TEXTURE / "item.png").resize((384, 96), Image.Resampling.LANCZOS)
    section_pairs = _section_pairs(sections)
    groups = [
        {
            "sections": pair,
            "rows": max((len(_mapping_list(section.get("items"))) for section in pair), default=1),
        }
        for pair in section_pairs
    ]
    height = sum(head.height + int(group["rows"]) * item.height for group in groups) + 50
    image = Image.new("RGBA", (head.width, max(height, head.height + item.height + 50)), ANN_BG)

    y = 0
    for group_index, group in enumerate(groups):
        pair = group["sections"]
        if group_index == 0:
            image.paste(head, (0, y), head)
        else:
            _draw_section_headers(image, pair, y)
        y_items = y + head.height
        for column, section in enumerate(pair):
            x = 45 if column == 0 else 472
            for index, row in enumerate(_mapping_list(section.get("items"))):
                card = _announcement_list_item(row, item)
                image.paste(card, (x, y_items + index * item.height), card)
        y = y_items + int(group["rows"]) * item.height

    tip = "*可以使用 announcements show --id 0000 或 --latest 查看详细内容"
    ImageDraw.Draw(image).text(
        (12, image.height - 30),
        tip,
        fill=ANN_MUTED,
        font=font(18),
        anchor="la",
    )
    return png_bytes(image, rgb=True)


def announcement_detail_image_urls(announcement: Mapping[str, object]) -> list[str]:
    urls: list[str] = []
    _append_url(urls, announcement.get("banner_url"))
    for url in _html_image_urls(text_value(announcement.get("content_html")) or ""):
        _append_url(urls, url)
    for url in sequence(announcement.get("image_urls")):
        _append_url(urls, url)
    return urls


def render_announcement_detail_card(
    announcement: Mapping[str, object],
    *,
    asset_images: Mapping[str, bytes] | None = None,
) -> bytes:
    asset_images = asset_images or {}
    blocks = _announcement_blocks(announcement)
    if not blocks:
        blocks = [
            {"type": "text", "text": text_value(announcement.get("title")) or "公告详情"},
            {"type": "text", "text": text_value(announcement.get("summary")) or ""},
        ]

    measured = [_measure_detail_block(block, asset_images) for block in blocks]
    height = max(sum(item[1] for item in measured) + 60, 240)
    image = Image.new("RGBA", (1080, height), ANN_BG)
    draw = ImageDraw.Draw(image)
    y = 30
    for block, block_height, prepared in measured:
        if block.get("type") == "image":
            pic = prepared if isinstance(prepared, Image.Image) else None
            if pic is not None:
                image.paste(pic, ((1080 - pic.width) // 2, y), pic)
            y += block_height
            continue
        text = str(prepared or "")
        draw.multiline_text((40, y), text, fill=(0, 0, 0), font=font(26), spacing=8)
        y += block_height

    return png_bytes(image, rgb=True)


def _event_rows(data: Mapping[str, object], kind: str) -> list[Mapping[str, object]]:
    key = "banners" if kind == "banners" else "events"
    rows = _mapping_list(data.get(key))
    if kind == "events":
        rows = [row for row in rows if not _is_gacha_event(row) and not _is_banned_event(row)]
    return [row for row in rows if text_value(row.get("banner_url"))]


def _is_gacha_event(event: Mapping[str, object]) -> bool:
    text = f"{event.get('name') or ''} {event.get('name_full') or ''}"
    return "祈愿" in text or "扭蛋" in text or "wish" in text.casefold()


def _is_banned_event(event: Mapping[str, object]) -> bool:
    text = f"{event.get('name') or ''} {event.get('name_full') or ''}"
    return any(word in text for word in ("首充", "深境螺旋", "传说任务", "纪行", "更新修复"))


def _announcement_sections(data: Mapping[str, object]) -> list[Mapping[str, object]]:
    sections = _mapping_list(data.get("sections"))
    if sections:
        return sections
    rows = _mapping_list(data.get("announcements"))
    return [{"type_id": 2, "items": rows}]


def _section_pairs(sections: Sequence[Mapping[str, object]]) -> list[list[Mapping[str, object]]]:
    if not sections:
        return [[{"type_id": 2, "type_label": "游戏公告", "items": []}]]
    ordered = list(sections)
    return [ordered[index : index + 2] for index in range(0, len(ordered), 2)]


def _draw_section_headers(
    image: Image.Image,
    sections: Sequence[Mapping[str, object]],
    y: int,
) -> None:
    draw = ImageDraw.Draw(image)
    for column, section in enumerate(sections):
        x0 = 90 if column == 0 else 562
        x1 = x0 + 230
        label = text_value(section.get("type_label")) or "公告"
        draw.rounded_rectangle((x0, y + 22, x1, y + 74), radius=24, fill=(164, 186, 224))
        draw.rounded_rectangle(
            (x0 + 5, y + 27, x1 - 5, y + 69), radius=20, outline="white", width=2
        )
        draw.text(((x0 + x1) // 2, y + 48), label[:8], fill="white", font=font(32), anchor="mm")


def _announcement_list_item(row: Mapping[str, object], template: Image.Image) -> Image.Image:
    card = template.copy()
    draw = ImageDraw.Draw(card)
    title = text_value(row.get("subtitle")) or text_value(row.get("title")) or "公告"
    title_font = font(26)
    lines = _wrap_text(title, title_font, 210).splitlines()
    y = max(14, (card.height - len(lines) * 31) // 2 + 2)
    _draw_lines_centered(draw, lines, y, title_font, ANN_TEXT, card.width)
    draw.text(
        (card.width - 80, 10),
        str(row.get("id") or ""),
        fill=ANN_TEXT,
        font=font(18),
        anchor="la",
    )
    return card


def _announcement_blocks(announcement: Mapping[str, object]) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    banner = text_value(announcement.get("banner_url"))
    if banner:
        blocks.append({"type": "image", "url": banner})
    html = text_value(announcement.get("content_html")) or ""
    blocks.extend(_html_blocks(html))
    if not blocks:
        text = text_value(announcement.get("text"))
        if text:
            blocks.append({"type": "text", "text": text})
    return blocks


def _html_blocks(html: str) -> list[dict[str, str]]:
    html = unescape(html).replace("<<", "")
    blocks: list[dict[str, str]] = []
    image_spans = list(
        re.finditer(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"'][^>]*>", html, flags=re.IGNORECASE)
    )
    cursor = 0
    for match in image_spans:
        _append_text_block(blocks, html[cursor : match.start()])
        blocks.append({"type": "image", "url": unescape(match.group(1))})
        cursor = match.end()
    _append_text_block(blocks, html[cursor:])
    return blocks


def _append_text_block(blocks: list[dict[str, str]], html: str) -> None:
    text = _html_text(html)
    if text:
        blocks.append({"type": "text", "text": text})


def _html_image_urls(html: str) -> list[str]:
    html = unescape(html)
    return [
        unescape(match.group(1))
        for match in re.finditer(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"'][^>]*>", html, re.I)
    ]


def _html_text(html: str) -> str:
    html = unescape(html).replace("<<", "")
    html = re.sub(r"</(?:p|div|li|h[1-6])\s*>", "\n", html, flags=re.I)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", "", html)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _measure_detail_block(
    block: Mapping[str, str],
    asset_images: Mapping[str, bytes],
) -> tuple[Mapping[str, str], int, Image.Image | str | None]:
    if block.get("type") == "image":
        pic = _detail_image(block.get("url"), asset_images)
        return block, (pic.height + 40 if pic is not None else 0), pic
    wrapped = _wrap_text(block.get("text") or "", font(26), 1000)
    lines = wrapped.count("\n") + 1 if wrapped else 0
    return block, max(lines * 38 + 24, 0), wrapped


def _detail_image(url: object, asset_images: Mapping[str, bytes]) -> Image.Image | None:
    content = asset_images.get(str(url or ""))
    if content is None:
        return None
    try:
        image = Image.open(BytesIO(content)).convert("RGBA")
    except OSError:
        return None
    if image.width > 1000:
        height = round(image.height * 1000 / image.width)
        image = image.resize((1000, height), Image.Resampling.LANCZOS)
    return image


def _remote_image(
    url: object,
    asset_images: Mapping[str, bytes],
    size: tuple[int, int],
) -> Image.Image | None:
    text = text_value(url)
    if not text:
        return None
    content = asset_images.get(text)
    if content is None:
        return None
    return image_from_bytes(content, size)


def _placeholder_banner(size: tuple[int, int], label: str) -> Image.Image:
    image = Image.new("RGBA", size, (230, 226, 220, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, size[0] - 5, size[1] - 5), 12, outline=(180, 170, 158), width=2)
    draw.text((size[0] // 2, size[1] // 2), label[:10], TEXT_COLOR, font(28), "mm")
    return image


def _light_background(width: int, height: int) -> Image.Image:
    source = Image.open(PUBLIC_TEXTURE / "bg.jpg")
    image = crop_center(source, width, height).filter(ImageFilter.GaussianBlur(radius=12))
    overlay = Image.new("RGBA", (width, height), (249, 246, 242, 165))
    image = image.convert("RGBA")
    image.paste(overlay, (0, 0), overlay)
    return image


def _month_and_time(value: object) -> tuple[str, str]:
    text = text_value(value) or ""
    if "永久开放" in text:
        return text[:5] or "--/--", "永久开放"
    if any(word in text for word in ("更新后", "版本", "版更")):
        return text[:5] or "--/--", "更新后"
    cleaned = text.replace("/", "-")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return "--/--", "--:--"
    suffix = "AM" if parsed.hour <= 12 else "PM"
    return parsed.strftime("%m/%d"), parsed.strftime("%H:%M") + suffix


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    max_width: int,
    text_font,
    fill: str | tuple[int, int, int],
) -> None:
    draw.multiline_text(
        xy,
        _wrap_text(text, text_font, max_width),
        fill=fill,
        font=text_font,
        spacing=2,
    )


def _draw_lines_centered(
    draw: ImageDraw.ImageDraw,
    lines: Sequence[str],
    y: int,
    text_font,
    fill: str | tuple[int, int, int],
    width: int,
) -> None:
    for index, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=text_font)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y + index * 31), line, fill=fill, font=text_font)


def _wrap_text(text: str, text_font, max_width: int) -> str:
    lines: list[str] = []
    current = ""
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for char in text:
        candidate = current + char
        bbox = measure.textbbox((0, 0), candidate, font=text_font)
        if current and bbox[2] - bbox[0] > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines)


def _mapping_list(value: object) -> list[Mapping[str, object]]:
    return [item for item in sequence(value) if isinstance(item, Mapping)]


def _append_url(urls: list[str], value: object) -> None:
    url = text_value(value)
    if url and url not in urls:
        urls.append(url)
