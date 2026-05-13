from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from urllib.parse import quote

from PIL import Image, ImageDraw, ImageFilter

from gsuid_cli.renderers._text_helpers import _mapping
from gsuid_cli.renderers.common import (
    asset_path,
    crop_center,
    font,
    image_from_bytes,
    int_value,
    open_rgba,
    png_bytes,
    sequence as _sequence,
    text_value,
)
from gsuid_cli.text import t as _t

TEXTURE = asset_path("wiki", "textures")
AMBR_UI_URL = "https://gi.yatta.moe/assets/UI"
GENSHINUID_RESOURCE_BASE = "genshinuid://resource"

WHITE = (255, 255, 255)
GRAY = (230, 230, 230)
GOLD = (255, 206, 51)
BROWN = (154, 123, 51)
ARTIFACT_BONUS_TEXT_X = 151
ARTIFACT_BONUS_TEXT_WIDTH = 367

WEAPON_TYPE_NAMES = {
    "WEAPON_SWORD_ONE_HAND": _t("gsuid.renderers.panel.text.61_29.19c268b4"),
    "WEAPON_CLAYMORE": _t("gsuid.renderers.panel.text.62_23.1a1f46df"),
    "WEAPON_POLE": _t("gsuid.renderers.panel.text.63_19.5d4b74a8"),
    "WEAPON_CATALYST": _t("gsuid.renderers.panel.metrics.1053_22.4813ba67"),
    "WEAPON_BOW": _t("gsuid.renderers.panel.metrics.1055_24.a0ec11cd"),
}
ELEMENT_NAMES = {
    "Fire": _t("gsuid.renderers.wiki.picwiki.41_12.efb26208"),
    "Water": _t("gsuid.renderers.wiki.picwiki.42_13.8ffbf192"),
    "Wind": _t("gsuid.renderers.wiki.picwiki.43_12.534418ad"),
    "Electric": _t("gsuid.renderers.wiki.picwiki.44_16.deaefde2"),
    "Grass": _t("gsuid.renderers.wiki.picwiki.45_13.67447716"),
    "Ice": _t("gsuid.renderers.wiki.picwiki.46_11.6c20967f"),
    "Rock": _t("gsuid.renderers.wiki.picwiki.47_12.9ba9dc86"),
}


def render_wiki_food_card(
    item: Mapping[str, object],
    *,
    asset_images: Mapping[str, bytes] | None = None,
) -> bytes:
    asset_images = asset_images or {}
    recipe = _food_recipe(item.get("recipe"))
    effect = _food_effect(item)
    desc = _clean_text(item.get("description")) or _t("gsuid.renderers.wiki.picwiki.59_51.6baf31a7")

    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    effect_text = _wrap_text(effect, font(22), 440, measure)
    desc_text = _wrap_text(desc, font(22), 440, measure)
    effect_h = _text_height(effect_text, font(22), measure)
    desc_h = _text_height(desc_text, font(22), measure)
    width, height = 600, 750 + effect_h + desc_h

    image = _simple_bg(width, height)
    draw = ImageDraw.Draw(image)

    type_icon = _remote_or_local_icon(
        text_value(recipe.get("effect_icon_url")),
        asset_images,
        local_name=f"{text_value(recipe.get('effect_icon')) or ''}.png",
        size=(40, 40),
    )
    image.paste(type_icon, (49, 38), type_icon)
    _draw_text(draw, (105, 59), _name(item), WHITE, font(44), "lm")
    image.paste(_star_png(_rank(item)), (45, 83), _star_png(_rank(item)))

    btag = open_rgba(TEXTURE / "btag.png")
    image.paste(btag, (50, 29), btag)

    food_icon = _remote_image(text_value(item.get("icon_url")), asset_images, (320, 320))
    if food_icon is None:
        food_icon = _placeholder((320, 320), _name(item)[:2])
    image.paste(food_icon, (140, 119), food_icon)

    _draw_text(
        draw, (45, 465), _t("gsuid.renderers.wiki.picwiki.89_32.f488e9b9"), GRAY, font(18), "lm"
    )
    _draw_text(
        draw, (45, 500), _t("gsuid.renderers.wiki.picwiki.90_32.df2144b4"), WHITE, font(36), "lm"
    )

    cost_tag = open_rgba(TEXTURE / "cost_tag.png")
    desc_tag = open_rgba(TEXTURE / "desc_tag.png")
    image.paste(cost_tag, (25, 550), cost_tag)
    image.paste(desc_tag, (25, 570 + effect_h), desc_tag)
    draw.multiline_text((90, 560), effect_text, fill=GRAY, font=font(22), spacing=6)
    draw.multiline_text((90, 580 + effect_h), desc_text, fill=GRAY, font=font(22), spacing=6)

    cost_bg = open_rgba(TEXTURE / "wiki_weapon_cost.png")
    cost_draw = ImageDraw.Draw(cost_bg)
    for index, material in enumerate(_food_inputs(recipe)[:5]):
        icon = _remote_image(text_value(material.get("icon_url")), asset_images, (64, 64))
        if icon is None:
            icon = _unknown((64, 64))
        x = 67 + 100 * index
        cost_bg.paste(icon, (x, 46), icon)
        _draw_text(
            cost_draw, (x + 32, 123), str(int_value(material.get("count"))), WHITE, font(18), "mm"
        )
    image.paste(cost_bg, (0, 580 + effect_h + desc_h), cost_bg)

    return png_bytes(image, rgb=True)


