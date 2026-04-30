from __future__ import annotations

import re
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
    v4_background,
)

TEXTURE = asset_path("rerun", "textures")
COLOR_MAP = {
    1.5: (241, 18, 18),
    1.3: (112, 18, 241),
    1.1: (49, 88, 192),
    0.8: (66, 114, 14),
}


def rerun_asset_urls(data: Mapping[str, object]) -> list[str]:
    urls: list[str] = []
    for item in _rerun_items(data):
        url = text_value(item.get("icon_url"))
        if url and url not in urls:
            urls.append(url)
    return urls


def render_rerun_list(
    data: Mapping[str, object],
    *,
    asset_images: Mapping[str, bytes] | None = None,
) -> bytes:
    asset_images = asset_images or {}
    groups = _groups(data)
    char5 = _group_items(groups, "character", 5)
    char4 = _group_items(groups, "character", 4)
    weapon5 = _group_items(groups, "weapon", 5)
    weapon4 = _group_items(groups, "weapon", 4)

    len1 = _group_height(char5)
    len2 = _group_height(char4)
    len3 = _group_height(weapon5)
    len4 = _group_height(weapon4)
    height = 500 + 150 + 100 + 110 + len1 + len2 + len3 + len4
    image = v4_background(1400, height)

    title = open_rgba(TEXTURE / "title.png")
    title_draw = ImageDraw.Draw(title)
    title_draw.text(
        (643, 356),
        text_value(data.get("version")) or "当前版本",
        (255, 255, 255),
        font(30),
        "mm",
    )
    image.paste(title, (0, 0), title)

    bar1 = open_rgba(TEXTURE / "bar1.png")
    bar2 = open_rgba(TEXTURE / "bar2.png")
    image.paste(bar1, (0, 540), bar1)
    _paste_group(image, char5, y=623, asset_images=asset_images, current_version=_version(data))
    _paste_group(
        image, char4, y=623 + len1, asset_images=asset_images, current_version=_version(data)
    )

    weapon_y = 623 + len1 + len2 + 90 + 40
    image.paste(bar2, (0, 540 + 90 + 40 + len1 + len2), bar2)
    _paste_group(
        image, weapon5, y=weapon_y, asset_images=asset_images, current_version=_version(data)
    )
    _paste_group(
        image,
        weapon4,
        y=weapon_y + len3,
        asset_images=asset_images,
        current_version=_version(data),
    )

    draw = ImageDraw.Draw(image)
    draw.text(
        (700, height - 38),
        "Created by GenshinUID & Power by GsCore & Design by Wuyi无疑 & Data by Teyvat",
        (220, 220, 220),
        font(20),
        "mm",
    )
    return png_bytes(image, rgb=True)


def _paste_group(
    image: Image.Image,
    items: Sequence[Mapping[str, object]],
    *,
    y: int,
    asset_images: Mapping[str, bytes],
    current_version: float,
) -> None:
    for index, item in enumerate(items):
        card = _item_card(item, asset_images=asset_images, current_version=current_version)
        image.paste(card, ((index % 6) * 210 + 67, y + (index // 6) * 274), card)


def _item_card(
    item: Mapping[str, object],
    *,
    asset_images: Mapping[str, bytes],
    current_version: float,
) -> Image.Image:
    rarity = min(max(int_value(item.get("rarity"), 5), 4), 5)
    card = open_rgba(TEXTURE / f"star{rarity}.png")
    draw = ImageDraw.Draw(card)
    icon = _remote_icon(text_value(item.get("icon_url")) or "", asset_images)
    card.paste(icon, (25, 35), icon)

    version_text = text_value(item.get("last_banner_version")) or ""
    draw.rounded_rectangle(
        (55, 30, 155, 60), fill=_version_color(version_text, current_version), radius=20
    )
    draw.text(
        (105, 228), f"{int_value(item.get('days_since_last_banner'))}天", "white", font(38), "mm"
    )
    draw.text((105, 45), version_text[:-1] if version_text else "", "white", font(24), "mm")
    return card


def _remote_icon(url: str, asset_images: Mapping[str, bytes]) -> Image.Image:
    image = image_from_bytes(asset_images.get(url, b""), (164, 164)) if url else None
    if image is not None:
        return image
    placeholder = Image.new("RGBA", (164, 164), (48, 48, 60, 255))
    draw = ImageDraw.Draw(placeholder)
    draw.text((82, 82), "?", (220, 220, 220), font(48), "mm")
    return placeholder


def _version_color(version_text: str, current_version: float) -> tuple[int, int, int]:
    version = _version_number(version_text)
    cut = current_version - version if version else 0
    for threshold, color in COLOR_MAP.items():
        if cut >= threshold:
            return color
    return (37, 37, 37)


def _version(data: Mapping[str, object]) -> float:
    return _version_number(text_value(data.get("version")) or "")


def _version_number(value: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)", value)
    return float(match.group(1)) if match else 0.0


def _group_height(items: Sequence[Mapping[str, object]]) -> int:
    return (((len(items) - 1) // 6) + 1) * 274 if items else 0


def _group_items(
    groups: Sequence[Mapping[str, object]],
    kind: str,
    rarity: int,
) -> list[Mapping[str, object]]:
    for group in groups:
        if group.get("kind") == kind and int_value(group.get("rarity")) == rarity:
            return _sequence_of_maps(group.get("items"))
    return []


def _rerun_items(data: Mapping[str, object]) -> list[Mapping[str, object]]:
    items = []
    for group in _groups(data):
        items.extend(_sequence_of_maps(group.get("items")))
    return items


def _groups(data: Mapping[str, object]) -> list[Mapping[str, object]]:
    return _sequence_of_maps(data.get("groups"))


def _sequence_of_maps(value: object) -> list[Mapping[str, object]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []
