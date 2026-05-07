from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from PIL import Image, ImageDraw, ImageFilter

from gsuid_cli.renderers.common import (
    asset_path,
    crop_center,
    font,
    image_from_bytes,
    int_value,
    open_rgba,
    text_value,
)

PUBLIC_TEXTURE = asset_path("public", "textures")
CHAR_CARD_TEXTURE = PUBLIC_TEXTURE / "char_card"
GENSHINUID_RESOURCE_BASE = "genshinuid://resource"
FOOTER_TEXT = "Created by gsuid-cli & Render style/assets by GenshinUID & Data by 米游社"


def color_background(width: int, height: int, *, source: Image.Image | None = None) -> Image.Image:
    background = source or open_rgba(PUBLIC_TEXTURE / "bg.jpg")
    image = crop_center(background, width, height).convert("RGBA")
    color = _background_color(image)
    mask = open_rgba(PUBLIC_TEXTURE / "mask.png").resize((width, height), Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", (width, height), color)
    image.paste(overlay, (0, 0), mask)
    return image


def dark_blurred_background(width: int, height: int, *, black_value: int = 190) -> Image.Image:
    image = crop_center(open_rgba(PUBLIC_TEXTURE / "bg.jpg"), width, height).convert("RGBA")
    image = image.filter(ImageFilter.GaussianBlur(radius=15))
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, black_value))
    image.paste(overlay, (0, 0), overlay)
    return image


