from __future__ import annotations

from collections.abc import Mapping, Sequence

from gsuid_cli.renderers._text_helpers import _finish, _mapping, _mapping_list
from gsuid_cli.renderers.common import int_value, text_value
from gsuid_cli.text import t as _t

OCULUS_LABELS = {
    "anemoculus_number": _t("gsuid.renderers.player.summary.44_4.59d5cc2a"),
    "geoculus_number": _t("gsuid.renderers.player.summary.45_4.56e70957"),
    "electroculus_number": _t("gsuid.renderers.player.summary.46_4.6eeccf4e"),
    "dendroculus_number": _t("gsuid.renderers.player.summary.47_4.d5bbd092"),
    "hydroculus_number": _t("gsuid.renderers.player.summary.48_4.53cdf0ba"),
    "pyroculus_number": _t("gsuid.renderers.player.summary.50_4.600de4a5"),
    "cryoculus_number": _t("gsuid.renderers.player.summary.49_4.463844dd"),
    "moono_culus_number": _t("gsuid.renderers.player.summary.51_4.68a591a2"),
}
CHEST_LABELS = {
    "common_chest_number": _t("gsuid.renderers.player.text.19_27.7f79561c"),
    "exquisite_chest_number": _t("gsuid.renderers.player.text.20_30.7fa82824"),
    "precious_chest_number": _t("gsuid.renderers.player.text.21_29.2e776c1e"),
    "luxurious_chest_number": _t("gsuid.renderers.player.text.22_30.01c3d96c"),
    "magic_chest_number": _t("gsuid.renderers.player.summary.56_4.0788ed91"),
}
POOL_LABELS = {
    "avatar_card_pool_list": _t("gsuid.renderers.gacha.58_27.abe86e08"),
    "weapon_card_pool_list": _t("gsuid.renderers.gacha.50_14.59d0c22d"),
}
ACT_LABELS = {
    "act_list": _t("gsuid.renderers.player.text.30_16.6fe77200"),
    "fixed_act_list": _t("gsuid.renderers.player.text.31_22.94350a08"),
}
CATEGORY_LABELS = {
    "avatar_consume": _t("gsuid.renderers.player.text.34_22.25f98f17"),
    "avatar_skill_consume": _t("gsuid.renderers.player.text.35_28.8e48a345"),
    "weapon_consume": _t("gsuid.renderers.player.text.36_22.a24662b7"),
    "reliquary_consume": _t("gsuid.renderers.guide.text.100_62.619c6618"),
}
SOURCE_LABELS = {
    "mys_anniversary_game_data": _t("gsuid.renderers.player.text.40_33.5ee58ab3"),
}
CONFIDENCE_LABELS = {
    "provider": _t("gsuid.renderers.player.text.43_16.4fc33dd9"),
}


def render_player_summary_text(
    *,
    uid: str,
    summary: Mapping[str, object],
    characters: Sequence[Mapping[str, object]],
) -> str:
    role = _mapping(summary.get("role"))
    stats = _mapping(summary.get("stats"))
    nickname = text_value(role.get("nickname")) or _t(
        "gsuid.renderers.challenge.text.275_47.b2457913"
    )
    lines = [_t("gsuid.renderers.player.text.56_13.4a2f059e", nickname), f"UID: {uid}"]
    level = _optional_int_text(role.get("level"))
    if level:
        lines.append(_t("gsuid.renderers.panel.text.228_21.9655db21", level))
    region_name = text_value(role.get("region_name")) or text_value(role.get("region"))
    if region_name:
        lines.append(_t("gsuid.renderers.player.text.62_21.237b6a6c", region_name))

    lines.append("")
    _append_stat(
        lines, _t("gsuid.renderers.player.text.65_24.f9a46c9a"), stats.get("active_day_number")
    )
    _append_stat(
        lines, _t("gsuid.renderers.player.text.66_24.2c50e1e1"), stats.get("achievement_number")
    )
    abyss = text_value(stats.get("spiral_abyss"))
    if abyss:
        lines.append(_t("gsuid.renderers.player.text.69_21.db86a574", abyss))
    avatar_count = _summary_avatar_count(summary, characters)
    if avatar_count:
        lines.append(_t("gsuid.renderers.player.text.72_21.34d4a9fc", avatar_count))

    _append_counter_section(
        lines, _t("gsuid.renderers.player.text.74_35.677a3a7a"), stats, OCULUS_LABELS
    )
    _append_counter_section(
        lines, _t("gsuid.renderers.player.text.75_35.e3687653"), stats, CHEST_LABELS
    )
    _append_worlds(lines, summary.get("world_explorations"))
    _append_character_lines(
        lines,
        _t("gsuid.renderers.gacha.663_15.6b26695e"),
        characters or _mapping_list(summary.get("avatars")),
    )
    return _finish(lines)


