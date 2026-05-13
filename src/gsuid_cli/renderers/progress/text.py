from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache

from gsuid_cli.renderers._text_helpers import _finish, _first_mapping, _mapping, _mapping_list
from gsuid_cli.renderers.common import asset_path, int_value, sequence, text_value
from gsuid_cli.text import t as _t

GCG_CARD_NAME_PATH = asset_path("progress", "gcg", "data", "card_names.json")

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
OTHER_LABELS = {
    "avatar_number": _t("gsuid.renderers.progress.text.30_21.18697cb1"),
    "way_point_number": _t("gsuid.renderers.progress.text.31_24.9651404b"),
    "domain_number": _t("gsuid.renderers.progress.text.32_21.ac3aa6c2"),
}
GUIDE_LABELS = {
    "achievement": _t("gsuid.renderers.progress.text.35_19.61ef3922"),
    "commission": _t("gsuid.renderers.progress.text.36_18.6b6612a5"),
}


def render_progress_completion_text(*, uid: str, completion: Mapping[str, object]) -> str:
    stats = _stats(completion)
    lines = [_t("gsuid.renderers.progress.text.42_13.722d50c7"), f"UID: {uid}"]
    _append_stat(
        lines, _t("gsuid.renderers.player.text.65_24.f9a46c9a"), stats.get("active_day_number")
    )
    _append_stat(
        lines, _t("gsuid.renderers.player.text.66_24.2c50e1e1"), stats.get("achievement_number")
    )
    abyss = text_value(stats.get("spiral_abyss"))
    if abyss:
        lines.append(_t("gsuid.renderers.player.text.69_21.db86a574", abyss))
    exploration_count = completion.get("exploration_count")
    if exploration_count not in (None, ""):
        lines.append(_t("gsuid.renderers.progress.text.50_21.ed68cbf8", exploration_count))

    _append_worlds(lines, completion.get("world_explorations"))
    _append_counter_section(
        lines, _t("gsuid.renderers.player.text.74_35.677a3a7a"), stats, OCULUS_LABELS
    )
    _append_counter_section(
        lines,
        _t("gsuid.renderers.progress.text.54_35.3297422a"),
        stats,
        {**CHEST_LABELS, **OTHER_LABELS},
    )
    return _finish(lines)


def render_progress_exploration_text(*, uid: str, exploration: Mapping[str, object]) -> str:
    lines = [_t("gsuid.renderers.progress.text.59_13.86e4305b"), f"UID: {uid}"]
    worlds = _mapping_list(exploration.get("world_explorations"))
    if not worlds:
        lines.extend(["", _t("gsuid.renderers.progress.text.62_26.6f7fbe53")])
        return _finish(lines)
    _append_worlds(lines, worlds)
    return _finish(lines)


def render_progress_collection_text(*, uid: str, collection: Mapping[str, object]) -> str:
    stats = _stats(collection)
    lines = [_t("gsuid.renderers.progress.text.70_13.528f0688"), f"UID: {uid}"]
    _append_stat(
        lines, _t("gsuid.renderers.player.text.65_24.f9a46c9a"), stats.get("active_day_number")
    )
    _append_stat(
        lines, _t("gsuid.renderers.player.text.66_24.2c50e1e1"), stats.get("achievement_number")
    )
    _append_counter_section(
        lines, _t("gsuid.renderers.player.text.74_35.677a3a7a"), stats, OCULUS_LABELS
    )
    _append_counter_section(
        lines, _t("gsuid.renderers.player.text.75_35.e3687653"), stats, CHEST_LABELS
    )
    _append_counter_section(
        lines, _t("gsuid.renderers.player.diary.31_4.1a26edf9"), stats, OTHER_LABELS
    )
    return _finish(lines)


