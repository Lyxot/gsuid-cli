from __future__ import annotations

from collections.abc import Mapping

from PIL import Image, ImageDraw

from gsuid_cli.renderers.common import (
    asset_path,
    font,
    image_from_bytes,
    int_value,
    open_rgba,
    png_bytes,
    sequence,
    text_value,
    v4_background,
)
from gsuid_cli.renderers.player.summary import (
    paste_player_footer,
    render_player_title_section,
)

TEXTURE = asset_path("player", "inventory", "textures")
WIDTH = 1680
ITEMS_PER_ROW = 14
ITEM_WIDTH = 110
ITEM_HEIGHT = 145
ITEM_LEFT = 65
ITEM_TOP = 713
BOTTOM_PADDING = 92


def render_player_inventory_card(
    *,
    uid: str,
    summary: Mapping[str, object],
    inventory: Mapping[str, object],
    asset_images: Mapping[str, bytes] | None = None,
    title_avatar_url: str | None = None,
) -> bytes:
    """Render a GenshinUID-style player inventory card as PNG bytes."""
    asset_images = asset_images or {}
    items = _inventory_items(inventory)
    rows = max((len(items) + ITEMS_PER_ROW - 1) // ITEMS_PER_ROW, 1)
    height = ITEM_TOP + rows * ITEM_HEIGHT + BOTTOM_PADDING
    image = v4_background(WIDTH, height)
    title = render_player_title_section(
        uid=uid,
        summary=summary,
        asset_images=asset_images,
        title_avatar_url=title_avatar_url,
    )
    image.paste(title, (0, 0), title)

    if not items:
        _draw_empty(image)
    for index, item in enumerate(items):
        card = _inventory_item_card(item, asset_images)
        x = ITEM_LEFT + (index % ITEMS_PER_ROW) * ITEM_WIDTH
        y = ITEM_TOP + (index // ITEMS_PER_ROW) * ITEM_HEIGHT
        image.paste(card, (x, y), card)

    paste_player_footer(image)
    return png_bytes(image, rgb=True)


def player_inventory_icon_urls(inventory: Mapping[str, object]) -> list[str]:
    urls: list[str] = []
    for item in _inventory_items(inventory):
        url = text_value(item.get("icon"))
        if url and url not in urls:
            urls.append(url)
    return urls


def _inventory_items(inventory: Mapping[str, object]) -> list[Mapping[str, object]]:
    return [item for item in sequence(inventory.get("overall")) if isinstance(item, Mapping)]


def _inventory_item_card(
    item: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    card = open_rgba(TEXTURE / "one.png")
    icon = _remote_icon(text_value(item.get("icon")), asset_images, (80, 80))
    if icon is not None:
        card.paste(icon, (15, 20), icon)
    else:
        _paste_placeholder_icon(card, item)

    draw = ImageDraw.Draw(card)
    draw.text(
        (55, 125),
        str(int_value(item.get("owned"))),
        font=font(20),
        fill="white",
        anchor="mm",
    )
    return card


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


def _paste_placeholder_icon(card: Image.Image, item: Mapping[str, object]) -> None:
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((15, 20, 95, 100), radius=10, outline=(255, 255, 255, 160), width=2)
    name = text_value(item.get("name")) or "?"
    draw.text((55, 60), name[:2], font=font(22), fill="white", anchor="mm")


def _draw_empty(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    draw.text((WIDTH // 2, ITEM_TOP + 70), "暂无背包素材", fill="white", font=font(36), anchor="mm")
