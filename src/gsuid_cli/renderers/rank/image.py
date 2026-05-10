from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from functools import lru_cache
from urllib.parse import quote

from PIL import Image, ImageDraw

from gsuid_cli.providers.public import GENSHINUID_RESOURCE_ASSET_BASE
from gsuid_cli.renderers.common import (
    asset_path,
    crop_center,
    font,
    image_from_bytes,
    int_value,
    open_rgba,
    png_bytes,
    sequence as _sequence,
    text_value,
    v4_background,
)

TEXTURE = asset_path("rank", "textures")
PANEL_TEXTURE = asset_path("panel", "textures")
THEATER_TEXTURE = asset_path("challenge", "theater", "textures")
HARD_TEXTURE = asset_path("challenge", "hard", "textures")
PANEL_DATA = asset_path("panel", "data")
REGION_COLORS = {
    "CN": (255, 58, 58),
    "ASIA": (169, 109, 57),
    "NA": (255, 165, 0),
    "EU": (80, 98, 255),
    "TW": (37, 37, 37),
    "B": (128, 35, 151),
}
GREY = (170, 170, 170)
STAT_LABELS = {
    "Flat ATK": "攻击力",
    "Flat HP": "生命值",
    "Flat DEF": "防御力",
    "ATK%": "攻击力",
    "HP%": "生命值",
    "DEF%": "防御力",
    "Elemental Mastery": "元素精通",
    "Energy Recharge": "元素充能效率",
    "Crit RATE": "暴击率",
    "Crit DMG": "暴击伤害",
    "Cryo DMG Bonus": "冰元素伤害加成",
    "Pyro DMG Bonus": "火元素伤害加成",
    "Hydro DMG Bonus": "水元素伤害加成",
    "Electro DMG Bonus": "雷元素伤害加成",
    "Anemo DMG Bonus": "风元素伤害加成",
    "Geo DMG Bonus": "岩元素伤害加成",
    "Dendro DMG Bonus": "草元素伤害加成",
    "Healing Bonus": "治疗加成",
    "Physical DMG Bonus": "物理伤害加成",
}
EQUIP_LABELS = {
    "EQUIP_BRACER": "生之花",
    "EQUIP_NECKLACE": "死之羽",
    "EQUIP_SHOES": "时之沙",
    "EQUIP_RING": "空之杯",
    "EQUIP_DRESS": "理之冠",
}


def user_rank_asset_urls(characters: Sequence[Mapping[str, object]]) -> list[str]:
    urls: list[str] = []
    for character in characters:
        urls.append(_character_icon_url(character))
        weapon = _dict(character.get("weapon"))
        urls.append(_weapon_icon_url(weapon))
        urls.extend(_artifact_set_urls(_dict(character.get("artifact_sets"))))
    return [url for url in urls if url]


def character_rank_asset_urls(
    character_id: str, entries: Sequence[Mapping[str, object]]
) -> list[str]:
    urls = [_character_url(character_id)]
    for entry in entries:
        urls.extend(_artifact_set_urls(_dict(entry.get("artifactSets"))))
    return [url for url in urls if url]


def artifact_rank_asset_urls(artifacts: Sequence[Mapping[str, object]]) -> list[str]:
    return [url for item in artifacts if (url := text_value(item.get("icon")))]


def render_user_rank_list(
    *,
    uid: str,
    player: Mapping[str, object],
    characters: Sequence[Mapping[str, object]],
    asset_images: Mapping[str, bytes],
) -> bytes:
    height = 570 + 150 + len(characters) * 90 + 80
    image = v4_background(1600, height, black_value=200)
    draw = ImageDraw.Draw(image)
    _draw_user_header(image, uid, player, characters, asset_images)
    for index, character in enumerate(characters):
        row = _user_rank_row(character, asset_images)
        image.paste(row, (0, 700 + index * 90), row)
    draw.text(
        (800, height - 35),
        "Created by GenshinUID & Power by GsCore & Design by Wuyi无疑 & Data by 米游社",
        (200, 200, 200),
        font(20),
        anchor="mm",
    )
    return png_bytes(image)


