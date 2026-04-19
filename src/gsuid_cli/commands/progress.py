from __future__ import annotations

import argparse
import hashlib
import re
from collections.abc import Mapping

from gsuid_cli.commands.auth import _credential, _uid_and_region
from gsuid_cli.commands.player import _player_title_render_context
from gsuid_cli.commands.render_assets import fetch_render_images
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.errors import EXIT_NO_RESULT, EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.providers import provider_for_region
from gsuid_cli.renderers.player.summary import player_summary_mys_icon_urls
from gsuid_cli.renderers.progress.achievements import (
    progress_achievement_image_urls,
    render_progress_achievements_card,
)
from gsuid_cli.renderers.progress.collection import (
    render_progress_collection_card,
    render_progress_completion_card,
    render_progress_exploration_card,
)
from gsuid_cli.renderers.progress.gcg import (
    has_gcg_covers,
    progress_gcg_deck_image_urls,
    progress_gcg_image_urls,
    render_progress_gcg_card,
    render_progress_gcg_deck_card,
)

PROGRESS_IMAGE_WORKERS = 12

CAPABILITIES = [
    {
        "command": "progress.completion",
        "description": "Show authenticated account completion summary data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "off",
    },
    {
        "command": "progress.exploration",
        "description": "Show authenticated world exploration data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "off",
    },
    {
        "command": "progress.collection",
        "description": "Show authenticated collection count data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "off",
    },
    {
        "command": "progress.achievements",
        "description": "Show authenticated achievement category data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
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
        "render": ["data", "image", "both"],
        "cache": "off",
    },
    {
        "command": "progress.gcg-deck",
        "description": "Show authenticated Genius Invokation TCG deck data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
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
    provider = _provider(args, region)
    result = provider.progress_completion(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    if args.render == "data":
        return result
    return _completion_render_result(args, result=result, uid=uid, region=region)


def exploration_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    provider = _provider(args, region)
    result = provider.progress_exploration(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    if args.render == "data":
        return result
    completion_result = provider.progress_completion(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    return _exploration_render_result(
        args,
        provider=provider,
        result=result,
        completion_result=completion_result,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def collection_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    provider = _provider(args, region)
    result = provider.progress_collection(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    if args.render == "data":
        return result
    return _collection_render_result(
        args,
        provider=provider,
        result=result,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def achievements_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    provider = _provider(args, region)
    result = provider.progress_achievements(
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
    if args.render == "data":
        return result
    return _achievements_render_result(
        args,
        provider=provider,
        result=result,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def achievement_guide_command(args: argparse.Namespace) -> CommandResult:
    return _source_limited_guide("achievement", args.query)


def commission_guide_command(args: argparse.Namespace) -> CommandResult:
    return _source_limited_guide("commission", args.query)


def gcg_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    provider = _provider(args, region)
    result = provider.progress_gcg(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    if args.render == "data":
        return result
    return _gcg_render_result(args, result=result, uid=uid, region=region)


def gcg_deck_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    provider = _provider(args, region)
    result = provider.progress_gcg_deck(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
        deck_id=args.deck_id,
    )
    if args.render == "data":
        return result
    return _gcg_deck_render_result(
        args,
        provider=provider,
        result=result,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
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


def _completion_render_result(
    args: argparse.Namespace,
    *,
    result: CommandResult,
    uid: str,
    region: str,
) -> CommandResult:
    completion = _mapping_data(result, "completion", "progress.completion")
    images, image_warnings = fetch_render_images(
        args,
        player_summary_mys_icon_urls(completion),
        provider="mys",
        region=region,
        category="progress.completion.icon",
        unavailable_warning="{count} progress completion icons unavailable; rendered placeholders",
        max_workers=PROGRESS_IMAGE_WORKERS,
    )
    png = render_progress_completion_card(completion=completion, asset_images=images)
    artifact = _write_image_artifact(
        args,
        name="progress/completion",
        filename=f"progress-completion_{_safe_filename(uid)}.png",
        description="GenshinUID-style completion card",
        content=png,
    )
    render_data = {
        "uid": uid,
        "render": "progress/completion",
        "exploration_count": completion.get("exploration_count"),
        "artifact_sha256": artifact["sha256"],
    }
    data = {**result.data, **render_data} if args.render == "both" else render_data
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *image_warnings],
        pagination=result.pagination,
    )


def _exploration_render_result(
    args: argparse.Namespace,
    *,
    provider,
    result: CommandResult,
    completion_result: CommandResult,
    uid: str,
    region: str,
    cookie: str,
    credential_source: str,
    storage_backend: str | None,
) -> CommandResult:
    _mapping_data(result, "exploration", "progress.exploration")
    completion = _mapping_data(completion_result, "completion", "progress.exploration.completion")
    summary, title_images, title_avatar_url, title_warnings = _title_context(
        args,
        provider=provider,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
        category_prefix="progress.exploration",
    )
    png = render_progress_exploration_card(
        uid=uid,
        summary=summary,
        completion=completion,
        asset_images=title_images,
        title_avatar_url=title_avatar_url,
    )
    artifact = _write_image_artifact(
        args,
        name="progress/exploration",
        filename=f"progress-exploration_{_safe_filename(uid)}.png",
        description="GenshinUID-style exploration progress card",
        content=png,
    )
    render_data = {
        "uid": uid,
        "render": "progress/exploration",
        "artifact_sha256": artifact["sha256"],
    }
    data = {**result.data, **render_data} if args.render == "both" else render_data
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *completion_result.warnings, *title_warnings],
        pagination=result.pagination,
    )


def _collection_render_result(
    args: argparse.Namespace,
    *,
    provider,
    result: CommandResult,
    uid: str,
    region: str,
    cookie: str,
    credential_source: str,
    storage_backend: str | None,
) -> CommandResult:
    collection = _mapping_data(result, "collection", "progress.collection")
    summary, title_images, title_avatar_url, title_warnings = _title_context(
        args,
        provider=provider,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
        category_prefix="progress.collection",
    )
    png = render_progress_collection_card(
        uid=uid,
        summary=summary,
        collection=collection,
        asset_images=title_images,
        title_avatar_url=title_avatar_url,
    )
    artifact = _write_image_artifact(
        args,
        name="progress/collection",
        filename=f"progress-collection_{_safe_filename(uid)}.png",
        description="GenshinUID-style collection progress card",
        content=png,
    )
    render_data = {
        "uid": uid,
        "render": "progress/collection",
        "artifact_sha256": artifact["sha256"],
    }
    data = {**result.data, **render_data} if args.render == "both" else render_data
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *title_warnings],
        pagination=result.pagination,
    )


def _achievements_render_result(
    args: argparse.Namespace,
    *,
    provider,
    result: CommandResult,
    uid: str,
    region: str,
    cookie: str,
    credential_source: str,
    storage_backend: str | None,
) -> CommandResult:
    achievements = _mapping_sequence(result.data.get("achievements"))
    summary, title_images, title_avatar_url, title_warnings = _title_context(
        args,
        provider=provider,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
        category_prefix="progress.achievements",
    )
    achievement_images, achievement_warnings = fetch_render_images(
        args,
        progress_achievement_image_urls(achievements),
        provider="mys",
        region=region,
        category="progress.achievements.icon",
        unavailable_warning="{count} achievement icons unavailable; rendered placeholders",
        max_workers=PROGRESS_IMAGE_WORKERS,
    )
    png = render_progress_achievements_card(
        uid=uid,
        summary=summary,
        achievements=achievements,
        asset_images={**title_images, **achievement_images},
        title_avatar_url=title_avatar_url,
    )
    artifact = _write_image_artifact(
        args,
        name="progress/achievements",
        filename=f"progress-achievements_{_safe_filename(uid)}.png",
        description="GenshinUID-style achievements card",
        content=png,
    )
    render_data = {
        "uid": uid,
        "render": "progress/achievements",
        "count": len(achievements),
        "artifact_sha256": artifact["sha256"],
    }
    data = {**result.data, **render_data} if args.render == "both" else render_data
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *title_warnings, *achievement_warnings],
        pagination=result.pagination,
    )


def _gcg_render_result(
    args: argparse.Namespace,
    *,
    result: CommandResult,
    uid: str,
    region: str,
) -> CommandResult:
    gcg = _mapping_data(result, "gcg", "progress.gcg")
    if not has_gcg_covers(gcg):
        raise CliError(
            "NO_RESULT",
            "GCG image render requires activated cover cards.",
            EXIT_NO_RESULT,
            {"uid": uid},
            source=result.source,
        )
    images, image_warnings = fetch_render_images(
        args,
        progress_gcg_image_urls(gcg),
        provider="mys",
        region=region,
        category="progress.gcg.card",
        unavailable_warning="{count} GCG card images unavailable; rendered placeholders",
        max_workers=PROGRESS_IMAGE_WORKERS,
    )
    png = render_progress_gcg_card(uid=uid, gcg=gcg, asset_images=images)
    artifact = _write_image_artifact(
        args,
        name="progress/gcg",
        filename=f"progress-gcg_{_safe_filename(uid)}.png",
        description="GenshinUID-style GCG overview card",
        content=png,
    )
    render_data = {
        "uid": uid,
        "render": "progress/gcg",
        "deck_count": gcg.get("deck_count"),
        "artifact_sha256": artifact["sha256"],
    }
    data = {**result.data, **render_data} if args.render == "both" else render_data
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *image_warnings],
        pagination=result.pagination,
    )


def _gcg_deck_render_result(
    args: argparse.Namespace,
    *,
    provider,
    result: CommandResult,
    uid: str,
    region: str,
    cookie: str,
    credential_source: str,
    storage_backend: str | None,
) -> CommandResult:
    deck = _first_mapping(result.data.get("decks"))
    if not deck:
        raise CliError(
            "NO_RESULT",
            "No GCG deck matched the request.",
            EXIT_NO_RESULT,
            {"uid": uid, "deck_id": result.data.get("deck_id")},
            source=result.source,
        )
    summary, title_images, title_avatar_url, title_warnings = _title_context(
        args,
        provider=provider,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
        category_prefix="progress.gcg-deck",
    )
    card_images, card_warnings = fetch_render_images(
        args,
        progress_gcg_deck_image_urls(deck),
        provider="mys",
        region=region,
        category="progress.gcg-deck.card",
        unavailable_warning="{count} GCG deck card images unavailable; rendered placeholders",
        max_workers=PROGRESS_IMAGE_WORKERS,
    )
    png = render_progress_gcg_deck_card(
        uid=uid,
        summary=summary,
        deck=deck,
        asset_images={**title_images, **card_images},
        title_avatar_url=title_avatar_url,
    )
    artifact = _write_image_artifact(
        args,
        name="progress/gcg-deck",
        filename=f"progress-gcg-deck_{_safe_filename(uid)}.png",
        description="GenshinUID-style GCG deck card",
        content=png,
    )
    render_data = {
        "uid": uid,
        "render": "progress/gcg-deck",
        "deck_id": deck.get("id", result.data.get("deck_id")),
        "deck_name": deck.get("name"),
        "artifact_sha256": artifact["sha256"],
    }
    data = {**result.data, **render_data} if args.render == "both" else render_data
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *title_warnings, *card_warnings],
        pagination=result.pagination,
    )


