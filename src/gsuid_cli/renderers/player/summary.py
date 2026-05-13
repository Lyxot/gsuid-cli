from __future__ import annotations

from collections.abc import Mapping, Sequence
from urllib.parse import quote

from PIL import Image, ImageDraw

from gsuid_cli.renderers.common import (
    asset_path,
    crop_center,
    font,
    image_from_bytes,
    int_value,
    open_rgba,
    png_bytes,
    text_value,
    v4_background,
)
from gsuid_cli.renderers.player.characters import (
    WIDTH,
    character_portrait_url,
    render_player_characters_section,
)
from gsuid_cli.text import t as _t

SUMMARY_TEXTURE = asset_path("player", "summary", "textures")
PUBLIC_TEXTURE = asset_path("public", "textures")
ENKA_UI_BASE = "https://enka.network/ui"

CMAP = {
    _t("gsuid.renderers.daily.text.22_9.71f4594b"): [10, 8, 6, 4, 2],
    _t("gsuid.renderers.daily.text.21_9.d6e52915"): [10, 8, 6, 4, 2],
    _t("gsuid.renderers.player.summary.32_4.080b44d7"): [10, 8, 6, 4, 2],
    _t("gsuid.renderers.player.summary.33_4.5bfde491"): [10, 8, 6, 4, 2],
    _t("gsuid.renderers.player.summary.34_4.3d931c3a"): [0, 0, 0, 0, 0],
    _t("gsuid.renderers.daily.text.20_9.60582a7f"): [10, 8, 6, 4, 2],
    _t("gsuid.renderers.player.summary.36_4.df0e3caf"): [12, 10, 8, 5, 2],
    _t("gsuid.renderers.daily.text.19_9.cf9effa7"): [8, 7, 6, 4, 2],
    _t("gsuid.renderers.daily.text.18_9.4e2f394b"): [8, 7, 6, 4, 2],
    _t("gsuid.renderers.player.summary.39_4.92406835"): [20, 16, 12, 8, 4],
    _t("gsuid.renderers.player.summary.40_4.ed2a2cc9"): [50, 40, 30, 20, 10],
    _t("gsuid.renderers.player.summary.41_4.ab9bf2de"): [10, 8, 6, 4, 2],
    _t("gsuid.renderers.player.summary.42_4.bb6a4532"): [50, 40, 30, 20, 10],
    _t("gsuid.renderers.player.summary.43_4.9b782077"): [12, 10, 8, 5, 2],
    _t("gsuid.renderers.player.summary.44_4.59d5cc2a"): [66, 50, 35, 25, 10],
    _t("gsuid.renderers.player.summary.45_4.56e70957"): [131, 100, 70, 40, 10],
    _t("gsuid.renderers.player.summary.46_4.6eeccf4e"): [181, 141, 100, 60, 15],
    _t("gsuid.renderers.player.summary.47_4.d5bbd092"): [271, 211, 150, 90, 20],
    _t("gsuid.renderers.player.summary.48_4.53cdf0ba"): [271, 211, 150, 90, 20],
    _t("gsuid.renderers.player.summary.49_4.463844dd"): [271, 211, 150, 90, 20],
    _t("gsuid.renderers.player.summary.50_4.600de4a5"): [271, 211, 150, 90, 20],
    _t("gsuid.renderers.player.summary.51_4.68a591a2"): [271, 211, 150, 90, 20],
    _t("gsuid.renderers.player.summary.52_4.2eef40ce"): [367, 293, 220, 146, 73],
    _t("gsuid.renderers.player.summary.53_4.cad09647"): [960, 768, 576, 384, 192],
    _t("gsuid.renderers.player.summary.54_4.8d1ca1ac"): [3043, 2434, 1825, 1217, 608],
    _t("gsuid.renderers.player.summary.55_4.33e13053"): [3570, 2856, 2142, 1428, 714],
    _t("gsuid.renderers.player.summary.56_4.0788ed91"): [366, 292, 219, 146, 73],
}

DMAP = {
    _t("gsuid.renderers.daily.text.22_9.71f4594b"): 14,
    _t("gsuid.renderers.daily.text.21_9.d6e52915"): 250,
    _t("gsuid.renderers.player.summary.32_4.080b44d7"): 220,
    _t("gsuid.renderers.player.summary.33_4.5bfde491"): 220,
    _t("gsuid.renderers.player.summary.34_4.3d931c3a"): 45,
    _t("gsuid.renderers.daily.text.20_9.60582a7f"): 30,
    _t("gsuid.renderers.player.summary.36_4.df0e3caf"): -60,
    _t("gsuid.renderers.daily.text.19_9.cf9effa7"): 200,
    _t("gsuid.renderers.daily.text.18_9.4e2f394b"): 300,
}

