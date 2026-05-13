from __future__ import annotations

from collections.abc import Mapping, Sequence

from PIL import Image, ImageDraw

from gsuid_cli.renderers._text_helpers import _mapping_list
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
from gsuid_cli.renderers.player.summary import (
    paste_player_footer,
    render_player_title_section,
)
from gsuid_cli.text import t as _t

TEXTURE = asset_path("player", "calendar", "textures")
PUBLIC_TEXTURE = asset_path("public", "textures")
WIDTH = 1000
GREY = (189, 189, 189)


def render_player_calendar_card(
    *,
    uid: str,
    summary: Mapping[str, object],
    calendar: Mapping[str, object],
    asset_images: Mapping[str, bytes] | None = None,
    title_avatar_url: str | None = None,
) -> bytes:
    """Render a GenshinUID-style player activity calendar card as PNG bytes."""
    asset_images = asset_images or {}
    act_list = _calendar_acts(calendar)
    fixed_acts = _mapping_list(calendar.get("fixed_act_list"))
    avatar_pools = _mapping_list(calendar.get("avatar_card_pool_list"))
    weapon_pools = _mapping_list(calendar.get("weapon_card_pool_list"))

    title = render_player_title_section(
        uid=uid,
        summary=summary,
        asset_images=asset_images,
        title_avatar_url=title_avatar_url,
    ).resize((1058, 441), Image.Resampling.LANCZOS)
    height = title.size[1] + 385
    if avatar_pools:
        height += 270
    if weapon_pools:
        height += 270
    height += len(act_list) * 160
    height += len(fixed_acts) * 160

    image = v4_background(WIDTH, max(height, 900))
    image.paste(title, (-30, 34), title)
    y = title.size[1] + 60
    image.paste(open_rgba(TEXTURE / "bar1.png"), (0, y), open_rgba(TEXTURE / "bar1.png"))
    y += 60

    if avatar_pools:
        pool = _pool_card(avatar_pools, "avatars", asset_images)
        image.paste(pool, (0, y), pool)
        y += 270
    if weapon_pools:
        pool = _pool_card(weapon_pools, "weapon", asset_images)
        image.paste(pool, (0, y), pool)
        y += 270

    y += 30
    image.paste(open_rgba(TEXTURE / "bar2.png"), (0, y), open_rgba(TEXTURE / "bar2.png"))
    y += 60
    for act in act_list:
        card = _act_card(act, asset_images)
        image.paste(card, (0, y), card)
        y += 160

    y += 30
    image.paste(open_rgba(TEXTURE / "bar3.png"), (0, y), open_rgba(TEXTURE / "bar3.png"))
    y += 60
    for act in fixed_acts:
        card = _act_card(act, asset_images)
        image.paste(card, (0, y), card)
        y += 160

    paste_player_footer(image, font_size=20)
    return png_bytes(image, rgb=True)


def player_calendar_icon_urls(calendar: Mapping[str, object]) -> list[str]:
    urls: list[str] = []
    for pool_key, item_key in (
        ("avatar_card_pool_list", "avatars"),
        ("selected_avatar_card_pool_list", "avatars"),
        ("weapon_card_pool_list", "weapon"),
        ("mixed_card_pool_list", "avatars"),
        ("selected_mixed_card_pool_list", "avatars"),
    ):
        for pool in _mapping_list(calendar.get(pool_key)):
            for item in _mapping_list(pool.get(item_key)):
                _append_url(urls, item.get("icon"))
            for item in _mapping_list(pool.get("weapon")):
                _append_url(urls, item.get("icon"))
    for act in [*_calendar_acts(calendar), *_mapping_list(calendar.get("fixed_act_list"))]:
        for reward in _mapping_list(act.get("reward_list")):
            _append_url(urls, reward.get("icon"))
    return urls