def render_wiki_artifact_card(
    item: Mapping[str, object],
    *,
    asset_images: Mapping[str, bytes] | None = None,
) -> bytes:
    asset_images = asset_images or {}
    bonuses = [value for value in _mapping(item.get("bonuses")).values() if value]
    if not bonuses:
        bonuses = [_t("gsuid.renderers.wiki.picwiki.123_19.d07b7a24")]

    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bonus_texts = [
        _wrap_text(_clean_text(value), font(22), ARTIFACT_BONUS_TEXT_WIDTH, measure)
        for value in bonuses[:2]
    ]
    heights = [_text_height(text, font(22), measure) for text in bonus_texts]
    y1 = heights[0] if heights else 0
    y2 = heights[1] if len(heights) > 1 else 0
    image, height = _artifact_base(y1, y2)

    if len(bonus_texts) == 1:
        suitbar = open_rgba(TEXTURE / "wiki_artifacts_suitbar1.png")
        image.paste(suitbar, (63, 260), suitbar)
    else:
        suitbar2 = open_rgba(TEXTURE / "wiki_artifacts_suitbar2.png")
        suitbar4 = open_rgba(TEXTURE / "wiki_artifacts_suitbar4.png")
        image.paste(suitbar2, (63, 260), suitbar2)
        image.paste(suitbar4, (63, 290 + y1), suitbar4)
        slider = open_rgba(TEXTURE / "slider.png")
        image.paste(slider, (0, 270 + y1), slider)

    artifacts_bar = open_rgba(TEXTURE / "artifacts_bar.png")
    artifacts_draw = ImageDraw.Draw(artifacts_bar)
    for index, part in enumerate(_artifact_parts(item)[:5]):
        icon = _remote_image(text_value(part.get("icon_url")), asset_images, (70, 70))
        if icon is None:
            icon = _unknown((70, 70))
        artifacts_bar.paste(icon, (81, 37 + index * 90), icon)
        _draw_text(
            artifacts_draw,
            (183, 58 + 90 * index),
            text_value(part.get("name")) or "",
            BROWN,
            font(26),
            "lm",
        )
        desc = _wrap_text(text_value(part.get("description")) or "", font(14), 340, artifacts_draw)
        artifacts_draw.multiline_text(
            (183, 90 + 90 * index),
            desc,
            fill=(182, 173, 165),
            font=font(14),
            anchor="lm",
            spacing=2,
        )
    image.paste(artifacts_bar, (0, 300 + y1 + y2), artifacts_bar)

    draw = ImageDraw.Draw(image)
    _draw_text(draw, (295, 182), _name(item), BROWN, font(40), "mm")
    rarity = (
        _t("gsuid.renderers.wiki.picwiki.174_13.d7cff412")
        + "/".join(str(v) for v in _sequence(item.get("level_list")))
        + _t("gsuid.renderers.gacha.600_70.92ae747c")
    )
    _draw_text(draw, (295, 230), rarity, (175, 145, 75), font(22), "mm")
    for index, text in enumerate(bonus_texts):
        draw.multiline_text(
            (ARTIFACT_BONUS_TEXT_X, 263 + (y1 + 30) * index),
            text,
            fill=(111, 100, 80),
            font=font(22),
            spacing=6,
        )

    logo = open_rgba(TEXTURE / "wuyi_dark.png")
    image.paste(logo, (370, height - 30), logo)
    return png_bytes(image, rgb=True)