def render_player_characters_text(data: Mapping[str, object]) -> str:
    uid = text_value(data.get("uid")) or _t("gsuid.renderers.daily.text.211_11.d9c32a4c")
    characters = _sorted_characters(_mapping_list(data.get("characters")))
    lines = [
        _t("gsuid.renderers.player.text.84_13.55d15f00"),
        f"UID: {uid}",
        _t("gsuid.renderers.challenge.text.186_8.a63927f2", data.get("count", len(characters))),
    ]
    _append_character_lines(lines, _t("gsuid.renderers.gacha.663_15.6b26695e"), characters)
    return _finish(lines)


def render_player_inventory_text(
    *,
    uid: str,
    summary: Mapping[str, object],
    inventory: Mapping[str, object],
) -> str:
    nickname = _nickname(summary)
    lines = [
        _t("gsuid.renderers.player.text.96_13.bafd47bf", nickname),
        f"UID: {uid}",
        _t("gsuid.renderers.challenge.text.186_8.a63927f2", inventory.get("count", 0)),
    ]
    items = _mapping_list(inventory.get("overall"))
    if items:
        lines.extend(["", _t("gsuid.renderers.player.text.99_26.c0b8d1f8")])
        for item in items:
            lines.append(f"  - {_inventory_item_text(item)}")
    else:
        lines.extend(["", _t("gsuid.renderers.player.text.103_26.19fc38ff")])

    categories = _mapping(inventory.get("categories"))
    category_lines = []
    for key, label in CATEGORY_LABELS.items():
        category_items = _mapping_list(categories.get(key))
        if category_items:
            category_lines.append(f"  - {label}: {len(category_items)}")
    if category_lines:
        lines.extend(["", _t("gsuid.renderers.player.text.112_26.7637e94e")])
        lines.extend(category_lines)
    return _finish(lines)


def render_player_calendar_text(
    *,
    uid: str,
    summary: Mapping[str, object],
    calendar: Mapping[str, object],
) -> str:
    nickname = _nickname(summary)
    counts = _mapping(calendar.get("counts"))
    lines = [_t("gsuid.renderers.player.text.125_13.b78d2e3f", nickname), f"UID: {uid}"]
    for key, label in (
        ("avatar_card_pool_list", _t("gsuid.renderers.gacha.58_27.abe86e08")),
        ("weapon_card_pool_list", _t("gsuid.renderers.gacha.50_14.59d0c22d")),
        ("act_list", _t("gsuid.renderers.player.text.30_16.6fe77200")),
        ("fixed_act_list", _t("gsuid.renderers.player.text.31_22.94350a08")),
    ):
        count = counts.get(key)
        if count not in (None, ""):
            lines.append(f"{label}: {count}")

    pool_lines: list[str] = []
    for key, label in POOL_LABELS.items():
        for pool in _mapping_list(calendar.get(key)):
            pool_lines.extend(_pool_lines(label, pool))
    if pool_lines:
        lines.extend(["", _t("gsuid.renderers.player.text.141_26.6eda0d67")])
        lines.extend(pool_lines)

    for key, label in ACT_LABELS.items():
        acts = _mapping_list(calendar.get(key))
        if not acts:
            continue
        lines.extend(["", f"{label}:"])
        for act in acts:
            lines.extend(_activity_lines(act))
    return _finish(lines)


