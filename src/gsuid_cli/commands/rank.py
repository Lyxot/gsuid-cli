from __future__ import annotations

import argparse

from gsuid_cli.commands.auth import _uid_and_region
from gsuid_cli.commands.panel_cache import (
    artifact_entries,
    avatar_summaries,
    cache_source,
    find_avatar,
    load_panel_cache,
    normalized_avatar,
    sort_rank_entries,
)
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.state import state_db

ARTIFACT_SORT_PROPS = {
    "crit-rate": {"FIGHT_PROP_CRITICAL", "crit_rate", "20"},
    "crit-damage": {"FIGHT_PROP_CRITICAL_HURT", "crit_damage", "22"},
    "em": {"FIGHT_PROP_ELEMENT_MASTERY", "elemental_mastery", "28"},
    "recharge": {"FIGHT_PROP_CHARGE_EFFICIENCY", "energy_recharge", "23"},
    "atk": {"FIGHT_PROP_ATTACK", "FIGHT_PROP_ATTACK_PERCENT", "atk", "atk_percent", "5", "6"},
}

CAPABILITIES = [
    {
        "command": "rank.summary",
        "description": "Summarize local cached panel ranking inputs.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "rank.list",
        "description": "List local cached character scores.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "rank.character",
        "description": "Show local cached score details for one character.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "rank.artifact",
        "description": "List local cached artifacts sorted by score.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
]


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    rank = groups.add_parser("rank", help="Rank cached panel data locally.")
    commands = rank.add_subparsers(dest="rank_command", required=True, metavar="<command>")

    summary = commands.add_parser("summary", help="Summarize cached rank inputs.")
    summary.add_argument("--uid", dest="command_uid")
    summary.set_defaults(handler=summary_command, command_name="rank.summary")

    list_parser = commands.add_parser("list", help="List cached character scores.")
    list_parser.add_argument("--uid", dest="command_uid")
    list_parser.add_argument(
        "--sort",
        choices=("artifact-score", "level"),
        default="artifact-score",
    )
    list_parser.set_defaults(handler=list_command, command_name="rank.list")

    character = commands.add_parser("character", help="Show one cached character score.")
    character.add_argument("--uid", dest="command_uid")
    character.add_argument("--character", required=True)
    character.add_argument("--nearby", action="store_true")
    character.set_defaults(handler=character_command, command_name="rank.character")

    artifact = commands.add_parser("artifact", help="List cached artifacts.")
    artifact.add_argument("--uid", dest="command_uid")
    artifact.add_argument("--character")
    artifact.add_argument(
        "--sort",
        choices=("crit", "crit-rate", "crit-damage", "em", "recharge", "atk"),
        default="crit",
    )
    artifact.set_defaults(handler=artifact_command, command_name="rank.artifact")


def summary_command(args: argparse.Namespace) -> CommandResult:
    uid, _region = _uid_and_region(args)
    cache = _load(uid, args.output_dir)
    entries = avatar_summaries(cache)
    artifact_count = len(artifact_entries(cache))
    scores = [float(entry["artifact_score"]) for entry in entries]
    return CommandResult(
        data={
            "uid": uid,
            "source": "local-panel-cache",
            "character_count": len(entries),
            "artifact_count": artifact_count,
            "max_artifact_score": max(scores, default=0.0),
            "average_artifact_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
            "scoring_rule": "crit_value = crit_rate * 2 + crit_damage",
        },
        source=cache_source(cache),
    )


def list_command(args: argparse.Namespace) -> CommandResult:
    uid, _region = _uid_and_region(args)
    cache = _load(uid, args.output_dir)
    entries = sort_rank_entries(avatar_summaries(cache), args.sort)
    return CommandResult(
        data={
            "uid": uid,
            "source": "local-panel-cache",
            "sort": args.sort,
            "characters": entries,
            "count": len(entries),
            "scoring_rule": "crit_value = crit_rate * 2 + crit_damage",
        },
        source=cache_source(cache),
    )


def character_command(args: argparse.Namespace) -> CommandResult:
    uid, _region = _uid_and_region(args)
    cache = _load(uid, args.output_dir)
    panel = normalized_avatar(find_avatar(cache, args.character))
    warnings = []
    if args.nearby:
        warnings.append("nearby rank lookup is not implemented for local cache rankings")
    return CommandResult(
        data={
            "uid": uid,
            "source": "local-panel-cache",
            "character": args.character,
            "rank": {
                "name": panel["name"],
                "avatar_id": panel["avatar_id"],
                "artifact_score": panel["artifact_score"],
                "artifact_count": len(panel["artifacts"]),
                "scoring_rule": "crit_value = crit_rate * 2 + crit_damage",
                "percentile": None,
            },
            "panel": panel,
        },
        warnings=warnings,
        source=cache_source(cache),
    )


def artifact_command(args: argparse.Namespace) -> CommandResult:
    uid, _region = _uid_and_region(args)
    cache = _load(uid, args.output_dir)
    avatar = find_avatar(cache, args.character) if args.character else None
    artifacts = sorted(
        artifact_entries(cache, avatar),
        key=lambda item: _artifact_sort_value(item, args.sort),
        reverse=True,
    )
    return CommandResult(
        data={
            "uid": uid,
            "source": "local-panel-cache",
            "character": args.character,
            "sort": args.sort,
            "artifacts": artifacts,
            "count": len(artifacts),
            "scoring_rule": "crit_value = crit_rate * 2 + crit_damage",
        },
        source=cache_source(cache),
    )


def _load(uid: str, output_dir: str | None) -> dict[str, object]:
    with state_db(output_dir) as conn:
        return load_panel_cache(conn, uid)


def _artifact_sort_value(artifact: dict[str, object], sort_key: str) -> float:
    if sort_key == "crit":
        return _float_value(artifact.get("score"))
    return _substat_total(artifact, ARTIFACT_SORT_PROPS[sort_key])


def _substat_total(artifact: dict[str, object], props: set[str]) -> float:
    substats = artifact.get("substats")
    if not isinstance(substats, list):
        return 0.0
    total = 0.0
    for substat in substats:
        if not isinstance(substat, dict):
            continue
        prop = str(substat.get("appendPropId") or substat.get("prop") or "")
        if prop in props:
            total += _float_value(substat.get("statValue") or substat.get("value"))
    return total


def _float_value(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