def render_wiki_weapon_card(
    item: Mapping[str, object],
    *,
    asset_images: Mapping[str, bytes] | None = None,
) -> bytes:
    asset_images = asset_images or {}
    effect_name, effect_desc = _weapon_effect(item)
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    effect_text = _wrap_text(effect_desc, font(22), 490, measure)
    effect_h = _text_height(effect_text, font(22), measure)
    width, height = 600, 1110 + effect_h

    image = _simple_bg(width, height)
    draw = ImageDraw.Draw(image)
    _draw_text(draw, (44, 59), _name(item), WHITE, font(44), "lm")
    image.paste(_star_png(_rank(item)), (45, 83), _star_png(_rank(item)))

    type_name = _weapon_type(item)
    type_path = TEXTURE / f"{type_name}.png"
    if type_path.exists():
        type_icon = open_rgba(type_path)
        image.paste(type_icon, (44, 158), type_icon)

    weapon_icon = _first_remote_image(
        [weapon_resource_url(item), text_value(item.get("icon_url"))],
        asset_images,
        (320, 320),
    )
    if weapon_icon is None:
        weapon_icon = _placeholder((320, 320), _name(item)[:2])
    image.paste(weapon_icon, (140, 130), weapon_icon)

    _draw_text(
        draw,
        (45, 744),
        _t("gsuid.renderers.panel.image.90_30.1ad8495e"),
        (214, 214, 214),
        font(18),
        "lm",
    )
    _draw_text(
        draw, (545, 744), _prop_label(item.get("special_prop")), (214, 214, 214), font(18), "rm"
    )
    base_atk = _base_attack(item)
    _draw_text(
        draw,
        (45, 779),
        str(base_atk) if base_atk else _t("gsuid.renderers.daily.text.211_11.d9c32a4c"),
        WHITE,
        font(36),
        "lm",
    )
    _draw_text(
        draw, (545, 779), _t("gsuid.renderers.wiki.picwiki.228_33.9ebf33bf"), WHITE, font(36), "rm"
    )
    _draw_text(draw, (46, 837), effect_name, GOLD, font(28), "lm")
    draw.multiline_text((46, 866), effect_text, fill=(214, 214, 214), font=font(22), spacing=6)

    cost_tag = open_rgba(TEXTURE / "cost_tag.png")
    image.paste(cost_tag, (37, 890 + effect_h), cost_tag)
    cost_bg = _cost_bar(_weapon_cost_entries(item), asset_images, max_items=5)
    _draw_text(
        draw,
        (88, 918 + effect_h),
        _t("gsuid.renderers.wiki.picwiki.235_43.dcb7501d"),
        WHITE,
        font(22),
        "lm",
    )
    image.paste(cost_bg, (0, 920 + effect_h), cost_bg)
    return png_bytes(image, rgb=True)


