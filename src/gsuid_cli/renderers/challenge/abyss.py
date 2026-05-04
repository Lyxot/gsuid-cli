from __future__ import annotations

from collections.abc import Mapping

from PIL import Image, ImageDraw

from gsuid_cli.renderers.challenge.common import (
    append_url,
    avatar_with_ring,
    challenge_character_card,
    character_image_urls,
    character_side_urls,
    first_remote_image,
    timestamp_text,
)
from gsuid_cli.renderers.common import (
    asset_path,
    crop_center,
    font,
    int_value,
    open_rgba,
    png_bytes,
    sequence,
)

TEXTURE = asset_path("challenge", "abyss", "textures")
WIDTH = 950
FIRST_COLOR = (29, 29, 29)
SECOND_COLOR = (67, 61, 56)
RED = (255, 66, 66)
BLUE = (53, 157, 249)
GRAY = (150, 150, 150)
WHITE = (255, 255, 255)


def render_challenge_abyss_card(
    *,
    uid: str,
    abyss: Mapping[str, object],
    summary: Mapping[str, object],
    asset_images: Mapping[str, bytes] | None = None,
    avatar_url: str | None = None,
) -> bytes:
    """Render a GenshinUID-style Spiral Abyss card as PNG bytes."""
    asset_images = asset_images or {}
    floors = _floors(abyss)
    selected_floor = floors[-1] if floors else {}
    full_floor = _has_battles(selected_floor)
    height = 2000 if full_floor else 900
    image = crop_center(open_rgba(TEXTURE / "bg.jpg"), WIDTH, height)

    title = open_rgba(TEXTURE / "abyss_title.png")
    image.paste(title, (0, 0), title)
    avatar = avatar_with_ring(
        summary=summary,
        asset_images=asset_images,
        size=320,
        avatar_url=avatar_url,
    )
    image.paste(avatar, (320, 50), avatar)

    draw = ImageDraw.Draw(image)
    draw.text((475, 469), f"UID {uid}", FIRST_COLOR, font(36), "mm")
    draw.text(
        (475, 413),
        f"挑战次数 - {int_value(abyss.get('total_battle_times'))}",
        FIRST_COLOR,
        font(26),
        "mm",
    )
    _paste_rankings(image, abyss, asset_images)
    _paste_floor_overview(image, floors, full_floor)

    if not full_floor:
        hint = open_rgba(TEXTURE / "hint.png")
        image.paste(hint, (0, 830), hint)
        draw.text((475, 865), "暂无可渲染的本层战斗记录", FIRST_COLOR, font(28), "mm")
    else:
        _paste_floor_detail(image, selected_floor, asset_images)

    return png_bytes(image, rgb=True)


def challenge_abyss_image_urls(
    abyss: Mapping[str, object],
    summary: Mapping[str, object],
    avatar_url: str | None = None,
) -> list[str]:
    urls: list[str] = []
    append_url(urls, avatar_url)
    role = summary.get("role")
    if isinstance(role, Mapping):
        append_url(urls, role.get("avatar_icon"))

    rankings = abyss.get("rankings")
    if isinstance(rankings, Mapping):
        for value in rankings.values():
            for character in _mapping_sequence(value):
                for url in character_side_urls(character):
                    append_url(urls, url)
                for url in character_image_urls(character):
                    append_url(urls, url)

    for floor in _floors(abyss):
        for level in _mapping_sequence(floor.get("levels")):
            for battle in _mapping_sequence(level.get("battles")):
                for character in _mapping_sequence(battle.get("avatars")):
                    for url in character_image_urls(character):
                        append_url(urls, url)
    return urls