def render_progress_achievements_text(
    *,
    uid: str,
    achievements: list[Mapping[str, object]],
    query: object = None,
) -> str:
    lines = [_t("gsuid.renderers.progress.text.85_13.83911417"), f"UID: {uid}"]
    query_text = text_value(query)
    if query_text:
        lines.append(_t("gsuid.renderers.progress.text.103_8.6796ffc0", query_text))
    lines.append(_t("gsuid.renderers.challenge.text.186_8.a63927f2", len(achievements)))
    if not achievements:
        lines.extend(["", _t("gsuid.renderers.progress.text.91_26.0d57ed83")])
        return _finish(lines)
    lines.extend(["", _t("gsuid.renderers.progress.text.93_22.46024b43")])
    for achievement in achievements:
        lines.append(f"  - {_achievement_text(achievement)}")
    return _finish(lines)


def render_progress_guide_status_text(data: Mapping[str, object]) -> str:
    kind = text_value(data.get("kind"))
    lines = [
        GUIDE_LABELS.get(kind, _t("gsuid.renderers.progress.text.102_31.98da8ead")),
        _t("gsuid.renderers.progress.text.103_8.6796ffc0", text_value(data.get("query")) or "-"),
        _t("gsuid.renderers.challenge.text.186_8.a63927f2", data.get("count", 0)),
    ]
    limitations = [
        text
        for text in (text_value(item) for item in sequence(data.get("source_limitations")))
        if text
    ]
    if limitations:
        lines.extend(["", _t("gsuid.renderers.challenge.text.209_26.2196ffb6")])
        lines.extend(f"  - {limitation}" for limitation in limitations)
    matches = _mapping_list(data.get("matches"))
    if matches:
        lines.extend(["", _t("gsuid.renderers.progress.text.116_26.b2957dbc")])
        for match in matches:
            _append_guide_match(lines, kind, match)
    return _finish(lines)


def render_progress_gcg_text(*, uid: str, gcg: Mapping[str, object]) -> str:
    basic = _mapping(gcg.get("basic"))
    nickname = text_value(basic.get("nickname")) or _t(
        "gsuid.renderers.progress.text.124_52.9c6d4f19"
    )
    lines = [_t("gsuid.renderers.progress.text.125_13.d0ff2562", nickname), f"UID: {uid}"]
    _append_stat(lines, _t("gsuid.renderers.progress.text.126_24.c2d829d3"), basic.get("level"))
    _append_ratio(
        lines,
        _t("gsuid.renderers.progress.text.129_8.a7a3f469"),
        basic.get("avatar_card_num_gained"),
        basic.get("avatar_card_num_total"),
    )
    _append_ratio(
        lines,
        _t("gsuid.renderers.progress.text.135_8.a5e95538"),
        basic.get("action_card_num_gained"),
        basic.get("action_card_num_total"),
    )
    if gcg.get("deck_count") not in (None, ""):
        lines.append(_t("gsuid.renderers.progress.text.140_21.fa599411", gcg["deck_count"]))
    covers = _mapping_list(basic.get("covers"))
    if covers:
        lines.extend(["", _t("gsuid.renderers.progress.text.143_26.42f3f955")])
        lines.extend(f"  - {_card_name(card)}" for card in covers)
    return _finish(lines)


def render_progress_gcg_deck_text(*, uid: str, data: Mapping[str, object]) -> str:
    deck = _first_mapping(data.get("decks"))
    deck_name = text_value(deck.get("name")) or _t("gsuid.renderers.progress.text.150_48.a839934c")
    lines = [_t("gsuid.renderers.progress.text.151_13.2d9f0375", deck_name), f"UID: {uid}"]
    deck_id = deck.get("id", data.get("deck_id"))
    if deck_id not in (None, ""):
        lines.append(_t("gsuid.renderers.progress.text.154_21.a4b4b4ab", deck_id))
    if not deck:
        lines.extend(["", _t("gsuid.renderers.progress.text.156_26.91fb2b2e")])
        return _finish(lines)
    avatar_cards = _mapping_list(deck.get("avatar_cards"))
    if avatar_cards:
        lines.extend(["", _t("gsuid.renderers.progress.text.160_26.0ee174ea")])
        lines.extend(f"  - {_card_name(card)}" for card in avatar_cards)
    action_cards = _mapping_list(deck.get("action_cards"))
    if action_cards:
        lines.extend(["", _t("gsuid.renderers.progress.text.164_26.f59e23c3")])
        lines.extend(f"  - {_action_card_text(card)}" for card in action_cards)
    return _finish(lines)


