from __future__ import annotations

from collections.abc import Mapping

from PIL import Image, ImageDraw

from gsuid_cli.renderers._text_helpers import (
    _mapping,
    _mapping_list as _mapping_sequence,
)
from gsuid_cli.renderers.challenge.common import (
    append_url,
    avatar_with_ring,
    challenge_character_card,
    character_image_urls,
    character_side_urls,
    first_remote_image,
    paste_footer,
    remote_image,
    timestamp_text,
)
from gsuid_cli.renderers.common import asset_path, font, int_value, open_rgba, png_bytes
from gsuid_cli.text import t as _t

TEXTURE = asset_path("challenge", "theater", "textures")
WIDTH = 1200
DIFFICULTY_MAP = {
    1: _t("gsuid.renderers.challenge.text.10_7.b96a5429"),
    2: _t("gsuid.renderers.challenge.text.11_7.e8a4554e"),
    3: _t("gsuid.renderers.challenge.text.12_7.49b6a116"),
    4: _t("gsuid.renderers.challenge.text.13_7.c528888a"),
    5: _t("gsuid.renderers.challenge.text.14_7.93eacb2e"),
}


def render_challenge_theater_card(
    *,
    uid: str,
    theater: Mapping[str, object],
    summary: Mapping[str, object],
    asset_images: Mapping[str, bytes] | None = None,
    avatar_url: str | None = None,
) -> bytes:
    """Render a GenshinUID-style Imaginarium Theater card as PNG bytes."""
    asset_images = asset_images or {}
    session = _selected_session(theater)
    detail = _mapping(session.get("detail"))
    raw_rounds = _mapping_sequence(detail.get("rounds_data"))
    rounds = _filtered_rounds(raw_rounds)
    rows = max((len(rounds) + 1) // 2, 1)
    image = Image.new("RGBA", (WIDTH, 840 + rows * 280), (22, 18, 20, 255))

    stat = _mapping(session.get("stat")) or _mapping(detail.get("detail_stat"))
    schedule = _mapping(session.get("schedule"))
    fight = _mapping(detail.get("fight_statisic"))
    _paste_title(image, uid, summary, stat, schedule, fight, asset_images, avatar_url)
    _paste_status(image, stat, fight)
    if rounds:
        _paste_rounds(image, rounds, asset_images)
    else:
        draw = ImageDraw.Draw(image)
        draw.text(
            (WIDTH // 2, 835),
            _t("gsuid.renderers.challenge.text.109_26.780f83be"),
            "white",
            font(36),
            "mm",
        )

    paste_footer(image, font_size=24)
    return png_bytes(image, rgb=True)


def challenge_theater_image_urls(
    theater: Mapping[str, object],
    summary: Mapping[str, object],
    avatar_url: str | None = None,
) -> list[str]:
    urls: list[str] = []
    append_url(urls, avatar_url)
    role = summary.get("role")
    if isinstance(role, Mapping):
        append_url(urls, role.get("avatar_icon"))
    session = _selected_session(theater)
    detail = _mapping(session.get("detail"))
    fight = _mapping(detail.get("fight_statisic"))
    max_damage = fight.get("max_damage_avatar")
    if isinstance(max_damage, Mapping):
        for url in character_side_urls(max_damage):
            append_url(urls, url)
    for round_data in _mapping_sequence(detail.get("rounds_data")):
        splendour = _mapping(round_data.get("splendour_buff"))
        for buff in _mapping_sequence(splendour.get("buffs")):
            append_url(urls, buff.get("icon"))
        enemies = _mapping_sequence(round_data.get("enemies"))
        if len(enemies) == 1:
            append_url(urls, enemies[0].get("icon"))
        for character in _mapping_sequence(round_data.get("avatars")):
            for url in character_image_urls(character):
                append_url(urls, url)
    return urls


def _paste_title(
    image: Image.Image,
    uid: str,
    summary: Mapping[str, object],
    stat: Mapping[str, object],
    schedule: Mapping[str, object],
    fight: Mapping[str, object],
    asset_images: Mapping[str, bytes],
    avatar_url: str | None,
) -> None:
    title = open_rgba(TEXTURE / "title.png")
    title_fg = open_rgba(TEXTURE / "title_fg.png")
    avatar = avatar_with_ring(
        summary=summary,
        asset_images=asset_images,
        size=180,
        avatar_url=avatar_url,
    )
    title.paste(avatar, (119, 328), avatar)
    title.paste(title_fg, (0, 0), title_fg)

    difficulty_id = int_value(stat.get("difficulty_id"))
    max_round, medal = _round_medal_counts(stat)
    icon = open_rgba(TEXTURE / _difficulty_icon_name(stat))
    title.paste(icon, (726, 406), icon)

    draw = ImageDraw.Draw(title)
    draw.text((362, 428), _nickname(summary), "white", font(40), "lm")
    draw.text((458, 478), f"UID {uid}", (207, 207, 207), font(30), "mm")
    draw.text(
        (875, 430),
        DIFFICULTY_MAP.get(difficulty_id, _t("gsuid.renderers.challenge.text.12_7.49b6a116")),
        "white",
        font(30),
        "mm",
    )
    draw.text((1072, 430), f"{medal}/{max_round}", "white", font(30), "mm")
    start = timestamp_text(schedule.get("start_time"))
    end = timestamp_text(schedule.get("end_time"))
    draw.text((1118, 482), f"{start} ~ {end}", (139, 137, 133), font(20), "rm")

    max_damage = fight.get("max_damage_avatar")
    if isinstance(max_damage, Mapping):
        best_hit = open_rgba(TEXTURE / "best_hit.png")
        side = first_remote_image(character_side_urls(max_damage), asset_images, (75, 75))
        if side is not None:
            best_hit.paste(side, (27, 7), side)
        best_draw = ImageDraw.Draw(best_hit)
        best_draw.text((189, 58), str(max_damage.get("value") or "-"), "white", font(26), "mm")
        best_draw.text(
            (68, 91),
            _t("gsuid.renderers.challenge.theater.140_33.28915553"),
            "white",
            font(20),
            "mm",
        )
        title.paste(best_hit, (860, 222), best_hit)

    image.paste(title, (0, 0), title)


def _paste_status(
    image: Image.Image,
    stat: Mapping[str, object],
    fight: Mapping[str, object],
) -> None:
    status = open_rgba(TEXTURE / "bar.png")
    draw = ImageDraw.Draw(status)
    total_time = int_value(fight.get("total_use_time"))
    total_time_text = _t(
        "gsuid.renderers.challenge.theater.154_22.163ee8ea", total_time // 60, total_time % 60
    )
    values = (
        (
            145,
            _t(
                "gsuid.renderers.challenge.text.117_17.9f1f6bf4",
                int_value(stat.get("max_round_id")),
            ),
        ),
        (
            327,
            _t(
                "gsuid.renderers.challenge.text.115_12.1b02ae01",
                int_value(stat.get("tarot_finished_cnt")),
            ),
        ),
        (508, str(int_value(stat.get("coin_num")))),
        (690, str(int_value(stat.get("avatar_bonus_num")))),
        (871, str(int_value(stat.get("rent_cnt")))),
        (1052, total_time_text),
    )
    for x, value in values:
        draw.text((x, 41), value, "white", font(38), "mm")
    image.paste(status, (0, 577), status)


def _paste_rounds(
    image: Image.Image,
    rounds: list[Mapping[str, object]],
    asset_images: Mapping[str, bytes],
) -> None:
    flower_yes = open_rgba(TEXTURE / "flower_yes.png")
    flower_no = open_rgba(TEXTURE / "flower_no.png")
    div = open_rgba(TEXTURE / "div.png")
    for index, round_data in enumerate(rounds):
        stage_name = "stage_moon.png" if round_data.get("is_tarot") else "stage.png"
        stage = open_rgba(TEXTURE / stage_name)
        draw = ImageDraw.Draw(stage)
        round_name = (
            _t(
                "gsuid.renderers.challenge.text.115_12.1b02ae01",
                int_value(round_data.get("tarot_serial_no")),
            )
            if round_data.get("is_tarot")
            else _t(
                "gsuid.renderers.challenge.text.117_17.9f1f6bf4",
                int_value(round_data.get("round_id")),
            )
        )
        medal = flower_yes if round_data.get("is_get_medal") else flower_no
        draw.text((172, 63), round_name, "white", font(28), "mm")
        stage.paste(medal, (57, 38), medal)
        _paste_buffs(stage, round_data, asset_images)
        _paste_enemy(stage, round_data, asset_images)
        for char_index, character in enumerate(_mapping_sequence(round_data.get("avatars"))[:4]):
            char_card = challenge_character_card(
                character,
                asset_images,
                size=(110, 133),
                level_anchor_x=128,
            )
            stage.paste(char_card, (45 + 123 * char_index, 109), char_card)
            char_type = int_value(character.get("avatar_type"), 1)
            if char_type != 1 and (TEXTURE / f"{char_type}.png").exists():
                tag = open_rgba(TEXTURE / f"{char_type}.png")
                stage.paste(tag, (74 + 123 * char_index, 99), tag)
        image.paste(stage, (30 + 570 * (index % 2), 760 + 280 * (index // 2)), stage)
        if index % 2 == 1:
            image.paste(div, (75, 756 + 280 * ((index // 2) + 1)), div)


def _paste_buffs(
    stage: Image.Image,
    round_data: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> None:
    splendour = _mapping(round_data.get("splendour_buff"))
    for index, buff in enumerate(_mapping_sequence(splendour.get("buffs"))[:3]):
        buff_image = Image.new("RGBA", (80, 80))
        icon = remote_image(str(buff.get("icon") or ""), asset_images, (51, 51))
        if icon is not None:
            buff_image.paste(icon, (14, 5), icon)
        buff_draw = ImageDraw.Draw(buff_image)
        buff_draw.text((40, 62), f"Lv{int_value(buff.get('level'))}", "white", font(20), "mm")
        stage.paste(buff_image, (323 + 66 * index, 18), buff_image)


def _paste_enemy(
    stage: Image.Image,
    round_data: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> None:
    enemies = _mapping_sequence(round_data.get("enemies"))
    if len(enemies) != 1:
        return
    monster = Image.new("RGBA", (75, 75))
    icon = remote_image(str(enemies[0].get("icon") or ""), asset_images, (75, 75))
    if icon is not None:
        monster.paste(icon, (0, 0), icon)
    fg = open_rgba(TEXTURE / "monster_fg.png")
    monster.paste(fg, (0, 0), fg)
    stage.paste(monster, (243, 19), monster)


def _selected_session(theater: Mapping[str, object]) -> Mapping[str, object]:
    selected = theater.get("selected")
    return selected if isinstance(selected, Mapping) else {}


def _filtered_rounds(rounds: list[Mapping[str, object]]) -> list[Mapping[str, object]]:
    tarot_count = sum(1 for item in rounds if item.get("is_tarot") is True)
    if tarot_count <= 2:
        return rounds
    return [
        item
        for item in rounds
        if not item.get("is_tarot", False) or item.get("is_get_medal", False)
    ]


def _round_medal_counts(stat: Mapping[str, object]) -> tuple[int, int]:
    difficulty_id = int_value(stat.get("difficulty_id"))
    max_round = int_value(stat.get("max_round_id"))
    medal = int_value(stat.get("medal_num"))
    if difficulty_id == 5:
        max_round = 12
        medal += int_value(stat.get("tarot_finished_cnt"))
    return max_round, medal


def _difficulty_icon_name(stat: Mapping[str, object]) -> str:
    difficulty_id = int_value(stat.get("difficulty_id"))
    max_round = int_value(stat.get("max_round_id"))
    tarot = int_value(stat.get("tarot_finished_cnt"))
    if difficulty_id == 3:
        return "gold_yes.png" if max_round == 8 else "gold_no.png"
    if difficulty_id == 4:
        return "super_yes.png" if max_round == 10 else "super_no.png"
    if difficulty_id == 5:
        return "moon_yes.png" if max_round == 10 and tarot == 2 else "moon_no.png"
    return "gold_no.png"


def _nickname(summary: Mapping[str, object]) -> str:
    role = summary.get("role")
    if isinstance(role, Mapping):
        nickname = role.get("nickname")
        if isinstance(nickname, str) and nickname:
            return nickname
    return _t("gsuid.renderers.challenge.text.275_47.b2457913")