def _paste_rankings(
    image: Image.Image,
    abyss: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> None:
    rankings = abyss.get("rankings")
    if not isinstance(rankings, Mapping):
        rankings = {}
    title_data = (
        ("最强一击!", _first_mapping(rankings.get("damage_rank"))),
        ("最多击破!", _first_mapping(rankings.get("defeat_rank"))),
        ("承受伤害", _first_mapping(rankings.get("take_damage_rank"))),
        ("元素爆发", _first_mapping(rankings.get("energy_skill_rank"))),
    )
    draw = ImageDraw.Draw(image)
    for index, (label, character) in enumerate(title_data):
        offset = index * 224
        side = (
            first_remote_image(character_side_urls(character), asset_images, (75, 75))
            if character
            else None
        )
        if side is not None:
            image.paste(side, (43 + offset, 484), side)
        else:
            draw.rounded_rectangle(
                (43 + offset, 484, 118 + offset, 559),
                radius=16,
                outline=(255, 255, 255, 170),
                width=2,
            )
        draw.text((115 + offset, 523), label, FIRST_COLOR, font(20), "lm")
        value = str(character.get("value")) if character else "-"
        draw.text((115 + offset, 545), value, FIRST_COLOR, font(26), "lm")


def _paste_floor_overview(
    image: Image.Image,
    floors: list[Mapping[str, object]],
    full_floor: bool,
) -> None:
    draw = ImageDraw.Draw(image)
    for index, floor in enumerate(_overview_floor_slots(floors)):
        number = int_value(floor.get("index"), index + 9)
        card = open_rgba(TEXTURE / "abyss_omit.png")
        card_draw = ImageDraw.Draw(card)
        card_draw.text((56, 34), f"第{number}层", FIRST_COLOR, font(32), "lm")
        if not floor:
            color, text, time_text = GRAY, "未解锁", "请挑战后查看时间数据!"
        elif str(floor.get("settle_time")) == "0000-00-00 00:00:00":
            color, text, time_text = RED, "已跳过", "跳过楼层不存在时间顺序!"
        elif int_value(floor.get("star")) >= int_value(floor.get("max_star"), 9):
            color, text = RED, "全满星"
            time_text = _floor_time_text(floor, full_floor)
        else:
            gap = int_value(floor.get("max_star"), 9) - int_value(floor.get("star"))
            color, text = BLUE, f"差{max(gap, 0)}颗"
            time_text = _floor_time_text(floor, full_floor)
        card_draw.rounded_rectangle((165, 19, 255, 49), 20, color)
        card_draw.text((210, 34), text, WHITE, font(26), "mm")
        card_draw.text((54, 65), time_text, SECOND_COLOR, font(22), "lm")
        image.paste(card, (20 + 459 * (index % 2), 613 + 106 * (index // 2)), card)
    if not floors:
        draw.text((475, 590), "本期深渊暂无楼层详情", FIRST_COLOR, font(28), "mm")


def _paste_floor_detail(
    image: Image.Image,
    floor: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> None:
    for index, level in enumerate(_mapping_sequence(floor.get("levels"))[:3]):
        card = open_rgba(TEXTURE / "abyss_floor.png")
        star = min(max(int_value(level.get("star")), 0), 3)
        star_image = open_rgba(TEXTURE / f"star{star}.png")
        card.paste(star_image, (690, 170), star_image)
        card_draw = ImageDraw.Draw(card)
        floor_num = int_value(floor.get("index"))
        card_draw.text((652, 71), f"第{floor_num}层第{index + 1}间", FIRST_COLOR, font(32), "lm")
        time_text = _level_time_text(level)
        for line_index, line in enumerate(time_text.split(" ")):
            card_draw.text((655, 102 + line_index * 22), line, FIRST_COLOR, font(22), "lm")
        for part_index, battle in enumerate(_mapping_sequence(level.get("battles"))[:2]):
            for char_index, character in enumerate(_mapping_sequence(battle.get("avatars"))[:4]):
                char_card = challenge_character_card(
                    character,
                    asset_images,
                    size=(128, 160),
                    level_anchor_x=77,
                )
                card.paste(char_card, (70 + 147 * char_index, 39 + part_index * 170), char_card)
        image.paste(card, (0, 818 + index * 391), card)


def _floor_time_text(floor: Mapping[str, object], full_floor: bool) -> str:
    if not full_floor:
        return "请挑战后查看时间数据!"
    levels = _mapping_sequence(floor.get("levels"))
    if not levels:
        return "请挑战后查看时间数据!"
    return _level_time_text(levels[-1])


def _level_time_text(level: Mapping[str, object]) -> str:
    battles = _mapping_sequence(level.get("battles"))
    if not battles:
        return "请挑战后查看时间数据!"
    time_text = timestamp_text(battles[0].get("timestamp"))
    return time_text.replace(".", "-") if time_text else "请挑战后查看时间数据!"


def _has_battles(floor: Mapping[str, object]) -> bool:
    levels = _mapping_sequence(floor.get("levels"))
    if not levels:
        return False
    battles = levels[-1].get("battles")
    return bool(_mapping_sequence(battles))


def _floors(abyss: Mapping[str, object]) -> list[Mapping[str, object]]:
    floors = [
        floor
        for floor in _mapping_sequence(abyss.get("floors"))
        if int_value(floor.get("index")) >= 9
    ]
    return sorted(floors, key=lambda floor: int_value(floor.get("index")))


def _overview_floor_slots(floors: list[Mapping[str, object]]) -> list[Mapping[str, object]]:
    if not floors:
        return [{"index": number} for number in range(9, 13)]

    slots: list[Mapping[str, object]] = []
    first_index = int_value(floors[0].get("index"))
    for number in range(9, min(first_index, 13)):
        slots.append(_skipped_floor(number))
    slots.extend(floors)
    present = {int_value(floor.get("index")) for floor in slots}
    for number in range(9, 13):
        if number not in present:
            slots.append({"index": number})
    return sorted(slots, key=lambda floor: int_value(floor.get("index")))[:4]


def _skipped_floor(index: int) -> Mapping[str, object]:
    return {
        "index": index,
        "levels": [],
        "is_unlock": True,
        "star": 9,
        "max_star": 9,
        "settle_time": "0000-00-00 00:00:00",
        "icon": "",
    }


def _first_mapping(value: object) -> Mapping[str, object]:
    values = _mapping_sequence(value)
    return values[0] if values else {}


def _mapping_sequence(value: object) -> list[Mapping[str, object]]:
    return [item for item in sequence(value) if isinstance(item, Mapping)]
