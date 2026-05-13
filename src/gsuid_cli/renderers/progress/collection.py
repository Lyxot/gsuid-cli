from __future__ import annotations

from collections.abc import Mapping

from PIL import Image, ImageDraw

from gsuid_cli.renderers.common import (
    asset_path,
    crop_center,
    font,
    int_value,
    open_rgba,
    png_bytes,
    v4_background,
)
from gsuid_cli.renderers.player.summary import (
    paste_player_footer,
    player_title_avatar_image,
    render_player_exploration_section,
)
from gsuid_cli.text import t as _t

TEXTURE = asset_path("progress", "collection", "textures")
SUMMARY_TEXTURE = asset_path("player", "summary", "textures")
WIDTH = 750
FIRST_COLOR = (29, 29, 29)
BROWN = (142, 91, 35)
CHARACTER_MAX = 119

COLLECTION_MAX = {
    _t("gsuid.renderers.progress.collection.30_4.5dc7d7ba"): 1677,
    _t("gsuid.renderers.player.summary.55_4.33e13053"): 3570,
    _t("gsuid.renderers.player.summary.54_4.8d1ca1ac"): 3043,
    _t("gsuid.renderers.player.summary.53_4.cad09647"): 960,
    _t("gsuid.renderers.player.summary.52_4.2eef40ce"): 367,
    _t("gsuid.renderers.player.summary.56_4.0788ed91"): 366,
    _t("gsuid.renderers.progress.collection.36_4.8f1e37e8"): 691,
    _t("gsuid.renderers.progress.collection.37_4.2dcc7eb2"): 69,
}
COLLECTION_AWARD = {
    _t("gsuid.renderers.progress.collection.30_4.5dc7d7ba"): 5,
    _t("gsuid.renderers.player.summary.55_4.33e13053"): 1,
    _t("gsuid.renderers.player.summary.54_4.8d1ca1ac"): 3,
    _t("gsuid.renderers.player.summary.53_4.cad09647"): 8,
    _t("gsuid.renderers.player.summary.52_4.2eef40ce"): 10,
    _t("gsuid.renderers.player.summary.56_4.0788ed91"): 2,
    _t("gsuid.renderers.progress.collection.36_4.8f1e37e8"): 0,
    _t("gsuid.renderers.progress.collection.37_4.2dcc7eb2"): 0,
}
EXPLORATION_MAX = {
    _t("gsuid.renderers.progress.collection.50_4.1e543adb"): CHARACTER_MAX,
    _t("gsuid.renderers.player.summary.44_4.59d5cc2a"): 66,
    _t("gsuid.renderers.player.summary.45_4.56e70957"): 131,
    _t("gsuid.renderers.player.summary.46_4.6eeccf4e"): 181,
    _t("gsuid.renderers.player.summary.47_4.d5bbd092"): 271,
    _t("gsuid.renderers.player.summary.48_4.53cdf0ba"): 271,
    _t("gsuid.renderers.player.summary.49_4.463844dd"): 271,
    _t("gsuid.renderers.player.summary.50_4.600de4a5"): 271,
    _t("gsuid.renderers.player.summary.51_4.68a591a2"): 271,
}
STCMAP = {
    "anemo": _t("gsuid.renderers.player.summary.44_4.59d5cc2a"),
    "geo": _t("gsuid.renderers.player.summary.45_4.56e70957"),
    "electro": _t("gsuid.renderers.player.summary.46_4.6eeccf4e"),
    "dendro": _t("gsuid.renderers.player.summary.47_4.d5bbd092"),
    "hydro": _t("gsuid.renderers.player.summary.48_4.53cdf0ba"),
    "cryo": _t("gsuid.renderers.player.summary.49_4.463844dd"),
    "pyro": _t("gsuid.renderers.player.summary.50_4.600de4a5"),
    "moono": _t("gsuid.renderers.player.summary.51_4.68a591a2"),
}
ELEMENT_LABELS = set(STCMAP.values())


def render_progress_completion_card(
    *,
    completion: Mapping[str, object],
    asset_images: Mapping[str, bytes] | None = None,
) -> bytes:
    asset_images = asset_images or {}
    foreground = render_player_exploration_section(summary=completion, asset_images=asset_images)
    image = v4_background(foreground.size[0], foreground.size[1])
    image.paste(foreground, (0, 0), foreground)
    paste_player_footer(image)
    return png_bytes(image, rgb=True)


