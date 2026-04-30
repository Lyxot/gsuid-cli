from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from functools import lru_cache
from io import BytesIO
from urllib.parse import quote

from PIL import Image, ImageChops, ImageDraw

from gsuid_cli.renderers.common import (
    asset_path,
    crop_center,
    font,
    int_value,
    open_rgba,
    png_bytes,
    text_value,
    v4_background,
)
from gsuid_cli.renderers.panel_metrics import panel_reference_metrics

TEXTURE = asset_path("panel", "textures")
DATA = asset_path("panel", "data")
RANK_TEXTURE = asset_path("rank", "textures")
THEATER_TEXTURE = asset_path("challenge", "theater", "textures")
HARD_TEXTURE = asset_path("challenge", "hard", "textures")
GRADUATION_TEXTURE = TEXTURE / "graduation"
FETTER_TEXTURE = TEXTURE / "fetter"
GENSHINUID_RESOURCE_BASE = "https://example.test/GenshinUID/resource"
ENKA_UI_BASE = "https://enka.network/ui"

WIDTH = 950
HEIGHT = 1850
ARTIFACT_POSITIONS = {
    "EQUIP_BRACER": (13, 1087),
    "EQUIP_NECKLACE": (323, 1087),
    "EQUIP_SHOES": (633, 1087),
    "EQUIP_RING": (13, 1447),
    "EQUIP_DRESS": (323, 1447),
}
ELEMENT_COLORS = {
    "Anemo": (0, 145, 137),
    "Cryo": (4, 126, 152),
    "Dendro": (28, 145, 0),
    "Electro": (133, 12, 159),
    "Geo": (147, 112, 3),
    "Hydro": (51, 73, 162),
    "Pyro": (136, 28, 33),
}
ELEMENT_DAMAGE_PROP = {
    "Anemo": "44",
    "Cryo": "46",
    "Dendro": "43",
    "Electro": "41",
    "Geo": "45",
    "Hydro": "42",
    "Pyro": "40",
}
FIXED_VALUE_PROPS = {
    "FIGHT_PROP_ATTACK",
    "FIGHT_PROP_BASE_ATTACK",
    "FIGHT_PROP_DEFENSE",
    "FIGHT_PROP_BASE_DEFENSE",
    "FIGHT_PROP_HP",
    "FIGHT_PROP_BASE_HP",
    "FIGHT_PROP_ELEMENT_MASTERY",
}
PERCENT_PROPS = {
    "FIGHT_PROP_ATTACK_PERCENT",
    "FIGHT_PROP_DEFENSE_PERCENT",
    "FIGHT_PROP_HP_PERCENT",
    "FIGHT_PROP_CRITICAL",
    "FIGHT_PROP_CRITICAL_HURT",
    "FIGHT_PROP_CHARGE_EFFICIENCY",
    "FIGHT_PROP_HEAL_ADD",
    "FIGHT_PROP_FIRE_ADD_HURT",
    "FIGHT_PROP_ELEC_ADD_HURT",
    "FIGHT_PROP_WATER_ADD_HURT",
    "FIGHT_PROP_GRASS_ADD_HURT",
    "FIGHT_PROP_WIND_ADD_HURT",
    "FIGHT_PROP_ROCK_ADD_HURT",
    "FIGHT_PROP_ICE_ADD_HURT",
    "FIGHT_PROP_PHYSICAL_ADD_HURT",
}
PROP_LABEL_FALLBACKS = {
    "FIGHT_PROP_ATTACK": "攻击力",
    "FIGHT_PROP_ATTACK_PERCENT": "百分比攻击力",
    "FIGHT_PROP_BASE_ATTACK": "基础攻击力",
    "FIGHT_PROP_DEFENSE": "防御力",
    "FIGHT_PROP_DEFENSE_PERCENT": "百分比防御力",
    "FIGHT_PROP_BASE_DEFENSE": "基础防御力",
    "FIGHT_PROP_HP": "血量",
    "FIGHT_PROP_HP_PERCENT": "百分比血量",
    "FIGHT_PROP_BASE_HP": "基础血量",
    "FIGHT_PROP_ELEMENT_MASTERY": "元素精通",
    "FIGHT_PROP_CRITICAL": "暴击率",
    "FIGHT_PROP_CRITICAL_HURT": "暴击伤害",
    "FIGHT_PROP_CHARGE_EFFICIENCY": "元素充能效率",
    "FIGHT_PROP_HEAL_ADD": "治疗加成",
    "FIGHT_PROP_FIRE_ADD_HURT": "火元素伤害加成",
    "FIGHT_PROP_ELEC_ADD_HURT": "雷元素伤害加成",
    "FIGHT_PROP_WATER_ADD_HURT": "水元素伤害加成",
    "FIGHT_PROP_GRASS_ADD_HURT": "草元素伤害加成",
    "FIGHT_PROP_WIND_ADD_HURT": "风元素伤害加成",
    "FIGHT_PROP_ROCK_ADD_HURT": "岩元素伤害加成",
    "FIGHT_PROP_ICE_ADD_HURT": "冰元素伤害加成",
    "FIGHT_PROP_PHYSICAL_ADD_HURT": "物理伤害加成",
}
FOOTER_TEXT = "Created by gsuid-cli & Render style/assets by GenshinUID & Data by Enka.network"


def render_panel_show_card(
    *,
    uid: str,
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
    cached_at: str,
    asset_images: Mapping[str, bytes] | None = None,
) -> bytes:
    """Render a GenshinUID-style Enka character panel card."""
    asset_images = asset_images or {}
    element = _avatar_element(avatar, panel)
    character = _character_image(avatar, panel, asset_images)
    metrics = panel_reference_metrics(avatar, panel)
    damage_rows = _metric_rows(metrics.get("damage_rows"))
    image_height = HEIGHT + (len(damage_rows) + 2) * 40 if damage_rows else HEIGHT
    image = _panel_background(element, character, image_height)
    image.paste(character, (0, 0), character)

    base = _base_info_layer(uid, avatar, panel, cached_at, asset_images)
    image.paste(base, (0, 0), base)
    info2 = open_rgba(TEXTURE / "char_info_2.png")
    image.paste(info2, (0, 1085), info2)

    artifacts = _artifact_pairs(avatar, panel)
    artifact_scores = _metric_scores(metrics.get("artifact_effective_scores"))
    for raw_artifact, normalized in artifacts:
        item_id = str(normalized.get("item_id") or raw_artifact.get("itemId") or "")
        card = _artifact_card(
            raw_artifact,
            normalized,
            asset_images,
            effective_score=artifact_scores.get(item_id, 0.0),
        )
        slot = _artifact_slot(raw_artifact, normalized)
        position = ARTIFACT_POSITIONS.get(slot)
        if position is not None:
            image.paste(card, position, card)

    if damage_rows:
        damage_table = _damage_table(damage_rows)
        image.paste(damage_table, (0, 1820), damage_table)

    draw = ImageDraw.Draw(image)
    _draw_reference_scores(draw, metrics)
    draw.text((475, image.size[1] - 35), FOOTER_TEXT, (255, 255, 255), font(18), "mm")

    black = Image.new("RGBA", image.size, (0, 0, 0, 255))
    image = Image.alpha_composite(black, image)
    return png_bytes(image, rgb=True)


def panel_asset_urls(avatar: Mapping[str, object], panel: Mapping[str, object]) -> list[str]:
    urls: list[str] = []
    _append_url(urls, character_full_image_url(avatar, panel))
    _append_url(urls, character_icon_url(avatar, panel))

    weapon = _weapon_equip(avatar)
    weapon_name = _weapon_name(weapon, panel)
    _append_url(urls, _weapon_resource_url(weapon_name))
    _append_url(urls, _enka_icon_url(_flat_icon(weapon)))

    for raw_artifact, _normalized in _artifact_pairs(avatar, panel):
        _append_url(urls, _enka_icon_url(_flat_icon(raw_artifact)))

    for skill in _skill_entries(avatar):
        _append_url(urls, skill.get("icon_url"))
    for icon_url in _talent_icon_urls(avatar):
        _append_url(urls, icon_url)
    return urls


def panel_artifacts_asset_urls(
    avatars: Sequence[Mapping[str, object]],
    panels: Sequence[Mapping[str, object]],
    *,
    page: int,
    page_size: int = 20,
) -> list[str]:
    urls: list[str] = []
    for item in _artifact_library_items(avatars, panels)[(page - 1) * page_size : page * page_size]:
        artifact = item["artifact"]
        if isinstance(artifact, Mapping):
            _append_url(urls, _enka_icon_url(_flat_icon(artifact)))

    avatar, panel = _first_avatar_panel(avatars, panels)
    if avatar and panel:
        _append_url(urls, character_icon_url(avatar, panel))
        _append_url(urls, character_full_image_url(avatar, panel))
    return urls


def panel_showcase_asset_urls(
    avatars: Sequence[Mapping[str, object]],
    panels: Sequence[Mapping[str, object]],
    *,
    limit: int = 8,
) -> list[str]:
    urls: list[str] = []
    for avatar, panel in _showcase_items(avatars, panels, limit=limit):
        for url in panel_asset_urls(avatar, panel):
            _append_url(urls, url)
    return urls


def panel_graduation_asset_urls(
    avatars: Sequence[Mapping[str, object]],
    panels: Sequence[Mapping[str, object]],
) -> list[str]:
    urls: list[str] = []
    for avatar, panel in zip(avatars, panels, strict=False):
        _append_url(urls, character_icon_url(avatar, panel))
        weapon = _weapon_equip(avatar)
        _append_url(urls, _weapon_resource_url(_weapon_name(weapon, panel)))
        _append_url(urls, _enka_icon_url(_flat_icon(weapon)))
    return urls


