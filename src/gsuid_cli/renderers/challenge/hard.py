from __future__ import annotations

from collections.abc import Mapping

from PIL import Image, ImageDraw

from gsuid_cli.renderers.challenge.common import (
    append_url,
    avatar_with_ring,
    challenge_character_card,
    character_side_urls,
    first_remote_image,
    paste_footer,
    remote_image,
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

TEXTURE = asset_path("challenge", "hard", "textures")
WIDTH = 900


def render_challenge_hard_card(
    *,
    uid: str,
    hard: Mapping[str, object],
    summary: Mapping[str, object],
    asset_images: Mapping[str, bytes] | None = None,
    avatar_url: str | None = None,
) -> bytes:
    """Render a GenshinUID-style hard challenge card as PNG bytes."""
    asset_images = asset_images or {}
    schedule, single = _hard_sections(hard)
    challenge = _mapping_sequence(single.get("challenge"))
    height = max(1900, 576 + max(len(challenge), 1) * 420 + 64)
    image = crop_center(open_rgba(TEXTURE / "bg.jpg"), WIDTH, height).convert("RGBA")
    _paste_title(image, uid, summary, schedule, asset_images, avatar_url)

    best = single.get("best")
    if not isinstance(best, Mapping) or not challenge:
        draw = ImageDraw.Draw(image)
        draw.text((WIDTH // 2, 620), "暂无肃靖险乱挑战记录", "white", font(40), "mm")
        paste_footer(image, font_size=22)
        return png_bytes(image, rgb=True)

    _paste_banner(image, best)
    for index, floor in enumerate(challenge):
        card = _challenge_card(floor, asset_images)
        image.paste(card, (0, 576 + index * 420), card)
    paste_footer(image, font_size=22)
    return png_bytes(image, rgb=True)


def challenge_hard_image_urls(
    hard: Mapping[str, object],
    summary: Mapping[str, object],
    avatar_url: str | None = None,
) -> list[str]:
    urls: list[str] = []
    append_url(urls, avatar_url)
    role = summary.get("role")
    if isinstance(role, Mapping):
        append_url(urls, role.get("avatar_icon"))
    _, single = _hard_sections(hard)
    for floor in _mapping_sequence(single.get("challenge")):
        monster = floor.get("monster")
        if isinstance(monster, Mapping):
            append_url(urls, monster.get("icon"))
        for character in _mapping_sequence(floor.get("teams")):
            append_url(urls, character.get("image"))
            append_url(urls, character.get("icon"))
            append_url(urls, character.get("avatar_icon"))
        for character in _mapping_sequence(floor.get("best_avatar")):
            append_url(urls, character.get("side_icon"))
            append_url(urls, character.get("avatar_icon"))
    return urls


def _paste_title(
    image: Image.Image,
    uid: str,
    summary: Mapping[str, object],
    schedule: Mapping[str, object],
    asset_images: Mapping[str, bytes],
    avatar_url: str | None,
) -> None:
    title = open_rgba(TEXTURE / "title.png")
    avatar = avatar_with_ring(
        summary=summary,
        asset_images=asset_images,
        size=278,
        avatar_url=avatar_url,
    )
    title.paste(avatar, (315, 50), avatar)
    start = timestamp_text(schedule.get("start_time"), date_only=True)
    end = timestamp_text(schedule.get("end_time"), date_only=True)
    draw = ImageDraw.Draw(title)
    draw.text((450, 380), f"UID {uid}", "white", font(26), "mm")
    draw.text((450, 422), f"{start} ~ {end}", (199, 199, 199), font(22), "mm")
    image.paste(title, (0, 0), title)


def _paste_banner(image: Image.Image, best: Mapping[str, object]) -> None:
    banner = open_rgba(TEXTURE / "banner.png")
    difficulty = min(max(int_value(best.get("difficulty"), 3), 3), 6)
    medal_path = TEXTURE / f"medal_{difficulty}.png"
    if medal_path.exists():
        medal = open_rgba(medal_path).resize((84, 84), Image.Resampling.LANCZOS)
        banner.paste(medal, (636, 9), medal)
    draw = ImageDraw.Draw(banner)
    draw.text((820, 51), f"{int_value(best.get('second'))}秒", "white", font(32), "rm")
    image.paste(banner, (0, 470), banner)


def _challenge_card(
    floor: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    card = open_rgba(TEXTURE / "card.png")
    draw = ImageDraw.Draw(card)
    draw.text((59, 63), str(floor.get("name") or ""), "white", font(36), "lm")
    draw.text((79, 123), "战斗用时", "white", font(26), "lm")
    draw.text((456, 123), f"{int_value(floor.get('second'))}秒", "white", font(26), "rm")

    monster = floor.get("monster")
    if isinstance(monster, Mapping):
        monster_icon = remote_image(str(monster.get("icon") or ""), asset_images, (563, 563))
        if monster_icon is not None:
            card.paste(monster_icon, (425, -73), monster_icon)
        draw.rounded_rectangle((726, 31, 826, 68), 5, (192, 24, 24))
        draw.text((776, 50), f"Lv{int_value(monster.get('level'))}", "white", font(26), "mm")

    card_fg = open_rgba(TEXTURE / "card_fg.png")
    card.paste(card_fg, (0, 0), card_fg)

    for index, avatar in enumerate(_mapping_sequence(floor.get("teams"))[:4]):
        character = _avatar_mapping(avatar)
        char_card = challenge_character_card(character, asset_images, size=(102, 124))
        card.paste(char_card, (111 * index + 58, 171), char_card)

    best_avatars = _mapping_sequence(floor.get("best_avatar"))
    if len(best_avatars) >= 2:
        _paste_best_avatar(
            card,
            best_avatars[0],
            asset_images,
            (54, 291),
            "最强一击",
            (141, 354),
            (426, 354),
        )
        _paste_best_avatar(
            card,
            best_avatars[1],
            asset_images,
            (435, 291),
            "最高总伤",
            (521, 354),
            (806, 354),
        )
    return card


def _paste_best_avatar(
    card: Image.Image,
    avatar: Mapping[str, object],
    asset_images: Mapping[str, bytes],
    image_xy: tuple[int, int],
    label: str,
    label_xy: tuple[int, int],
    value_xy: tuple[int, int],
) -> None:
    draw = ImageDraw.Draw(card)
    side = first_remote_image(character_side_urls(_avatar_mapping(avatar)), asset_images, (83, 83))
    if side is not None:
        card.paste(side, image_xy, side)
    draw.text(label_xy, label, "white", font(26), "lm")
    draw.text(
        value_xy,
        str(avatar.get("dps") or avatar.get("value") or "-"),
        "white",
        font(26),
        "rm",
    )


def _hard_sections(hard: Mapping[str, object]) -> tuple[Mapping[str, object], Mapping[str, object]]:
    root = hard.get("hard_challenge")
    root = root if isinstance(root, Mapping) else hard
    sessions = root.get("data") if isinstance(root, Mapping) else None
    session = {}
    if isinstance(sessions, list) and sessions and isinstance(sessions[0], Mapping):
        session = sessions[0]
    elif isinstance(root, Mapping):
        session = root
    schedule = session.get("schedule") if isinstance(session.get("schedule"), Mapping) else {}
    single = session.get("single") if isinstance(session.get("single"), Mapping) else session
    return schedule, single if isinstance(single, Mapping) else {}


def _avatar_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    if "avatar_id" in value and "id" not in value:
        return {**value, "id": value.get("avatar_id"), "icon": value.get("image")}
    return value


def _mapping_sequence(value: object) -> list[Mapping[str, object]]:
    return [item for item in sequence(value) if isinstance(item, Mapping)]