def _title_context(
    args: argparse.Namespace,
    *,
    provider,
    uid: str,
    region: str,
    cookie: str,
    credential_source: str,
    storage_backend: str | None,
    category_prefix: str,
) -> tuple[Mapping[str, object], dict[str, bytes], str | None, list[str]]:
    return _player_title_render_context(
        args,
        provider=provider,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
        category_prefix=category_prefix,
    )


def _write_image_artifact(
    args: argparse.Namespace,
    *,
    name: str,
    filename: str,
    description: str,
    content: bytes,
) -> dict[str, object]:
    return ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name=name,
        filename=filename,
        media_type="image/png",
        content=content,
        description=description,
        kind="image",
    )


def _mapping_data(result: CommandResult, field: str, command: str) -> Mapping[str, object]:
    value = result.data.get(field)
    if isinstance(value, Mapping):
        return value
    raise CliError(
        "UPSTREAM_INVALID_RESPONSE",
        f"Provider returned {command} data without a renderable {field}.",
        EXIT_UPSTREAM,
        {"command": command},
        source=result.source,
    )


def _mapping_sequence(value: object) -> list[Mapping[str, object]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _first_mapping(value: object) -> Mapping[str, object]:
    values = _mapping_sequence(value)
    return values[0] if values else {}


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    if safe:
        return safe[:80]
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]
