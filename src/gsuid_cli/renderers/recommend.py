from __future__ import annotations

from collections.abc import Mapping, Sequence

from PIL import Image, ImageDraw

from gsuid_cli.renderers.common import font, png_bytes, text_value, v4_background

WIDTH = 900
PAD = 48
CARD_X0 = 42
CARD_X1 = WIDTH - 42
TEXT_WIDTH = CARD_X1 - CARD_X0 - 56

WHITE = (255, 255, 255)
MUTED = (214, 208, 196)
GOLD = (232, 190, 112)
PANEL = (22, 20, 25, 178)
PANEL_BORDER = (229, 199, 139, 92)
FOOTER_TEXT = "Created by gsuid-cli & Data by GenshinUID"


def render_recommend_build_card(data: Mapping[str, object]) -> bytes:
    character = text_value(data.get("character")) or "未知角色"
    sections = _build_sections(data)
    return _render_text_card(
        title="角色养成推荐",
        subtitle=f"「{character}」",
        sections=sections,
        footer=FOOTER_TEXT,
    )


def render_recommend_holder_card(data: Mapping[str, object]) -> bytes:
    item = text_value(data.get("item")) or "未知物品"
    sections = _holder_sections(data)
    return _render_text_card(
        title="适用角色推荐",
        subtitle=f"「{item}」",
        sections=sections,
        footer=FOOTER_TEXT,
    )


def _render_text_card(
    *,
    title: str,
    subtitle: str,
    sections: list[tuple[str, list[str]]],
    footer: str,
) -> bytes:
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    card_heights = [_section_height(lines, measure) for _, lines in sections]
    height = 190 + sum(card_heights) + 24 * max(len(sections) - 1, 0) + 78
    image = v4_background(WIDTH, max(height, 520), black_value=160)
    draw = ImageDraw.Draw(image)

    draw.text((PAD, 62), title, fill=WHITE, font=font(44), anchor="lm")
    draw.text((PAD, 110), subtitle, fill=GOLD, font=font(30), anchor="lm")
    draw.rounded_rectangle((PAD, 136, WIDTH - PAD, 141), 3, fill=GOLD)

    y = 172
    for (section_title, lines), section_height in zip(sections, card_heights, strict=True):
        draw.rounded_rectangle(
            (CARD_X0, y, CARD_X1, y + section_height),
            radius=16,
            fill=PANEL,
            outline=PANEL_BORDER,
            width=2,
        )
        draw.text((CARD_X0 + 28, y + 36), section_title, fill=GOLD, font=font(30), anchor="lm")
        body_y = y + 74
        for line in lines:
            wrapped = _wrap_text(line, font(23), TEXT_WIDTH, measure)
            draw.multiline_text(
                (CARD_X0 + 28, body_y),
                wrapped,
                fill=MUTED,
                font=font(23),
                spacing=8,
            )
            body_y += _text_height(wrapped, font(23), measure) + 14
        y += section_height + 24

    draw.text(
        (WIDTH // 2, image.height - 34), footer, fill=(230, 226, 218), font=font(18), anchor="mm"
    )
    return png_bytes(image, rgb=True)


def _build_sections(data: Mapping[str, object]) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    weapon_lines: list[str] = []
    for group in _sequence(data.get("weapons")):
        if not isinstance(group, Mapping):
            continue
        rarity = text_value(group.get("rarity")) or "?"
        items = _text_list(group.get("items"))
        if items:
            weapon_lines.append(f"{rarity}星武器：{'、'.join(items)}")
    if weapon_lines:
        sections.append(("推荐武器", weapon_lines))

    artifact_lines: list[str] = []
    for group in _sequence(data.get("artifacts")):
        if not isinstance(group, Mapping):
            continue
        sets = _text_list(group.get("sets"))
        pieces = _sequence(group.get("pieces"))
        if not sets:
            continue
        labels = []
        for index, name in enumerate(sets):
            piece = text_value(pieces[index]) if index < len(pieces) else "2"
            labels.append(f"{name}{piece or '2'}件")
        artifact_lines.append(" + ".join(labels))
    if artifact_lines:
        sections.append(("推荐圣遗物", artifact_lines))

    remarks = _text_list(data.get("remarks"))
    if remarks:
        sections.append(("备注", remarks))
    return sections or [("推荐", ["没有可展示的推荐内容。"])]


def _holder_sections(data: Mapping[str, object]) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    for match in _sequence(data.get("matches")):
        if not isinstance(match, Mapping):
            continue
        kind = "武器" if match.get("kind") == "weapon" else "圣遗物"
        name = text_value(match.get("match")) or kind
        holders = _text_list(match.get("holders"))
        if holders:
            sections.append((f"{kind} · {name}", ["、".join(holders)]))
    return sections or [("推荐", ["没有角色能使用该物品。"])]


def _section_height(lines: list[str], draw: ImageDraw.ImageDraw) -> int:
    height = 98
    for line in lines:
        wrapped = _wrap_text(line, font(23), TEXT_WIDTH, draw)
        height += _text_height(wrapped, font(23), draw) + 14
    return max(height, 132)


def _wrap_text(value: str, text_font, max_width: int, draw: ImageDraw.ImageDraw) -> str:
    lines: list[str] = []
    for source_line in value.splitlines() or [""]:
        line = ""
        for char in source_line:
            candidate = line + char
            if draw.textlength(candidate, font=text_font) <= max_width or not line:
                line = candidate
            else:
                lines.append(line)
                line = char
        lines.append(line)
    return "\n".join(lines)


def _text_height(text: str, text_font, draw: ImageDraw.ImageDraw) -> int:
    if not text:
        return 0
    bbox = draw.multiline_textbbox((0, 0), text, font=text_font, spacing=8)
    return bbox[3] - bbox[1]


def _sequence(value: object) -> Sequence[object]:
    return value if isinstance(value, list) else []


def _text_list(value: object) -> list[str]:
    return [text for item in _sequence(value) if (text := text_value(item))]