def render_progress_collection_card(
    *,
    uid: str,
    summary: Mapping[str, object],
    collection: Mapping[str, object],
    asset_images: Mapping[str, bytes] | None = None,
    title_avatar_url: str | None = None,
) -> bytes:
    asset_images = asset_images or {}
    bars = _collection_bars(collection)
    image = _base_progress_image(
        uid=uid,
        summary=summary,
        title_name="collection_title.png",
        stat_left=_active_days(collection),
        stat_middle=_format_percent(_average_percent(bars)),
        stat_right=_t(
            "gsuid.renderers.progress.collection.102_19.777c9529", _remaining_primogems(bars)
        ),
        bar_count=len(bars),
        asset_images=asset_images,
        title_avatar_url=title_avatar_url,
    )
    for index, (name, percent, value) in enumerate(bars):
        bar = _bar(f"·{name}", percent, value)
        image.paste(bar, (0, 600 + index * 115), bar)
    return png_bytes(image, rgb=True)


def render_progress_exploration_card(
    *,
    uid: str,
    summary: Mapping[str, object],
    completion: Mapping[str, object],
    asset_images: Mapping[str, bytes] | None = None,
    title_avatar_url: str | None = None,
) -> bytes:
    asset_images = asset_images or {}
    bars = _exploration_bars(completion)
    image = _base_progress_image(
        uid=uid,
        summary=summary,
        title_name="explora_title.png",
        stat_left=str(int_value(_stats(completion).get("active_day_number"))),
        stat_middle=_format_percent(
            _average_percent([bar for bar in bars if bar[0] in ELEMENT_LABELS])
        ),
        stat_right=_format_percent(
            _average_percent(
                [
                    bar
                    for bar in bars
                    if bar[0]
                    not in ELEMENT_LABELS
                    | {_t("gsuid.renderers.progress.collection.50_4.1e543adb")}
                ]
            )
        ),
        bar_count=len(bars),
        asset_images=asset_images,
        title_avatar_url=title_avatar_url,
    )
    for index, (name, percent, value) in enumerate(bars):
        bar = _bar(f"·{name}", percent, value)
        image.paste(bar, (0, 600 + index * 115), bar)
    return png_bytes(image, rgb=True)


def _base_progress_image(
    *,
    uid: str,
    summary: Mapping[str, object],
    title_name: str,
    stat_left: str,
    stat_middle: str,
    stat_right: str,
    bar_count: int,
    asset_images: Mapping[str, bytes],
    title_avatar_url: str | None,
) -> Image.Image:
    image = _color_background(WIDTH, 600 + bar_count * 115)
    title = open_rgba(SUMMARY_TEXTURE / title_name)
    image.paste(title, (0, 0), title)
    avatar = player_title_avatar_image(
        summary=summary,
        asset_images=asset_images,
        size=264,
        title_avatar_url=title_avatar_url,
        with_ring=True,
    )
    image.paste(avatar, (241, 40), avatar)
    draw = ImageDraw.Draw(image)
    draw.text((378, 357), f"UID {uid}", FIRST_COLOR, font(30), "mm")
    draw.text((137, 498), stat_left, FIRST_COLOR, font(40), "mm")
    draw.text((372, 498), stat_middle, FIRST_COLOR, font(40), "mm")
    draw.text((607, 498), stat_right, FIRST_COLOR, font(40), "mm")
    return image


def _collection_bars(collection: Mapping[str, object]) -> list[tuple[str, float, str]]:
    stats = _stats(collection)
    values = {
        _t("gsuid.renderers.progress.collection.30_4.5dc7d7ba"): int_value(
            stats.get("achievement_number"),
            int_value(collection.get("achievements")),
        ),
        _t("gsuid.renderers.player.summary.55_4.33e13053"): int_value(
            stats.get("common_chest_number")
        ),
        _t("gsuid.renderers.player.summary.54_4.8d1ca1ac"): int_value(
            stats.get("exquisite_chest_number")
        ),
        _t("gsuid.renderers.player.summary.53_4.cad09647"): int_value(
            stats.get("precious_chest_number")
        ),
        _t("gsuid.renderers.player.summary.52_4.2eef40ce"): int_value(
            stats.get("luxurious_chest_number")
        ),
        _t("gsuid.renderers.player.summary.56_4.0788ed91"): int_value(
            stats.get("magic_chest_number")
        ),
        _t("gsuid.renderers.progress.collection.36_4.8f1e37e8"): int_value(
            stats.get("way_point_number"),
            int_value(collection.get("waypoints")),
        ),
        _t("gsuid.renderers.progress.collection.37_4.2dcc7eb2"): int_value(
            stats.get("domain_number"), int_value(collection.get("domains"))
        ),
    }
    bars: list[tuple[str, float, str]] = []
    for name, value in values.items():
        maximum = COLLECTION_MAX[name]
        percent = value / maximum if maximum else 0
        bars.append((name, percent, f"{value} / {maximum} | {_format_percent(percent * 100)}"))
    return bars