def render_wiki_character_materials_card(
    item: Mapping[str, object],
    *,
    asset_images: Mapping[str, bytes] | None = None,
) -> bytes:
    asset_images = asset_images or {}
    image = _simple_bg(900, 1800)
    draw = ImageDraw.Draw(image)

    avatar = _first_remote_image(
        [character_resource_url(item), text_value(item.get("icon_url"))],
        asset_images,
        (222, 222),
    )
    if avatar is None:
        avatar = _placeholder((222, 222), _name(item)[:2])
    ring = _circle_with_ring(avatar, 222)
    image.paste(ring, (80, 90), ring)

    desc = _wrap_text(text_value(item.get("description")) or "", font(24), 341, draw)
    title = (text_value(item.get("title")) or "").replace("「", "").replace("」", "")
    _draw_text(draw, (400, 161), f"{title}·{_name(item)}".strip("·"), WHITE, font(44), "lm")
    draw.multiline_text((336, 230), desc, fill=GRAY, font=font(24), spacing=6)
    _paste_element_and_stars(image, item, (330, 130), (335, 188), star_size=None)

    talent_one = _talent_cost_entries(item)
    talent_all = [{**entry, "count": int_value(entry.get("count")) * 3} for entry in talent_one]
    sections = [
        (_t("gsuid.renderers.wiki.picwiki.268_9.117d629a"), _character_ascension_entries(item)),
        (_t("gsuid.renderers.wiki.picwiki.269_9.957f8b65"), talent_all),
        (_t("gsuid.renderers.wiki.picwiki.270_9.1a8a715d"), talent_one),
    ]
    cost_title = open_rgba(TEXTURE / "cost_title.png")
    image.paste(cost_title, (0, 338), cost_title)
    _draw_text(
        draw, (450, 383), _t("gsuid.renderers.wiki.picwiki.274_33.6a3c868a"), WHITE, font(30), "mm"
    )

    for index, (title_text, entries) in enumerate(sections):
        section = _material_section(title_text, entries, asset_images)
        image.paste(section, (0, 460 + 445 * index), section)
    return png_bytes(image, rgb=True)


def render_wiki_constellation_card(
    item: Mapping[str, object],
    *,
    constellation: int | None,
    asset_images: Mapping[str, bytes] | None = None,
) -> bytes:
    asset_images = asset_images or {}
    constellations = _constellation_entries(item)
    if constellation is not None:
        selected = constellations[constellation - 1 : constellation]
        card = _constellation_entry_card(selected[0], asset_images, with_background=True)
        return png_bytes(card, rgb=True)

    cards = [
        _constellation_entry_card(row, asset_images, with_background=False)
        for row in constellations
    ]
    body_height = sum(card.size[1] for card in cards)
    image = _simple_bg(600, 280 + body_height)
    draw = ImageDraw.Draw(image)

    avatar = _first_remote_image(
        [character_resource_url(item), text_value(item.get("icon_url"))],
        asset_images,
        (148, 148),
    )
    if avatar is None:
        avatar = _placeholder((148, 148), _name(item)[:2])
    ring = _circle_with_ring(avatar, 148)
    image.paste(ring, (40, 77), ring)

    desc = _wrap_text(text_value(item.get("description")) or "", font(18), 350, draw)
    draw.multiline_text((205, 161), desc, fill=GRAY, font=font(18), spacing=4)
    _draw_text(
        draw,
        (232, 102),
        f"{text_value(item.get('title')) or ''}·{_name(item)}".strip("·"),
        WHITE,
        font(32),
        "lm",
    )
    _paste_element_and_stars(image, item, (188, 81), (201, 120), star_size=(129, 33))

    y = 253
    for card in cards:
        image.paste(card, (0, y), card)
        y += card.size[1]
    return png_bytes(image, rgb=True)


