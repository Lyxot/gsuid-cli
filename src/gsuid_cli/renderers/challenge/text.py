from __future__ import annotations

from collections.abc import Mapping, Sequence

from gsuid_cli.renderers._text_helpers import _finish, _first_mapping, _mapping, _mapping_list
from gsuid_cli.renderers.challenge.common import timestamp_text
from gsuid_cli.renderers.common import int_value, sequence, text_value
from gsuid_cli.text import t as _t

DIFFICULTY_LABELS = {
    1: _t("gsuid.renderers.challenge.text.10_7.b96a5429"),
    2: _t("gsuid.renderers.challenge.text.11_7.e8a4554e"),
    3: _t("gsuid.renderers.challenge.text.12_7.49b6a116"),
    4: _t("gsuid.renderers.challenge.text.13_7.c528888a"),
    5: _t("gsuid.renderers.challenge.text.14_7.93eacb2e"),
}
RANKING_LABELS = {
    "damage_rank": _t("gsuid.renderers.challenge.hard.156_12.45aecde0"),
    "defeat_rank": _t("gsuid.renderers.challenge.text.18_19.0a2c8737"),
    "take_damage_rank": _t("gsuid.renderers.challenge.abyss.127_9.5a3fae76"),
    "energy_skill_rank": _t("gsuid.renderers.challenge.abyss.128_9.4e5b3902"),
}


def render_challenge_abyss_text(
    *,
    uid: str,
    abyss: Mapping[str, object],
    summary: Mapping[str, object],
) -> str:
    names = _summary_avatar_names(summary)
    lines = [_t("gsuid.renderers.challenge.text.31_13.8c528fa0", _nickname(summary)), f"UID: {uid}"]
    lines.append(
        _t(
            "gsuid.renderers.challenge.text.32_17.36ade5a2",
            int_value(abyss.get("total_battle_times")),
        )
    )
    if abyss.get("max_floor") not in (None, ""):
        lines.append(_t("gsuid.renderers.challenge.text.34_21.b9ad4bf3", abyss["max_floor"]))
    if abyss.get("total_star") not in (None, ""):
        lines.append(_t("gsuid.renderers.challenge.text.36_21.16e823f0", abyss["total_star"]))

    rankings = _mapping(abyss.get("rankings"))
    ranking_lines = []
    for key, label in RANKING_LABELS.items():
        character = _first_mapping(rankings.get(key))
        if character:
            ranking_lines.append(
                f"  - {label}: {_character_name(character, names)} {character.get('value')}"
            )
    if ranking_lines:
        lines.extend(["", _t("gsuid.renderers.challenge.text.47_26.facc74c9")])
        lines.extend(ranking_lines)

    floors = _abyss_floors(abyss)
    if not floors:
        lines.extend(["", _t("gsuid.renderers.challenge.text.52_26.93c4b2e7")])
        return _finish(lines)

    lines.extend(["", _t("gsuid.renderers.challenge.text.55_22.ad233f25")])
    for floor in floors:
        index = int_value(floor.get("index"))
        star = int_value(floor.get("star"))
        max_star = int_value(floor.get("max_star"), 9)
        heading = _t("gsuid.renderers.challenge.text.60_18.b0e278a4", index, star, max_star)
        settle = text_value(floor.get("settle_time"))
        if settle and settle not in {"0", "0000-00-00 00:00:00"}:
            heading += _t("gsuid.renderers.challenge.text.63_23.831d0ec9", settle)
        lines.append(heading)
        for level_index, level in enumerate(_mapping_list(floor.get("levels")), start=1):
            lines.append(
                _t(
                    "gsuid.renderers.challenge.text.66_25.dc0e6d5e",
                    level_index,
                    int_value(level.get("star")),
                )
            )
            for battle_index, battle in enumerate(_mapping_list(level.get("battles")), start=1):
                time_text = timestamp_text(battle.get("timestamp"))
                if time_text:
                    lines.append(
                        _t("gsuid.renderers.challenge.text.70_33.493512b1", battle_index, time_text)
                    )
                avatars = _character_names(_mapping_list(battle.get("avatars")), names)
                if avatars:
                    lines.append(
                        _t("gsuid.renderers.challenge.text.73_33.42d02a42", "、".join(avatars))
                    )
    return _finish(lines)


