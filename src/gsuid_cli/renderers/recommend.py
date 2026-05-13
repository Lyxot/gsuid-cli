from __future__ import annotations

from collections.abc import Mapping

from PIL import Image, ImageDraw

from gsuid_cli.renderers.common import (
    font,
    png_bytes,
    sequence as _sequence,
    text_value,
    v4_background,
)
from gsuid_cli.text import t as _t

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
    character = text_value(data.get("character")) or _t(
        "gsuid.renderers.challenge.text.293_68.876cfbce"
    )
    sections = _build_sections(data)
    return _render_text_card(
        title=_t("gsuid.renderers.recommend.33_14.185b009f"),
        subtitle=f"「{character}」",
        sections=sections,
        footer=FOOTER_TEXT,
    )


def render_recommend_holder_card(data: Mapping[str, object]) -> bytes:
    item = text_value(data.get("item")) or _t("gsuid.renderers.gacha.630_43.988a9ca3")
    sections = _holder_sections(data)
    return _render_text_card(
        title=_t("gsuid.renderers.recommend.44_14.a43135ca"),
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
            weapon_lines.append(
                _t("gsuid.renderers.recommend.106_32.36e87c90", rarity, "、".join(items))
            )
    if weapon_lines:
        sections.append((_t("gsuid.renderers.recommend.108_25.3166cfe3"), weapon_lines))

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
            labels.append(_t("gsuid.renderers.guide.text.187_26.12201c09", name, piece or "2"))
        artifact_lines.append(" + ".join(labels))
    if artifact_lines:
        sections.append((_t("gsuid.renderers.recommend.124_25.bd103bbd"), artifact_lines))

    remarks = _text_list(data.get("remarks"))
    if remarks:
        sections.append((_t("gsuid.renderers.recommend.128_25.e0361480"), remarks))
    return sections or [
        (
            _t("gsuid.renderers.recommend.129_25.62b46f24"),
            [_t("gsuid.renderers.recommend.129_36.ca727dd4")],
        )
    ]


def _holder_sections(data: Mapping[str, object]) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    for match in _sequence(data.get("matches")):
        if not isinstance(match, Mapping):
            continue
        kind = (
            _t("gsuid.commands.panel.impl.988_24.6f0f16e0")
            if match.get("kind") == "weapon"
            else _t("gsuid.renderers.guide.text.100_62.619c6618")
        )
        name = text_value(match.get("match")) or kind
        holders = _text_list(match.get("holders"))
        if holders:
            sections.append((f"{kind} · {name}", ["、".join(holders)]))
    return sections or [
        (
            _t("gsuid.renderers.recommend.129_25.62b46f24"),
            [_t("gsuid.renderers.recommend.142_36.2ac7dbe4")],
        )
    ]


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


def _text_list(value: object) -> list[str]:
    return [text for item in _sequence(value) if (text := text_value(item))]
