from collections.abc import Mapping

import pytest

from gsuid_cli.renderers.player.char_score import (
    character_build_score,
    character_total_score,
    pool_factor,
)
from gsuid_cli.renderers.player.characters import _sorted_characters


def _weapon(*, rarity: int, level: int, refinement: int) -> dict[str, object]:
    return {
        "name": "test weapon",
        "rarity": rarity,
        "level": level,
        "affix_level": refinement,
    }


def _artifact(*, level: int, set_name: str) -> dict[str, object]:
    return {"rarity": 5, "level": level, "set": {"name": set_name}}


def _character(
    *,
    name: str = "胡桃",
    character_id: int = 10000046,
    rarity: int = 5,
    level: int = 90,
    constellation: int = 0,
    fetter: int = 10,
    weapon: Mapping[str, object] | None = None,
    artifacts: list[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "id": character_id,
        "name": name,
        "rarity": rarity,
        "level": level,
        "actived_constellation_num": constellation,
        "fetter": fetter,
        "weapon": weapon or _weapon(rarity=5, level=90, refinement=1),
        "reliquaries": artifacts or [],
    }


def test_pool_factor_distinguishes_character_pools() -> None:
    assert pool_factor(_character(name="胡桃")) == 1.0
    for name in ("琴", "迪卢克", "莫娜", "七七", "提纳里", "刻晴", "迪希雅"):
        assert pool_factor(_character(name=name)) == 0.86
    assert pool_factor(_character(name="香菱", rarity=4)) == 0.72
    assert pool_factor(_character(name="荧", character_id=10000007)) == 0.72


def test_weapon_score_matches_upstream_anchors() -> None:
    def weapon_only(rarity: int, refinement: int) -> float:
        character = _character(
            fetter=0,
            weapon=_weapon(rarity=rarity, level=90, refinement=refinement),
        )
        return character_build_score(character) - 22.0

    assert round(weapon_only(5, 1), 1) == 22.4
    assert round(weapon_only(5, 5), 1) == 26.0
    assert round(weapon_only(4, 1), 1) == 17.4
    assert round(weapon_only(4, 5)) == 23
    assert round(weapon_only(3, 5)) == 16


def test_character_sort_uses_total_build_score() -> None:
    artifacts = [_artifact(level=20, set_name="绝缘") for _ in range(5)]
    weak_limited = _character(
        name="胡桃",
        level=20,
        fetter=0,
        weapon=_weapon(rarity=3, level=20, refinement=1),
    )
    strong_four_star = _character(
        name="香菱",
        rarity=4,
        constellation=6,
        weapon=_weapon(rarity=4, level=90, refinement=5),
        artifacts=artifacts,
    )

    assert character_total_score(strong_four_star) > character_total_score(weak_limited)
    assert _sorted_characters([weak_limited, strong_four_star]) == [
        strong_four_star,
        weak_limited,
    ]


def test_character_score_tolerates_incomplete_provider_data() -> None:
    assert character_total_score({}) == pytest.approx(0.072)