def render_player_diary_text(
    *,
    uid: str,
    summary: Mapping[str, object],
    diary: Mapping[str, object],
) -> str:
    nickname = _nickname(summary)
    month = (
        text_value(diary.get("data_month"))
        or text_value(diary.get("month"))
        or _t("gsuid.renderers.daily.text.211_11.d9c32a4c")
    )
    day_data = _mapping(diary.get("day_data"))
    month_data = _mapping(diary.get("month_data"))
    lines = [
        _t("gsuid.renderers.player.text.164_13.fc433d48", nickname),
        f"UID: {uid}",
        _t("gsuid.renderers.player.text.164_58.693a0ed3", month),
    ]

    lines.extend(
        [
            "",
            (
                _t(
                    "gsuid.renderers.player.text.170_16.ff95daf9",
                    _num(day_data.get("current_primogems")),
                    _num(day_data.get("current_mora")),
                )
            ),
            (
                _t(
                    "gsuid.renderers.player.text.175_16.396f5090",
                    _num(day_data.get("last_primogems")),
                    _num(day_data.get("last_mora")),
                )
            ),
            (
                _t(
                    "gsuid.renderers.player.text.180_16.e6ece34f",
                    _num(month_data.get("current_primogems")),
                    _num(month_data.get("current_mora")),
                )
            ),
            (
                _t(
                    "gsuid.renderers.player.text.185_16.15428b64",
                    _num(month_data.get("last_primogems")),
                    _num(month_data.get("last_mora")),
                )
            ),
        ]
    )

    groups = _mapping_list(month_data.get("group_by"))
    if groups:
        lines.extend(["", _t("gsuid.renderers.player.text.194_26.49471bd8")])
        for group in groups:
            action = text_value(group.get("action")) or _t(
                "gsuid.renderers.player.diary.31_4.1a26edf9"
            )
            num = _num(group.get("num"))
            percent = _optional_int_text(group.get("percent"))
            suffix = f"（{percent}%）" if percent else ""
            lines.append(f"  - {action}: {num}{suffix}")
    return _finish(lines)


def render_player_register_time_text(data: Mapping[str, object]) -> str:
    uid = text_value(data.get("uid")) or _t("gsuid.renderers.daily.text.211_11.d9c32a4c")
    register_time = _mapping(data.get("register_time"))
    lines = [_t("gsuid.renderers.player.text.207_13.525ad5e2"), f"UID: {uid}"]
    registered_at = text_value(register_time.get("registered_at"))
    if registered_at:
        lines.append(_t("gsuid.renderers.player.text.210_21.8fb9a530", registered_at))
    timezone = text_value(register_time.get("timezone"))
    if timezone:
        lines.append(_t("gsuid.renderers.player.text.213_21.47a7c524", timezone))
    source = text_value(register_time.get("source"))
    if source:
        lines.append(
            _t("gsuid.renderers.events.text.53_21.15097066", SOURCE_LABELS.get(source, source))
        )
    confidence = text_value(register_time.get("confidence"))
    if confidence:
        lines.append(
            _t(
                "gsuid.renderers.player.text.219_21.c51ff10c",
                CONFIDENCE_LABELS.get(confidence, confidence),
            )
        )
    return _finish(lines)


def _append_stat(lines: list[str], label: str, value: object) -> None:
    text = _optional_int_text(value)
    if text:
        lines.append(f"{label}: {text}")


def _append_counter_section(
    lines: list[str],
    title: str,
    stats: Mapping[str, object],
    labels: Mapping[str, str],
) -> None:
    values = []
    for key, label in labels.items():
        value = int_value(stats.get(key), 0)
        if value:
            values.append(f"  - {label}: {value}")
    if values:
        lines.extend(["", f"{title}:"])
        lines.extend(values)


