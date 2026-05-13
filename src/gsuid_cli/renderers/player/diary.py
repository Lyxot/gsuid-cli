from __future__ import annotations

from collections.abc import Mapping

from PIL import Image, ImageDraw

from gsuid_cli.renderers._text_helpers import _mapping
from gsuid_cli.renderers.common import (
    asset_path,
    crop_center,
    font,
    int_value,
    open_rgba,
    png_bytes,
    sequence,
)
from gsuid_cli.renderers.player.summary import paste_player_footer, player_title_avatar_image
from gsuid_cli.text import t as _t

TEXTURE = asset_path("player", "diary", "textures")
FIRST_COLOR = (29, 29, 29)
SECOND_COLOR = (67, 61, 56)

COLOR_MAP = {
    _t("gsuid.renderers.player.diary.24_4.cf8d6bf7"): (127, 115, 173),
    _t("gsuid.renderers.player.diary.25_4.2ed6f382"): (190, 158, 97),
    _t("gsuid.renderers.player.diary.26_4.24317b86"): (89, 126, 162),
    _t("gsuid.renderers.events.image.186_51.ce963b83"): (113, 152, 113),
    _t("gsuid.renderers.player.diary.28_4.15dd8ad7"): (152, 102, 146),
    _t("gsuid.renderers.player.diary.29_4.f2d9f0e8"): (220, 99, 96),
    _t("gsuid.renderers.player.diary.30_4.abca6dc3"): (107, 182, 181),
    _t("gsuid.renderers.player.diary.31_4.1a26edf9"): (118, 168, 196),
    "Mail": (127, 115, 173),
    "Daily Activity": (190, 158, 97),
    "Events": (89, 126, 162),
    "Spiral Abyss": (113, 152, 113),
    "Adventure": (220, 99, 96),
    "Quests": (107, 182, 181),
    "Other": (118, 168, 196),
}


def render_player_diary_card(
    *,
    uid: str,
    summary: Mapping[str, object],
    diary: Mapping[str, object],
    asset_images: Mapping[str, bytes] | None = None,
    title_avatar_url: str | None = None,
) -> bytes:
    """Render a GenshinUID-style monthly traveler diary card as PNG bytes."""
    asset_images = asset_images or {}
    image = _color_background(850, 1950)
    avatar = _avatar_with_ring(
        summary=summary,
        asset_images=asset_images,
        size=317,
        title_avatar_url=title_avatar_url,
    )
    image.paste(avatar, (267, 83), avatar)
    note = open_rgba(TEXTURE / "note.png")
    image.paste(note, (0, 0), note)

    day_data = _mapping(diary.get("day_data"))
    month_data = _mapping(diary.get("month_data"))
    values = _diary_values(day_data, month_data)
    _paste_rings(image, values)
    _paste_text(image, uid, values)
    _paste_group_chart(image, _group_by(month_data))

    paste_player_footer(image, font_size=18)
    return png_bytes(image, rgb=True)


def _diary_values(
    day_data: Mapping[str, object],
    month_data: Mapping[str, object],
) -> dict[str, int]:
    return {
        "day_stone": int_value(day_data.get("current_primogems")),
        "day_mora": int_value(day_data.get("current_mora")),
        "lastday_stone": int_value(day_data.get("last_primogems")),
        "lastday_mora": int_value(day_data.get("last_mora")),
        "month_stone": int_value(month_data.get("current_primogems")),
        "month_mora": int_value(month_data.get("current_mora")),
        "lastmonth_stone": int_value(month_data.get("last_primogems")),
        "lastmonth_mora": int_value(month_data.get("last_mora")),
    }


def _paste_rings(image: Image.Image, values: Mapping[str, int]) -> None:
    ring = Image.open(TEXTURE / "ring.apng")
    ring_data = [
        (_ratio_frame(values["day_stone"], values["lastday_stone"]), (-5, 475)),
        (_ratio_frame(values["day_mora"], values["lastday_mora"]), (371, 475)),
        (_ratio_frame(values["month_stone"], values["lastmonth_stone"]), (-5, 948)),
        (_ratio_frame(values["month_mora"], values["lastmonth_mora"]), (371, 948)),
    ]
    for frame, position in sorted(ring_data):
        try:
            ring.seek(frame)
        except EOFError:
            ring.seek(0)
        frame_image = ring.convert("RGBA")
        image.paste(frame_image, position, frame_image)