def render_character_rank(
    *,
    character_id: str,
    tag: str,
    total_count: int,
    entries: Sequence[Mapping[str, object]],
    selected_uid: str | None,
    asset_images: Mapping[str, bytes],
) -> bytes:
    image = crop_center(Image.open(TEXTURE / "deep_grey.jpg"), 950, 2450).convert("RGBA")
    title = open_rgba(TEXTURE / "title.png")
    avatar = _ring_icon(_remote_image(_character_url(character_id), asset_images, (314, 314)), 314)
    title.paste(avatar, (318, 57), avatar)
    image.paste(title, (0, 0), title)
    draw = ImageDraw.Draw(image)
    draw.text((475, 425), f"{tag} / 总数据 {total_count}条", "white", font(26), anchor="mm")
    rank = 0
    for index, entry in enumerate(entries[:20]):
        raw_rank = entry.get("index")
        if index == 0:
            rank = _rank_number(raw_rank)
        else:
            rank += 1
        row = _character_rank_row(entry, rank, selected_uid, index, asset_images)
        image.paste(row, (0, 475 + index * 95), row)
    draw.text(
        (475, image.size[1] - 35),
        "Power by GenshinUID & Data by AKS & CV Created by GsCore & gsuid-cli",
        (200, 200, 200),
        font(18),
        anchor="mm",
    )
    return png_bytes(image)


