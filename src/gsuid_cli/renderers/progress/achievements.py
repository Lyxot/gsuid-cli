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
    v4_background,
)
from gsuid_cli.renderers.player.summary import paste_player_footer, render_player_title_section

TEXTURE = asset_path("progress", "achievements", "textures")
WIDTH = 1950


def render_progress_achievements_card(
    *,
    uid: str,
    summary: Mapping[str, object],
    achievements: list[Mapping[str, object]],
    asset_images: Mapping[str, bytes] | None = None,
    title_avatar_url: str | None = None,
) -> bytes:
    asset_images = asset_images or {}
    title = render_player_title_section(
        uid=uid,
        summary=summary,
        asset_images=asset_images,
        title_avatar_url=title_avatar_url,
    )
    rows = ((len(achievements) - 1) // 3) + 1 if achievements else 1
    height = title.size[1] + rows * 170 + 240
    image = v4_background(WIDTH, height)
    image.paste(title, (137, 0), title)
    bar = open_rgba(TEXTURE / "bar.png")
    image.paste(bar, (0, title.size[1] + 20), bar)

    for index, achievement in enumerate(achievements):
        card = _achievement_card(achievement, asset_images)
        image.paste(card, ((index % 3) * 600 + 71, (index // 3) * 170 + 837), card)

    paste_player_footer(image)
    return png_bytes(image, rgb=True)


def progress_achievement_image_urls(achievements: list[Mapping[str, object]]) -> list[str]:
    urls: list[str] = []
    for achievement in achievements:
        url = achievement.get("icon")
        if isinstance(url, str) and url and url not in urls:
            urls.append(url)
    return urls


def _achievement_card(
    achievement: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    percent = _percent(achievement)
    level, color = _level_color(percent)
    card = open_rgba(TEXTURE / f"bg{level}.png")
    icon = image_from_bytes(asset_images.get(str(achievement.get("icon") or ""), b""), (128, 128))
    if icon is None:
        icon = Image.new("RGBA", (128, 128), (255, 255, 255, 80))
    card.paste(icon, (28, 21), icon)

    finish_num = int_value(achievement.get("finish_num"))
    total = "?"
    if percent > 0:
        total = str(int(finish_num / percent * 100))

    draw = ImageDraw.Draw(card)
    draw.text((160, 50), str(achievement.get("name") or "")[:10], (255, 173, 0), font(36), "lm")
    draw.text((160, 93), f"{finish_num} / ~{total}", color, font(30), "lm")
    draw.text((543, 93), f"{percent:g}%", color, font(30), "rm")
    add_x = int((544 - 163) * percent / 100)
    draw.rounded_rectangle((160, 117, 547, 137), 0, (0, 0, 0, 150))
    draw.rounded_rectangle((163, 120, 163 + add_x, 134), 0, color)
    return card


def _percent(achievement: Mapping[str, object]) -> float:
    value = achievement.get("percentage")
    try:
        percent = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return min(max(percent, 0.0), 100.0)


def _level_color(percent: float) -> tuple[int, tuple[int, int, int]]:
    if percent >= 95:
        return 5, (249, 53, 53)
    if percent >= 80:
        return 4, (255, 173, 0)
    if percent >= 60:
        return 3, (243, 53, 249)
    if percent >= 30:
        return 2, (53, 157, 249)
    return 1, (96, 220, 52)