def wiki_asset_urls(render_kind: str, item: Mapping[str, object]) -> list[str]:
    urls: list[str] = []
    if render_kind == "food":
        _append_url(urls, item.get("icon_url"))
        recipe = _food_recipe(item.get("recipe"))
        _append_url(urls, recipe.get("effect_icon_url"))
        for material in _food_inputs(recipe):
            _append_url(urls, material.get("icon_url"))
    elif render_kind == "artifact":
        for part in _artifact_parts(item):
            _append_url(urls, part.get("icon_url"))
    elif render_kind == "weapon":
        _append_url(urls, weapon_resource_url(item))
        _append_url(urls, item.get("icon_url"))
        for material in _weapon_cost_entries(item):
            _append_url(urls, material.get("icon_url"))
    elif render_kind == "character-materials":
        _append_url(urls, character_resource_url(item))
        _append_url(urls, item.get("icon_url"))
        for material in [*_character_ascension_entries(item), *_talent_cost_entries(item)]:
            _append_url(urls, material.get("icon_url"))
    elif render_kind == "constellation":
        _append_url(urls, character_resource_url(item))
        _append_url(urls, item.get("icon_url"))
        for row in _constellation_entries(item):
            _append_url(urls, row.get("icon_url"))
    return urls


def weapon_resource_url(item: Mapping[str, object]) -> str | None:
    name = text_value(item.get("name"))
    return f"{GENSHINUID_RESOURCE_BASE}/weapon/{quote(name, safe='')}.png" if name else None


def character_resource_url(item: Mapping[str, object]) -> str | None:
    character_id = int_value(item.get("id"))
    if character_id <= 0:
        return None
    return f"{GENSHINUID_RESOURCE_BASE}/chars/{character_id}.png"


def _simple_bg(width: int, height: int) -> Image.Image:
    source = Image.open(TEXTURE / "wiki_weapon_bg.jpg")
    image = crop_center(source, width, height).convert("RGBA")
    if height > 1200:
        image = image.filter(ImageFilter.GaussianBlur(radius=1))
    return image