def avatar_with_ring(
    *,
    summary: Mapping[str, object],
    asset_images: Mapping[str, bytes],
    size: int,
    avatar_url: str | None,
) -> Image.Image:
    url = avatar_url or summary_avatar_url(summary)
    avatar = remote_image(url, asset_images, (size, size))
    if avatar is None:
        avatar = Image.new("RGBA", (size, size), (55, 58, 73, 255))
        draw = ImageDraw.Draw(avatar)
        draw.text(
            (size // 2, size // 2),
            "GS",
            fill="white",
            font=font(max(size // 5, 18)),
            anchor="mm",
        )
    mask = open_rgba(PUBLIC_TEXTURE / "mask.png").resize((size, size), Image.Resampling.LANCZOS)
    output = Image.new("RGBA", (size, size))
    output.paste(crop_center(avatar, size, size), (0, 0), mask)
    ring = open_rgba(PUBLIC_TEXTURE / "avatar_ring.png").resize(
        (size, size),
        Image.Resampling.LANCZOS,
    )
    output.paste(ring, (0, 0), ring)
    return output


def challenge_character_card(
    character: Mapping[str, object],
    asset_images: Mapping[str, bytes],
    *,
    size: tuple[int, int],
    level_anchor_x: int = 77,
) -> Image.Image:
    rarity = min(max(int_value(character.get("rarity"), 5), 1), 5)
    frame = open_rgba(CHAR_CARD_TEXTURE / "frame.png")
    background = open_rgba(CHAR_CARD_TEXTURE / f"star{rarity}bg.png")
    mask = open_rgba(CHAR_CARD_TEXTURE / "mask.png")
    portrait = first_remote_image(character_image_urls(character), asset_images, (256, 256))
    if portrait is None:
        portrait = Image.new("RGBA", (256, 256))
        draw = ImageDraw.Draw(portrait)
        draw.rounded_rectangle((25, 25, 231, 231), radius=28, outline=(255, 255, 255, 150), width=3)
        draw.text(
            (128, 128),
            (text_value(character.get("name")) or "?")[:2],
            fill=(255, 255, 255, 220),
            font=font(44),
            anchor="mm",
        )

    card = Image.new("RGBA", (256, 310))
    masked = Image.new("RGBA", (256, 310))
    masked.paste(background, (0, 0), background)
    masked.paste(portrait, (0, 0), portrait)
    masked.paste(frame, (0, 0), frame)
    card.paste(masked, (0, 0), mask)

    draw = ImageDraw.Draw(card)
    draw.text(
        (level_anchor_x, 280),
        f"Lv.{int_value(character.get('level'))}",
        fill=(29, 29, 29),
        font=font(40),
        anchor="mm",
    )
    rank = character.get("rank", character.get("actived_constellation_num"))
    if rank not in (None, ""):
        rank_value = int_value(rank)
        fill = (224, 36, 36, 235) if rank_value >= 6 else (255, 255, 255, 220)
        text_fill = (255, 255, 255) if rank_value >= 6 else (29, 29, 29)
        draw.rounded_rectangle((152, 260, 236, 300), radius=14, fill=fill)
        draw.text(
            (194, 281),
            "满命" if rank_value >= 6 else f"{rank_value}命",
            fill=text_fill,
            font=font(32),
            anchor="mm",
        )

    return card.resize(size, Image.Resampling.LANCZOS)


def remote_image(
    url: str | None,
    asset_images: Mapping[str, bytes],
    size: tuple[int, int],
) -> Image.Image | None:
    if not url:
        return None
    content = asset_images.get(url)
    if content is None:
        return None
    return image_from_bytes(content, size)


def first_remote_image(
    urls: Sequence[str | None],
    asset_images: Mapping[str, bytes],
    size: tuple[int, int],
) -> Image.Image | None:
    for url in urls:
        image = remote_image(url, asset_images, size)
        if image is not None:
            return image
    return None


def summary_avatar_url(summary: Mapping[str, object]) -> str | None:
    role = summary.get("role")
    if isinstance(role, Mapping):
        return text_value(role.get("avatar_icon"))
    return None


def character_id(character: Mapping[str, object]) -> int:
    return int_value(character.get("avatar_id"), int_value(character.get("id")))


def character_portrait_url(character: Mapping[str, object]) -> str | None:
    avatar_id = character_id(character)
    if avatar_id <= 0:
        return None
    return f"{GENSHINUID_RESOURCE_BASE}/chars/{avatar_id}.png"


def character_side_url(character: Mapping[str, object]) -> str | None:
    avatar_id = character_id(character)
    if avatar_id <= 0:
        return None
    return f"{GENSHINUID_RESOURCE_BASE}/char_side/{avatar_id}.png"


def character_image_urls(character: Mapping[str, object]) -> list[str]:
    urls: list[str] = []
    for value in (
        character_portrait_url(character),
        character.get("image"),
        character.get("icon"),
        character.get("avatar_icon"),
    ):
        append_url(urls, value)
    return urls


def character_side_urls(character: Mapping[str, object]) -> list[str]:
    urls: list[str] = []
    for value in (
        character.get("side_icon"),
        character.get("avatar_icon"),
        character_side_url(character),
    ):
        append_url(urls, value)
    return urls


def append_url(urls: list[str], value: object) -> None:
    url = text_value(value)
    if url and url not in urls:
        urls.append(url)


def timestamp_text(value: object, *, date_only: bool = False) -> str:
    timestamp = int_value(value)
    if timestamp <= 0:
        return ""
    fmt = "%Y/%m/%d" if date_only else "%Y.%m.%d %H:%M:%S"
    return datetime.fromtimestamp(timestamp, UTC).astimezone().strftime(fmt)


def paste_footer(image: Image.Image, *, font_size: int = 24, invert: bool = False) -> None:
    draw = ImageDraw.Draw(image)
    fill = (67, 61, 56) if invert else (255, 255, 255)
    shadow = (255, 255, 255, 160) if invert else (0, 0, 0, 180)
    x = image.size[0] // 2
    y = image.size[1] - 34
    footer_font = font(font_size)
    draw.text((x + 1, y + 1), FOOTER_TEXT, fill=shadow, font=footer_font, anchor="mm")
    draw.text((x, y), FOOTER_TEXT, fill=fill, font=footer_font, anchor="mm")


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