STCMAP = {
    "electro": _t("gsuid.renderers.player.summary.46_4.6eeccf4e"),
    "geo": _t("gsuid.renderers.player.summary.45_4.56e70957"),
    "hydro": _t("gsuid.renderers.player.summary.48_4.53cdf0ba"),
    "anemo": _t("gsuid.renderers.player.summary.44_4.59d5cc2a"),
    "dendro": _t("gsuid.renderers.player.summary.47_4.d5bbd092"),
    "cryo": _t("gsuid.renderers.player.summary.49_4.463844dd"),
    "pyro": _t("gsuid.renderers.player.summary.50_4.600de4a5"),
    "moono": _t("gsuid.renderers.player.summary.51_4.68a591a2"),
}

EXPMAX_DATA = {
    _t("gsuid.renderers.player.summary.44_4.59d5cc2a"): 66,
    _t("gsuid.renderers.player.summary.45_4.56e70957"): 131,
    _t("gsuid.renderers.player.summary.46_4.6eeccf4e"): 181,
    _t("gsuid.renderers.player.summary.47_4.d5bbd092"): 271,
    _t("gsuid.renderers.player.summary.48_4.53cdf0ba"): 271,
    _t("gsuid.renderers.player.summary.49_4.463844dd"): 271,
    _t("gsuid.renderers.player.summary.50_4.600de4a5"): 271,
    _t("gsuid.renderers.player.summary.51_4.68a591a2"): 271,
}

CHEST_MAX = {
    _t("gsuid.renderers.player.summary.55_4.33e13053"): 3570,
    _t("gsuid.renderers.player.summary.54_4.8d1ca1ac"): 3043,
    _t("gsuid.renderers.player.summary.53_4.cad09647"): 960,
    _t("gsuid.renderers.player.summary.52_4.2eef40ce"): 367,
    _t("gsuid.renderers.player.summary.56_4.0788ed91"): 366,
}

COLOR_MAP = {
    0: (200, 12, 12),
    1: (200, 100, 12),
    2: (151, 80, 186),
    3: (33, 142, 212),
    4: (47, 107, 56),
    5: (64, 64, 66),
}
HALF_WHITE = (255, 255, 255, 120)
WHITE = (255, 255, 255)
BLACK = (2, 2, 2)
FOOTER_TEXT = _t("gsuid.renderers.challenge.common.21_14.f6d11959")


def render_player_summary_card(
    *,
    uid: str,
    summary: Mapping[str, object],
    characters: Sequence[Mapping[str, object]],
    asset_images: Mapping[str, bytes] | None = None,
    title_avatar_url: str | None = None,
) -> bytes:
    """Render a GenshinUID-style full player role-info card as PNG bytes."""
    asset_images = asset_images or {}
    title = render_player_title_section(
        uid=uid,
        summary=summary,
        asset_images=asset_images,
        title_avatar_url=title_avatar_url,
    )
    exploration = _exploration_section(summary, asset_images)
    character_section = render_player_characters_section(
        characters=characters,
        asset_images=asset_images,
    )

    height = character_section.size[1] + exploration.size[1] + 560
    foreground = Image.new("RGBA", (WIDTH, height))
    foreground.paste(title, (0, 0), title)
    foreground.paste(exploration, (0, 650), exploration)
    foreground.paste(character_section, (0, 500 + exploration.size[1] + 40), character_section)
    paste_player_footer(foreground)

    background = v4_background(WIDTH, foreground.size[1])
    background.paste(foreground, (0, 0), foreground)
    return png_bytes(background, rgb=True)


def render_player_title_section(
    *,
    uid: str,
    summary: Mapping[str, object],
    asset_images: Mapping[str, bytes],
    title_avatar_url: str | None = None,
) -> Image.Image:
    """Render the shared GenshinUID-style player title section."""
    return _title_section(uid, summary, asset_images, title_avatar_url)


