from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BACKGROUND = (22, 26, 31)
PANEL = (35, 41, 49)
PANEL_ALT = (42, 50, 58)
TEXT = (242, 237, 228)
MUTED = (171, 181, 190)
ACCENT = (229, 183, 109)
BLUE = (116, 178, 210)
GREEN = (128, 190, 158)


def render_daily_note(data: dict[str, object]) -> bytes:
    note = _dict(data.get("note"))
    rows = [
        ("Resin", _count(note.get("current_resin"), note.get("max_resin"))),
        ("Commissions", _count(note.get("finished_task_num"), note.get("total_task_num"))),
        (
            "Expeditions",
            _count(note.get("current_expedition_num"), note.get("max_expedition_num")),
        ),
        ("Realm Currency", _count(note.get("current_home_coin"), note.get("max_home_coin"))),
        (
            "Weekly Discounts",
            _count(note.get("remain_resin_discount_num"), note.get("resin_discount_num_limit")),
        ),
    ]
    subtitle = f"UID {data.get('uid') or '-'}"
    return _card(
        title="Daily Note",
        subtitle=subtitle,
        rows=rows,
        footer="Live account status",
        width=960,
        height=540,
    )


def render_abyss_summary(data: dict[str, object]) -> bytes:
    abyss = _dict(data.get("abyss"))
    floors = _list_of_dicts(abyss.get("floors"))
    rows = [
        ("Season", str(data.get("season") or "-")),
        ("Total Stars", _value(abyss.get("total_star"))),
        ("Max Floor", _value(abyss.get("max_floor"))),
        ("Battles", _value(abyss.get("total_battle_times"))),
        ("Wins", _value(abyss.get("total_win_times"))),
    ]
    for floor in floors[:4]:
        rows.append((f"Floor {floor.get('index')}", f"{_value(floor.get('star'))} stars"))
    return _card(
        title="Spiral Abyss",
        subtitle=f"UID {data.get('uid') or '-'}",
        rows=rows,
        footer=f"{len(floors)} floors returned",
        width=960,
        height=540,
    )


def render_panel(data: dict[str, object]) -> bytes:
    panel = _dict(data.get("panel"))
    weapon = _dict(panel.get("weapon"))
    props = _dict(panel.get("fight_props"))
    rows = [
        ("Level", _value(panel.get("level"))),
        ("Constellation", _value(panel.get("constellation"))),
        ("Friendship", _value(panel.get("friendship"))),
        ("Weapon", _weapon_label(weapon)),
        ("Artifact Score", _value(panel.get("artifact_score"))),
        ("Crit Rate", _percent_value(props.get("crit_rate"))),
        ("Crit Damage", _percent_value(props.get("crit_damage"))),
        ("Energy Recharge", _percent_value(props.get("energy_recharge"))),
        ("ATK", _value(props.get("atk"))),
        ("Elemental Mastery", _value(props.get("elemental_mastery"))),
    ]
    return _card(
        title=str(panel.get("name") or data.get("character") or "Panel"),
        subtitle=f"UID {data.get('uid') or '-'}",
        rows=rows,
        footer=f"{len(_list_of_dicts(panel.get('artifacts')))} artifacts",
        width=1080,
        height=720,
    )


def _card(
    *,
    title: str,
    subtitle: str,
    rows: list[tuple[str, str]],
    footer: str,
    width: int,
    height: int,
) -> bytes:
    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    _draw_background(draw, width, height)
    title_font = _font(48)
    subtitle_font = _font(24)
    row_font = _font(25)
    value_font = _font(30)
    footer_font = _font(20)

    draw.text((52, 44), title, fill=TEXT, font=title_font)
    draw.text((54, 103), subtitle, fill=MUTED, font=subtitle_font)
    draw.rounded_rectangle((48, 150, width - 48, height - 74), radius=22, fill=PANEL)

    row_top = 176
    row_height = 48
    for index, (label, value) in enumerate(rows[:10]):
        top = row_top + index * row_height
        if index % 2:
            draw.rounded_rectangle((70, top - 8, width - 70, top + 34), radius=10, fill=PANEL_ALT)
        draw.text((88, top), label, fill=MUTED, font=row_font)
        draw.text((width - 88, top - 3), value, fill=TEXT, font=value_font, anchor="ra")

    draw.line((52, height - 56, width - 52, height - 56), fill=(68, 76, 84), width=1)
    draw.text((54, height - 42), footer, fill=MUTED, font=footer_font)
    return _png_bytes(image)


def _draw_background(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    draw.rectangle((0, 0, width, height), fill=BACKGROUND)
    draw.rectangle((0, 0, width, 16), fill=ACCENT)
    draw.rectangle((0, 16, width // 2, 22), fill=BLUE)
    draw.rectangle((width // 2, 16, width, 22), fill=GREEN)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _font_paths():
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _font_paths() -> list[Path]:
    return [
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]


def _png_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=False)
    return output.getvalue()


def _count(current: object, maximum: object) -> str:
    if current is None and maximum is None:
        return "-"
    return f"{_value(current)} / {_value(maximum)}"


def _weapon_label(weapon: dict[str, object]) -> str:
    if not weapon:
        return "-"
    name = str(weapon.get("name") or "Weapon")
    level = weapon.get("level")
    rank = weapon.get("rank")
    parts = [name]
    if level is not None:
        parts.append(f"Lv. {level}")
    if rank is not None:
        parts.append(f"R{rank}")
    return " ".join(parts)


def _percent_value(value: object) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return str(value)


def _value(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