def _append_worlds(lines: list[str], value: object) -> None:
    worlds = _mapping_list(value)
    if not worlds:
        return
    lines.extend(["", _t("gsuid.renderers.player.text.249_22.d28df406")])
    for world in sorted(worlds, key=lambda item: int_value(item.get("id"))):
        name = text_value(world.get("name")) or _t("gsuid.renderers.player.text.251_48.d851c775")
        percent = int_value(world.get("exploration_percentage"), 0) / 10
        level = _optional_int_text(world.get("level"))
        detail = f"{percent:.1f}%"
        if level:
            detail += _t("gsuid.renderers.player.text.256_22.e7855c7f", level)
        lines.append(f"  - {name}: {detail}")
        for offering in _mapping_list(world.get("offerings")):
            offering_name = text_value(offering.get("name")) or _t(
                "gsuid.renderers.player.text.259_64.15a7a673"
            )
            offering_level = _optional_int_text(offering.get("level"))
            if offering_level:
                lines.append(
                    _t("gsuid.renderers.player.text.262_29.937780b0", offering_name, offering_level)
                )


def _append_character_lines(
    lines: list[str],
    title: str,
    characters: Sequence[Mapping[str, object]],
) -> None:
    if not characters:
        lines.extend(["", _t("gsuid.renderers.player.text.271_26.48c4049b", title)])
        return
    lines.extend(["", f"{title}:"])
    for character in _sorted_characters(characters):
        lines.append(f"  - {_character_text(character)}")
        weapon = character.get("weapon")
        if isinstance(weapon, Mapping) and weapon:
            lines.append(_t("gsuid.renderers.player.text.278_25.a1038de0", _weapon_text(weapon)))


def _character_text(character: Mapping[str, object]) -> str:
    name = text_value(character.get("name")) or _t("gsuid.renderers.challenge.text.293_68.876cfbce")
    parts = [name]
    rarity = _stars(character.get("rarity"))
    if rarity:
        parts.append(rarity)
    level = _optional_int_text(character.get("level"))
    if level:
        parts.append(f"Lv{level}")
    fetter = _optional_int_text(character.get("fetter"))
    if fetter:
        parts.append(_t("gsuid.renderers.player.text.292_21.bd739f47", fetter))
    constellation = _optional_int_text(character.get("actived_constellation_num"))
    if constellation:
        parts.append(_t("gsuid.renderers.challenge.common.119_45.fd9e8859", constellation))
    return " ".join(parts)


def _weapon_text(weapon: Mapping[str, object]) -> str:
    name = text_value(weapon.get("name")) or _t("gsuid.renderers.panel.image.1086_49.6eb8409d")
    parts = [name]
    rarity = _stars(weapon.get("rarity"))
    if rarity:
        parts.append(rarity)
    level = _optional_int_text(weapon.get("level"))
    if level:
        parts.append(f"Lv{level}")
    refinement = _optional_int_text(weapon.get("affix_level"))
    if refinement:
        parts.append(_t("gsuid.renderers.panel.image.1101_25.071fef7c", refinement))
    return " ".join(parts)


def _inventory_item_text(item: Mapping[str, object]) -> str:
    name = text_value(item.get("name")) or _t("gsuid.renderers.player.text.315_43.9d20fd89")
    owned = int_value(item.get("owned"), 0)
    required = int_value(item.get("required"), 0)
    missing = int_value(item.get("missing"), 0)
    detail = _t("gsuid.renderers.player.text.319_13.bc06c2b5", owned)
    if required:
        detail += _t("gsuid.renderers.player.text.321_18.82c0c939", required)
    if missing:
        detail += _t("gsuid.renderers.player.text.323_18.46184580", missing)
    return f"{name}: {detail}"


def _pool_lines(label: str, pool: Mapping[str, object]) -> list[str]:
    name = text_value(pool.get("pool_name")) or _t("gsuid.renderers.player.text.328_48.92a67983")
    version = text_value(pool.get("version_name"))
    duration = _duration_text(pool.get("countdown_seconds"))
    suffixes = []
    if version:
        suffixes.append(_t("gsuid.renderers.player.text.333_24.55d3d8c4", version))
    if duration:
        suffixes.append(_t("gsuid.renderers.player.text.335_24.a769ff8e", duration))
    heading = f"  - [{label}] {name}"
    if suffixes:
        heading += f"（{'，'.join(suffixes)}）"
    lines = [heading]
    for item_key, item_label in (
        ("avatars", _t("gsuid.renderers.gacha.663_15.6b26695e")),
        ("weapon", _t("gsuid.commands.panel.impl.988_24.6f0f16e0")),
    ):
        item_names = [_pool_item_text(item) for item in _mapping_list(pool.get(item_key))]
        if item_names:
            lines.append(f"    {item_label}: {'、'.join(item_names)}")
    return lines


