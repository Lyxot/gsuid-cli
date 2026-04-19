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
)
from gsuid_cli.renderers.player.summary import player_title_avatar_image
from gsuid_cli.renderers.progress.collection import _color_background

TEXTURE = asset_path("progress", "gcg", "textures")
FIRST_COLOR = (45, 45, 45)
SECOND_COLOR = (53, 53, 53)
LIGHT_COLOR = (255, 255, 255)


def render_progress_gcg_card(
    *,
    uid: str,
    gcg: Mapping[str, object],
    asset_images: Mapping[str, bytes] | None = None,
) -> bytes:
    asset_images = asset_images or {}
    basic = _mapping(gcg.get("basic"))
    image = open_rgba(TEXTURE / "BG.png")
    avatar_total = int_value(basic.get("avatar_card_num_total"))
    action_total = int_value(basic.get("action_card_num_total"))
    avatar_rate = _rate(int_value(basic.get("avatar_card_num_gained")), avatar_total)
    action_rate = _rate(int_value(basic.get("action_card_num_gained")), action_total)
    image.paste(_bar(avatar_rate), (440, 36), _bar(avatar_rate))
    image.paste(_bar(action_rate), (440, 101), _bar(action_rate))

    draw = ImageDraw.Draw(image)
    draw.text((469, 63), "已解锁角色牌", FIRST_COLOR, font(26), "lm")
    draw.text((469, 128), "已收集行动牌", FIRST_COLOR, font(26), "lm")
    draw.text(
        (805, 63),
        f"{int_value(basic.get('avatar_card_num_gained'))} / {avatar_total}",
        FIRST_COLOR,
        font(26),
        "rm",
    )
    draw.text(
        (805, 128),
        f"{int_value(basic.get('action_card_num_gained'))} / {action_total}",
        FIRST_COLOR,
        font(26),
        "rm",
    )
    draw.text((165, 87), str(basic.get("nickname") or ""), FIRST_COLOR, font(32), "lm")
    draw.text((165, 120), f"UID{uid}", FIRST_COLOR, font(18), "lm")
    draw.text((102, 97), str(int_value(basic.get("level"))), "white", font(50), "mm")

    for index, card in enumerate(_sequence(basic.get("covers"))[:4]):
        card_image = _card_image(card, asset_images, (160, 275))
        image.paste(card_image, (65 + index * 204, 198), card_image)
    return png_bytes(image, rgb=True)


def render_progress_gcg_deck_card(
    *,
    uid: str,
    summary: Mapping[str, object],
    deck: Mapping[str, object],
    asset_images: Mapping[str, bytes] | None = None,
    title_avatar_url: str | None = None,
) -> bytes:
    asset_images = asset_images or {}
    image = _color_background(950, 2300)
    char_mask = open_rgba(TEXTURE / "char_mask.png")
    for index, avatar in enumerate(_sequence(deck.get("avatar_cards"))[:3]):
        card = _card_image(avatar, asset_images, (420, 720))
        empty = Image.new("RGBA", (320, 320))
        masked = Image.new("RGBA", (320, 320))
        empty.paste(card, (-29, 5), card)
        masked.paste(empty, (0, 0), char_mask)
        image.paste(masked, (18 + index * 296, 518), masked)

    title = open_rgba(TEXTURE / "desk_title.png")
    image.paste(title, (0, 0), title)
    avatar = player_title_avatar_image(
        summary=summary,
        asset_images=asset_images,
        size=320,
        title_avatar_url=title_avatar_url,
        with_ring=True,
    )
    image.paste(avatar, (318, 45), avatar)
    draw = ImageDraw.Draw(image)
    draw.text((475, 410), f"UID {uid}", FIRST_COLOR, font(36), "mm")
    draw.text((475, 466), str(deck.get("name") or ""), FIRST_COLOR, font(36), "mm")

    action_cards = _expanded_action_cards(deck)
    same = open_rgba(TEXTURE / "same.png")
    void = open_rgba(TEXTURE / "void.png")
    for cut in range(5):
        start = cut * 6
        bar = open_rgba(TEXTURE / "bar.png")
        bar_draw = ImageDraw.Draw(bar)
        for index, action in enumerate(action_cards[start : start + 6]):
            card = _card_image(action, asset_images, (109, 187))
            bar.paste(card, (82 + index * 137, 39), card)
            cost = _first_cost(action)
            icon = same if cost.get("cost_type") == "CostTypeSame" else void
            color = SECOND_COLOR if cost.get("cost_type") == "CostTypeSame" else LIGHT_COLOR
            bar.paste(icon, (148 + index * 137, 43), icon)
            bar_draw.text(
                (168 + index * 137, 63),
                str(int_value(cost.get("cost_value"))),
                color,
                font(20),
                "mm",
            )
            bar_draw.text(
                (137 + index * 137, 249),
                str(action.get("name") or ""),
                FIRST_COLOR,
                font(20),
                "mm",
            )
        image.paste(bar, (0, 827 + cut * 285), bar)
    return png_bytes(image, rgb=True)


def progress_gcg_image_urls(gcg: Mapping[str, object]) -> list[str]:
    return _card_urls(_sequence(_mapping(gcg.get("basic")).get("covers")))


def progress_gcg_deck_image_urls(deck: Mapping[str, object]) -> list[str]:
    cards = [*_sequence(deck.get("avatar_cards")), *_sequence(deck.get("action_cards"))]
    return _card_urls(cards)


def has_gcg_covers(gcg: Mapping[str, object]) -> bool:
    return bool(_sequence(_mapping(gcg.get("basic")).get("covers")))


def _bar(rate: float) -> Image.Image:
    if rate <= 0.25:
        source = "1.png"
    elif rate <= 0.58:
        source = "2.png"
    elif rate <= 0.8:
        source = "3.png"
    else:
        source = "4.png"
    return open_rgba(TEXTURE / source).resize((400, 54), Image.Resampling.LANCZOS)


def _rate(value: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return value / total


def _card_image(
    card: Mapping[str, object],
    asset_images: Mapping[str, bytes],
    size: tuple[int, int],
) -> Image.Image:
    url = str(card.get("image") or "")
    image = image_from_bytes(asset_images.get(url, b""), size)
    if image is not None:
        return image
    return open_rgba(TEXTURE / "void.png").resize(size, Image.Resampling.LANCZOS)


def _expanded_action_cards(deck: Mapping[str, object]) -> list[Mapping[str, object]]:
    cards: list[Mapping[str, object]] = []
    for action in _sequence(deck.get("action_cards")):
        for _ in range(max(int_value(action.get("num")), 1)):
            cards.append(action)
    return cards


def _first_cost(card: Mapping[str, object]) -> Mapping[str, object]:
    costs = _sequence(card.get("action_cost"))
    return costs[0] if costs else {}


def _card_urls(cards: list[Mapping[str, object]]) -> list[str]:
    urls: list[str] = []
    for card in cards:
        url = card.get("image")
        if isinstance(url, str) and url and url not in urls:
            urls.append(url)
    return urls


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> list[Mapping[str, object]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []
