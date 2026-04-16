from __future__ import annotations

from collections.abc import Mapping, Sequence

from PIL import Image, ImageDraw

from gsuid_cli.renderers.common import (
    asset_path,
    font,
    image_from_bytes,
    int_value,
    open_rgba,
    png_bytes,
    text_value,
)

TEXTURE = asset_path("daily", "materials", "textures")
PUBLIC_TEXTURE = asset_path("public", "textures")

WIDTH = 950
TITLE_HEIGHT = 600
DOMAIN_HEADER_HEIGHT = 110
ITEM_SIZE = 100
ITEM_GAP = 10
ITEMS_PER_ROW = 8
ITEM_LEFT = 36
BOTTOM_PADDING = 30


def render_daily_materials_card(
    *,
    day: str,
    domains: Sequence[Mapping[str, object]],
    icon_images: Mapping[str, bytes] | None = None,
) -> bytes:
    """Render a GenshinUID-style daily materials card as PNG bytes."""
    icon_images = icon_images or {}
    height = TITLE_HEIGHT + BOTTOM_PADDING
    for domain in domains:
        height += DOMAIN_HEADER_HEIGHT + _domain_rows(domain) * DOMAIN_HEADER_HEIGHT

    img = Image.new(
        "RGBA", (WIDTH, max(height, TITLE_HEIGHT + DOMAIN_HEADER_HEIGHT)), (255, 255, 255)
    )
    title = open_rgba(TEXTURE / "title.png")
    title_draw = ImageDraw.Draw(title)
    title_draw.text(
        (475, 474),
        f"今天是{_weekday_label(day)}哦!",
        fill="black",
        font=font(36),
        anchor="mm",
    )
    title_draw.text((475, 531), "每日材料", fill="black", font=font(36), anchor="mm")
    img.paste(title, (0, 0), title)

    y = TITLE_HEIGHT
    for domain in domains:
        _paste_domain(img, domain, icon_images, y)
        y += DOMAIN_HEADER_HEIGHT + _domain_rows(domain) * DOMAIN_HEADER_HEIGHT

    return png_bytes(img, rgb=True)


def _paste_domain(
    img: Image.Image,
    domain: Mapping[str, object],
    icon_images: Mapping[str, bytes],
    y: int,
) -> None:
    bar = open_rgba(TEXTURE / "bar.png")
    bar_draw = ImageDraw.Draw(bar)
    domain_icon = _icon_image(text_value(domain.get("domain_icon_url")), icon_images, (77, 77))
    if domain_icon is not None:
        bar.paste(domain_icon, (43, 10), domain_icon)

    domain_type, domain_name = _domain_parts(text_value(domain.get("name")) or "")
    bar_draw.text((142, 50), domain_name, fill="black", font=font(44), anchor="lm")
    bar_draw.text((900, 50), domain_type, fill="black", font=font(26), anchor="rm")
    img.paste(bar, (0, y), bar)

    for index, item in enumerate(_items(domain)):
        row, column = divmod(index, ITEMS_PER_ROW)
        x = ITEM_LEFT + column * (ITEM_SIZE + ITEM_GAP)
        item_y = y + DOMAIN_HEADER_HEIGHT + row * DOMAIN_HEADER_HEIGHT
        _paste_item(img, item, icon_images, x, item_y)


def _paste_item(
    img: Image.Image,
    item: Mapping[str, object],
    icon_images: Mapping[str, bytes],
    x: int,
    y: int,
) -> None:
    rank = _rank(item.get("rank"))
    card = _rarity_bg(rank).resize((ITEM_SIZE, ITEM_SIZE), Image.Resampling.LANCZOS)
    icon = _icon_image(text_value(item.get("icon_url")), icon_images, (ITEM_SIZE, ITEM_SIZE))
    if icon is not None:
        card.paste(icon, (0, 0), icon)
    else:
        draw = ImageDraw.Draw(card)
        draw.rounded_rectangle((8, 8, 92, 92), radius=12, outline=(255, 255, 255, 180), width=2)
        name = text_value(item.get("name")) or "?"
        draw.text((50, 50), name[:2], fill=(255, 255, 255), font=font(24), anchor="mm")
    img.paste(card, (x, y), card)


def _icon_image(
    url: str | None, icon_images: Mapping[str, bytes], size: tuple[int, int]
) -> Image.Image | None:
    if not url:
        return None
    content = icon_images.get(url)
    if content is None:
        return None
    return image_from_bytes(content, size)


def _rarity_bg(rank: int) -> Image.Image:
    path = PUBLIC_TEXTURE / "weapon" / f"weapon_bg{rank}.png"
    if not path.exists():
        path = PUBLIC_TEXTURE / "weapon" / "weapon_bg1.png"
    return open_rgba(path)


def _domain_rows(domain: Mapping[str, object]) -> int:
    count = len(_items(domain))
    return max((count + ITEMS_PER_ROW - 1) // ITEMS_PER_ROW, 1)


def _items(domain: Mapping[str, object]) -> list[Mapping[str, object]]:
    value = domain.get("items")
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _domain_parts(name: str) -> tuple[str, str]:
    left, separator, right = name.partition("：")
    if not separator:
        return "", left
    return left, right


def _weekday_label(day: str) -> str:
    return {
        "monday": "周一",
        "tuesday": "周二",
        "wednesday": "周三",
        "thursday": "周四",
        "friday": "周五",
        "saturday": "周六",
        "sunday": "周日",
    }.get(day, day)


def _rank(value: object) -> int:
    rank = int_value(value, 1)
    return min(max(rank, 1), 5)