def _pool_item_text(item: Mapping[str, object]) -> str:
    name = text_value(item.get("name")) or _t("gsuid.renderers.daily.text.211_11.d9c32a4c")
    rarity = _stars(item.get("rarity"))
    return f"{name} {rarity}".rstrip()


def _activity_lines(act: Mapping[str, object]) -> list[str]:
    name = text_value(act.get("name")) or _t("gsuid.renderers.player.text.354_42.75032a76")
    status, extra = _activity_status_text(act)
    duration = _duration_text(act.get("countdown_seconds"))
    details = [status]
    if duration:
        details.append(_t("gsuid.renderers.player.text.335_24.a769ff8e", duration))
    if extra:
        details.append(extra)
    lines = [f"  - {name}: {'，'.join(details)}"]
    rewards = [
        reward_text
        for reward in _mapping_list(act.get("reward_list"))
        if (reward_text := _reward_text(reward)) is not None
    ]
    if rewards:
        lines.append(_t("gsuid.renderers.events.text.68_25.87cab234", "、".join(rewards)))
    return lines


def _activity_status_text(act: Mapping[str, object]) -> tuple[str, str | None]:
    if int_value(act.get("status")) != 2:
        return _t("gsuid.renderers.player.calendar.148_21.062e5e67"), None
    if act.get("type") == "ActTypeHardChallenge":
        detail = _mapping(act.get("hard_challenge_detail"))
        seconds = int_value(detail.get("second"), 0)
        if seconds:
            return _t(
                "gsuid.renderers.player.calendar.258_19.bc37d2ed",
                int_value(detail.get("difficulty")),
            ), _t("gsuid.renderers.challenge.hard.119_25.05854e94", seconds)
    if act.get("type") == "ActTypeExplore":
        detail = _mapping(act.get("explore_detail"))
        percent = int_value(detail.get("explore_percent"), 0)
        if percent:
            return f"{percent}%", None
    return (
        _t("gsuid.renderers.daily.text.161_13.e99b48a2")
        if act.get("is_finished")
        else _t("gsuid.renderers.daily.text.247_11.b61b08ae")
    ), None


def _reward_text(reward: Mapping[str, object]) -> str | None:
    name = text_value(reward.get("name")) or _t("gsuid.renderers.player.text.390_45.8a19ae00")
    count = reward.get("num")
    if int_value(count, 0) == 0:
        return None
    return f"{name} x{count}" if count not in (None, "") else name


def _summary_avatar_count(
    summary: Mapping[str, object],
    characters: Sequence[Mapping[str, object]],
) -> int:
    count = int_value(summary.get("avatar_count"), 0)
    if count:
        return count
    avatars = _mapping_list(summary.get("avatars"))
    return len(characters) or len(avatars)


def _nickname(summary: Mapping[str, object]) -> str:
    role = _mapping(summary.get("role"))
    return text_value(role.get("nickname")) or _t("gsuid.renderers.challenge.text.275_47.b2457913")


def _sorted_characters(
    characters: Sequence[Mapping[str, object]],
) -> list[Mapping[str, object]]:
    return sorted(
        characters,
        key=lambda character: (
            -int_value(character.get("rarity"), 0),
            -int_value(character.get("level"), 0),
            -int_value(character.get("fetter"), 0),
            text_value(character.get("name")) or "",
        ),
    )


def _stars(value: object) -> str:
    rarity = int_value(value, 0)
    if rarity <= 0:
        return ""
    return "★" * min(rarity, 5)


def _duration_text(value: object) -> str | None:
    seconds = int_value(value, 0)
    if seconds <= 0:
        return None
    days = seconds // (24 * 3600)
    hours = (seconds % (24 * 3600)) // 3600
    minutes = (seconds % 3600) // 60
    return _t("gsuid.renderers.player.calendar.272_11.64b9941b", days, hours, minutes)


def _num(value: object) -> str:
    return str(int_value(value, 0))


def _optional_int_text(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(int_value(value))