def render_artifact_rank(
    *,
    sort_label: str,
    artifacts: Sequence[Mapping[str, object]],
    asset_images: Mapping[str, bytes],
) -> bytes:
    image = Image.open(TEXTURE / "star.jpg").convert("RGBA")
    draw = ImageDraw.Draw(image)
    for index, artifact in enumerate(artifacts[:20]):
        card = _artifact_rank_card(artifact, asset_images)
        image.paste(card, (15 + 318 * (index % 4), 468 + 410 * (index // 4)), card)
    draw.text((650, 425), f"前20 / 当前排序 {sort_label or '双爆'}", "white", font(26), anchor="mm")
    draw.text(
        (650, image.size[1] - 35),
        "Power by GenshinUID & Data by AKS & CV Created by GsCore & gsuid-cli",
        (200, 200, 200),
        font(18),
        anchor="mm",
    )
    return png_bytes(image)


def _draw_user_header(
    image: Image.Image,
    uid: str,
    player: Mapping[str, object],
    characters: Sequence[Mapping[str, object]],
    asset_images: Mapping[str, bytes],
) -> None:
    title = open_rgba(TEXTURE / "title_2.png")
    profile_url = text_value(player.get("profile_picture_url")) or ""
    profile = _circle_image(_remote_image(profile_url, asset_images, (180, 180)), 180)
    title.paste(profile, (88, 328), profile)
    title_fg = open_rgba(TEXTURE / "title_fg_2.png")
    title.paste(title_fg, (0, 0), title_fg)
    draw = ImageDraw.Draw(title)
    nickname = text_value(player.get("nickname")) or "旅行者"
    draw.text((331, 428), nickname, "white", font(40), anchor="lm")
    draw.text((427, 478), f"UID {uid}", (207, 207, 207), font(30), anchor="mm")
    _draw_title_badges(title, player)
    image.paste(title, (0, 0), title)

    title_bar = open_rgba(TEXTURE / "title_bar_2.png")
    bar_draw = ImageDraw.Draw(title_bar)
    for index, value in enumerate(_title_stats(player, characters)):
        bar_draw.text((int(142 + index * 187.4), 52), str(value), "white", font(38), anchor="mm")
    image.paste(title_bar, (0, 570), title_bar)


def _draw_title_badges(title: Image.Image, player: Mapping[str, object]) -> None:
    draw = ImageDraw.Draw(title)
    theater_icon = _theater_icon(player)
    title.paste(theater_icon, (1151, 438), theater_icon)
    hard_icon = _hard_icon(player)
    title.paste(hard_icon, (1326, 358), hard_icon)
    draw.text((1476, 462), _abyss_label(player), "white", font(28), anchor="mm")
    draw.text((1476, 383), _hard_label(player), "white", font(28), anchor="mm")
    draw.text((1301, 462), _theater_label(player), "white", font(28), anchor="mm")


def _user_rank_row(
    character: Mapping[str, object], asset_images: Mapping[str, bytes]
) -> Image.Image:
    row = open_rgba(TEXTURE / "rank_bar.png")
    mask = Image.new("RGBA", row.size, (0, 0, 0, 0))
    mask_draw = ImageDraw.Draw(mask)
    percent = _number(character.get("percent"))
    rect_x = 81 + (1266 - 81) * min(max(percent, 0), 100) / 100
    mask_draw.rectangle((int(rect_x), 0, 1266, 90), fill="white")
    row.paste(open_rgba(TEXTURE / "rank_bar_fill.png"), (0, 0), mask)

    draw = ImageDraw.Draw(row)
    text_layer = open_rgba(TEXTURE / "rank_bar_text.png")
    row.paste(text_layer, (0, 0), text_layer)
    char_pic = _quality_ring_icon(
        _remote_image(_character_icon_url(character), asset_images, (90, 90)),
        _character_quality(character),
    )
    row.paste(char_pic, (68, 6), char_pic)

    weapon = _dict(character.get("weapon"))
    weapon_ring = _quality_ring_icon(
        _remote_image(_weapon_icon_url(weapon), asset_images, (90, 90)),
        int_value(weapon.get("rarity"), 5),
    )
    row.paste(weapon_ring, (844, 0), weapon_ring)
    _paste_small_icon(
        row, _constellation_icon(int_value(character.get("constellation"))), (770, 30)
    )
    _paste_small_icon(row, _weapon_affix_icon(int_value(weapon.get("refinement"), 1)), (953, 30))
    _draw_artifact_sets(row, _dict(character.get("artifact_sets")), asset_images, (155, 14))

    stats = _dict(character.get("stats"))
    cr = _number(stats.get("critRate")) * 100
    cd = _number(stats.get("critDMG")) * 100
    cv = _number(stats.get("critValue"))
    hp = int(_number(stats.get("maxHP")))
    atk = int(_number(stats.get("maxATK")))
    rank = int_value(character.get("rank"))
    out_of = int_value(character.get("out_of"))
    result = int(_number(character.get("result")))
    label = _variant_label(character)
    percent_show, percent_color = _percent_label(rank, out_of)

    draw.text((242, 36), f"{cr:.1f}: {cd:.1f}", "white", font(26), anchor="lm")
    draw.text(
        (242, 59),
        f"{cv:.1f} cv",
        _grade_color(cv, [260, 245, 225, 180]),
        font(20),
        anchor="lm",
    )
    draw.text((492, 46), f"{hp}", "white", font(26), anchor="lm")
    draw.text((690, 46), f"{atk}", "white", font(26), anchor="lm")
    draw.text((1401, 34), f"{result}", "white", font(32), anchor="mm")
    draw.text((1401, 64), label, (150, 150, 150), font(22), anchor="mm")
    draw.text((1238, 34), percent_show, percent_color, font(30), anchor="rm")
    draw.text((1238, 64), f"{rank} / {out_of}", (150, 150, 150), font(22), anchor="rm")
    return row


def _character_rank_row(
    entry: Mapping[str, object],
    rank: int,
    selected_uid: str | None,
    index: int,
    asset_images: Mapping[str, bytes],
) -> Image.Image:
    uid = str(entry.get("uid") or "")
    if selected_uid and selected_uid == uid:
        row = open_rgba(TEXTURE / "sp.png")
    else:
        row = open_rgba(TEXTURE / ("white.png" if index % 2 == 0 else "black.png"))
    draw = ImageDraw.Draw(row)
    owner = _dict(entry.get("owner"))
    region = str(owner.get("region") or "")
    nickname = str(owner.get("nickname") or "")
    stats = _dict(entry.get("stats"))
    weapon = _dict(entry.get("weapon"))
    weapon_info = _dict(weapon.get("weaponInfo"))
    refinement = int_value(_dict(weapon_info.get("refinementLevel")).get("value")) + 1
    constellation = int_value(entry.get("constellation"))
    hp = int(_stat(stats, "maxHp"))
    atk = int(_stat(stats, "atk"))
    cr = _stat(stats, "critRate") * 100
    cd = _stat(stats, "critDamage") * 100
    cv = _number(entry.get("critValue"))

    x1, x2 = 15, 64 + 15 * len(str(rank))
    draw.rounded_rectangle((x1, 0, x2, 25), 9, (96, 33, 109))
    draw.text(((x1 + x2) / 2 + 1, 13), f"#{rank}名", "white", font(24), anchor="mm")
    draw.rounded_rectangle((47, 35, 150, 75), 10, REGION_COLORS.get(region, (128, 128, 128)))
    draw.text((99, 55), region, "white", font(30), anchor="mm")
    draw.text((162, 41), nickname, "white", font(26), anchor="lm")
    draw.text((162, 66), f"UID {uid}", GREY, font(20), anchor="lm")
    draw.text((398, 42), f"{cr:.1f}: {cd:.1f}", "white", font(26), anchor="lm")
    draw.text(
        (398, 66),
        f"{cv:.1f} cv",
        _grade_color(cv, [260, 245, 225, 180]),
        font(20),
        anchor="lm",
    )
    draw.text((665, 34), f"{hp}", "white", font(26), anchor="lm")
    draw.text((665, 70), f"{atk}", "white", font(26), anchor="lm")
    _draw_artifact_sets(row, _dict(entry.get("artifactSets")), asset_images, (318, 15))
    _paste_small_icon(row, _constellation_icon(constellation), (764, 35))
    _paste_small_icon(row, _weapon_affix_icon(refinement), (840, 35))
    return row


def _artifact_rank_card(
    artifact: Mapping[str, object], asset_images: Mapping[str, bytes]
) -> Image.Image:
    card = open_rgba(TEXTURE / "arti_bg.png")
    panel = _artifact_panel_card(artifact, asset_images)
    card.paste(panel, (0, 0), panel)
    draw = ImageDraw.Draw(card)
    owner = _dict(artifact.get("owner"))
    region = str(owner.get("region") or "")
    draw.rounded_rectangle((27, 366, 112, 396), 20, REGION_COLORS.get(region, (128, 128, 128)))
    draw.text((70, 381), region, "white", font(24), anchor="mm")
    draw.text((120, 381), str(owner.get("nickname") or ""), "white", font(24), anchor="lm")
    draw.text((155, 333), f"UID {artifact.get('uid') or ''}", GREY, font(15), anchor="mm")
    return card


def _artifact_panel_card(
    artifact: Mapping[str, object], asset_images: Mapping[str, bytes]
) -> Image.Image:
    bg = open_rgba(PANEL_TEXTURE / "char_info_artifacts_bg.png")
    card = open_rgba(PANEL_TEXTURE / "char_info_artifacts.png")
    icon_url = text_value(artifact.get("icon")) or ""
    icon = _remote_image(icon_url, asset_images, (90, 90))
    card.paste(icon, (26, 32), icon)
    star = open_rgba(PANEL_TEXTURE / f"s-{min(max(int_value(artifact.get('stars'), 5), 1), 5)}.png")
    star = star.resize((90, 23), Image.Resampling.LANCZOS)
    card.paste(star, (121, 63), star)

    draw = ImageDraw.Draw(card)
    draw.text(
        (124, 51),
        _truncate(_artifact_name(artifact), 9),
        (255, 255, 255),
        font(22),
        anchor="lm",
    )
    draw.text(
        (38, 150),
        _short_stat_label(str(artifact.get("mainStatKey") or "")),
        (255, 255, 255),
        font(28),
        anchor="lm",
    )
    draw.text(
        (271, 150),
        _main_stat_value_text(artifact),
        (255, 255, 255),
        font(28),
        anchor="rm",
    )
    draw.text(
        (232, 75),
        f"+{max(int_value(artifact.get('level')) - 1, 0)}",
        (255, 255, 255),
        font(15),
        anchor="mm",
    )
    substats = list(_dict(artifact.get("substats")).items())
    for index, (name, value) in enumerate(substats[:4]):
        draw.text(
            (22, 200 + index * 35),
            f"·{_short_stat_label(name)}",
            (255, 255, 255),
            font(25),
            anchor="lm",
        )
        draw.text(
            (266, 200 + index * 35),
            _stat_value_text(value, name),
            (255, 255, 255),
            font(25),
            anchor="rm",
        )
    cv = _number(artifact.get("critValue"))
    draw.rounded_rectangle((121, 99, 193, 119), 8, _grade_color(cv / 5, [9, 8, 7, 6]))
    draw.rounded_rectangle((200, 99, 272, 119), 8, _grade_color(cv, [50, 45, 39, 30]))
    draw.text((156, 109), f"{cv / 10:.2f}条", (255, 255, 255), font(18), anchor="mm")
    draw.text((235, 109), f"{cv:.1f}分", (255, 255, 255), font(18), anchor="mm")
    bg.paste(card, (0, 0), card)
    return bg


def _draw_artifact_sets(
    row: Image.Image,
    sets: Mapping[str, object],
    asset_images: Mapping[str, bytes],
    origin: tuple[int, int],
) -> None:
    icons = []
    for item in sets.values():
        data = _dict(item)
        if int_value(data.get("count")) < 2:
            continue
        icon_url = _artifact_icon_url(data.get("icon"))
        icon = _remote_image(icon_url, asset_images, (64, 64))
        if int_value(data.get("count")) >= 4:
            icons = [icon]
            break
        icons.append(icon.resize((51, 51), Image.Resampling.LANCZOS))
    draw = ImageDraw.Draw(row)
    if len(icons) == 1:
        row.paste(icons[0], (origin[0] + 7, origin[1] + 2), icons[0])
        text = "4"
    elif len(icons) >= 2:
        row.paste(icons[0], (origin[0] + 16, origin[1] + 15), icons[0])
        row.paste(icons[1], (origin[0], origin[1]), icons[1])
        text = "2+2"
    else:
        text = "0"
    draw.text((origin[0] + 52, origin[1] + 52), text, (214, 255, 192), font(20), anchor="mm")


def _remote_image(
    url: str, asset_images: Mapping[str, bytes], size: tuple[int, int]
) -> Image.Image:
    image = image_from_bytes(asset_images.get(url, b""), size) if url else None
    if image is not None:
        return image
    placeholder = Image.new("RGBA", size, (45, 45, 55, 255))
    draw = ImageDraw.Draw(placeholder)
    draw.text((size[0] / 2, size[1] / 2), "?", (200, 200, 200), font(28), anchor="mm")
    return placeholder


def _circle_image(image: Image.Image, size: int) -> Image.Image:
    image = image.resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(image, (0, 0), mask)
    return result


def _ring_icon(image: Image.Image, size: int) -> Image.Image:
    image = image.resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(image, (0, 0), mask)
    ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ring_draw = ImageDraw.Draw(ring)
    ring_draw.ellipse(
        (2, 2, size - 3, size - 3),
        outline=(255, 255, 255, 245),
        width=max(3, size // 18),
    )
    result.paste(ring, (0, 0), ring)
    return result


def _quality_ring_icon(image: Image.Image, star: int) -> Image.Image:
    star = min(max(star, 1), 5)
    bg_path = TEXTURE / f"star_{star}.png"
    ring_path = TEXTURE / "ring.png"
    mask_path = TEXTURE / "ring_mask.png"
    if not bg_path.exists() or not ring_path.exists() or not mask_path.exists():
        return _ring_icon(image, 90)
    bg = open_rgba(bg_path).resize((90, 90), Image.Resampling.LANCZOS)
    ring = open_rgba(ring_path).resize((90, 90), Image.Resampling.LANCZOS)
    mask = open_rgba(mask_path).resize((90, 90), Image.Resampling.LANCZOS)
    framed = Image.new("RGBA", (90, 90), (0, 0, 0, 0))
    framed.paste(image.resize((90, 90), Image.Resampling.LANCZOS), (0, 0), mask)
    bg.paste(framed, (0, 0), framed)
    bg.paste(ring, (0, 0), ring)
    return bg


def _title_stats(
    player: Mapping[str, object], characters: Sequence[Mapping[str, object]]
) -> list[object]:
    title_stats = player.get("title_stats")
    if isinstance(title_stats, list) and len(title_stats) == 8:
        return title_stats
    owned = [str(item) for item in _sequence(player.get("owned_characters"))]
    if not owned:
        owned = [str(item.get("avatar_id")) for item in characters if item.get("avatar_id")]
    star_map = _json_map("avatarId2Star_mapping_6.5.0.json")
    star5 = [avatar_id for avatar_id in owned if str(star_map.get(avatar_id)) == "5"]
    star4 = [avatar_id for avatar_id in owned if str(star_map.get(avatar_id)) == "4"]
    full_star4 = _full_constellation_count(characters, star_map, "4")
    star5_weapon = sum(
        1 for item in characters if int_value(_dict(item.get("weapon")).get("rarity")) == 5
    )
    high_score = sum(1 for item in characters if _stat_cv(item) >= 210)
    useful = sum(1 for item in characters if _stat_cv(item) >= 180)
    max_friendship = int_value(player.get("max_friendship_count"))
    owned_count = int_value(player.get("owned_character_count"), len(owned)) or len(owned)
    return [
        "0/0",
        f"{max_friendship}/{owned_count}",
        f"{full_star4}/{len(star4)}",
        f"{len(star5)}/{_total_star_count(star_map, '5')}",
        f"{len(star4)}/{_total_star_count(star_map, '4')}",
        f"{star5_weapon}/{len(_json_map('weaponId2Name_mapping_6.5.0.json'))}",
        high_score,
        useful,
    ]


def _full_constellation_count(
    characters: Sequence[Mapping[str, object]],
    star_map: Mapping[str, object],
    star: str,
) -> int:
    return sum(
        1
        for item in characters
        if int_value(item.get("constellation")) >= 6
        and str(star_map.get(str(item.get("avatar_id")))) == star
    )


def _total_star_count(star_map: Mapping[str, object], star: str) -> int:
    return sum(1 for value in star_map.values() if str(value) == star)


def _stat_cv(character: Mapping[str, object]) -> float:
    return _number(_dict(character.get("stats")).get("critValue"))


def _character_quality(character: Mapping[str, object]) -> int:
    star_map = _json_map("avatarId2Star_mapping_6.5.0.json")
    return int_value(star_map.get(str(character.get("avatar_id"))), 5)


def _theater_icon(player: Mapping[str, object]) -> Image.Image:
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


def _hard_icon(player: Mapping[str, object]) -> Image.Image:
    level = max(int_value(player.get("stygian_index"), 3), 3)
    path = HARD_TEXTURE / f"medal_{min(level, 6)}.png"
    if not path.exists():
        path = HARD_TEXTURE / "medal_3.png"
    return open_rgba(path).resize((52, 52), Image.Resampling.LANCZOS)


def _abyss_label(player: Mapping[str, object]) -> str:
    floor = int_value(player.get("abyss_floor"))
    chamber = int_value(player.get("abyss_chamber"))
    return f"深渊{floor}-{chamber}" if floor and chamber else "深渊--"


def _hard_label(player: Mapping[str, object]) -> str:
    return text_value(player.get("hard_name")) or "断玉之役"


def _theater_label(player: Mapping[str, object]) -> str:
    theater = _dict(player.get("theater"))
    return f"第{int_value(theater.get('max_round_id'))}幕"


def _paste_small_icon(image: Image.Image, icon: Image.Image | None, pos: tuple[int, int]) -> None:
    if icon is not None:
        image.paste(icon, pos, icon)


def _weapon_affix_icon(refinement: int) -> Image.Image | None:
    path = PANEL_TEXTURE / "weapon_affix" / f"weapon_affix_{min(max(refinement, 1), 5)}.png"
    return open_rgba(path) if path.exists() else None


def _constellation_icon(level: int) -> Image.Image | None:
    path = TEXTURE / f"talent_{min(max(level, 0), 6)}.png"
    return open_rgba(path) if path.exists() else None


def _character_url(character_id: str) -> str:
    return f"{GENSHINUID_RESOURCE_ASSET_BASE}/chars/{character_id}.png" if character_id else ""


def _character_icon_url(character: Mapping[str, object]) -> str:
    icon = text_value(character.get("icon"))
    if icon:
        return icon
    return _character_url(str(character.get("avatar_id") or ""))


def _weapon_url(name: str) -> str:
    return f"{GENSHINUID_RESOURCE_ASSET_BASE}/weapon/{quote(name)}.png" if name else ""


def _weapon_icon_url(weapon: Mapping[str, object]) -> str:
    icon = text_value(weapon.get("icon"))
    if icon:
        return icon
    return _weapon_url(text_value(weapon.get("name")) or "")


def _artifact_set_urls(sets: Mapping[str, object]) -> list[str]:
    return [_artifact_icon_url(_dict(item).get("icon")) for item in sets.values()]


def _artifact_icon_url(value: object) -> str:
    text = text_value(value)
    if not text:
        return ""
    if text.startswith("http"):
        return text
    return f"https://enka.network/ui/{text}.png"


def _variant_label(character: Mapping[str, object]) -> str:
    variant = _dict(character.get("variant"))
    return str(variant.get("displayName") or character.get("short") or "")


def _percent_label(rank: int, out_of: int) -> tuple[str, tuple[int, int, int]]:
    percent = (rank / out_of) * 100 if out_of else 100
    if rank <= 100:
        return f"全球前{rank}名", (255, 73, 29)
    if percent <= 10:
        return f"全球前{percent:.1f}%", (255, 41, 169)
    if percent <= 40:
        return f"全球前{percent:.1f}%", (75, 69, 255)
    return f"全球前{percent:.1f}%", (255, 255, 255)


def _grade_color(value: float, thresholds: list[int]) -> tuple[int, int, int]:
    colors = {
        0: (200, 12, 12),
        1: (200, 100, 12),
        2: (151, 80, 186),
        3: (33, 142, 212),
        4: (47, 107, 56),
        5: (64, 64, 66),
    }
    for index, threshold in enumerate(thresholds):
        if value >= threshold:
            return colors[index]
    return colors[5]


def _short_stat_label(name: str) -> str:
    label = STAT_LABELS.get(name, name)
    return (
        label.replace("百分比", "")
        .replace("伤害加成", "伤加成")
        .replace("元素", "")
        .replace("理", "")
    )


def _main_stat_value_text(artifact: Mapping[str, object]) -> str:
    return _stat_value_text(artifact.get("mainStatValue"), str(artifact.get("mainStatKey") or ""))


def _artifact_name(artifact: Mapping[str, object]) -> str:
    icon_url = text_value(artifact.get("icon")) or ""
    icon_key = icon_url.rsplit("/", 1)[-1].split(".", 1)[0]
    mapped = _json_map("icon2Name_mapping_6.5.0.json").get(icon_key)
    return str(mapped or artifact.get("name") or "")


def _stat_value_text(value: object, stat_name: str) -> str:
    number = _number(value)
    suffix = "%" if _is_percent_stat(stat_name) else ""
    if number.is_integer():
        return f"{int(number)}{suffix}"
    return f"{number:.1f}{suffix}"


def _is_percent_stat(stat_name: str) -> bool:
    return (
        "%" in stat_name
        or "Bonus" in stat_name
        or stat_name in {"Crit RATE", "Crit DMG", "Energy Recharge"}
    )


def _truncate(value: str, max_chars: int) -> str:
    return value if len(value) <= max_chars else f"{value[: max_chars - 1]}…"


def _stat(stats: Mapping[str, object], key: str) -> float:
    value = stats.get(key)
    return _number(_dict(value).get("value") if isinstance(value, dict) else value)


def _rank_number(value: object) -> int:
    if isinstance(value, str) and value.startswith("~"):
        value = value[1:]
    return int_value(value)


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


@lru_cache(maxsize=8)
def _json_map(filename: str) -> dict[str, object]:
    try:
        data = json.loads((PANEL_DATA / filename).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