def _pool_card(
    pools: Sequence[Mapping[str, object]],
    item_key: str,
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    pool_bg = open_rgba(TEXTURE / "pool_bg.png")
    draw = ImageDraw.Draw(pool_bg)
    first = pools[0]
    draw.text((159, 61), text_value(first.get("pool_name")) or "", "white", font(38), "lm")
    draw.text((110, 61), text_value(first.get("version_name")) or "", "white", font(30), "mm")
    draw.text(
        (110, 106),
        _t("gsuid.renderers.player.calendar.125_8.be962ae8")
        + _duration_text(int_value(first.get("countdown_seconds"))),
        GREY,
        font(26),
        "lm",
    )

    for pool_index, pool in enumerate(pools):
        items = _mapping_list(pool.get(item_key))
        for item_index, item in enumerate(items):
            icon = _rarity_icon(item, asset_images)
            x = 64 + item_index * 105 + pool_index * 444
            pool_bg.paste(icon, (x, 136), icon)
    return pool_bg


def _act_card(act: Mapping[str, object], asset_images: Mapping[str, bytes]) -> Image.Image:
    card = open_rgba(TEXTURE / "act_bg.png")
    status = _act_status(act)
    overlay = open_rgba(TEXTURE / f"{status}.png")
    card.paste(overlay, (0, 0), overlay)
    draw = ImageDraw.Draw(card)

    if status == "un":
        state_text = _t("gsuid.renderers.player.calendar.148_21.062e5e67")
        prefix = _t("gsuid.renderers.player.calendar.149_17.6d518ee6")
        sub_text = None
    else:
        state_text, sub_text = _finished_text(act)
        prefix = _t("gsuid.renderers.player.calendar.153_17.f5c64340")

    draw.text((94, 60), text_value(act.get("name")) or "", "white", font(38), "lm")
    draw.text(
        (130, 102),
        prefix + _duration_text(int_value(act.get("countdown_seconds"))),
        GREY,
        font(26),
        "lm",
    )
    draw.text((840, 81), state_text, "white", font(30), "mm")
    if sub_text:
        draw.text((840, 120), sub_text, (25, 153, 245), font(24), "mm")

    for index, reward in enumerate(_mapping_list(act.get("reward_list"))[:2]):
        reward_card = _reward_card(reward, asset_images)
        card.paste(reward_card, (539 + index * 105, 31), reward_card)
    return card


def _reward_card(
    reward: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    card = open_rgba(TEXTURE / "icon_bg.png")
    icon = _remote_icon(text_value(reward.get("icon")), asset_images, (100, 100))
    if icon is not None:
        card.paste(icon, (0, 0), icon)
    card.paste(open_rgba(TEXTURE / "icon_fg.png"), (0, 0), open_rgba(TEXTURE / "icon_fg.png"))
    draw = ImageDraw.Draw(card)
    draw.text((50, 81), str(int_value(reward.get("num"))), "white", font(26), "mm")
    return card


def _rarity_icon(
    item: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    rarity = min(max(int_value(item.get("rarity"), 1), 1), 5)
    path = PUBLIC_TEXTURE / "weapon" / f"weapon_bg{rarity}.png"
    card = open_rgba(path).resize((105, 105), Image.Resampling.LANCZOS)
    icon = _remote_icon(text_value(item.get("icon")), asset_images, (105, 105))
    if icon is not None:
        card.paste(icon, (0, 0), icon)
    else:
        draw = ImageDraw.Draw(card)
        draw.text((52, 52), (text_value(item.get("name")) or "?")[:2], "white", font(22), "mm")
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


def _calendar_acts(calendar: Mapping[str, object]) -> list[Mapping[str, object]]:
    acts: list[Mapping[str, object]] = []
    for act in _mapping_list(calendar.get("act_list")):
        acts.append(act)
        sub = _hard_challenge_sub(act)
        if sub is not None:
            acts.append(sub)
    return acts


def _hard_challenge_sub(act: Mapping[str, object]) -> Mapping[str, object] | None:
    if act.get("type") != "ActTypeHardChallenge":
        return None
    detail = act.get("hard_challenge_detail")
    if not isinstance(detail, Mapping):
        return None
    sub = detail.get("sub")
    if not isinstance(sub, Mapping):
        return None
    rewards = _mapping_list(act.get("reward_list"))
    return {
        "type": "ActTypeHardChallengeSub",
        "name": _t("gsuid.renderers.player.calendar.238_16.68a41218"),
        "countdown_seconds": sub.get("seconds"),
        "x": sub.get("x"),
        "y": sub.get("y"),
        "is_finished": int_value(sub.get("x")) >= int_value(sub.get("y")),
        "status": 2,
        "reward_list": rewards[1:2],
    }


def _act_status(act: Mapping[str, object]) -> str:
    return "un" if int_value(act.get("status")) != 2 else "yes" if act.get("is_finished") else "no"


def _finished_text(act: Mapping[str, object]) -> tuple[str, str | None]:
    if act.get("type") == "ActTypeHardChallenge":
        detail = act.get("hard_challenge_detail")
        if isinstance(detail, Mapping) and int_value(detail.get("second")) > 0:
            difficulty = int_value(detail.get("difficulty"))
            seconds = int_value(detail.get("second"))
            return _t("gsuid.renderers.player.calendar.258_19.bc37d2ed", difficulty), _t(
                "gsuid.renderers.challenge.hard.119_25.05854e94", seconds
            )
    if act.get("type") == "ActTypeHardChallengeSub" and not act.get("is_finished"):
        return _t(
            "gsuid.renderers.player.calendar.260_15.c8ba58fe",
            int_value(act.get("y")) - int_value(act.get("x")),
        ), None
    if act.get("type") == "ActTypeExplore":
        detail = act.get("explore_detail")
        if isinstance(detail, Mapping):
            return f"{int_value(detail.get('explore_percent'))}%", None
    return _t("gsuid.renderers.daily.text.161_13.e99b48a2") if act.get("is_finished") else _t(
        "gsuid.renderers.daily.text.247_11.b61b08ae"
    ), None


def _duration_text(seconds: int) -> str:
    days = max(seconds, 0) // (24 * 3600)
    hours = (max(seconds, 0) % (24 * 3600)) // 3600
    minutes = (max(seconds, 0) % 3600) // 60
    return _t("gsuid.renderers.player.calendar.272_11.64b9941b", days, hours, minutes)


def _append_url(urls: list[str], value: object) -> None:
    url = text_value(value)
    if url and url not in urls:
        urls.append(url)