def _paste_text(image: Image.Image, uid: str, values: Mapping[str, int]) -> None:
    draw = ImageDraw.Draw(image)
    draw.text((430, 464), f"UID {uid}", SECOND_COLOR, font(38), "mm")

    draw.text((243, 718), _int_carry(values["day_stone"]), FIRST_COLOR, font(58), "mm")
    draw.text((625, 718), _int_carry(values["day_mora"]), FIRST_COLOR, font(58), "mm")
    draw.text((245, 1192), _int_carry(values["month_stone"]), FIRST_COLOR, font(58), "mm")
    draw.text((621, 1192), _int_carry(values["month_mora"]), FIRST_COLOR, font(58), "mm")

    draw.text(
        (245, 923),
        _t("gsuid.renderers.player.diary.118_8.997c84a6", _int_carry(values["lastday_stone"])),
        SECOND_COLOR,
        font(26),
        "mm",
    )
    draw.text(
        (621, 923),
        _t("gsuid.renderers.player.diary.125_8.bff5893f", _int_carry(values["lastday_mora"])),
        SECOND_COLOR,
        font(26),
        "mm",
    )
    draw.text(
        (245, 1396),
        _t("gsuid.renderers.player.diary.132_8.22d3370a", _int_carry(values["lastmonth_stone"])),
        SECOND_COLOR,
        font(26),
        "mm",
    )
    draw.text(
        (621, 1396),
        _t("gsuid.renderers.player.diary.139_8.2330b993", _int_carry(values["lastmonth_mora"])),
        SECOND_COLOR,
        font(26),
        "mm",
    )


def _paste_group_chart(image: Image.Image, groups: list[Mapping[str, object]]) -> None:
    draw = ImageDraw.Draw(image)
    if not groups:
        for index, action in enumerate(COLOR_MAP):
            if action in {_t("gsuid.renderers.player.diary.31_4.1a26edf9"), "Other"}:
                continue
            draw.text(
                (614, 1535 + index * 52),
                _t("gsuid.renderers.player.diary.152_48.4dde36d4", action),
                SECOND_COLOR,
                font(26),
                "mm",
            )
        oops = open_rgba(TEXTURE / "oops.png")
        image.paste(oops, (106, 1513), oops)
        return

    xy = ((89, 1545), (379, 1835))
    start = -90.0
    for index, group in enumerate(groups):
        percent = int_value(group.get("percent"))
        action = str(group.get("action") or "")
        end = start + percent / 100 * 360
        color = COLOR_MAP.get(action, (152, 102, 146))
        draw.pieslice(xy, start, end, color)
        start = end
        if action in {_t("gsuid.renderers.player.diary.31_4.1a26edf9"), "Other"}:
            continue
        y = 1523 + index * 52
        draw.rectangle(((407, y), (453, y + 25)), fill=color)
        draw.text(
            (614, 1535 + index * 52),
            f"{action}:{int_value(group.get('num'))}",
            SECOND_COLOR,
            font(26),
            "mm",
        )
    ok = open_rgba(TEXTURE / "ok.png")
    image.paste(ok, (110, 1565), ok)


def _color_background(width: int, height: int) -> Image.Image:
    image = crop_center(open_rgba(TEXTURE / "bg.jpg"), width, height).convert("RGBA")
    color = _background_color(image)
    color_mask = Image.new("RGBA", (width, height), color)
    mask = open_rgba(TEXTURE / "bg_mask.png").resize((width, height), Image.Resampling.LANCZOS)
    image.paste(color_mask, (0, 0), mask)
    return image


def _background_color(image: Image.Image) -> tuple[int, int, int]:
    quantized = image.convert("RGB").quantize(colors=8, method=Image.Quantize.FASTOCTREE)
    palette = quantized.getpalette() or []
    selected = (195, 195, 195)
    distance = 9999.0
    for index in range(8):
        offset = index * 3
        if offset + 2 >= len(palette):
            continue
        color = tuple(palette[offset : offset + 3])
        light = color[0] * 0.3 + color[1] * 0.6 + color[2] * 0.1
        next_distance = abs(light - 195)
        if next_distance < distance:
            selected = color
            distance = next_distance
    return selected


def _avatar_with_ring(
    *,
    summary: Mapping[str, object],
    asset_images: Mapping[str, bytes],
    size: int,
    title_avatar_url: str | None,
) -> Image.Image:
    avatar = player_title_avatar_image(
        summary=summary,
        asset_images=asset_images,
        size=size,
        title_avatar_url=title_avatar_url,
    )
    image = Image.new("RGBA", (size, size))
    image.paste(avatar, (0, 0), avatar)
    ring = open_rgba(TEXTURE / "avatar_ring.png").resize((size, size), Image.Resampling.LANCZOS)
    image.paste(ring, (0, 0), ring)
    return image


def _ratio_frame(current: int, previous: int) -> int:
    percent = current / previous if previous else 1
    return min(max(int(min(percent, 1) * 49 + 0.5), 0), 49)


def _group_by(month_data: Mapping[str, object]) -> list[Mapping[str, object]]:
    return [item for item in sequence(month_data.get("group_by")) if isinstance(item, Mapping)]


def _int_carry(value: int) -> str:
    if value >= 100000:
        return f"{value / 10000:.1f}W"
    return str(value)
