from __future__ import annotations

from collections.abc import Mapping, Sequence

from PIL import Image, ImageDraw

from gsuid_cli.renderers._text_helpers import _mapping_list
from gsuid_cli.renderers.common import (
    asset_path,
    crop_center,
    font,
    image_from_bytes,
    int_value,
    open_rgba,
    png_bytes,
    text_value,
)

ABYSS_TEXTURE = asset_path("guide", "abyss", "textures")
THEATER_TEXTURE = asset_path("guide", "theater", "textures")
WIDTH_ABYSS = 1100
WIDTH_THEATER = 1000
MONSTER_BACKGROUND_ALPHA = 190


def render_guide_abyss_card(
    abyss: Mapping[str, object],
    *,
    asset_images: Mapping[str, bytes] | None = None,
) -> bytes:
    asset_images = asset_images or {}
    chambers = _mapping_list(abyss.get("chambers"))
    chamber_images = [_abyss_chamber(chamber, asset_images) for chamber in chambers]
    height = 456 + sum(image.height for image in chamber_images)
    image = crop_center(open_rgba(ABYSS_TEXTURE / "bg" / "bg.jpg"), WIDTH_ABYSS, height)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((421, 292, 548, 330), 10, (144, 0, 0))
    draw.rounded_rectangle((570, 292, 772, 330), 10, (27, 82, 155))
    draw.text(
        (425, 175),
        f"深境螺旋 {int_value(abyss.get('floor'), 12)}层",
        "white",
        font(84),
        "lm",
    )
    draw.multiline_text(
        (429, 229),
        str(abyss.get("disorder") or ""),
        fill=(215, 215, 215),
        font=font(26),
        anchor="la",
        spacing=4,
    )
    version = text_value(abyss.get("version")) or text_value(abyss.get("schedule_name")) or "-"
    draw.text((485, 311), f"版本{version}", "white", font(28), "mm")
    draw.text((670, 311), "数据 妮可少年", "white", font(28), "mm")
    icon = open_rgba(ABYSS_TEXTURE / "icon.png").resize((260, 260), Image.Resampling.LANCZOS)
    image.paste(icon, (45, 80), icon)

    y = 456
    for chamber in chamber_images:
        image.paste(chamber, (0, y), chamber)
        y += chamber.height
    return png_bytes(image, rgb=True)


def render_guide_theater_card(
    theater: Mapping[str, object],
    *,
    asset_images: Mapping[str, bytes] | None = None,
) -> bytes:
    asset_images = asset_images or {}
    rooms = _mapping_list(theater.get("rooms"))
    room_images = [_theater_room(room, asset_images) for room in rooms]
    height = 1270 + sum(image.height for image in room_images)
    image = Image.new("RGBA", (WIDTH_THEATER, height), (22, 18, 20, 255))
    _paste_theater_title(image, theater, asset_images)
    y = 1270
    for room in room_images:
        image.paste(room, (0, y), room)
        y += room.height
    return png_bytes(image, rgb=True)


def guide_abyss_image_urls(abyss: Mapping[str, object]) -> list[str]:
    urls: list[str] = []
    for chamber in _mapping_list(abyss.get("chambers")):
        for side in ("upper", "lower"):
            for wave in _mapping_list(chamber.get(side)):
                for monster in _mapping_list(wave.get("monsters")):
                    _append_url(urls, monster.get("icon_url"))
    return urls


def guide_theater_image_urls(theater: Mapping[str, object]) -> list[str]:
    urls: list[str] = []
    for avatar in [
        *_mapping_list(theater.get("buff_avatars")),
        *_mapping_list(theater.get("invite_avatars")),
    ]:
        _append_url(urls, avatar.get("image_url"))
    for room in _mapping_list(theater.get("rooms")):
        for monster in _mapping_list(room.get("monsters")):
            icon_urls = monster.get("icon_urls")
            if isinstance(icon_urls, list):
                for url in icon_urls:
                    _append_url(urls, url)
            else:
                _append_url(urls, monster.get("icon_url"))
    return urls