def render_panel_graduation(
    *,
    uid: str,
    player: Mapping[str, object],
    avatars: Sequence[Mapping[str, object]],
    panels: Sequence[Mapping[str, object]],
    asset_images: Mapping[str, bytes] | None = None,
) -> bytes:
    """Render GenshinUID-style local panel graduation rows."""
    asset_images = asset_images or {}
    rows = _graduation_rows(avatars, panels)
    mode = 3 if len(rows) > 86 else 2
    columns = mode
    width = 2370 if mode == 3 else 1600
    row_count = (len(rows) + columns - 1) // columns
    height = 750 + 80 + 90 * max(row_count, 1)
    image = v4_background(width, height, black_value=200)

    title = _graduation_title(uid, player, avatars, panels, asset_images, mode=mode)
    image.paste(title, (0, 0), title)
    for index, row in enumerate(rows):
        card = _graduation_card(row, asset_images)
        image.paste(card, (50 + (index % columns) * 750, 750 + 90 * (index // columns)), card)

    draw = ImageDraw.Draw(image)
    div = open_rgba(RANK_TEXTURE / "div.png")
    image.paste(div, (0, height - 61), div)
    draw.text(
        (900 if mode == 3 else 700, height - 30),
        "Created by GenshinUID & Power by GsCore & Design by Wuyi无疑 & Data by Enka.network",
        (200, 200, 200),
        font(18),
        "mm",
    )
    return png_bytes(image, rgb=True)


def render_panel_compare_cards(cards: Sequence[bytes]) -> bytes:
    """Compose GenshinUID panel cards side-by-side for panel compare."""
    images = []
    for content in cards:
        try:
            images.append(Image.open(BytesIO(content)).convert("RGBA"))
        except OSError:
            continue
    if not images:
        return png_bytes(Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255)), rgb=True)

    width = sum(image.size[0] for image in images)
    height = max(image.size[1] for image in images)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    x = 0
    for image in images:
        canvas.paste(image, (x, 0), image)
        x += image.size[0]
    return png_bytes(canvas, rgb=True)


def render_panel_artifacts_library(
    *,
    uid: str,
    avatars: Sequence[Mapping[str, object]],
    panels: Sequence[Mapping[str, object]],
    page: int,
    asset_images: Mapping[str, bytes] | None = None,
) -> bytes:
    """Render the Enka artifact warehouse page used by GenshinUID."""
    asset_images = asset_images or {}
    items = _artifact_library_items(avatars, panels)
    total_pages = (len(items) + 19) // 20 if items else 0
    page_items = items[(page - 1) * 20 : page * 20]

    image = open_rgba(TEXTURE / "artifacts_lib_bg.png")
    profile = _artifact_library_avatar(avatars, panels, asset_images)
    image.paste(profile, (120, 88), profile)

    for index, item in enumerate(page_items):
        artifact = item["artifact"]
        normalized = item["normalized"]
        if not isinstance(artifact, Mapping) or not isinstance(normalized, Mapping):
            continue
        card = _artifact_card(
            artifact,
            normalized,
            asset_images,
            effective_score=_float_value(item.get("effective_score")),
        )
        image.paste(card, (24 + (index % 4) * 310, 570 + (index // 4) * 360), card)

    stats = _artifact_library_stats(items)
    draw = ImageDraw.Draw(image)
    draw.text((268, 498), f"UID {uid}", (255, 255, 255), font(36), "mm")

    xo = 236
    yo = 156
    draw.text((650, 141), str(stats["total"]), (255, 255, 255), font(38), "mm")
    draw.text((650 + xo, 141), str(stats["level_20"]), (255, 255, 255), font(38), "mm")
    draw.text((650 + xo * 2, 141), str(stats["usable"]), (255, 255, 255), font(38), "mm")
    draw.text((650, 141 + yo), f"{stats['avg_effective']:.2f}", (255, 255, 255), font(38), "mm")
    draw.text((650 + xo, 141 + yo), f"{stats['avg_cv']:.2f}", (255, 255, 255), font(38), "mm")
    draw.text(
        (650 + xo * 2, 141 + yo),
        f"{stats['usable_percent']:.2f}%",
        (255, 255, 255),
        font(38),
        "mm",
    )
    draw.text((650, 141 + yo * 2), str(stats["high_effective"]), (255, 255, 255), font(38), "mm")
    draw.text((650 + xo, 141 + yo * 2), str(stats["high_cv"]), (255, 255, 255), font(38), "mm")
    draw.text(
        (650 + xo * 2, 141 + yo * 2),
        f"{stats['high_percent']:.2f}%",
        (255, 255, 255),
        font(38),
        "mm",
    )

    if total_pages and page < total_pages:
        notice = f"可用 panel artifacts --page {page + 1} 查看第{page + 1}页"
    else:
        notice = "暂无更多页数"
    draw.text(
        (650, 2420),
        f"当前 {page} / {total_pages} 页, {notice}",
        (210, 210, 210),
        font(25),
        "mm",
    )

    black = Image.new("RGBA", image.size, (0, 0, 0, 255))
    return png_bytes(Image.alpha_composite(black, image), rgb=True)


def render_panel_showcase(
    *,
    uid: str,
    player: Mapping[str, object],
    avatars: Sequence[Mapping[str, object]],
    panels: Sequence[Mapping[str, object]],
    asset_images: Mapping[str, bytes] | None = None,
    limit: int = 8,
) -> bytes:
    """Render the cached character showcase summary."""
    asset_images = asset_images or {}
    items = _showcase_items(avatars, panels, limit=limit)
    if not items:
        return png_bytes(v4_background(WIDTH, 200, black_value=180), rgb=True)

    columns = min(len(items), 4)
    rows = (len(items) - 1) // 4 + 1
    image = v4_background(columns * WIDTH + 50, rows * 1280 + 50, black_value=190)
    for index, (avatar, panel) in enumerate(items):
        card = _showcase_card(avatar, panel, asset_images)
        image.paste(card, (25 + (index % 4) * WIDTH, 25 + (index // 4) * 1280), card)

    draw = ImageDraw.Draw(image)
    nickname = text_value(player.get("nickname")) or "旅行者"
    draw.text((40, image.size[1] - 30), f"{nickname} | UID: {uid}", (255, 255, 255), font(28), "lm")
    return png_bytes(image, rgb=True)


def character_full_image_url(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> str | None:
    name = _avatar_name(avatar, panel)
    if not name:
        return None
    return f"{GENSHINUID_RESOURCE_BASE}/gacha_img/{quote(name, safe='')}.png"


def character_icon_url(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> str | None:
    avatar_id = _avatar_id(avatar, panel)
    if not avatar_id:
        return None
    return f"{GENSHINUID_RESOURCE_BASE}/chars/{quote(avatar_id, safe='')}.png"


def _artifact_library_items(
    avatars: Sequence[Mapping[str, object]],
    panels: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for avatar, panel in zip(avatars, panels, strict=False):
        metrics = panel_reference_metrics(avatar, panel)
        effective_scores = _metric_scores(metrics.get("artifact_effective_scores"))
        for artifact, normalized in _artifact_pairs(avatar, panel):
            item_id = str(normalized.get("item_id") or artifact.get("itemId") or "")
            substats = _artifact_substats(artifact, normalized)
            effective_score = effective_scores.get(item_id, 0.0)
            cv_score = _artifact_cv_score(normalized, substats)
            items.append(
                {
                    "avatar": avatar,
                    "panel": panel,
                    "artifact": artifact,
                    "normalized": normalized,
                    "effective_score": effective_score,
                    "cv_score": cv_score,
                    "level": _artifact_level(artifact, normalized),
                }
            )
    items.sort(key=lambda item: _float_value(item.get("cv_score")), reverse=True)
    return items


def _artifact_library_stats(items: Sequence[Mapping[str, object]]) -> dict[str, object]:
    total = len(items)
    if not total:
        return {
            "total": 0,
            "level_20": 0,
            "usable": 0,
            "avg_effective": 0.0,
            "avg_cv": 0.0,
            "usable_percent": 0.0,
            "high_effective": 0,
            "high_cv": 0,
            "high_percent": 0.0,
        }

    effective_values = [_float_value(item.get("effective_score")) for item in items]
    cv_values = [_float_value(item.get("cv_score")) for item in items]
    level_20 = sum(1 for item in items if int_value(item.get("level")) >= 20)
    usable = sum(
        1
        for effective, cv in zip(effective_values, cv_values, strict=False)
        if effective >= 5.2 or cv >= 35.5
    )
    high_effective = sum(1 for effective in effective_values if effective >= 6.5)
    high_cv = sum(1 for cv in cv_values if cv >= 44.5)
    return {
        "total": total,
        "level_20": level_20,
        "usable": usable,
        "avg_effective": sum(effective_values) / total,
        "avg_cv": sum(cv_values) / total,
        "usable_percent": usable * 100 / total,
        "high_effective": high_effective,
        "high_cv": high_cv,
        "high_percent": high_cv * 100 / total,
    }


def _artifact_library_avatar(
    avatars: Sequence[Mapping[str, object]],
    panels: Sequence[Mapping[str, object]],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    avatar, panel = _first_avatar_panel(avatars, panels)
    source = None
    if avatar and panel:
        source = _first_remote_image(
            [character_icon_url(avatar, panel), character_full_image_url(avatar, panel)],
            asset_images,
        )
    if source is None:
        source = _placeholder_square("UID")
    source = crop_center(source, 280, 280)
    mask = Image.new("L", (280, 280), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 279, 279), fill=255)
    result = Image.new("RGBA", (280, 280), (0, 0, 0, 0))
    result.paste(source, (0, 0), mask)
    return result


def _first_avatar_panel(
    avatars: Sequence[Mapping[str, object]],
    panels: Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, object] | None, Mapping[str, object] | None]:
    if not avatars or not panels:
        return None, None
    return avatars[0], panels[0]


def _showcase_items(
    avatars: Sequence[Mapping[str, object]],
    panels: Sequence[Mapping[str, object]],
    *,
    limit: int,
) -> list[tuple[Mapping[str, object], Mapping[str, object]]]:
    items = list(zip(avatars, panels, strict=False))
    items.sort(
        key=lambda item: (
            _float_value(panel_reference_metrics(item[0], item[1]).get("graduation_percent")),
            _float_value(item[1].get("artifact_score")),
        ),
        reverse=True,
    )
    return items[:limit]


def _graduation_rows(
    avatars: Sequence[Mapping[str, object]],
    panels: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for avatar, panel in zip(avatars, panels, strict=False):
        metrics = panel_reference_metrics(avatar, panel)
        value = round(_float_value(metrics.get("effective_stat_count")), 2)
        skills = _graduation_skill_levels(avatar, panel)
        weapon = _weapon_equip(avatar)
        weapon_name = _weapon_name(weapon, panel) or ""
        weapon_star = _weapon_rank(weapon, panel)
        weapon_affix = _weapon_affix(weapon)
        talent_num = _talent_count(avatar, panel)
        char_star = _avatar_star(avatar, panel)
        score = (
            sum(skills)
            + talent_num * max(char_star - 3, 0)
            + weapon_affix * max(weapon_star - 3, 0)
            + value
        )
        rows.append(
            {
                "avatar": avatar,
                "panel": panel,
                "avatar_id": _avatar_id(avatar, panel),
                "name": _avatar_name(avatar, panel) or "",
                "char_star": char_star,
                "fetter": _friendship(avatar, panel),
                "skills": skills,
                "talent_num": talent_num,
                "value": value,
                "score": score,
                "weapon_name": weapon_name,
                "weapon_level": _weapon_level(weapon, panel),
                "weapon_affix": weapon_affix,
                "weapon_star": weapon_star,
                "weapon_url": _weapon_resource_url(weapon_name)
                or _enka_icon_url(_flat_icon(weapon))
                or "",
            }
        )
    rows.sort(key=lambda row: _float_value(row.get("score")), reverse=True)
    return rows


def _graduation_title(
    uid: str,
    player: Mapping[str, object],
    avatars: Sequence[Mapping[str, object]],
    panels: Sequence[Mapping[str, object]],
    asset_images: Mapping[str, bytes],
    *,
    mode: int,
) -> Image.Image:
    width = 2370 if mode == 3 else 1600
    title = Image.new("RGBA", (width, 750), (0, 0, 0, 0))
    title_bg = open_rgba(RANK_TEXTURE / f"title_{mode}.png")
    title_fg = open_rgba(RANK_TEXTURE / f"title_fg_{mode}.png")
    profile = _graduation_profile_avatar(avatars, panels, asset_images)
    title_bg.paste(profile, (117, 328) if mode == 3 else (88, 328), profile)
    title_bg.paste(title_fg, (0, 0), title_fg)

    draw = ImageDraw.Draw(title_bg)
    nickname = text_value(player.get("nickname")) or "旅行者"
    draw.text((360, 428) if mode == 3 else (331, 428), nickname, "white", font(40), "lm")
    draw.text(
        (456, 478) if mode == 3 else (427, 478),
        f"UID {uid}",
        (207, 207, 207),
        font(30),
        "mm",
    )
    _draw_graduation_title_badges(title_bg, player, mode=mode)
    title.paste(title_bg, (0, 0), title_bg)

    title_bar = open_rgba(RANK_TEXTURE / f"title_bar_{mode}.png")
    title_bar_draw = ImageDraw.Draw(title_bar)
    stats = _graduation_title_stats(avatars, panels, mode=mode)
    start_x, offset = (181, 201.8) if mode == 3 else (142, 187.4)
    for index, value in enumerate(stats):
        title_bar_draw.text(
            (int(start_x + index * offset), 52), str(value), "white", font(38), "mm"
        )
    title.paste(title_bar, (0, 600), title_bar)
    return title


def _draw_graduation_title_badges(
    title: Image.Image, player: Mapping[str, object], *, mode: int
) -> None:
    draw = ImageDraw.Draw(title)
    if mode == 3:
        theater_pos = (1882, 438)
        theater_text = (2033, 462)
        hard_pos = (2057, 358)
        hard_text = (2208, 383)
        abyss_text = (2208, 462)
    else:
        theater_pos = (1151, 438)
        theater_text = (1301, 462)
        hard_pos = (1326, 358)
        hard_text = (1476, 383)
        abyss_text = (1476, 462)
    theater_icon = _graduation_theater_icon(player)
    title.paste(theater_icon, theater_pos, theater_icon)
    hard_icon = _graduation_hard_icon(player)
    title.paste(hard_icon, hard_pos, hard_icon)
    draw.text(abyss_text, _graduation_abyss_label(player), "white", font(28), "mm")
    draw.text(hard_text, _graduation_hard_label(player), "white", font(28), "mm")
    draw.text(theater_text, _graduation_theater_label(player), "white", font(28), "mm")


def _graduation_theater_icon(player: Mapping[str, object]) -> Image.Image:
    theater = _dict(player.get("theater"))
    difficulty = int_value(theater.get("difficulty_id"))
    max_round = int_value(theater.get("max_round_id"))
    tarot = int_value(theater.get("tarot_finished_cnt"))
    if difficulty == 5:
        name = "moon_yes.png" if max_round >= 10 and tarot >= 2 else "moon_no.png"
    elif difficulty == 4:
        name = "super_yes.png" if max_round >= 10 else "super_no.png"
    elif difficulty == 3:
        name = "gold_yes.png" if max_round >= 8 else "gold_no.png"
    else:
        name = "gold_no.png"
    return open_rgba(THEATER_TEXTURE / name)


def _graduation_hard_icon(player: Mapping[str, object]) -> Image.Image:
    level = max(int_value(player.get("stygian_index"), 3), 3)
    path = HARD_TEXTURE / f"medal_{min(level, 6)}.png"
    if not path.exists():
        path = HARD_TEXTURE / "medal_3.png"
    return open_rgba(path).resize((52, 52), Image.Resampling.LANCZOS)


def _graduation_abyss_label(player: Mapping[str, object]) -> str:
    floor = int_value(player.get("abyss_floor"))
    chamber = int_value(player.get("abyss_chamber"))
    return f"深渊{floor}-{chamber}" if floor and chamber else "深渊--"


def _graduation_hard_label(player: Mapping[str, object]) -> str:
    return text_value(player.get("hard_name")) or "断玉之役"


def _graduation_theater_label(player: Mapping[str, object]) -> str:
    theater = _dict(player.get("theater"))
    return f"第{int_value(theater.get('max_round_id'))}幕"


def _graduation_title_stats(
    avatars: Sequence[Mapping[str, object]],
    panels: Sequence[Mapping[str, object]],
    *,
    mode: int,
) -> list[object]:
    rows = _graduation_rows(avatars, panels)
    star5 = [row for row in rows if int_value(row.get("char_star")) == 5]
    star4 = [row for row in rows if int_value(row.get("char_star")) == 4]
    full_star5 = sum(1 for row in star5 if _panel_constellation(row) >= 6)
    full_star4 = sum(1 for row in star4 if _panel_constellation(row) >= 6)
    star5_weapon = [row for row in rows if int_value(row.get("weapon_star")) == 5]
    star4_weapon = [row for row in rows if int_value(row.get("weapon_star")) == 4]
    full_star5_weapon = sum(1 for row in star5_weapon if int_value(row.get("weapon_affix")) >= 5)
    full_star4_weapon = sum(1 for row in star4_weapon if int_value(row.get("weapon_affix")) >= 5)
    crown_cost = sum(
        1 for row in rows for skill in _sequence(row.get("skills")) if int_value(skill) >= 10
    )
    full_fetter = sum(1 for row in rows if int_value(row.get("fetter")) >= 10)
    high_score = sum(1 for row in rows if _float_value(row.get("value")) >= 27)
    useful = sum(1 for row in rows if _graduation_row_done(row))
    total_star5 = _total_avatar_star("5")
    total_star4 = _total_avatar_star("4")
    total_star5_weapon = _total_weapon_star("5")

    if mode == 3:
        return [
            f"{crown_cost}/{crown_cost}",
            f"{full_fetter}/{len(rows)}",
            f"{full_star5}/{len(star5)}",
            f"{full_star4}/{len(star4)}",
            f"{len(star5)}/{total_star5}",
            f"{len(star4)}/{total_star4}",
            f"{len(star5_weapon)}/{total_star5_weapon}",
            f"{full_star4_weapon}/{len(star4_weapon)}",
            f"{full_star5_weapon}/{len(star5_weapon)}",
            high_score,
            useful,
        ]
    return [
        f"{crown_cost}/{crown_cost}",
        f"{full_fetter}/{len(rows)}",
        f"{full_star4}/{len(star4)}",
        f"{len(star5)}/{total_star5}",
        f"{len(star4)}/{total_star4}",
        f"{len(star5_weapon)}/{total_star5_weapon}",
        high_score,
        useful,
    ]


def _graduation_profile_avatar(
    avatars: Sequence[Mapping[str, object]],
    panels: Sequence[Mapping[str, object]],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    avatar, panel = _first_avatar_panel(avatars, panels)
    source = None
    if avatar and panel:
        source = _first_remote_image([character_icon_url(avatar, panel)], asset_images)
    if source is None:
        source = _placeholder_square("UID")
    return _circle_crop(source, 180)


def _graduation_card(row: Mapping[str, object], asset_images: Mapping[str, bytes]) -> Image.Image:
    card = open_rgba(
        GRADUATION_TEXTURE / ("char_rank_yes.png" if _graduation_row_done(row) else "char_rank.png")
    )
    avatar = row.get("avatar")
    panel = row.get("panel")
    avatar_map = avatar if isinstance(avatar, Mapping) else {}
    panel_map = panel if isinstance(panel, Mapping) else {}
    char_icon = _first_remote_image([character_icon_url(avatar_map, panel_map)], asset_images)
    if char_icon is None:
        char_icon = _placeholder_square(text_value(row.get("name")) or "?")
    framed_character = _graduation_quality_icon(char_icon, int_value(row.get("char_star"), 5))
    card.paste(framed_character, (8, 0), framed_character)

    weapon_icon = _remote_image(text_value(row.get("weapon_url")), asset_images)
    if weapon_icon is None:
        weapon_icon = _placeholder_square(text_value(row.get("weapon_name")) or "?")
    framed_weapon = _graduation_quality_icon(weapon_icon, int_value(row.get("weapon_star"), 5))
    card.paste(framed_weapon, (472, 0), framed_weapon)

    draw = ImageDraw.Draw(card)
    draw.text(
        (98, 31), _truncate(text_value(row.get("name")) or "未知", 4), "white", font(28), "lm"
    )
    skills = [int_value(value) for value in _sequence(row.get("skills"))][:3]
    while len(skills) < 3:
        skills.append(0)
    skill_mask = open_rgba(GRADUATION_TEXTURE / "skill_mask.png")
    for index, level in enumerate(skills):
        x = 99 + index * 38
        color = _graduation_level_color("skill", level)
        color_img = Image.new("RGBA", (35, 28), color)
        card.paste(color_img, (x, 48), skill_mask)
        draw.text((x + 17, 62), str(level), (245, 245, 245), font(26), "mm")

    value = _float_value(row.get("value"))
    value_mask = open_rgba(GRADUATION_TEXTURE / "value_mask.png")
    value_img = Image.new("RGBA", (77, 33), _graduation_level_color("equip", value))
    card.paste(value_img, (225, 28), value_mask)
    draw.text((263, 45), f"{_number_text(value, 2)[:4]}条", (245, 245, 245), font(24), "mm")

    fetter_pic = _graduation_fetter_icon(int_value(row.get("fetter"))).resize(
        (77, 33), Image.Resampling.LANCZOS
    )
    card.paste(fetter_pic, (308, 28), fetter_pic)
    talent_pic = _graduation_talent_icon(int_value(row.get("talent_num"))).resize(
        (66, 33), Image.Resampling.LANCZOS
    )
    card.paste(talent_pic, (391, 28), talent_pic)

    affix_pic = open_rgba(
        TEXTURE
        / "weapon_affix"
        / f"weapon_affix_{min(max(int_value(row.get('weapon_affix'), 1), 1), 5)}.png"
    )
    card.paste(affix_pic, (561, 47), affix_pic)
    draw.text((635, 61), f"Lv.{int_value(row.get('weapon_level'))}", "white", font(26), "lm")
    draw.text(
        (559, 27),
        _truncate(text_value(row.get("weapon_name")) or "未知武器", 7),
        "white",
        font(26),
        "lm",
    )
    return card


def _graduation_row_done(row: Mapping[str, object]) -> bool:
    return _float_value(row.get("value")) >= 24 and any(
        int_value(skill) >= 8 for skill in _sequence(row.get("skills"))
    )


def _graduation_skill_levels(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> list[int]:
    skills = [int_value(skill.get("level")) for skill in _skill_entries(avatar)]
    if not skills:
        raw = panel.get("skill_levels")
        if isinstance(raw, Mapping):
            skills = [int_value(value) for value in raw.values()]
    if len(skills) > 3:
        skills = [skills[0], skills[1], skills[-1]]
    return skills[:3]


def _graduation_quality_icon(image: Image.Image, star: int) -> Image.Image:
    star = min(max(star, 1), 5)
    bg = open_rgba(RANK_TEXTURE / f"star_{star}.png").resize((90, 90), Image.Resampling.LANCZOS)
    ring = open_rgba(RANK_TEXTURE / "ring.png").resize((90, 90), Image.Resampling.LANCZOS)
    mask = open_rgba(RANK_TEXTURE / "ring_mask.png").resize((90, 90), Image.Resampling.LANCZOS)
    inner = Image.new("RGBA", (90, 90), (0, 0, 0, 0))
    inner.paste(crop_center(image, 90, 90), (0, 0), mask)
    bg.paste(inner, (0, 0), inner)
    bg.paste(ring, (0, 0), ring)
    return bg


def _graduation_fetter_icon(level: int) -> Image.Image:
    path = FETTER_TEXTURE / f"fetter_{min(max(level, 0), 10)}.png"
    if path.exists():
        return open_rgba(path)
    return _graduation_badge(str(level), (80, 50, 95))


def _graduation_talent_icon(level: int) -> Image.Image:
    path = RANK_TEXTURE / f"talent_{min(max(level, 0), 6)}.png"
    if path.exists():
        return open_rgba(path)
    return _graduation_badge(str(level), (80, 50, 95))


def _graduation_badge(text: str, color: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGBA", (77, 33), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, 76, 32), 8, color)
    draw.text((38, 16), text, "white", font(22), "mm")
    return image


def _graduation_level_color(kind: str, value: object) -> tuple[int, int, int]:
    number = _float_value(value)
    if kind == "skill":
        thresholds = [(10, 5), (7, 4), (5, 3), (3, 2), (0, 1)]
    elif kind == "equip":
        thresholds = [(33, 5), (27, 4), (21, 3), (15, 2), (0, 1)]
    else:
        thresholds = [(99, 5), (90, 4), (85, 3), (70, 2), (0, 1)]
    colors = {
        5: (230, 0, 0),
        4: (203, 131, 21),
        3: (97, 17, 156),
        2: (17, 105, 156),
        1: (94, 96, 95),
    }
    for threshold, level in thresholds:
        if number >= threshold:
            return colors[level]
    return colors[1]


def _circle_crop(image: Image.Image, size: int) -> Image.Image:
    image = crop_center(image, size, size)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(image, (0, 0), mask)
    return result


def _talent_count(avatar: Mapping[str, object], panel: Mapping[str, object]) -> int:
    talents = avatar.get("talentIdList")
    if isinstance(talents, list):
        return min(max(len(talents), 0), 6)
    return min(max(int_value(panel.get("talent_num")), 0), 6)


def _avatar_star(avatar: Mapping[str, object], panel: Mapping[str, object]) -> int:
    mapped = _map("avatarId2Star_mapping_6.5.0.json").get(_avatar_id(avatar, panel))
    return min(max(int_value(mapped, 5), 1), 5)


def _panel_constellation(row: Mapping[str, object]) -> int:
    panel = row.get("panel")
    if isinstance(panel, Mapping):
        return int_value(panel.get("constellation"))
    return 0


def _total_avatar_star(star: str) -> int:
    return sum(
        1 for value in _map("avatarId2Star_mapping_6.5.0.json").values() if str(value) == star
    )


def _total_weapon_star(star: str) -> int:
    weapon_list = _map("weaponList_6.5.0.json")
    count = 0
    for value in weapon_list.values():
        if isinstance(value, Mapping) and str(value.get("rank")) == star:
            count += 1
    return count


def _showcase_card(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    overlay = open_rgba(TEXTURE / "info_bg_a.png")
    color = ELEMENT_COLORS.get(_avatar_element(avatar, panel), (65, 65, 72))
    color_temp = Image.new("RGBA", overlay.size)
    color_temp.paste(Image.new("RGBA", overlay.size, color), (0, 0), overlay)
    image = ImageChops.overlay(color_temp, overlay)

    for artifact, normalized in _artifact_pairs(avatar, panel):
        slot = _artifact_slot(artifact, normalized)
        position = _compact_artifact_position(slot)
        if position is None:
            continue
        metrics = panel_reference_metrics(avatar, panel)
        scores = _metric_scores(metrics.get("artifact_effective_scores"))
        item_id = str(normalized.get("item_id") or artifact.get("itemId") or "")
        card = _compact_artifact_card(
            artifact,
            normalized,
            asset_images,
            effective_score=scores.get(item_id, 0.0),
        )
        image.paste(card, position, card)

    attr = _showcase_attr_layer(avatar, panel)
    image.paste(attr, (427, 13), attr)
    weapon = _showcase_weapon_layer(avatar, panel, asset_images)
    image.paste(weapon, (-20, 52), weapon)
    character = _showcase_character_layer(avatar, panel, asset_images)
    image.paste(character, (-20, 260), character)

    metrics = panel_reference_metrics(avatar, panel)
    percent = _float_value(metrics.get("graduation_percent"))
    percent_text = "暂无匹配" if percent == 0 else f"{_number_text(percent, 2)}%"
    effective_count = _float_value(metrics.get("effective_stat_count"))
    draw = ImageDraw.Draw(image)
    draw.rectangle((324, 256, 423, 293), (0, 105, 255))
    draw.rectangle((432, 256, 571, 293), (255, 0, 0))
    draw.text((374, 276), f"{effective_count:.2f}", (255, 255, 255), font(36), "mm")
    draw.text((504, 276), percent_text, (255, 255, 255), font(36), "mm")
    return image


def _compact_artifact_position(slot: str) -> tuple[int, int] | None:
    return {
        "EQUIP_BRACER": (490, 537),
        "EQUIP_NECKLACE": (490, 673),
        "EQUIP_SHOES": (490, 809),
        "EQUIP_RING": (490, 945),
        "EQUIP_DRESS": (490, 1081),
    }.get(slot)


def _compact_artifact_card(
    raw_artifact: Mapping[str, object],
    normalized: Mapping[str, object],
    asset_images: Mapping[str, bytes],
    *,
    effective_score: float,
) -> Image.Image:
    card = Image.new("RGBA", (480, 136), (0, 0, 0, 0))
    icon = _remote_image(_enka_icon_url(_flat_icon(raw_artifact)), asset_images)
    if icon is not None:
        icon = icon.resize((128, 128), Image.Resampling.LANCZOS)
        card.paste(icon, (78, 4), icon)

    star = _star_image(_artifact_rank(raw_artifact, normalized)).resize(
        (96, 24),
        Image.Resampling.LANCZOS,
    )
    card.paste(star, (94, 100), star)
    fg = open_rgba(TEXTURE / "info_arti_fg.png")
    card.paste(fg, (0, 0), fg)

    draw = ImageDraw.Draw(card)
    main_stat = _artifact_main_stat(raw_artifact, normalized)
    main_name = _prop_name(text_value(main_stat.get("mainPropId")) or "")
    main_icon = _prop_icon(main_name, (30, 30))
    if main_icon is not None:
        card.paste(main_icon, (202, 9), main_icon)
    draw.text(
        (168, 90),
        f"+{_artifact_level(raw_artifact, normalized)}",
        (255, 255, 255),
        font(18),
        "mm",
    )
    draw.text((142, 24), _stat_value_text(main_stat), (255, 255, 255), font(22), "mm")

    for index, substat in enumerate(_artifact_substats(raw_artifact, normalized)[:4]):
        prop = text_value(substat.get("appendPropId")) or ""
        sub_name = _prop_name(prop)
        roll_value = _crit_roll_value(prop, substat.get("statValue"))
        bg_color = (0, 0, 0, 100)
        if roll_value >= 3.4:
            bg_color = (158, 39, 39) if roll_value >= 4.5 else (205, 135, 76)
        color = (120, 120, 120) if roll_value == 0 else (255, 255, 255)
        ox = (index % 2) * 113
        oy = (index // 2) * 33
        draw.rounded_rectangle((207 + ox, 55 + oy, 307 + ox, 80 + oy), 4, bg_color)
        sub_icon = _prop_icon(sub_name, (30, 30))
        if sub_icon is not None:
            card.paste(sub_icon, (208 + ox, 51 + oy), sub_icon)
        draw.text((305 + ox, 68 + oy), f"+{_stat_value_text(substat)}", color, font(20), "rm")

    cv_score = _artifact_cv_score(normalized, _artifact_substats(raw_artifact, normalized))
    draw.rounded_rectangle((269, 22, 340, 42), 8, _score_color(effective_score, (8.4, 6.5, 5.2)))
    draw.rounded_rectangle((349, 22, 420, 42), 8, _score_color(cv_score, (50, 45, 39)))
    draw.text((304, 32), f"{effective_score:.2f}条", (255, 255, 255), font(18), "mm")
    draw.text((384, 32), f"{cv_score:.1f}分", (255, 255, 255), font(18), "mm")
    return card


def _showcase_attr_layer(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> Image.Image:
    layer = open_rgba(TEXTURE / "info_attr_fg.png")
    draw = ImageDraw.Draw(layer)
    raw = _fight_props(avatar)
    element = _avatar_element(avatar, panel)
    hp = _raw_float(raw, "2000", _raw_float(raw, "1") + _raw_float(raw, "2"))
    atk = _raw_float(raw, "2001", _raw_float(raw, "4") + _raw_float(raw, "5"))
    defense = _raw_float(raw, "2002", _raw_float(raw, "7") + _raw_float(raw, "8"))
    em = _raw_float(raw, "28")
    crit_rate = _percent(raw, "20")
    crit_dmg = _percent(raw, "22")
    recharge = _percent(raw, "23")
    dmg_bonus = max(_percent(raw, "30"), _percent(raw, ELEMENT_DAMAGE_PROP.get(element, "")))
    values = [
        str(round(hp)),
        str(round(atk)),
        str(round(defense)),
        str(round(em)),
        f"{_number_text(crit_rate, 2)}%",
        f"{_number_text(crit_dmg, 2)}%",
        f"{_number_text(recharge, 1)}%",
        f"{_number_text(dmg_bonus, 1)}%",
    ]
    for index, value in enumerate(values):
        draw.text((347, 105 + index * 55), value, (255, 255, 255), font(28), "rm")
    return layer


def _showcase_weapon_layer(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    layer = Image.new("RGBA", (950, 1280), (0, 0, 0, 0))
    mask = open_rgba(TEXTURE / "info_weapon_bg.png")
    foreground = open_rgba(TEXTURE / "info_weapon_fg.png")
    layer.paste(Image.new("RGBA", mask.size, (0, 0, 0, 90)), (70, 16), mask)

    weapon = _weapon_equip(avatar)
    weapon_name = _weapon_name(weapon, panel) or "未知武器"
    icon = _first_remote_image(
        [_weapon_resource_url(weapon_name), _enka_icon_url(_flat_icon(weapon))],
        asset_images,
    )
    if icon is not None:
        icon = icon.resize((174, 174), Image.Resampling.LANCZOS)
        layer.paste(icon, (124, 35), icon)
    layer.paste(foreground, (0, 0), foreground)
    star = _star_image(_weapon_rank(weapon, panel)).resize((90, 23), Image.Resampling.LANCZOS)
    layer.paste(star, (147, 54), star)

    draw = ImageDraw.Draw(layer)
    draw.text((212, 222), _truncate(weapon_name, 10), (255, 255, 255), font(20), "mm")
    draw.text((394, 71), f"Lv.{_weapon_level(weapon, panel)} / 90", (255, 255, 255), font(20), "mm")
    draw.text((530, 71), f"精{_weapon_affix(weapon)}", (255, 235, 0), font(24), "mm")
    draw.text(
        (386, 117),
        _weapon_base_attack(_weapon_stats(weapon, panel)),
        (255, 235, 0),
        font(24),
        "mm",
    )
    stats = _weapon_stats(weapon, panel)
    if len(stats) >= 2:
        sub_name = _prop_name(text_value(stats[1].get("appendPropId")) or "")
        sub_icon = _prop_icon(sub_name, (30, 30))
        if sub_icon is not None:
            layer.paste(sub_icon, (443, 97), sub_icon)
        draw.text((562, 117), _stat_value_text(stats[1]), (255, 255, 255), font(24), "rm")
    else:
        draw.text((504, 117), "无副词条", (255, 255, 255), font(24), "mm")
    return layer


def _showcase_character_layer(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    foreground = open_rgba(TEXTURE / "info_char_fg.png")
    background = open_rgba(TEXTURE / "info_char_bg.png")
    source = _first_remote_image(
        [character_full_image_url(avatar, panel), character_icon_url(avatar, panel)],
        asset_images,
    )
    if source is None:
        source = _placeholder_square(_avatar_name(avatar, panel) or "?")
    source = source.resize((1776, 1000), Image.Resampling.LANCZOS)
    char_mask = Image.new("RGBA", (700, 1000), (0, 0, 0, 0))
    char_mask.paste(source, (-538, 0), source)
    layer = Image.new("RGBA", (700, 1000), (0, 0, 0, 0))
    layer.paste(char_mask, (0, 0), background)
    layer.paste(foreground, (0, 0), foreground)

    lock = open_rgba(TEXTURE / "icon_lock.png").resize((40, 40), Image.Resampling.LANCZOS)
    talent_urls = _talent_icon_urls(avatar)
    for index in range(6):
        icon = _remote_image(talent_urls[index] if index < len(talent_urls) else None, asset_images)
        if icon is None:
            icon = lock
        else:
            icon = icon.resize((40, 40), Image.Resampling.LANCZOS)
        layer.paste(icon, (134, 297 + index * 69), icon)

    skills = _skill_entries(avatar)
    if len(skills) > 3:
        skills = [skills[0], skills[1], skills[-1]]
    draw = ImageDraw.Draw(layer)
    for index, skill in enumerate(skills[:3]):
        icon = _remote_image(text_value(skill.get("icon_url")), asset_images)
        if icon is not None:
            icon = icon.resize((50, 50), Image.Resampling.LANCZOS)
            layer.paste(icon, (505, 488 + 100 * index), icon)
        level = int_value(skill.get("level"))
        color = (255, 223, 0) if level >= 9 else (255, 255, 255)
        draw.text((530, 558 + 100 * index), str(level), color, font(22), "mm")

    draw.text((350, 885), _avatar_name(avatar, panel) or "未知角色", (255, 233, 0), font(44), "mm")
    draw.text(
        (350, 929),
        f"Lv: {_avatar_level(avatar, panel)} / 90",
        (255, 255, 255),
        font(30),
        "mm",
    )
    return layer


def _prop_icon(name: str, size: tuple[int, int]) -> Image.Image | None:
    path = TEXTURE / "icon" / f"{name}.png"
    if not path.exists():
        return None
    return open_rgba(path).resize(size, Image.Resampling.LANCZOS)


def _placeholder_square(label: str) -> Image.Image:
    image = Image.new("RGBA", (512, 512), (48, 48, 60, 255))
    draw = ImageDraw.Draw(image)
    draw.text((256, 256), label[:3], (255, 255, 255), font(72), "mm")
    return image


def _base_info_layer(
    uid: str,
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
    cached_at: str,
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    layer = open_rgba(TEXTURE / "char_info_1.png")
    draw = ImageDraw.Draw(layer)
    _paste_constellations(layer, avatar, asset_images)
    _paste_skills(layer, avatar, asset_images)
    _draw_weapon(layer, draw, avatar, panel, asset_images)
    _draw_character_stats(draw, avatar, panel)
    _draw_base_labels(draw, uid, avatar, panel, cached_at)
    return layer


def _paste_constellations(
    layer: Image.Image,
    avatar: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> None:
    lock = open_rgba(TEXTURE / "icon_lock.png")
    talent_urls = _talent_icon_urls(avatar)
    for index in range(6):
        icon = _remote_image(talent_urls[index] if index < len(talent_urls) else None, asset_images)
        if icon is None:
            icon = lock
        icon = icon.resize((50, 50), Image.Resampling.LANCZOS)
        layer.paste(icon, (850, 375 + index * 81), icon)


def _paste_skills(
    layer: Image.Image,
    avatar: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> None:
    skill_entries = _skill_entries(avatar)
    if len(skill_entries) > 3:
        skill_entries = [skill_entries[0], skill_entries[1], skill_entries[-1]]
    draw = ImageDraw.Draw(layer)
    for index, skill in enumerate(skill_entries[:3]):
        icon = _remote_image(text_value(skill.get("icon_url")), asset_images)
        if icon is not None:
            icon = icon.resize((50, 50), Image.Resampling.LANCZOS)
            layer.paste(icon, (78, 756 + 101 * index), icon)
        draw.text(
            (103, 820 + 102 * index),
            str(int_value(skill.get("level"))),
            (255, 255, 255),
            font(22),
            "mm",
        )


def _draw_weapon(
    layer: Image.Image,
    draw: ImageDraw.ImageDraw,
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> None:
    weapon = _weapon_equip(avatar)
    weapon_name = _weapon_name(weapon, panel) or "未知武器"
    weapon_level = _weapon_level(weapon, panel)
    affix = _weapon_affix(weapon)
    rank = _weapon_rank(weapon, panel)
    stats = _weapon_stats(weapon, panel)

    icon = _first_remote_image(
        [_weapon_resource_url(weapon_name), _enka_icon_url(_flat_icon(weapon))],
        asset_images,
    )
    if icon is not None:
        icon = icon.resize((174, 174), Image.Resampling.LANCZOS)
        layer.paste(icon, (158, 655), icon)

    star = _star_image(rank)
    layer.paste(star, (402, 825), star)
    affix_icon = open_rgba(TEXTURE / "weapon_affix" / f"weapon_affix_{affix}.png")
    layer.paste(affix_icon, (420 + min(len(weapon_name), 7) * 50, 660), affix_icon)

    draw.text((412, 670), _truncate(weapon_name, 9), (255, 255, 255), font(50), "lm")
    draw.text((420, 710), _weapon_type(weapon), (255, 255, 255), font(20), "lm")
    draw.text((420, 750), "基础攻击力", (255, 255, 255), font(32), "lm")
    draw.text((755, 750), _weapon_base_attack(stats), (255, 255, 255), font(32), "rm")
    if len(stats) >= 2:
        name = _prop_name(text_value(stats[1].get("appendPropId")) or "")
        draw.text((420, 801), _short_prop_name(name), (255, 255, 255), font(32), "lm")
        draw.text((755, 801), _stat_value_text(stats[1]), (255, 255, 255), font(32), "rm")
    else:
        draw.text((420, 801), "该武器无副词条", (255, 255, 255), font(32), "lm")
    draw.text((460, 893), f"Lv.{weapon_level}", (255, 255, 255), font(28), "mm")
    effect = _weapon_effect(weapon, panel) or "无特效。"
    draw.multiline_text((412, 925), effect, (255, 255, 255), font(25), spacing=4)


def _draw_character_stats(
    draw: ImageDraw.ImageDraw,
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> None:
    raw = _fight_props(avatar)
    element = _avatar_element(avatar, panel)
    hp = _raw_float(raw, "2000", _raw_float(raw, "1") + _raw_float(raw, "2"))
    atk = _raw_float(raw, "2001", _raw_float(raw, "4") + _raw_float(raw, "5"))
    defense = _raw_float(raw, "2002", _raw_float(raw, "7") + _raw_float(raw, "8"))
    em = _raw_float(raw, "28")
    crit_rate = _percent(raw, "20")
    crit_dmg = _percent(raw, "22")
    recharge = _percent(raw, "23")
    dmg_bonus = max(_percent(raw, "30"), _percent(raw, ELEMENT_DAMAGE_PROP.get(element, "")))

    values = [
        str(round(hp)),
        str(round(atk)),
        str(round(defense)),
        str(round(em)),
        f"{_number_text(crit_rate, 2)}%",
        f"{_number_text(crit_dmg, 2)}%",
        f"{_number_text(recharge, 1)}%",
        f"{_number_text(dmg_bonus, 1)}%",
    ]
    for index, value in enumerate(values):
        draw.text((785, 174 + index * 53), value, (255, 255, 255), font(28), "rm")

    base_values = [("1", hp), ("4", atk), ("7", defense)]
    for index, (base_key, total) in enumerate(base_values):
        add_value = max(total - _raw_float(raw, base_key), 0)
        draw.text(
            (805, 174 + index * 53),
            f"(+{round(add_value)})",
            (95, 251, 80),
            font(28),
            "lm",
        )


def _draw_base_labels(
    draw: ImageDraw.ImageDraw,
    uid: str,
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
    cached_at: str,
) -> None:
    draw.text((411, 72), _avatar_name(avatar, panel) or "未知角色", (255, 255, 255), font(55), "lm")
    draw.text((411, 122), f"等级{_avatar_level(avatar, panel)}", (255, 255, 255), font(40), "lm")
    draw.text((747, 126), str(_friendship(avatar, panel)), (255, 255, 255), font(28), "lm")
    draw.text((350, 1035), f"UID{uid}", (255, 255, 255), font(24), "rm")
    draw.text(
        (780, 600), f"数据最后更新于{_short_time(cached_at)}", (255, 255, 255), font(22), "rm"
    )


def _artifact_card(
    raw_artifact: Mapping[str, object],
    normalized: Mapping[str, object],
    asset_images: Mapping[str, bytes],
    *,
    effective_score: float,
) -> Image.Image:
    bg = open_rgba(TEXTURE / "char_info_artifacts_bg.png")
    card = open_rgba(TEXTURE / "char_info_artifacts.png")
    icon = _remote_image(_enka_icon_url(_flat_icon(raw_artifact)), asset_images)
    if icon is not None:
        icon = icon.resize((90, 90), Image.Resampling.LANCZOS)
        card.paste(icon, (26, 32), icon)
    star = _star_image(_artifact_rank(raw_artifact, normalized)).resize(
        (90, 23),
        Image.Resampling.LANCZOS,
    )
    card.paste(star, (121, 63), star)

    draw = ImageDraw.Draw(card)
    name = _artifact_name(raw_artifact, normalized)
    draw.text((124, 51), _truncate(name, 8), (255, 255, 255), font(22), "lm")

    main_stat = _artifact_main_stat(raw_artifact, normalized)
    main_name = _prop_name(text_value(main_stat.get("mainPropId")) or "")
    main_value = _stat_value_text(main_stat)
    main_name_short = (
        main_name.replace("百分比", "")
        .replace("伤害加成", "伤加成")
        .replace("元素", "")
        .replace("理", "")
    )
    draw.text((38, 150), main_name_short, (255, 255, 255), font(28), "lm")
    draw.text((271, 150), main_value, (255, 255, 255), font(28), "rm")
    draw.text(
        (232, 75), f"+{_artifact_level(raw_artifact, normalized)}", (255, 255, 255), font(15), "mm"
    )

    substats = _artifact_substats(raw_artifact, normalized)
    for index, substat in enumerate(substats[:4]):
        prop = text_value(substat.get("appendPropId")) or ""
        sub_name = _short_prop_name(_prop_name(prop))
        sub_value = _stat_value_text(substat)
        roll_value = _crit_roll_value(prop, substat.get("statValue"))
        color = (120, 120, 120) if roll_value == 0 else (255, 255, 255)
        if roll_value >= 3.4:
            fill = (158, 39, 39) if roll_value >= 4.5 else (205, 135, 76)
            draw.rounded_rectangle((25, 184 + index * 35, 283, 213 + index * 35), 8, fill)
        draw.text((22, 200 + index * 35), f"·{sub_name}", color, font(25), "lm")
        draw.text((266, 200 + index * 35), sub_value, color, font(25), "rm")

    cv_score = _artifact_cv_score(normalized, substats)
    draw.rounded_rectangle((121, 99, 193, 119), 8, _score_color(effective_score, (8.4, 6.5, 5.2)))
    draw.rounded_rectangle((200, 99, 272, 119), 8, _score_color(cv_score, (50, 45, 39)))
    draw.text((156, 109), f"{effective_score:.2f}条", (255, 255, 255), font(18), "mm")
    draw.text((235, 109), f"{cv_score:.1f}分", (255, 255, 255), font(18), "mm")

    bg.paste(card, (0, 0), card)
    return bg


def _draw_reference_scores(draw: ImageDraw.ImageDraw, metrics: Mapping[str, object]) -> None:
    effective_count = _float_value(metrics.get("effective_stat_count"))
    percent = metrics.get("graduation_percent")
    percent_text = (
        "暂无匹配" if percent in (None, 0, 0.0) else f"{_number_text(_float_value(percent), 2)}%"
    )
    draw.text((783, 1570), _number_text(effective_count, 1), (255, 255, 255), font(50), "mm")
    draw.text(
        (783, 1676),
        text_value(metrics.get("sequence_label")) or "无匹配",
        (255, 255, 255),
        font(18),
        "mm",
    )
    draw.text((783, 1730), percent_text, (255, 255, 255), font(50), "mm")


def _damage_table(rows: Sequence[Mapping[str, object]]) -> Image.Image:
    image = Image.new("RGBA", (WIDTH, 40 * (len(rows) + 1)), (0, 0, 0, 0))
    bar_1 = open_rgba(TEXTURE / "dmgBar_1.png")
    bar_2 = open_rgba(TEXTURE / "dmgBar_2.png")
    for index in range(len(rows) + 1):
        bar = bar_1 if index % 2 == 0 else bar_2
        image.paste(bar, (0, index * 40), bar)
    draw = ImageDraw.Draw(image)
    title_color = (255, 255, 100)
    draw.text((45, 22), "角色动作", title_color, font(28), "lm")
    draw.text((450, 22), "暴击值", title_color, font(28), "lm")
    draw.text((615, 22), "期望值", title_color, font(28), "lm")
    draw.text((780, 22), "普通值", title_color, font(28), "lm")
    for index, row in enumerate(rows):
        y = 22 + (index + 1) * 40
        draw.text((45, y), text_value(row.get("action")) or "", (255, 255, 255), font(28), "lm")
        draw.text((450, y), _rounded_damage(row.get("crit")), (255, 255, 255), font(28), "lm")
        draw.text((615, y), _rounded_damage(row.get("avg")), (255, 255, 255), font(28), "lm")
        draw.text((780, y), _rounded_damage(row.get("normal")), (255, 255, 255), font(28), "lm")
    return image


def _panel_background(element: str, character: Image.Image, height: int) -> Image.Image:
    overlay = _fit_overlay(height)
    color = ELEMENT_COLORS.get(element, (65, 65, 72))
    color_img = Image.new("RGBA", overlay.size, color)
    if character.getbbox() is not None:
        sample = crop_center(character, 1, 1).convert("RGBA").getpixel((0, 0))
        if sample[3] > 0:
            color_img = Image.blend(color_img, Image.new("RGBA", overlay.size, sample[:3]), 0.08)
    return ImageChops.overlay(color_img, overlay)


def _fit_overlay(height: int) -> Image.Image:
    overlay = open_rgba(TEXTURE / "overlay.png")
    if overlay.size == (WIDTH, height):
        return overlay
    overlay_width, overlay_height = overlay.size
    if overlay_height < height:
        new_height = height
        new_width = round(new_height * overlay_width / overlay_height)
    else:
        new_width = WIDTH
        new_height = round(overlay_height * WIDTH / overlay_width)
    resized = overlay.resize((new_width, new_height), Image.Resampling.LANCZOS)
    return resized.crop((0, 0, WIDTH, height))


def _character_image(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    source = _first_remote_image(
        [character_full_image_url(avatar, panel), character_icon_url(avatar, panel)],
        asset_images,
    )
    if source is None:
        source = _placeholder_character(_avatar_name(avatar, panel) or "?")
    char_img = _crop_character(source)
    mask = open_rgba(TEXTURE / "char_info_mask.png")
    result = Image.new("RGBA", (600, 1200))
    result.paste(char_img, (0, 0), mask)
    return result


def _crop_character(image: Image.Image) -> Image.Image:
    width, height = image.size
    target_width, target_height = 800, 1200
    target_ratio = target_width / target_height
    source_ratio = width / height
    if source_ratio > target_ratio:
        resized_height = target_height
        resized_width = round(resized_height * source_ratio)
    else:
        resized_width = target_width
        resized_height = round(resized_width / source_ratio)
    resized = image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
    left = max((resized_width - target_width) // 2 + 200, 0)
    top = max((resized_height - target_height) // 2, 0)
    cropped = resized.crop((left, top, left + 600, top + 1200))
    if cropped.size != (600, 1200):
        return crop_center(resized, 600, 1200)
    return cropped


def _placeholder_character(name: str) -> Image.Image:
    image = Image.new("RGBA", (600, 1200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((90, 250, 510, 670), radius=50, fill=(255, 255, 255, 45))
    draw.text((300, 460), name[:3], (255, 255, 255, 220), font(60), "mm")
    return image


def _remote_image(url: str | None, asset_images: Mapping[str, bytes]) -> Image.Image | None:
    if not url:
        return None
    content = asset_images.get(url)
    if not content:
        return None
    try:
        return Image.open(BytesIO(content)).convert("RGBA")
    except OSError:
        return None


def _first_remote_image(
    urls: Sequence[str | None],
    asset_images: Mapping[str, bytes],
) -> Image.Image | None:
    for url in urls:
        image = _remote_image(url, asset_images)
        if image is not None:
            return image
    return None


def _artifact_pairs(
    avatar: Mapping[str, object],
    panel: Mapping[str, object],
) -> list[tuple[Mapping[str, object], Mapping[str, object]]]:
    normalized_artifacts = panel.get("artifacts")
    normalized_by_id: dict[str, Mapping[str, object]] = {}
    if isinstance(normalized_artifacts, list):
        for artifact in normalized_artifacts:
            if isinstance(artifact, Mapping):
                normalized_by_id[str(artifact.get("item_id") or "")] = artifact
    pairs = []
    for equip in _equip_list(avatar):
        flat = _flat(equip)
        if flat.get("itemType") != "ITEM_RELIQUARY" and not isinstance(
            equip.get("reliquary"), Mapping
        ):
            continue
        normalized = normalized_by_id.get(str(equip.get("itemId") or ""))
        if normalized is None:
            normalized = {}
        pairs.append((equip, normalized))
    return pairs


def _weapon_equip(avatar: Mapping[str, object]) -> Mapping[str, object]:
    for equip in _equip_list(avatar):
        flat = _flat(equip)
        if flat.get("itemType") == "ITEM_WEAPON" or isinstance(equip.get("weapon"), Mapping):
            return equip
    return {}


def _weapon_name(weapon: Mapping[str, object], panel: Mapping[str, object]) -> str | None:
    flat = _flat(weapon)
    mapped = _map("weaponHash2Name_mapping_6.5.0.json").get(str(flat.get("nameTextMapHash") or ""))
    if mapped:
        return str(mapped)
    panel_weapon = panel.get("weapon")
    if isinstance(panel_weapon, Mapping):
        value = text_value(panel_weapon.get("name"))
        if value:
            return value
    return text_value(flat.get("name"))


def _weapon_type(weapon: Mapping[str, object]) -> str:
    mapped = _map("weaponHash2Type_mapping_6.5.0.json").get(
        str(_flat(weapon).get("nameTextMapHash") or "")
    )
    return str(mapped or "")


def _weapon_level(weapon: Mapping[str, object], panel: Mapping[str, object]) -> int:
    raw_weapon = weapon.get("weapon")
    if isinstance(raw_weapon, Mapping):
        level = int_value(raw_weapon.get("level"))
        if level:
            return level
    panel_weapon = panel.get("weapon")
    if isinstance(panel_weapon, Mapping):
        return int_value(panel_weapon.get("level"))
    return 0


def _weapon_affix(weapon: Mapping[str, object]) -> int:
    raw_weapon = weapon.get("weapon")
    if isinstance(raw_weapon, Mapping):
        affix_map = raw_weapon.get("affixMap")
        if isinstance(affix_map, Mapping) and affix_map:
            return min(max(int_value(next(iter(affix_map.values()))) + 1, 1), 5)
    return 1


def _weapon_rank(weapon: Mapping[str, object], panel: Mapping[str, object]) -> int:
    rank = int_value(_flat(weapon).get("rankLevel"))
    if rank:
        return min(max(rank, 1), 5)
    panel_weapon = panel.get("weapon")
    if isinstance(panel_weapon, Mapping):
        return min(max(int_value(panel_weapon.get("rank"), 1), 1), 5)
    return 1


def _weapon_stats(
    weapon: Mapping[str, object],
    panel: Mapping[str, object],
) -> list[Mapping[str, object]]:
    flat_stats = _flat(weapon).get("weaponStats")
    if isinstance(flat_stats, list):
        return [item for item in flat_stats if isinstance(item, Mapping)]
    panel_weapon = panel.get("weapon")
    if isinstance(panel_weapon, Mapping):
        stats = panel_weapon.get("stats")
        if isinstance(stats, list):
            return [item for item in stats if isinstance(item, Mapping)]
    return []


def _weapon_effect(weapon: Mapping[str, object], panel: Mapping[str, object]) -> str:
    panel_weapon = panel.get("weapon")
    if isinstance(panel_weapon, Mapping):
        value = text_value(panel_weapon.get("effect"))
        if value:
            return "\n".join(_wrap_effect_text(value, size=25, limit=455)[:5])
    value = text_value(_flat(weapon).get("weaponEffect"))
    return "\n".join(_wrap_effect_text(value, size=25, limit=455)[:5]) if value else ""


def _wrap_effect_text(value: str, *, size: int, limit: int) -> list[str]:
    lines: list[str] = []
    for raw_line in value.splitlines() or [value]:
        line = ""
        width = 0.0
        for char in raw_line:
            if width >= limit:
                lines.append(line)
                line = char
                width = 0.0
            else:
                line += char
            width += _effect_char_width(char, size)
        if line:
            lines.append(line)
    return lines


def _effect_char_width(char: str, size: int) -> float:
    if char.isdigit():
        return round(size / 10 * 6)
    if char == "/":
        return round(size / 10 * 2.2)
    if char == ".":
        return round(size / 10 * 3)
    if char == "%":
        return round(size / 10 * 9.4)
    return size


def _weapon_base_attack(stats: Sequence[Mapping[str, object]]) -> str:
    if not stats:
        return "0"
    return _number_text(_float_value(stats[0].get("statValue")), 0)


def _artifact_name(
    raw_artifact: Mapping[str, object],
    normalized: Mapping[str, object],
) -> str:
    icon_name = _flat_icon(raw_artifact)
    mapped = _map("icon2Name_mapping_6.5.0.json").get(icon_name or "")
    return str(mapped or normalized.get("name") or "")


def _artifact_slot(
    raw_artifact: Mapping[str, object],
    normalized: Mapping[str, object],
) -> str:
    return str(_flat(raw_artifact).get("equipType") or normalized.get("slot") or "")


def _artifact_rank(
    raw_artifact: Mapping[str, object],
    normalized: Mapping[str, object],
) -> int:
    return min(
        max(int_value(_flat(raw_artifact).get("rankLevel") or normalized.get("rank"), 5), 1), 5
    )


def _artifact_level(
    raw_artifact: Mapping[str, object],
    normalized: Mapping[str, object],
) -> int:
    reliquary = raw_artifact.get("reliquary")
    if isinstance(reliquary, Mapping):
        level = int_value(reliquary.get("level"))
        if level:
            return max(level - 1, 0)
    level = int_value(normalized.get("level"))
    return max(level - 1, 0) if level > 20 else level


def _artifact_main_stat(
    raw_artifact: Mapping[str, object],
    normalized: Mapping[str, object],
) -> Mapping[str, object]:
    raw = _flat(raw_artifact).get("reliquaryMainstat")
    if isinstance(raw, Mapping):
        return raw
    normalized_stat = normalized.get("main_stat")
    return normalized_stat if isinstance(normalized_stat, Mapping) else {}


def _artifact_substats(
    raw_artifact: Mapping[str, object],
    normalized: Mapping[str, object],
) -> list[Mapping[str, object]]:
    raw = _flat(raw_artifact).get("reliquarySubstats")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, Mapping)]
    normalized_stats = normalized.get("substats")
    if isinstance(normalized_stats, list):
        return [item for item in normalized_stats if isinstance(item, Mapping)]
    return []


def _artifact_cv_score(
    normalized: Mapping[str, object],
    substats: Sequence[Mapping[str, object]],
) -> float:
    value = _float_value(normalized.get("score"))
    if value:
        return value
    score = 0.0
    for substat in substats:
        prop = text_value(substat.get("appendPropId")) or ""
        raw_value = _float_value(substat.get("statValue"))
        if prop == "FIGHT_PROP_CRITICAL":
            score += raw_value * 2
        elif prop == "FIGHT_PROP_CRITICAL_HURT":
            score += raw_value
    return score


def _crit_roll_value(prop: str, value: object) -> float:
    raw = _float_value(value)
    if prop == "FIGHT_PROP_CRITICAL":
        return raw * 2 / 7.8
    if prop == "FIGHT_PROP_CRITICAL_HURT":
        return raw / 7.8
    return 0.0


def _score_color(score: float, thresholds: tuple[float, float, float]) -> tuple[int, int, int]:
    if score >= thresholds[0]:
        return (158, 39, 39)
    if score >= thresholds[1]:
        return (205, 135, 76)
    if score >= thresholds[2]:
        return (143, 123, 174)
    return (94, 96, 95)


def _star_image(rank: int) -> Image.Image:
    rank = min(max(rank, 1), 5)
    return open_rgba(TEXTURE / f"s-{rank}.png")


def _skill_entries(avatar: Mapping[str, object]) -> list[dict[str, object]]:
    skill_map = avatar.get("skillLevelMap")
    if not isinstance(skill_map, Mapping):
        return []
    icons = _nested_map("skillId2Name_mapping_6.5.0.json", "Icon")
    entries = []
    for skill_id, level in skill_map.items():
        icon_name = icons.get(str(skill_id))
        entries.append(
            {
                "skill_id": str(skill_id),
                "level": int_value(level),
                "icon_url": _enka_icon_url(str(icon_name)) if icon_name else None,
            }
        )
    return entries


def _talent_icon_urls(avatar: Mapping[str, object]) -> list[str]:
    talents = avatar.get("talentIdList")
    if not isinstance(talents, list):
        return []
    icons = _nested_map("talentId2Name_mapping_6.5.0.json", "Icon")
    urls = []
    for talent in talents:
        icon_name = icons.get(str(talent))
        if icon_name:
            urls.append(_enka_icon_url(str(icon_name)))
    return urls


def _avatar_element(avatar: Mapping[str, object], panel: Mapping[str, object]) -> str:
    mapped = _map("avatarName2Element_mapping_6.5.0.json").get(_avatar_name(avatar, panel) or "")
    return str(mapped or "Anemo")


def _avatar_name(avatar: Mapping[str, object], panel: Mapping[str, object]) -> str | None:
    value = (
        text_value(panel.get("name"))
        or text_value(avatar.get("name"))
        or text_value(avatar.get("route"))
    )
    if value:
        return value
    mapped = _map("avatarId2Name_mapping_6.5.0.json").get(_avatar_id(avatar, panel))
    return str(mapped) if mapped else None


def _avatar_id(avatar: Mapping[str, object], panel: Mapping[str, object]) -> str:
    return str(panel.get("avatar_id") or avatar.get("avatarId") or avatar.get("id") or "")


def _avatar_level(avatar: Mapping[str, object], panel: Mapping[str, object]) -> int:
    level = int_value(panel.get("level") or avatar.get("level"))
    if level:
        return level
    prop_map = avatar.get("propMap")
    if isinstance(prop_map, Mapping):
        level_prop = prop_map.get("4001")
        if isinstance(level_prop, Mapping):
            return int_value(level_prop.get("val") or level_prop.get("ival"))
    return 0


def _friendship(avatar: Mapping[str, object], panel: Mapping[str, object]) -> int:
    friendship = int_value(panel.get("friendship"))
    if friendship:
        return friendship
    fetter = avatar.get("fetterInfo")
    if isinstance(fetter, Mapping):
        return int_value(fetter.get("expLevel"))
    return 0


def _fight_props(avatar: Mapping[str, object]) -> Mapping[str, object]:
    raw = avatar.get("fightPropMap")
    return raw if isinstance(raw, Mapping) else {}


def _equip_list(avatar: Mapping[str, object]) -> list[Mapping[str, object]]:
    equips = avatar.get("equipList")
    return (
        [item for item in equips if isinstance(item, Mapping)] if isinstance(equips, list) else []
    )


def _flat(equip: Mapping[str, object]) -> Mapping[str, object]:
    flat = equip.get("flat")
    return flat if isinstance(flat, Mapping) else {}


def _flat_icon(equip: Mapping[str, object]) -> str | None:
    return text_value(_flat(equip).get("icon"))


def _raw_float(raw: Mapping[str, object], key: str, default: float = 0.0) -> float:
    return _float_value(raw.get(key), default)


def _percent(raw: Mapping[str, object], key: str) -> float:
    value = _raw_float(raw, key)
    return value * 100 if abs(value) <= 2 else value


def _stat_value_text(stat: Mapping[str, object]) -> str:
    prop = text_value(stat.get("appendPropId") or stat.get("mainPropId")) or ""
    value = _float_value(stat.get("statValue"))
    suffix = "%" if prop in PERCENT_PROPS and prop not in FIXED_VALUE_PROPS else ""
    return f"{_number_text(value, 1)}{suffix}"


def _prop_name(prop: str) -> str:
    return str(_map("propId2Name_mapping.json").get(prop) or PROP_LABEL_FALLBACKS.get(prop) or prop)


def _short_prop_name(name: str) -> str:
    return name.replace("百分比", "").replace("元素", "")


def _number_text(value: float, digits: int = 0) -> str:
    if digits <= 0:
        return str(round(value))
    text = f"{value:.{digits}f}"
    return text.rstrip("0").rstrip(".")


def _rounded_damage(value: object) -> str:
    return str(round(_float_value(value)))


def _metric_rows(value: object) -> list[Mapping[str, object]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _metric_scores(value: object) -> Mapping[str, float]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _float_value(score) for key, score in value.items()}


def _sequence(value: object) -> Sequence[object]:
    return value if isinstance(value, list) else []


def _dict(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _float_value(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _short_time(value: str) -> str:
    if not value:
        return ""
    return value.replace("T", " ").replace("Z", "")[:19]


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


def _enka_icon_url(icon_name: str | None) -> str | None:
    if not icon_name:
        return None
    return f"{ENKA_UI_BASE}/{quote(icon_name, safe='')}.png"


def _weapon_resource_url(name: str | None) -> str | None:
    if not name:
        return None
    return f"{GENSHINUID_RESOURCE_BASE}/weapon/{quote(name, safe='')}.png"


def _append_url(urls: list[str], url: str | None) -> None:
    if url and url not in urls:
        urls.append(url)


@lru_cache(maxsize=32)
def _map(filename: str) -> Mapping[str, object]:
    with (DATA / filename).open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data if isinstance(data, dict) else {}


def _nested_map(filename: str, key: str) -> Mapping[str, object]:
    data = _map(filename).get(key)
    return data if isinstance(data, Mapping) else {}