def _artifact_base(y1: int, y2: int) -> tuple[Image.Image, int]:
    height = 250 + y1 + y2 + 30 + 500 + 50
    middle_count = ((height - 760) // 50) + 1
    image = Image.new("RGBA", (590, height))
    top = open_rgba(TEXTURE / "wiki_artifacts_bg1.png")
    middle = open_rgba(TEXTURE / "wiki_artifacts_bg2.png")
    bottom = open_rgba(TEXTURE / "wiki_artifacts_bg3.png")
    image.paste(top, (0, 0), top)
    for index in range(middle_count):
        image.paste(middle, (0, 660 + index * 50), middle)
    image.paste(bottom, (0, height - 100), bottom)
    star_bar = open_rgba(TEXTURE / "star_bar.png")
    image.paste(star_bar, (95, 215), star_bar)
    return image, height


def _material_section(
    title: str,
    entries: Sequence[Mapping[str, object]],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    image = Image.new("RGBA", (900, 450))
    draw = ImageDraw.Draw(image)
    cost_bg = open_rgba(TEXTURE / "cost_bg.png")
    row_bg = open_rgba(TEXTURE / "wiki_weapon_cost.png").resize((900, 255))
    tag = open_rgba(TEXTURE / "cost_tag.png").resize((75, 75))
    image.paste(cost_bg, (0, 0), cost_bg)
    image.paste(row_bg, (0, 15), row_bg)
    image.paste(row_bg, (0, 180), row_bg)
    image.paste(tag, (65, -20), tag)
    _draw_text(draw, (130, 22), title, WHITE, font(36), "lm")

    for index, material in enumerate(entries[:10]):
        icon = _remote_image(text_value(material.get("icon_url")), asset_images, (96, 96))
        if icon is None:
            icon = _unknown((96, 96))
        x = 101 + 150 * (index % 5)
        y = 84 + 165 * (index // 5)
        image.paste(icon, (x, y), icon)
        _draw_text(
            draw, (x + 48, y + 114), str(int_value(material.get("count"))), WHITE, font(26), "mm"
        )
    return image


def _cost_bar(
    entries: Sequence[Mapping[str, object]],
    asset_images: Mapping[str, bytes],
    *,
    max_items: int,
) -> Image.Image:
    image = open_rgba(TEXTURE / "wiki_weapon_cost.png")
    draw = ImageDraw.Draw(image)
    for index, material in enumerate(entries[:max_items]):
        icon = _remote_image(text_value(material.get("icon_url")), asset_images, (64, 64))
        if icon is None:
            icon = _unknown((64, 64))
        x = 67 + 100 * index
        image.paste(icon, (x, 46), icon)
        _draw_text(
            draw, (x + 32, 123), str(int_value(material.get("count"))), WHITE, font(18), "mm"
        )
    if len(entries) > max_items:
        _draw_text(draw, (560, 123), f"+{len(entries) - max_items}", WHITE, font(18), "mm")
    return image


def _constellation_entry_card(
    row: Mapping[str, object],
    asset_images: Mapping[str, bytes],
    *,
    with_background: bool,
) -> Image.Image:
    effect = _wrap_text(_clean_text(row.get("description")) or "", font(20), 420)
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    effect_h = _text_height(effect, font(20), measure)
    height = 90 + effect_h
    image = _simple_bg(600, height) if with_background else Image.new("RGBA", (600, height))
    draw = ImageDraw.Draw(image)
    if with_background:
        panel = Image.new("RGBA", (600, height))
        panel_draw = ImageDraw.Draw(panel)
        panel_draw.rounded_rectangle(
            (28, 7, 572, 80 + effect_h), fill=(255, 255, 255, 60), radius=20
        )
        image.paste(panel, (0, 0), panel)

    ring_bg = open_rgba(TEXTURE / "ring_bg.png").resize((74, 74))
    image.paste(ring_bg, (38, 20), ring_bg)
    icon = _remote_image(text_value(row.get("icon_url")), asset_images, (38, 38))
    if icon is None:
        icon = _unknown((38, 38))
    image.paste(icon, (57, 37), icon)
    _draw_text(draw, (134, 40), text_value(row.get("name")) or "", GOLD, font(28), "lm")
    draw.multiline_text((130, 60), effect, fill=GRAY, font=font(20), spacing=5)
    return image


def _paste_element_and_stars(
    image: Image.Image,
    item: Mapping[str, object],
    element_pos: tuple[int, int],
    star_pos: tuple[int, int],
    *,
    star_size: tuple[int, int] | None,
) -> None:
    element = _element_name(item.get("element"))
    element_path = TEXTURE / f"{element}.png"
    element_icon = (
        open_rgba(element_path).resize((54, 54) if star_size is None else (36, 36))
        if element_path.exists()
        else _unknown((54, 54))
    )
    image.paste(element_icon, element_pos, element_icon)
    stars = _star_png(_rank(item))
    if star_size is not None:
        stars = stars.resize(star_size)
    image.paste(stars, star_pos, stars)


def _circle_with_ring(source: Image.Image, size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(image)
    draw.ellipse((0, 0, size - 1, size - 1), fill=WHITE)
    inner = size - 14
    avatar = crop_center(source, inner, inner).convert("RGBA")
    mask = Image.new("L", (inner, inner), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, inner - 1, inner - 1), fill=255)
    image.paste(avatar, (7, 7), mask)
    return image


def _remote_or_local_icon(
    url: str | None,
    asset_images: Mapping[str, bytes],
    *,
    local_name: str,
    size: tuple[int, int],
) -> Image.Image:
    image = _remote_image(url, asset_images, size)
    if image is not None:
        return image
    local_path = TEXTURE / local_name
    if local_path.exists():
        return open_rgba(local_path).resize(size)
    return _unknown(size)


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


def _unknown(size: tuple[int, int]) -> Image.Image:
    return open_rgba(TEXTURE / "unknown.png").resize(size)


def _placeholder(size: tuple[int, int], text: str) -> Image.Image:
    image = Image.new("RGBA", size, (255, 255, 255, 35))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, size[0] - 1, size[1] - 1), radius=24, outline=(255, 255, 255, 120), width=3
    )
    _draw_text(draw, (size[0] // 2, size[1] // 2), text or "?", WHITE, font(42), "mm")
    return image


def _star_png(rank: int) -> Image.Image:
    rank = min(max(rank, 1), 5)
    return open_rgba(TEXTURE / "weapon_star" / f"s-{rank}.png")


def _food_effect(item: Mapping[str, object]) -> str:
    recipe = _mapping(item.get("recipe"))
    effect = recipe.get("effect")
    if isinstance(effect, Mapping):
        values = [text_value(value) for value in effect.values()]
        effect_text = next((value for value in values if value), None)
        if effect_text:
            return _clean_text(effect_text)
    return _clean_text(item.get("effect")) or _t("gsuid.renderers.wiki.picwiki.582_46.43ce197c")


def _food_inputs(recipe: Mapping[str, object]) -> list[Mapping[str, object]]:
    return [item for item in _sequence(recipe.get("input")) if isinstance(item, Mapping)]


def _food_recipe(value: object) -> Mapping[str, object]:
    recipe = _mapping(value)
    inputs = recipe.get("input")
    if isinstance(inputs, list):
        normalized_inputs = inputs
    else:
        normalized_inputs = []
        if isinstance(inputs, Mapping):
            for item_id, item in inputs.items():
                if not isinstance(item, Mapping):
                    continue
                icon = item.get("icon")
                normalized_inputs.append(
                    {
                        "id": str(item_id),
                        "name": item.get("name"),
                        "icon": icon,
                        "icon_url": _ambr_ui_icon_url(icon),
                        "count": item.get("count"),
                    }
                )
    effect_icon = recipe.get("effect_icon") or recipe.get("effectIcon")
    return {
        "effect": recipe.get("effect") or {},
        "effect_icon": effect_icon,
        "effect_icon_url": recipe.get("effect_icon_url") or _ambr_ui_icon_url(effect_icon),
        "input": normalized_inputs,
    }


def _artifact_parts(item: Mapping[str, object]) -> list[Mapping[str, object]]:
    return [part for part in _sequence(item.get("suit")) if isinstance(part, Mapping)]


def _weapon_effect(item: Mapping[str, object]) -> tuple[str, str]:
    affixes = [affix for affix in _sequence(item.get("affixes")) if isinstance(affix, Mapping)]
    if not affixes:
        return _t("gsuid.renderers.wiki.picwiki.626_15.c1adb117"), _t(
            "gsuid.renderers.wiki.picwiki.626_15.c1adb117"
        )
    affix = affixes[0]
    upgrade = _mapping(affix.get("upgrade"))
    effect = text_value(upgrade.get("0")) or text_value(next(iter(upgrade.values()), ""))
    return text_value(affix.get("name")) or _t(
        "gsuid.renderers.wiki.picwiki.630_44.037909eb"
    ), _clean_text(effect) or _t("gsuid.renderers.wiki.picwiki.626_15.c1adb117")


def _base_attack(item: Mapping[str, object]) -> int | None:
    upgrade = _mapping(item.get("upgrade"))
    props = _sequence(upgrade.get("prop"))
    for prop in props:
        if isinstance(prop, Mapping) and prop.get("propType") == "FIGHT_PROP_BASE_ATTACK":
            return round(float(prop.get("initValue") or 0))
    return None


def _weapon_cost_entries(item: Mapping[str, object]) -> list[Mapping[str, object]]:
    return _material_entries(_mapping(item.get("ascension")))


def _character_ascension_entries(item: Mapping[str, object]) -> list[Mapping[str, object]]:
    return _material_entries(_mapping(item.get("ascension")))


def _talent_cost_entries(item: Mapping[str, object]) -> list[Mapping[str, object]]:
    talents = [
        talent for talent in _mapping(item.get("talent")).values() if isinstance(talent, Mapping)
    ]
    for talent in talents:
        promote = _mapping(talent.get("promote"))
        entries: dict[str, int] = {}
        for level in promote.values():
            if not isinstance(level, Mapping):
                continue
            for item_id, count in _mapping(level.get("costItems")).items():
                entries[str(item_id)] = entries.get(str(item_id), 0) + int_value(count)
        if entries:
            return _material_entries(entries)
    return []


def _material_entries(counts: Mapping[str, object]) -> list[Mapping[str, object]]:
    entries = []
    for item_id, count in counts.items():
        text_id = str(item_id)
        entries.append(
            {"id": text_id, "count": count, "icon_url": f"{AMBR_UI_URL}/UI_ItemIcon_{text_id}.png"}
        )
    entries.sort(key=lambda entry: str(entry["id"]))
    return entries


def _ambr_ui_icon_url(icon: object) -> str | None:
    if not isinstance(icon, str) or not icon:
        return None
    if icon.startswith("UI_RelicIcon_"):
        return f"{AMBR_UI_URL}/reliquary/{icon}.png"
    return f"{AMBR_UI_URL}/{icon}.png"


def _constellation_entries(item: Mapping[str, object]) -> list[Mapping[str, object]]:
    entries = []
    for row in _mapping(item.get("constellation")).values():
        if not isinstance(row, Mapping):
            continue
        icon = text_value(row.get("icon"))
        entries.append(
            {
                **row,
                "icon_url": f"{AMBR_UI_URL}/{icon}.png" if icon else None,
            }
        )
    return entries[:6]


def _weapon_type(item: Mapping[str, object]) -> str:
    value = text_value(item.get("weapon_type"))
    if not value:
        return _t("gsuid.renderers.panel.text.61_29.19c268b4")
    return WEAPON_TYPE_NAMES.get(value, value)


def _element_name(value: object) -> str:
    text = text_value(value)
    if not text:
        return _t("gsuid.renderers.wiki.picwiki.43_12.534418ad")
    return ELEMENT_NAMES.get(text, text)


def _prop_label(value: object) -> str:
    labels = {
        "FIGHT_PROP_CHARGE_EFFICIENCY": _t("gsuid.providers.akasha.68_4.a7a24305"),
        "FIGHT_PROP_ATTACK_PERCENT": _t("gsuid.renderers.panel.image.88_25.ef28aed2"),
        "FIGHT_PROP_CRITICAL": _t("gsuid.providers.akasha.70_4.33e0f20a"),
        "FIGHT_PROP_CRITICAL_HURT": _t("gsuid.providers.akasha.72_4.7c0dd18b"),
        "FIGHT_PROP_ELEMENT_MASTERY": _t("gsuid.providers.akasha.66_4.af09dad1"),
        "FIGHT_PROP_HP_PERCENT": _t("gsuid.renderers.panel.metrics.357_7.575ca7a8"),
        "FIGHT_PROP_DEFENSE_PERCENT": _t("gsuid.renderers.panel.image.91_26.2557c107"),
        "FIGHT_PROP_PHYSICAL_ADD_HURT": _t("gsuid.renderers.panel.image.109_36.be65271f"),
    }
    return labels.get(text_value(value) or "", "")


def _clean_text(value: object) -> str:
    text = text_value(value) or ""
    text = text.replace("\\n", "\n")
    text = re.sub(r"</?color[^>]*>", "", text)
    return text.replace("**", "")


def _wrap_text(
    value: object,
    text_font,
    max_width: int,
    draw: ImageDraw.ImageDraw | None = None,
) -> str:
    draw = draw or ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines: list[str] = []
    for source_line in _clean_text(value).splitlines() or [""]:
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
    bbox = draw.multiline_textbbox((0, 0), text, font=text_font, spacing=6)
    return bbox[3] - bbox[1]


def _draw_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    fill: tuple[int, int, int] | str,
    text_font,
    anchor: str,
) -> None:
    draw.text(position, text, fill=fill, font=text_font, anchor=anchor)


def _name(item: Mapping[str, object]) -> str:
    return text_value(item.get("name")) or _t("gsuid.renderers.daily.text.211_11.d9c32a4c")


def _rank(item: Mapping[str, object]) -> int:
    rank = int_value(item.get("rank"), 0)
    if rank > 0:
        return rank
    level_list = [int_value(value) for value in _sequence(item.get("level_list"))]
    return max(level_list or [1])


def _append_url(urls: list[str], value: object) -> None:
    url = text_value(value)
    if url and url not in urls:
        urls.append(url)