def _abyss_chamber(
    chamber: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    upper = _abyss_half(_mapping_list(chamber.get("upper")), "Upper", asset_images)
    lower = _abyss_half(_mapping_list(chamber.get("lower")), "Lower", asset_images)
    image = Image.new("RGBA", (WIDTH_ABYSS, upper.height + lower.height + 70), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((320, 20, 780, 72), 10, (16, 13, 13, 120))
    draw.text(
        (550, 46),
        f"{chamber.get('name') or ''} · 怪物等级 Lv{int_value(chamber.get('level'))}",
        "white",
        font(36),
        "mm",
    )
    image.paste(upper, (0, 60), upper)
    image.paste(lower, (0, 50 + upper.height), lower)
    return image


def _abyss_half(
    waves: Sequence[Mapping[str, object]],
    half: str,
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    content = Image.new("RGBA", (WIDTH_ABYSS, 3000), (0, 0, 0, 0))
    draw = ImageDraw.Draw(content)
    y = 0
    height = 60
    for index, wave in enumerate(waves, start=1):
        monsters = _mapping_list(wave.get("monsters"))
        block_height = (((len(monsters) - 1) // 3) + 1) * 125 + 40
        tag = open_rgba(ABYSS_TEXTURE / "wave_tag.png")
        tag_draw = ImageDraw.Draw(tag)
        tag_draw.text((36, 20), f"第{index}波", (210, 210, 210), font(24), "lm")
        extra = text_value(wave.get("extra_desc"))
        if extra:
            draw.text((150, 65 + y), f" > {extra}", (210, 210, 210), font(24), "lm")
        content.paste(tag, (53, 45 + y), tag)
        for monster_index, monster in enumerate(monsters):
            monster_image = _abyss_monster(monster, asset_images)
            content.paste(
                monster_image,
                (-7 + (monster_index % 3) * 360, 40 + (monster_index // 3) * 136 + y),
                monster_image,
            )
        y += block_height
        height += block_height
    tag = open_rgba(ABYSS_TEXTURE / ("upper_tag.png" if half == "Upper" else "lower_tag.png"))
    content.paste(tag, (0, 0), tag)
    background = Image.new("RGBA", (WIDTH_ABYSS, height), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(background)
    bg_draw.rounded_rectangle((20, 30, 1080, height - 20), 10, (16, 13, 13, 120))
    cropped = content.crop((0, 0, WIDTH_ABYSS, height))
    background.paste(cropped, (0, 0), cropped)
    return background


def _abyss_monster(
    monster: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    image = open_rgba(ABYSS_TEXTURE / "monster_bg.png")
    image.putalpha(image.getchannel("A").point(lambda value: min(value, MONSTER_BACKGROUND_ALPHA)))
    icon = _remote_image(monster.get("icon_url"), asset_images, (110, 110))
    if icon is None:
        icon = _placeholder_icon((110, 110), text_value(monster.get("name")) or "?")
    image.paste(icon, (35, 45), icon)
    foreground = open_rgba(ABYSS_TEXTURE / "monster_fg.png")
    image.paste(foreground, (0, 0), foreground)
    draw = ImageDraw.Draw(image)
    draw.text(
        (160, 85),
        (text_value(monster.get("name")) or "未知怪物")[:7],
        "white",
        font(28),
        "lm",
    )
    draw.text((160, 115), f"x{int_value(monster.get('count'), 1)}", (210, 210, 210), font(26), "lm")
    return image


def _paste_theater_title(
    image: Image.Image,
    theater: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> None:
    title = open_rgba(THEATER_TEXTURE / "title.png")
    draw = ImageDraw.Draw(title)
    draw.text(
        (500, 473),
        f"剧诗ID：{theater.get('event_id') or '-'} 详细信息",
        (255, 255, 255),
        font=font(38),
        anchor="mm",
    )
    image.paste(title, (0, 0), title)

    avatar_bg = open_rgba(THEATER_TEXTURE / "avatar_bg.png")
    avatar_draw = ImageDraw.Draw(avatar_bg)
    avatar_draw.text(
        (500, 184),
        f"{theater.get('begin_time') or ''} ~ {theater.get('end_time') or ''}",
        (139, 137, 133),
        font=font(22),
        anchor="mm",
    )
    buff = text_value(theater.get("buff_description")) or ""
    avatar_draw.text((500, 474), buff[-28:], (139, 137, 133), font=font(26), anchor="mm")
    for index, avatar in enumerate(_mapping_list(theater.get("buff_avatars"))[:6]):
        card = _theater_avatar(avatar, asset_images)
        avatar_bg.paste(card, (121 + index * 130, 302), card)
    for index, avatar in enumerate(_mapping_list(theater.get("invite_avatars"))[:5]):
        card = _theater_avatar(avatar, asset_images)
        avatar_bg.paste(card, (252 + index * 130, 576), card)
    image.paste(avatar_bg, (0, 482), avatar_bg)


def _theater_avatar(
    avatar: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    card = _remote_image(avatar.get("image_url"), asset_images, (102, 124))
    if card is None:
        card = _placeholder_icon((102, 124), text_value(avatar.get("name")) or "?")
    draw = ImageDraw.Draw(card)
    draw.text((51, 111), (text_value(avatar.get("name")) or "?")[:4], (10, 10, 10), font(20), "mm")
    return card


def _theater_room(
    room: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    has_title = bool(text_value(room.get("title")))
    image = open_rgba(
        THEATER_TEXTURE / ("long_monster_bg.png" if has_title else "short_monster_bg.png")
    )
    draw = ImageDraw.Draw(image)
    draw.text((131, 69), f"第{room.get('id') or '-'}幕", "black", font(30), "lm")
    if has_title:
        draw.text((245, 69), str(room.get("title") or ""), "black", font(30), "lm")
        desc = (text_value(room.get("description")) or "")[:26]
        draw.text((131, 114), f"{desc}...", (99, 99, 99), font(28), "lm")
        for index, monster in enumerate(_mapping_list(room.get("monsters"))[:3]):
            mini = _theater_monster(monster, asset_images)
            image.paste(mini, (126 + index * 257, 158), mini)
    else:
        draw.text(
            (131, 114),
            f"怪物等级 Lv{int_value(room.get('monster_level'))}",
            (99, 99, 99),
            font(28),
            "lm",
        )
    return image


def _theater_monster(
    monster: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    image = Image.new("RGBA", (250, 90), (219, 209, 203))
    icon = None
    icon_urls = monster.get("icon_urls")
    if isinstance(icon_urls, list):
        for url in icon_urls:
            icon = _remote_image(url, asset_images, (90, 90))
            if icon is not None:
                break
    if icon is None:
        icon = _remote_image(monster.get("icon_url"), asset_images, (90, 90))
    if icon is None:
        icon = _placeholder_icon((90, 90), text_value(monster.get("name")) or "?")
    image.paste(icon, (0, 0), icon)
    draw = ImageDraw.Draw(image)
    draw.text(
        (100, 30), (text_value(monster.get("name")) or "未知怪物")[:6], (36, 36, 36), font(22), "lm"
    )
    draw.text((100, 57), f"HP {int_value(monster.get('hp'))}", (90, 90, 90), font(22), "lm")
    return image


def _remote_image(
    value: object,
    asset_images: Mapping[str, bytes],
    size: tuple[int, int],
) -> Image.Image | None:
    url = text_value(value)
    if not url:
        return None
    content = asset_images.get(url)
    if content is None:
        return None
    return image_from_bytes(content, size)


def _placeholder_icon(size: tuple[int, int], label: str) -> Image.Image:
    image = Image.new("RGBA", size, (68, 70, 78, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (4, 4, size[0] - 5, size[1] - 5), 8, outline=(255, 255, 255, 90), width=2
    )
    draw.text((size[0] // 2, size[1] // 2), label[:2], "white", font(max(size[0] // 4, 18)), "mm")
    return image


def _append_url(urls: list[str], value: object) -> None:
    url = text_value(value)
    if url and url not in urls:
        urls.append(url)