def render_player_exploration_section(
    *,
    summary: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    """Render the shared GenshinUID-style exploration/completion grid section."""
    return _exploration_section(summary, asset_images)


def player_title_avatar_image(
    *,
    summary: Mapping[str, object],
    asset_images: Mapping[str, bytes],
    size: int,
    title_avatar_url: str | None = None,
    with_ring: bool = False,
) -> Image.Image:
    """Render the shared masked player avatar used by player cards."""
    return _title_avatar(summary, asset_images, size, title_avatar_url, with_ring=with_ring)


def paste_player_footer(image: Image.Image, *, font_size: int = 32) -> None:
    """Paste the shared GenshinUID-style footer text onto a player image."""
    if font_size == 32:
        _paste_footer(image)
        return
    _paste_footer(image, font_size=font_size)


def player_summary_genshinuid_resource_urls(summary: Mapping[str, object]) -> list[str]:
    url = _summary_avatar_url(summary)
    return [url] if url else []


def player_summary_mys_icon_urls(summary: Mapping[str, object]) -> list[str]:
    urls: list[str] = []
    role = summary.get("role")
    if isinstance(role, Mapping):
        _append_url(urls, role.get("avatar_icon"))
    for world in _worlds(summary):
        _append_url(urls, _world_icon_url(world))
        for offering in _offerings(world):
            _append_url(urls, offering.get("icon"))
    return urls


def player_profile_picture_url(
    profile: Mapping[str, object],
    profile_picture_icons: Mapping[str, object] | None = None,
) -> str | None:
    player_info = profile.get("playerInfo")
    if not isinstance(player_info, Mapping):
        return None
    profile_picture = player_info.get("profilePicture")
    if isinstance(profile_picture, Mapping):
        avatar_id = int_value(profile_picture.get("avatarId"))
        if avatar_id > 0:
            return character_portrait_url({"id": avatar_id})
        picture_id = text_value(profile_picture.get("id"))
        icon_path = _profile_picture_icon_path(picture_id, profile_picture_icons)
        if icon_path:
            return f"{ENKA_UI_BASE}/{quote(icon_path, safe='')}.png"
        return None
    return _showcase_avatar_url(player_info)


def _title_section(
    uid: str,
    summary: Mapping[str, object],
    asset_images: Mapping[str, bytes],
    title_avatar_url: str | None,
) -> Image.Image:
    title = open_rgba(PUBLIC_TEXTURE / "title.png")
    avatar = _title_avatar(summary, asset_images, 377, title_avatar_url)
    title.paste(avatar, (651, 73), avatar)

    stats = _stats(summary)
    draw = ImageDraw.Draw(title)
    draw.text((840, 530), f"UID {uid}", fill=WHITE, font=font(36), anchor="mm")
    draw.text(
        (380, 627),
        str(int_value(stats.get("active_day_number"))),
        fill=WHITE,
        font=font(32),
        anchor="lm",
    )
    draw.text(
        (872, 627),
        str(int_value(stats.get("achievement_number"))),
        fill=WHITE,
        font=font(32),
        anchor="lm",
    )
    draw.text(
        (1365, 627),
        str(stats.get("spiral_abyss") or "0-0"),
        fill=WHITE,
        font=font(32),
        anchor="lm",
    )
    return title


def _title_avatar(
    summary: Mapping[str, object],
    asset_images: Mapping[str, bytes],
    size: int,
    title_avatar_url: str | None,
    *,
    with_ring: bool = False,
) -> Image.Image:
    role = summary.get("role")
    role_url = text_value(role.get("avatar_icon")) if isinstance(role, Mapping) else None
    for url in (role_url, title_avatar_url, _summary_avatar_url(summary)):
        content = asset_images.get(url or "")
        if content:
            image = image_from_bytes(content, (size, size))
            if image is not None:
                return _masked_avatar(image, size, with_ring=with_ring)

    avatar = Image.new("RGBA", (size, size), (55, 58, 73, 255))
    draw = ImageDraw.Draw(avatar)
    draw.text(
        (size // 2, size // 2),
        _t("gsuid.renderers.challenge.text.275_47.b2457913"),
        fill=WHITE,
        font=font(54),
        anchor="mm",
    )
    return _masked_avatar(avatar, size, with_ring=with_ring)


def _masked_avatar(image: Image.Image, size: int, *, with_ring: bool = False) -> Image.Image:
    avatar = crop_center(image, size, size).convert("RGBA")
    mask = open_rgba(PUBLIC_TEXTURE / "mask.png").resize((size, size), Image.Resampling.LANCZOS)
    output = Image.new("RGBA", (size, size))
    output.paste(avatar, (0, 0), mask)
    if with_ring:
        ring = open_rgba(PUBLIC_TEXTURE / "avatar_ring.png").resize(
            (size, size),
            Image.Resampling.LANCZOS,
        )
        output.paste(ring, (0, 0), ring)
    return output


def _exploration_section(
    summary: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    stats = _stats(summary)
    worlds = sorted(_worlds(summary), key=lambda world: int_value(world.get("id")))
    culi = _culus_numbers(stats)

    div_a = open_rgba(SUMMARY_TEXTURE / "div_a.png")
    div_b = open_rgba(SUMMARY_TEXTURE / "div_b.png")
    div_c = open_rgba(SUMMARY_TEXTURE / "div_c.png")

    title_offer = 50
    line = 390
    div_h = div_a.size[1] - 10
    column = 6
    card_x = 255
    card_actual_x = 300
    footer = 80
    offer_x = int((WIDTH - column * card_x) / 2 - (card_actual_x - card_x) / 2)
    culi_rows = _rows(len(culi), column)
    chest_rows = 1
    world_rows = _rows(len(worlds), column)
    height = line * (culi_rows + chest_rows + world_rows) + title_offer + div_h * 3 + footer

    image = Image.new("RGBA", (WIDTH, max(height, title_offer + div_h * 3 + footer)))
    image.paste(div_a, (0, title_offer), div_a)

    for index, (culus_key, number) in enumerate(culi):
        culi_name = culus_key.replace("culus_number", "")
        culi_label = STCMAP[culi_name]
        icon = _culus_icon(culi_name, culi_label)
        total = EXPMAX_DATA[culi_label]
        card = _area_card(
            icon=icon,
            icon_pos=(73, 50),
            percent=number / total * 100,
            sub_text=_t("gsuid.renderers.player.summary.337_21.b6570ea6", number, total),
            completion_text=_t("gsuid.renderers.player.summary.338_28.917258eb"),
            name=culi_label,
            level=number,
            level_name=_t("gsuid.renderers.player.summary.341_23.d3771680")
            if number >= CMAP[culi_label][0]
            else _t("gsuid.renderers.player.summary.341_73.7141d432"),
            offerings=[],
            asset_images=asset_images,
            offer=15,
        )
        _paste_grid_card(image, card, offer_x, card_x, div_h + title_offer, line, column, index)

    image.paste(div_b, (0, div_h + line * culi_rows + title_offer), div_b)
    chest_y = div_h * 2 + line * culi_rows + title_offer
    for index, (name, number) in enumerate(_chest_numbers(stats)):
        maximum = CHEST_MAX[name]
        icon = open_rgba(SUMMARY_TEXTURE / f"{name}.png")
        card = _area_card(
            icon=icon,
            icon_pos=(75, 55),
            percent=number / maximum * 100,
            sub_text=_t("gsuid.renderers.player.summary.337_21.b6570ea6", number, maximum),
            completion_text=_t("gsuid.renderers.player.summary.338_28.917258eb"),
            name=name,
            level=number,
            level_name=_t("gsuid.renderers.player.summary.341_23.d3771680")
            if number >= maximum
            else _t("gsuid.renderers.player.summary.341_73.7141d432"),
            offerings=[],
            asset_images=asset_images,
            offer=8,
        )
        _paste_grid_card(image, card, offer_x, card_x, chest_y, line, column, index)

    world_div_y = div_h * 2 + line * (culi_rows + chest_rows) + title_offer
    image.paste(div_c, (0, world_div_y), div_c)
    world_y = div_h * 3 + line * (culi_rows + chest_rows) + title_offer
    for index, world in enumerate(worlds):
        icon = _remote_icon(_world_icon_url(world), asset_images, (150, 150))
        if icon is None:
            icon = _placeholder_icon(_world_name(world), (150, 150))
        name = _world_name(world)
        level = int_value(world.get("level"))
        card = _area_card(
            icon=icon,
            icon_pos=(75, 36),
            percent=int_value(world.get("exploration_percentage")) / 10,
            sub_text="",
            completion_text=_t("gsuid.renderers.player.summary.382_28.361b8437"),
            name=name,
            level=level,
            level_name=_t("gsuid.renderers.player.summary.457_34.5dd3824b", level),
            offerings=_offerings(world),
            asset_images=asset_images,
        )
        _paste_grid_card(image, card, offer_x, card_x, world_y, line, column, index)

    return image


def _area_card(
    *,
    icon: Image.Image,
    icon_pos: tuple[int, int],
    percent: float,
    sub_text: str,
    completion_text: str,
    name: str,
    level: int,
    level_name: str,
    offerings: Sequence[Mapping[str, object]],
    asset_images: Mapping[str, bytes],
    offer: int = 0,
) -> Image.Image:
    area_bg = _shift_image_hue(open_rgba(SUMMARY_TEXTURE / "area_bg.png"), DMAP.get(name, 5))
    alpha = Image.new("RGBA", area_bg.size, (0, 0, 0, 0))
    alpha_draw = ImageDraw.Draw(alpha)
    draw = ImageDraw.Draw(area_bg)
    main_color = _level_color(level, CMAP.get(name, [10, 8, 6, 4, 2]))
    completion = f"{completion_text}: {percent:.1f}%"

    area_bg.paste(icon, icon_pos, icon)
    draw.text((150, 216 + offer), name, fill=WHITE, font=font(32), anchor="mm")

    alpha_draw.rounded_rectangle((98, 240 + offer, 201, 270 + offer), 20, main_color)
    alpha_draw.text((150, 256 + offer), level_name, fill=WHITE, font=font(24), anchor="mm")
    alpha_draw.rounded_rectangle((59, 283 + offer, 241, 295 + offer), 20, HALF_WHITE)
    alpha_draw.rounded_rectangle(
        (59, 283 + offer, 59 + percent * 1820 / 1000, 295 + offer),
        20,
        WHITE,
    )
    alpha_draw.text((150, 320 + offer), completion, fill=WHITE, font=font(20), anchor="mm")
    if sub_text:
        alpha_draw.text((150, 350 + offer), sub_text, fill=WHITE, font=font(20), anchor="mm")

    if offerings:
        offering = offerings[0]
        area_bg.alpha_composite(alpha)
        _paste_offering(area_bg, offering, asset_images, offer)
    else:
        area_bg.alpha_composite(alpha)
    return area_bg


def _paste_offering(
    area_bg: Image.Image,
    offering: Mapping[str, object],
    asset_images: Mapping[str, bytes],
    offer: int,
) -> None:
    draw = ImageDraw.Draw(area_bg)
    icon = _remote_icon(text_value(offering.get("icon")), asset_images, (38, 38))
    if icon is None:
        icon = _placeholder_icon(text_value(offering.get("name")) or "", (38, 38))
    name = text_value(offering.get("name")) or ""
    level = int_value(offering.get("level"))
    color = _level_color(level, CMAP.get(name, [10, 8, 6, 4, 2]))

    draw.rounded_rectangle((59, 340 + offer, 241, 387 + offer), 5, HALF_WHITE)
    area_bg.paste(icon, (63, 343 + offer), icon)
    draw.text((107, 352 + offer), name, fill=BLACK, font=font(20), anchor="lm")
    draw.rounded_rectangle((107, 364 + offer, 173, 384 + offer), 20, color)
    draw.text(
        (140, 374 + offer),
        _t("gsuid.renderers.player.summary.457_34.5dd3824b", level),
        fill=WHITE,
        font=font(15),
        anchor="mm",
    )


def _paste_grid_card(
    image: Image.Image,
    card: Image.Image,
    offer_x: int,
    card_x: int,
    y: int,
    line: int,
    column: int,
    index: int,
) -> None:
    image.paste(card, (offer_x + card_x * (index % column), y + line * (index // column)), card)


def _paste_footer(image: Image.Image, *, font_size: int = 32) -> None:
    draw = ImageDraw.Draw(image)
    x = image.size[0] // 2
    y = image.size[1] - 42
    footer_font = font(font_size)
    draw.text(
        (x + 2, y + 2),
        FOOTER_TEXT,
        fill=(0, 0, 0, 180),
        font=footer_font,
        anchor="mm",
    )
    draw.text((x, y), FOOTER_TEXT, fill=WHITE, font=footer_font, anchor="mm")


def _remote_icon(
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


def _culus_icon(culi_name: str, label: str) -> Image.Image:
    path = SUMMARY_TEXTURE / f"Item_{culi_name.capitalize()}culus.webp"
    if path.exists():
        return open_rgba(path).resize((154, 154), Image.Resampling.LANCZOS)
    return _placeholder_icon(label, (154, 154))


def _placeholder_icon(text: str, size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGBA", size, (255, 255, 255, 48))
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, size[0] - 4, size[1] - 4), outline=WHITE, width=3)
    draw.text(
        (size[0] // 2, size[1] // 2),
        (text or "?")[:2],
        fill=WHITE,
        font=font(20),
        anchor="mm",
    )
    return image


def _shift_image_hue(image: Image.Image, angle: float) -> Image.Image:
    alpha = image.getchannel("A")
    hsv = image.convert("HSV")
    pixels = hsv.load()
    if pixels is None:
        return image
    for y in range(hsv.height):
        for x in range(hsv.width):
            h, s, v = pixels[x, y]
            pixels[x, y] = ((h + int(angle)) % 256, s, v)
    shifted = hsv.convert("RGBA")
    shifted.putalpha(alpha)
    return shifted


def _level_color(value: float, data: Sequence[int]) -> tuple[int, int, int]:
    for index, threshold in enumerate(data):
        if value >= threshold:
            return COLOR_MAP[index]
    return COLOR_MAP[5]


def _stats(summary: Mapping[str, object]) -> Mapping[str, object]:
    stats = summary.get("stats")
    return stats if isinstance(stats, Mapping) else {}


def _worlds(summary: Mapping[str, object]) -> list[Mapping[str, object]]:
    worlds = summary.get("world_explorations")
    return (
        [world for world in worlds if isinstance(world, Mapping)]
        if isinstance(worlds, list)
        else []
    )


def _offerings(world: Mapping[str, object]) -> list[Mapping[str, object]]:
    offerings = world.get("offerings")
    return (
        [offering for offering in offerings if isinstance(offering, Mapping)]
        if isinstance(offerings, list)
        else []
    )


def _culus_numbers(stats: Mapping[str, object]) -> list[tuple[str, int]]:
    culi: list[tuple[str, int]] = []
    for key, value in stats.items():
        if key.endswith("culus_number"):
            culi_name = key.replace("culus_number", "")
            if culi_name in STCMAP:
                culi.append((str(key), int_value(value)))
    return culi


def _chest_numbers(stats: Mapping[str, object]) -> list[tuple[str, int]]:
    return [
        (
            _t("gsuid.renderers.player.summary.55_4.33e13053"),
            int_value(stats.get("common_chest_number")),
        ),
        (
            _t("gsuid.renderers.player.summary.54_4.8d1ca1ac"),
            int_value(stats.get("exquisite_chest_number")),
        ),
        (
            _t("gsuid.renderers.player.summary.53_4.cad09647"),
            int_value(stats.get("precious_chest_number")),
        ),
        (
            _t("gsuid.renderers.player.summary.52_4.2eef40ce"),
            int_value(stats.get("luxurious_chest_number")),
        ),
        (
            _t("gsuid.renderers.player.summary.56_4.0788ed91"),
            int_value(stats.get("magic_chest_number")),
        ),
    ]


def _world_name(world: Mapping[str, object]) -> str:
    name = text_value(world.get("name")) or ""
    if "·" in name:
        return name.split("·")[-1]
    return name


def _world_icon_url(world: Mapping[str, object]) -> str | None:
    name = text_value(world.get("name"))
    if name == _t("gsuid.renderers.player.summary.596_15.788f1f1b"):
        return "https://webstatic.mihoyo.com/app/community-game-records/images/world-logo-16.1c751ac9.png"
    if name == _t("gsuid.renderers.daily.text.24_9.b6b55ca3"):
        return "https://webstatic.mihoyo.com/app/community-game-records/images/world-logo-17.dadac5bf.png"
    return text_value(world.get("icon"))


def _summary_avatar_url(summary: Mapping[str, object]) -> str | None:
    avatars = summary.get("avatars")
    if not isinstance(avatars, list):
        return None
    for avatar in avatars:
        if isinstance(avatar, Mapping):
            url = character_portrait_url(avatar)
            if url:
                return url
    return None


def _profile_picture_icon_path(
    picture_id: str | None,
    profile_picture_icons: Mapping[str, object] | None,
) -> str | None:
    if not picture_id:
        return None
    icons = profile_picture_icons or {}
    entry = icons.get(picture_id)
    if isinstance(entry, Mapping):
        return text_value(entry.get("iconPath"))
    return None


def _showcase_avatar_url(player_info: Mapping[str, object]) -> str | None:
    avatars = player_info.get("showAvatarInfoList")
    if not isinstance(avatars, list):
        return None
    for avatar in avatars:
        if isinstance(avatar, Mapping):
            avatar_id = int_value(avatar.get("avatarId"))
            if avatar_id > 0:
                return character_portrait_url({"id": avatar_id})
    return None


def _append_url(urls: list[str], value: object) -> None:
    url = text_value(value)
    if url and url not in urls:
        urls.append(url)


def _rows(count: int, columns: int) -> int:
    return 0 if count <= 0 else (count + columns - 1) // columns