def _exploration_bars(completion: Mapping[str, object]) -> list[tuple[str, float, str]]:
    stats = _stats(completion)
    current = int_value(stats.get("avatar_number"))
    bars: list[tuple[str, float, str]] = [
        (
            _t("gsuid.renderers.progress.collection.50_4.1e543adb"),
            current / CHARACTER_MAX if CHARACTER_MAX else 0,
            f"{current} / {CHARACTER_MAX} | {_format_percent(current / CHARACTER_MAX * 100)}",
        )
    ]
    for element, label in STCMAP.items():
        key = f"{element}culus_number"
        if key not in stats:
            continue
        current = int_value(stats.get(key))
        maximum = EXPLORATION_MAX[label]
        percent = current / maximum if maximum else 0
        bars.append((label, percent, f"{current} / {maximum} | {_format_percent(percent * 100)}"))

    for world in _worlds(completion):
        name = str(world.get("name") or "")
        percent = int_value(world.get("exploration_percentage")) / 1000
        bars.append((name, percent, _format_percent(percent * 100)))
    return bars


def _bar(title: str, percent: float, value: str) -> Image.Image:
    image = open_rgba(TEXTURE / "slider_bar.png")
    draw = ImageDraw.Draw(image)
    percent = min(max(percent, 0), 1)
    draw.text((53, 38), title, BROWN, font(32), "lm")
    draw.text((706, 38), value, (13, 13, 13), font(32), "rm")
    draw.rounded_rectangle((40, 62, 40 + 670 * percent, 76), fill=BROWN, radius=20)
    return image


def _color_background(width: int, height: int) -> Image.Image:
    source = open_rgba(TEXTURE / "bg.jpg")
    image = crop_center(source, width, height)
    color_mask = Image.new("RGBA", (width, height), _background_mask_color(image))
    mask = open_rgba(TEXTURE / "mask.png").resize(
        (width, height),
        Image.Resampling.LANCZOS,
    )
    image.paste(color_mask, (0, 0), mask)
    return image


def _background_mask_color(image: Image.Image) -> tuple[int, int, int]:
    palette_size = 8
    quantized = image.quantize(colors=palette_size, method=Image.Quantize.FASTOCTREE)
    palette = quantized.getpalette() or []
    color = (0, 0, 0)
    distance = 9999.0
    for index in range(palette_size):
        offset = index * 3
        if offset + 3 > len(palette):
            break
        candidate = tuple(palette[offset : offset + 3])
        light = candidate[0] * 0.3 + candidate[1] * 0.6 + candidate[2] * 0.1
        next_distance = abs(light - 195)
        if next_distance < distance:
            color = candidate
            distance = next_distance
    return color


def _stats(data: Mapping[str, object]) -> Mapping[str, object]:
    stats = data.get("raw_stats") or data.get("stats")
    return stats if isinstance(stats, Mapping) else {}


def _worlds(data: Mapping[str, object]) -> list[Mapping[str, object]]:
    worlds = data.get("world_explorations")
    if not isinstance(worlds, list):
        return []
    return [world for world in worlds if isinstance(world, Mapping)]


def _active_days(collection: Mapping[str, object]) -> str:
    return str(int_value(_stats(collection).get("active_day_number")))


def _average_percent(bars: list[tuple[str, float, str]]) -> float:
    if not bars:
        return 0.0
    return sum(percent for _, percent, _ in bars) * 100 / len(bars)


def _remaining_primogems(bars: list[tuple[str, float, str]]) -> int:
    total = 0
    for name, percent, _ in bars:
        maximum = COLLECTION_MAX[name]
        current = int(maximum * percent)
        total += COLLECTION_AWARD[name] * max(maximum - current, 0)
    return total


def _format_percent(value: float) -> str:
    return f"{value:.2f}%"