def render_challenge_theater_text(
    *,
    uid: str,
    theater: Mapping[str, object],
    summary: Mapping[str, object],
) -> str:
    names = _summary_avatar_names(summary)
    session = _mapping(theater.get("selected"))
    detail = _mapping(session.get("detail"))
    stat = _mapping(session.get("stat")) or _mapping(detail.get("detail_stat"))
    fight = _mapping(detail.get("fight_statisic"))
    schedule = _mapping(session.get("schedule"))
    lines = [_t("gsuid.renderers.challenge.text.89_13.0be8af13", _nickname(summary)), f"UID: {uid}"]
    difficulty_id = int_value(stat.get("difficulty_id"))
    difficulty = DIFFICULTY_LABELS.get(difficulty_id)
    if difficulty_id and difficulty:
        lines.append(_t("gsuid.renderers.challenge.text.93_21.34f075bd", difficulty))
    max_round, medal = _theater_round_medal_counts(stat)
    if max_round or medal:
        lines.append(
            _t(
                "gsuid.renderers.challenge.text.96_21.0afdeff6",
                int_value(stat.get("max_round_id")),
                medal,
                max_round,
            )
        )
    time_range = _time_range(schedule.get("start_time"), schedule.get("end_time"))
    if time_range:
        lines.append(_t("gsuid.renderers.challenge.text.99_21.389c2b09", time_range))
    total_time = int_value(fight.get("total_use_time"))
    if total_time:
        lines.append(
            _t("gsuid.renderers.challenge.text.102_21.98011143", total_time // 60, total_time % 60)
        )
    max_damage = _mapping(fight.get("max_damage_avatar"))
    if max_damage:
        lines.append(
            _t(
                "gsuid.renderers.challenge.text.105_21.6509de56",
                _character_name(max_damage, names),
                max_damage.get("value"),
            )
        )

    rounds = _filtered_theater_rounds(_mapping_list(detail.get("rounds_data")))
    if not rounds:
        lines.extend(["", _t("gsuid.renderers.challenge.text.109_26.780f83be")])
        return _finish(lines)

    lines.extend(["", _t("gsuid.renderers.challenge.text.112_22.89730f32")])
    for round_data in rounds:
        label = (
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
        medal_text = (
            _t("gsuid.renderers.challenge.text.119_21.da1c0553")
            if round_data.get("is_get_medal")
            else _t("gsuid.renderers.challenge.text.119_75.5e0c35a4")
        )
        lines.append(f"  - {label}: {medal_text}")
        enemies = [
            text_value(enemy.get("name")) for enemy in _mapping_list(round_data.get("enemies"))
        ]
        enemies = [enemy for enemy in enemies if enemy]
        if enemies:
            lines.append(_t("gsuid.renderers.challenge.text.126_25.7136d63d", "、".join(enemies)))
        buffs = _theater_buff_texts(round_data)
        if buffs:
            lines.append(_t("gsuid.renderers.challenge.text.129_25.11d9e3bb", "、".join(buffs)))
        avatars = _character_names(_mapping_list(round_data.get("avatars")), names)
        if avatars:
            lines.append(_t("gsuid.renderers.challenge.text.132_25.edac9742", "、".join(avatars)))
    return _finish(lines)


def render_challenge_hard_text(
    *,
    uid: str,
    hard: Mapping[str, object],
    summary: Mapping[str, object],
) -> str:
    names = _summary_avatar_names(summary)
    schedule, single = _hard_sections(hard)
    lines = [
        _t("gsuid.renderers.challenge.text.144_13.98e3ddd6", _nickname(summary)),
        f"UID: {uid}",
    ]
    time_range = _time_range(schedule.get("start_time"), schedule.get("end_time"), date_only=True)
    if time_range:
        lines.append(_t("gsuid.renderers.challenge.text.99_21.389c2b09", time_range))
    best = _mapping(single.get("best"))
    if best:
        if best.get("difficulty") not in (None, ""):
            lines.append(_t("gsuid.renderers.challenge.text.151_25.a5d1380c", best["difficulty"]))
        if best.get("second") not in (None, ""):
            lines.append(_t("gsuid.renderers.challenge.text.153_25.18aaae52", best["second"]))

    challenges = _mapping_list(single.get("challenge"))
    if not challenges:
        lines.extend(["", _t("gsuid.renderers.challenge.text.157_26.b9d54c79")])
        return _finish(lines)

    lines.extend(["", _t("gsuid.renderers.challenge.text.160_22.6f46969b")])
    for challenge in challenges:
        name = text_value(challenge.get("name")) or _t(
            "gsuid.renderers.challenge.text.162_52.6dedebf0"
        )
        seconds = int_value(challenge.get("second"))
        lines.append(
            _t("gsuid.renderers.challenge.text.164_21.e3b03295", name, seconds)
            if seconds
            else f"  - {name}"
        )
        monster = _mapping(challenge.get("monster"))
        if monster:
            monster_text = text_value(monster.get("name")) or _t(
                "gsuid.renderers.challenge.text.167_62.9c4e01fa"
            )
            level = int_value(monster.get("level"))
            if level:
                monster_text += f" Lv{level}"
            lines.append(_t("gsuid.renderers.challenge.text.126_25.7136d63d", monster_text))
        teams = _character_names(_mapping_list(challenge.get("teams")), names)
        if teams:
            lines.append(_t("gsuid.renderers.challenge.text.174_25.bbbd7ac7", "、".join(teams)))
        best_avatars = _mapping_list(challenge.get("best_avatar"))
        if best_avatars:
            lines.append(
                _t(
                    "gsuid.renderers.challenge.text.177_25.9a0a7bd7",
                    _hard_best_avatar_text(best_avatars[0], names),
                )
            )
        if len(best_avatars) > 1:
            lines.append(
                _t(
                    "gsuid.renderers.challenge.text.179_25.5c3fb0ff",
                    _hard_best_avatar_text(best_avatars[1], names),
                )
            )
    return _finish(lines)


def render_challenge_hard_rank_text(data: Mapping[str, object]) -> str:
    lines = [
        _t("gsuid.renderers.challenge.text.185_8.251477e4"),
        _t("gsuid.renderers.challenge.text.186_8.a63927f2", data.get("count", 0)),
    ]
    if data.get("total_count") not in (None, ""):
        lines.append(_t("gsuid.renderers.challenge.text.189_21.a5c229cd", data["total_count"]))
    entries = _mapping_list(data.get("entries"))
    if entries:
        lines.extend(["", _t("gsuid.renderers.challenge.text.192_26.7d06966a")])
        for index, entry in enumerate(entries, start=1):
            nickname = text_value(entry.get("nickname")) or _t(
                "gsuid.renderers.challenge.text.194_60.db6c0c0b"
            )
            uid = text_value(entry.get("uid")) or "-"
            difficulty = text_value(entry.get("stygian_index")) or "-"
            time_text = text_value(entry.get("stygian_time")) or "-"
            achievement = text_value(entry.get("achievement_count")) or "-"
            lines.append(
                _t(
                    "gsuid.renderers.challenge.text.200_16.30795d10",
                    index,
                    nickname,
                    uid,
                    difficulty,
                    time_text,
                    achievement,
                )
            )
    limitations = [
        text
        for text in (text_value(item) for item in sequence(data.get("source_limitations")))
        if text
    ]
    if limitations:
        lines.extend(["", _t("gsuid.renderers.challenge.text.209_26.2196ffb6")])
        lines.extend(f"  - {limitation}" for limitation in limitations)
    return _finish(lines)


def _theater_round_medal_counts(stat: Mapping[str, object]) -> tuple[int, int]:
    difficulty_id = int_value(stat.get("difficulty_id"))
    max_round = int_value(stat.get("max_round_id"))
    medal = int_value(stat.get("medal_num"))
    if difficulty_id == 5:
        max_round = 12
        medal += int_value(stat.get("tarot_finished_cnt"))
    return max_round, medal


def _filtered_theater_rounds(rounds: list[Mapping[str, object]]) -> list[Mapping[str, object]]:
    tarot_count = sum(1 for item in rounds if item.get("is_tarot") is True)
    if tarot_count <= 2:
        return rounds
    return [
        item
        for item in rounds
        if not item.get("is_tarot", False) or item.get("is_get_medal", False)
    ]


def _theater_buff_texts(round_data: Mapping[str, object]) -> list[str]:
    splendour = _mapping(round_data.get("splendour_buff"))
    lines = []
    for buff in _mapping_list(splendour.get("buffs")):
        name = text_value(buff.get("name")) or _t("gsuid.renderers.challenge.text.239_47.fb9233d5")
        level = int_value(buff.get("level"))
        lines.append(f"{name} Lv{level}" if level else name)
    return lines


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


def _hard_best_avatar_text(avatar: Mapping[str, object], names: Mapping[str, str]) -> str:
    name = _character_name(avatar, names)
    value = avatar.get("dps") or avatar.get("value")
    return f"{name} {value}" if value not in (None, "") else name


def _time_range(start: object, end: object, *, date_only: bool = False) -> str | None:
    start_text = timestamp_text(start, date_only=date_only)
    end_text = timestamp_text(end, date_only=date_only)
    if start_text and end_text:
        return _t("gsuid.renderers.challenge.text.269_15.5881d084", start_text, end_text)
    return start_text or end_text or None


def _nickname(summary: Mapping[str, object]) -> str:
    role = _mapping(summary.get("role"))
    return text_value(role.get("nickname")) or _t("gsuid.renderers.challenge.text.275_47.b2457913")


def _character_names(
    characters: Sequence[Mapping[str, object]],
    names: Mapping[str, str],
) -> list[str]:
    return [name for character in characters if (name := _character_name(character, names))]


def _character_name(character: Mapping[str, object], names: Mapping[str, str]) -> str:
    name = text_value(character.get("name"))
    if name:
        return name
    avatar_id = character.get("avatar_id", character.get("id"))
    mapped = names.get(str(avatar_id))
    if mapped:
        return mapped
    return (
        _t("gsuid.renderers.challenge.text.293_11.c85c7dac", avatar_id)
        if avatar_id not in (None, "")
        else _t("gsuid.renderers.challenge.text.293_68.876cfbce")
    )


def _summary_avatar_names(summary: Mapping[str, object]) -> dict[str, str]:
    names = {}
    for avatar in _mapping_list(summary.get("avatars")):
        avatar_id = avatar.get("id", avatar.get("avatar_id"))
        name = text_value(avatar.get("name"))
        if avatar_id not in (None, "") and name:
            names[str(avatar_id)] = name
    return names


def _abyss_floors(abyss: Mapping[str, object]) -> list[Mapping[str, object]]:
    return sorted(
        [
            floor
            for floor in _mapping_list(abyss.get("floors"))
            if int_value(floor.get("index")) >= 9
        ],
        key=lambda floor: int_value(floor.get("index")),
    )
