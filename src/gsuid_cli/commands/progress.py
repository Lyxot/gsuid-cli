from __future__ import annotations

import argparse

from gsuid_cli.commands.auth import _credential, _uid_and_region
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.providers import provider_for_region

CAPABILITIES = [
    {
        "command": "progress.completion",
        "description": "Show authenticated account completion summary data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "progress.exploration",
        "description": "Show authenticated world exploration data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "progress.collection",
        "description": "Show authenticated collection count data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "progress.achievements",
        "description": "Show authenticated achievement category data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "progress.achievement-guide",
        "description": "Report achievement guide lookup support status.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "progress.commission-guide",
        "description": "Report commission guide lookup support status.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "progress.gcg",
        "description": "Show authenticated Genius Invokation TCG data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "progress.gcg-deck",
        "description": "Show authenticated Genius Invokation TCG deck data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
]


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    progress = groups.add_parser("progress", help="Show authenticated progress data.")
    commands = progress.add_subparsers(dest="progress_command", required=True, metavar="<command>")

    completion = commands.add_parser("completion", help="Show account completion summary.")
    _add_uid(completion)
    completion.set_defaults(handler=completion_command, command_name="progress.completion")

    exploration = commands.add_parser("exploration", help="Show world exploration data.")
    _add_uid(exploration)
    exploration.set_defaults(handler=exploration_command, command_name="progress.exploration")

    collection = commands.add_parser("collection", help="Show collection count data.")
    _add_uid(collection)
    collection.set_defaults(handler=collection_command, command_name="progress.collection")

    achievements = commands.add_parser("achievements", help="Show achievement category data.")
    _add_uid(achievements)
    achievements.add_argument("--query")
    achievements.set_defaults(handler=achievements_command, command_name="progress.achievements")

    achievement_guide = commands.add_parser(
        "achievement-guide",
        help="Report achievement guide lookup support status.",
    )
    achievement_guide.add_argument("--query", required=True)
    achievement_guide.set_defaults(
        handler=achievement_guide_command,
        command_name="progress.achievement-guide",
    )

    commission_guide = commands.add_parser(
        "commission-guide",
        help="Report commission guide lookup support status.",
    )
    commission_guide.add_argument("--query", required=True)
    commission_guide.set_defaults(
        handler=commission_guide_command,
        command_name="progress.commission-guide",
    )

    gcg = commands.add_parser("gcg", help="Show Genius Invokation TCG data.")
    _add_uid(gcg)
    gcg.set_defaults(handler=gcg_command, command_name="progress.gcg")

    gcg_deck = commands.add_parser("gcg-deck", help="Show Genius Invokation TCG deck data.")
    _add_uid(gcg_deck)
    gcg_deck.add_argument("--deck-id", type=int)
    gcg_deck.set_defaults(handler=gcg_deck_command, command_name="progress.gcg-deck")


def completion_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    return _provider(args, region).progress_completion(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def exploration_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    return _provider(args, region).progress_exploration(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def collection_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    return _provider(args, region).progress_collection(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def achievements_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    result = _provider(args, region).progress_achievements(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    if args.query:
        achievements = result.data.get("achievements")
        if not isinstance(achievements, list):
            achievements = []
        matches = [
            item
            for item in achievements
            if isinstance(item, dict) and _matches_query(item, args.query)
        ]
        result.data["query"] = args.query
        result.data["achievements"] = matches
        result.data["count"] = len(matches)
    return result


def achievement_guide_command(args: argparse.Namespace) -> CommandResult:
    return _source_limited_guide("achievement", args.query)


def commission_guide_command(args: argparse.Namespace) -> CommandResult:
    return _source_limited_guide("commission", args.query)


def gcg_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    return _provider(args, region).progress_gcg(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def gcg_deck_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    return _provider(args, region).progress_gcg_deck(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
        deck_id=args.deck_id,
    )


def _add_uid(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--uid", dest="command_uid")


def _provider(args: argparse.Namespace, region: str):
    return provider_for_region(
        region,
        HttpClient(
            timeout=args.timeout,
            cache_policy="off",
            output_dir=args.output_dir,
            debug=args.debug,
        ),
    )


def _cookie_context(args: argparse.Namespace) -> tuple[str, str, str, str, str | None]:
    uid, region = _uid_and_region(args)
    ensure_supported_region(region)
    args.credential_kind = "cookie"
    cookie, credential_source, storage_backend = _credential(args, uid)
    return uid, region, cookie, credential_source, storage_backend


def _source_limited_guide(kind: str, query: str) -> CommandResult:
    message = f"{kind} guide data is not available from configured sources"
    return CommandResult(
        data={
            "query": query,
            "kind": kind,
            "available": False,
            "matches": [],
            "count": 0,
            "source_limitations": [message],
        },
        warnings=[message],
    )


def _matches_query(item: dict[str, object], query: str) -> bool:
    normalized = query.casefold()
    text_parts = [str(value) for value in item.values() if isinstance(value, str | int)]
    return normalized in " ".join(text_parts).casefold()