def _append_stat(lines: list[str], label: str, value: object) -> None:
    text = _optional_int_text(value)
    if text:
        lines.append(f"{label}: {text}")


def _append_ratio(lines: list[str], label: str, current: object, total: object) -> None:
    current_text = _optional_int_text(current)
    total_text = _optional_int_text(total)
    if current_text or total_text:
        lines.append(f"{label}: {current_text or 0}/{total_text or 0}")


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
        detail = f"{percent:.1f}%"
        level = _optional_int_text(world.get("level"))
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
                    _t(
                        "gsuid.renderers.progress.text.215_29.5c430fff",
                        offering_name,
                        offering_level,
                    )
                )


def _achievement_text(achievement: Mapping[str, object]) -> str:
    name = text_value(achievement.get("name")) or _t(
        "gsuid.renderers.progress.text.219_50.e66b12b9"
    )
    finish = _optional_int_text(achievement.get("finish_num"))
    percent = _percent_text(achievement.get("percentage"))
    details = []
    if finish:
        details.append(_t("gsuid.renderers.progress.text.224_23.bb058a97", finish))
    if percent:
        details.append(percent)
    return f"{name}: {'，'.join(details)}" if details else name


def _action_card_text(card: Mapping[str, object]) -> str:
    name = _card_name(card)
    num = int_value(card.get("num"), 1)
    suffix = f" x{num}" if num > 1 else ""
    cost = _first_cost(card)
    cost_value = _optional_int_text(cost.get("cost_value"))
    if cost_value:
        suffix += _t("gsuid.renderers.progress.text.237_18.dd63df78", cost_value)
    return f"{name}{suffix}"


def _append_guide_match(lines: list[str], kind: str, match: Mapping[str, object]) -> None:
    name = text_value(match.get("name")) or _t("gsuid.renderers.progress.text.242_44.35563060")
    lines.append(f"  - {name}")
    if kind == "achievement":
        book = text_value(match.get("book"))
        if book:
            lines.append(_t("gsuid.renderers.progress.text.247_25.7242e14d", book))
    else:
        achievement = text_value(match.get("achievement"))
        if achievement:
            lines.append(_t("gsuid.renderers.progress.text.251_25.f70479e8", achievement))
    description = text_value(match.get("description"))
    if description:
        lines.append(_t("gsuid.renderers.progress.text.254_21.3133f291", description))
    guide = text_value(match.get("guide"))
    if guide:
        lines.append(_t("gsuid.renderers.progress.text.257_21.db930049", guide))
    link = text_value(match.get("link"))
    if link:
        lines.append(_t("gsuid.renderers.progress.text.260_21.dadda716", link))


def _card_name(card: Mapping[str, object]) -> str:
    name = text_value(card.get("name"))
    if name:
        return name
    card_id = text_value(card.get("id")) or text_value(card.get("rank_id"))
    if card_id:
        mapped_name = _gcg_card_names().get(card_id)
        if mapped_name:
            return mapped_name
    return _t("gsuid.renderers.progress.text.272_11.fb640464")


def _first_cost(card: Mapping[str, object]) -> Mapping[str, object]:
    costs = _mapping_list(card.get("action_cost"))
    return costs[0] if costs else {}


def _stats(data: Mapping[str, object]) -> Mapping[str, object]:
    stats = data.get("raw_stats") or data.get("stats")
    return stats if isinstance(stats, Mapping) else {}


def _optional_int_text(value: object) -> str:
    if value in (None, ""):
        return ""
    return str(int_value(value))


def _percent_text(value: object) -> str:
    try:
        percent = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    if percent < 0:
        return ""
    return f"{percent:g}%"


@lru_cache(maxsize=1)
def _gcg_card_names() -> Mapping[str, str]:
    try:
        payload = json.loads(GCG_CARD_NAME_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, Mapping):
        return {}
    return {str(key): str(value) for key, value in payload.items() if text_value(value)}
