from __future__ import annotations

from collections.abc import Mapping, Sequence
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
    v4_background,
)

TEXTURE = asset_path("player", "characters", "textures")
GENSHINUID_RESOURCE_BASE = "https://example.test/GenshinUID/resource"

WIDTH = 1680
CARD_SIZE = (374, 195)
CARD_GAP = 5
CARD_LEFT = 95
CARD_TOP = 160
COLUMNS = 4
HEADER_HEIGHT = 160
BOTTOM_PADDING = 80


def render_player_characters_card(
    *,
    characters: Sequence[Mapping[str, object]],
    asset_images: Mapping[str, bytes] | None = None,
) -> bytes:
    """Render a GenshinUID-style player character list card as PNG bytes."""
    foreground = render_player_characters_section(
        characters=characters,
        asset_images=asset_images,
    )
    background = v4_background(WIDTH, foreground.size[1])
    background.paste(foreground, (0, 0), foreground)
    return png_bytes(background, rgb=True)


def render_player_characters_section(
    *,
    characters: Sequence[Mapping[str, object]],
    asset_images: Mapping[str, bytes] | None = None,
) -> Image.Image:
    """Render the transparent GenshinUID character-list section."""
    asset_images = asset_images or {}
    ordered_characters = _sorted_characters(characters)
    rows = max((len(ordered_characters) + COLUMNS - 1) // COLUMNS, 1)
    height = HEADER_HEIGHT + rows * CARD_SIZE[1] + BOTTOM_PADDING

    foreground = Image.new("RGBA", (WIDTH, height))
    div_d = open_rgba(TEXTURE / "div_d.png")
    foreground.paste(div_d, (0, 65), div_d)

    for index, character in enumerate(ordered_characters):
        card = _character_card(character, asset_images).resize(CARD_SIZE, Image.Resampling.LANCZOS)
        x = CARD_LEFT + (index % COLUMNS) * (CARD_SIZE[0] + CARD_GAP)
        y = CARD_TOP + (index // COLUMNS) * CARD_SIZE[1]
        foreground.paste(card, (x, y), card)

    return foreground


def _character_card(
    character: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    char_rarity = _character_rarity(character.get("rarity"))
    weapon = character.get("weapon")
    if not isinstance(weapon, Mapping):
        weapon = {}

    card = open_rgba(TEXTURE / f"char_bg{char_rarity}.png")
    char_mask = open_rgba(TEXTURE / "charcard_mask.png")
    char_card = _remote_image(character_namecard_url(character), asset_images, (560, 268))
    if char_card is None:
        char_card = Image.new("RGBA", (560, 268))
    card.paste(char_card, (32, 29), char_mask)

    char_image = _first_remote_image(
        (
            character_portrait_url(character),
            *character_mys_image_urls(character),
        ),
        asset_images,
        (256, 256),
    )
    if char_image is not None:
        card.paste(char_image, (43, 35), char_image)
    else:
        _paste_character_placeholder(card, character)

    weapon_rarity = _rarity(weapon.get("rarity"), minimum=1, default=1)
    weapon_bg = open_rgba(TEXTURE / f"weapon{weapon_rarity}.png")
    card.paste(weapon_bg, (343, 33), weapon_bg)
    weapon_image = _first_remote_image(
        (
            weapon_icon_url(weapon),
            text_value(weapon.get("icon")),
        ),
        asset_images,
        (174, 174),
    )
    if weapon_image is not None:
        card.paste(weapon_image, (366, 55), weapon_image)

    char_fg = open_rgba(TEXTURE / "char_fg.png")
    card.paste(char_fg, (0, 0), char_fg)
    talent = _rarity(character.get("actived_constellation_num"), minimum=0, maximum=6, default=0)
    fetter = _rarity(character.get("fetter"), minimum=0, maximum=10, default=0)
    talent_icon = open_rgba(TEXTURE / "mz" / f"{talent}.png")
    fetter_icon = open_rgba(TEXTURE / "hg" / f"{fetter}.png")
    card.paste(talent_icon, (273, 55), talent_icon)
    card.paste(fetter_icon, (273, 124), fetter_icon)

    draw = ImageDraw.Draw(card)
    draw.text(
        (110, 261),
        f"Lv{int_value(character.get('level'))}",
        fill="white",
        font=font(30),
        anchor="mm",
    )
    draw.text(
        (453, 264),
        text_value(weapon.get("name")) or "",
        fill="white",
        font=font(28),
        anchor="mm",
    )
    draw.text(
        (496, 212),
        f"Lv{int_value(weapon.get('level'))}",
        fill="white",
        font=font(28),
        anchor="mm",
    )
    draw.text(
        (513, 80),
        str(int_value(weapon.get("affix_level"))),
        fill="white",
        font=font(28),
        anchor="mm",
    )
    return card


def _paste_character_placeholder(
    card: Image.Image,
    character: Mapping[str, object],
) -> None:
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((56, 58, 258, 260), radius=28, outline=(255, 255, 255, 130), width=3)
    name = text_value(character.get("name")) or "?"
    draw.text((157, 159), name[:2], fill=(255, 255, 255, 210), font=font(44), anchor="mm")


def _remote_image(
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


def _first_remote_image(
    urls: Sequence[str | None],
    asset_images: Mapping[str, bytes],
    size: tuple[int, int],
) -> Image.Image | None:
    for url in urls:
        image = _remote_image(url, asset_images, size)
        if image is not None:
            return image
    return None


def _sorted_characters(
    characters: Sequence[Mapping[str, object]],
) -> list[Mapping[str, object]]:
    return sorted(
        characters,
        key=lambda character: (
            -_character_rarity(character.get("rarity")),
            -int_value(character.get("fetter")),
            -int_value(character.get("actived_constellation_num")),
        ),
    )


def character_portrait_url(character: Mapping[str, object]) -> str | None:
    character_id = int_value(character.get("id"))
    if character_id <= 0:
        return None
    return f"{GENSHINUID_RESOURCE_BASE}/chars/{character_id}.png"


def weapon_icon_url(weapon: Mapping[str, object]) -> str | None:
    name = text_value(weapon.get("name"))
    if not name:
        return None
    return f"{GENSHINUID_RESOURCE_BASE}/weapon/{quote(name, safe='')}.png"


def character_mys_image_urls(character: Mapping[str, object]) -> tuple[str | None, str | None]:
    return text_value(character.get("image")), text_value(character.get("icon"))


def character_namecard_url(character: Mapping[str, object]) -> str | None:
    for key in ("namecard", "name_card", "namecard_pic", "namecard_url"):
        url = text_value(character.get(key))
        if url:
            return url
    character_id = int_value(character.get("id"))
    if character_id <= 0:
        return None
    return f"{GENSHINUID_RESOURCE_BASE}/char_namecard_pic/{character_id}.png"


def _character_rarity(value: object) -> int:
    rarity = int_value(value, 4)
    if rarity > 5:
        return 4
    return 5 if rarity == 5 else 4


def _rarity(value: object, *, minimum: int, maximum: int = 5, default: int) -> int:
    rarity = int_value(value, default)
    return min(max(rarity, minimum), maximum)
