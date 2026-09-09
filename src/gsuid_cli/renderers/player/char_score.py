from __future__ import annotations

from collections.abc import Mapping, Sequence

from gsuid_cli.renderers.common import int_value, text_value

_STANDARD_FIVE = frozenset({"琴", "迪卢克", "莫娜", "七七", "提纳里", "刻晴", "迪希雅"})
_TRAVELER_NAMES = frozenset({"旅行者", "空", "荧"})
_TRAVELER_IDS = frozenset({10000005, 10000007})

_FIVE_STAR_CONSTELLATION_SCORE = (0, 6, 11, 14, 16, 17, 18)
_FOUR_STAR_CONSTELLATION_SCORE = (0, 2, 4, 7, 10, 13, 18)


def pool_factor(character: Mapping[str, object]) -> float:
    if _is_traveler(character):
        return 0.72
    if text_value(character.get("name")) in _STANDARD_FIVE:
        return 0.86
    if int_value(character.get("rarity")) >= 5:
        return 1.0
    return 0.72


def character_build_score(character: Mapping[str, object]) -> float:
    total = (
        _level_score(int_value(character.get("level")))
        + _constellation_score(character)
        + _weapon_score(character)
        + _artifact_score(character)
    )
    return min(max(total, 0.1), 100.0)


def character_total_score(character: Mapping[str, object]) -> float:
    return pool_factor(character) * character_build_score(character) + _fetter_adjustment(character)


def _is_traveler(character: Mapping[str, object]) -> bool:
    return (
        int_value(character.get("id")) in _TRAVELER_IDS
        or text_value(character.get("name")) in _TRAVELER_NAMES
    )


def _level_score(level: int) -> float:
    if level <= 0:
        return 0.0
    return 22.0 * (level / 90.0) ** 1.15


def _constellation_score(character: Mapping[str, object]) -> float:
    constellation = min(max(int_value(character.get("actived_constellation_num")), 0), 6)
    if int_value(character.get("rarity")) >= 5 and not _is_traveler(character):
        return float(_FIVE_STAR_CONSTELLATION_SCORE[constellation])
    return float(_FOUR_STAR_CONSTELLATION_SCORE[constellation])


def _weapon_score(character: Mapping[str, object]) -> float:
    weapon = character.get("weapon")
    if not isinstance(weapon, Mapping):
        return 0.0

    rarity = int_value(weapon.get("rarity"))
    if rarity >= 5:
        base, refinement_step = 0.80, 0.04
    elif rarity == 4:
        base, refinement_step = 0.62, 0.08
    elif rarity == 3:
        base, refinement_step = 0.42, 0.08
    elif rarity == 2:
        base, refinement_step = 0.24, 0.08
    else:
        base, refinement_step = 0.16, 0.08

    level = int_value(weapon.get("level"))
    level_factor = (level / 90.0) ** 1.1 if level > 0 else 0.0
    refinement = max(int_value(weapon.get("affix_level"), 1) - 1, 0)
    score = 28.0 * base * level_factor * (1.0 + refinement * refinement_step)
    return min(score, 28.0)


def _artifact_score(character: Mapping[str, object]) -> float:
    reliquaries = character.get("reliquaries")
    if not isinstance(reliquaries, Sequence) or isinstance(reliquaries, (str, bytes)):
        return 0.0

    artifacts = [artifact for artifact in reliquaries if isinstance(artifact, Mapping)]
    levels = [
        int_value(artifact.get("level"))
        for artifact in artifacts
        if int_value(artifact.get("rarity")) >= 5
    ]
    if not levels:
        return 0.0

    average_level = sum(levels) / len(levels)
    score = 32.0 * (len(levels) / 5.0) * (average_level / 20.0)
    if not _has_four_piece_set(artifacts):
        score *= 0.85
    return min(score, 32.0)


def _has_four_piece_set(artifacts: Sequence[Mapping[str, object]]) -> bool:
    counts: dict[str, int] = {}
    for artifact in artifacts:
        artifact_set = artifact.get("set")
        if not isinstance(artifact_set, Mapping):
            continue
        name = text_value(artifact_set.get("name"))
        if name:
            counts[name] = counts.get(name, 0) + 1
    return any(count >= 4 for count in counts.values())


def _fetter_adjustment(character: Mapping[str, object]) -> float:
    return min(int_value(character.get("fetter")) * 0.1, 1.0)
