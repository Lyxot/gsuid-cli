from __future__ import annotations

import argparse
from collections.abc import Mapping

from gsuid_cli.commands._shared import (
    _add_uid,
    _cookie_context,
    _mapping_data,
    _provider,
    _safe_filename,
    _write_image_artifact,
)
from gsuid_cli.commands.player import _player_title_render_context
from gsuid_cli.commands.public_data._common import _provider as _public_provider
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.errors import EXIT_NO_RESULT, CliError
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.render import render_image_enabled, render_result_data, render_text_enabled
from gsuid_cli.providers.assets import fetch_render_images
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
from gsuid_cli.renderers.progress.text import (
    render_progress_achievements_text,
    render_progress_collection_text,
    render_progress_completion_text,
    render_progress_exploration_text,
    render_progress_gcg_deck_text,
    render_progress_gcg_text,
    render_progress_guide_status_text,
)

PROGRESS_IMAGE_WORKERS = 12

CAPABILITIES = [
    {
        "command": "progress.completion",
        "description": "显示账号完成度汇总。",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "progress.exploration",
        "description": "显示世界探索数据。",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "progress.collection",
        "description": "显示收集进度数据。",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "progress.achievements",
        "description": "显示成就分类数据。",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "progress.achievement-guide",
        "description": "查找成就攻略数据。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "progress.commission-guide",
        "description": "查找委托攻略数据。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "progress.gcg",
        "description": "显示七圣召唤数据。",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "progress.gcg-deck",
        "description": "显示七圣召唤卡组数据。",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
]

_HELPS = {str(c["command"]): str(c["description"]) for c in CAPABILITIES}


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    progress = groups.add_parser("progress", help="显示进度数据。")
    commands = progress.add_subparsers(dest="progress_command", required=True, metavar="<command>")

    completion = commands.add_parser("completion", help=_HELPS["progress.completion"])
    _add_uid(completion)
    completion.set_defaults(handler=completion_command, command_name="progress.completion")

    exploration = commands.add_parser("exploration", help=_HELPS["progress.exploration"])
    _add_uid(exploration)
    exploration.set_defaults(handler=exploration_command, command_name="progress.exploration")

    collection = commands.add_parser("collection", help=_HELPS["progress.collection"])
    _add_uid(collection)
    collection.set_defaults(handler=collection_command, command_name="progress.collection")

    achievements = commands.add_parser("achievements", help=_HELPS["progress.achievements"])
    _add_uid(achievements)
    achievements.add_argument("--query")
    achievements.set_defaults(handler=achievements_command, command_name="progress.achievements")

    achievement_guide = commands.add_parser(
        "achievement-guide",
        help=_HELPS["progress.achievement-guide"],
    )
    achievement_guide.add_argument("--query", required=True)
    achievement_guide.set_defaults(
        handler=achievement_guide_command,
        command_name="progress.achievement-guide",
    )

    commission_guide = commands.add_parser(
        "commission-guide",
        help=_HELPS["progress.commission-guide"],
    )
    commission_guide.add_argument("--query", required=True)
    commission_guide.set_defaults(
        handler=commission_guide_command,
        command_name="progress.commission-guide",
    )

    gcg = commands.add_parser("gcg", help=_HELPS["progress.gcg"])
    _add_uid(gcg)
    gcg.set_defaults(handler=gcg_command, command_name="progress.gcg")

    gcg_deck = commands.add_parser("gcg-deck", help=_HELPS["progress.gcg-deck"])
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
    if not (render_image_enabled(args) or render_text_enabled(args)):
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
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return result
    completion_result = None
    if render_image_enabled(args):
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
    if not (render_image_enabled(args) or render_text_enabled(args)):
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
    if not (render_image_enabled(args) or render_text_enabled(args)):
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
    result = _public_provider(args).achievement_guide(query=args.query)
    if not render_text_enabled(args):
        return result
    return _guide_render_result(args, result, "achievement")


def commission_guide_command(args: argparse.Namespace) -> CommandResult:
    result = _public_provider(args).commission_guide(query=args.query)
    if not render_text_enabled(args):
        return result
    return _guide_render_result(args, result, "commission")


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
    if not (render_image_enabled(args) or render_text_enabled(args)):
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
    if not (render_image_enabled(args) or render_text_enabled(args)):
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
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data = {"uid": uid, "exploration_count": completion.get("exploration_count")}
    if render_image_enabled(args):
        images, image_warnings = fetch_render_images(
            args,
            player_summary_mys_icon_urls(completion),
            provider="mys",
            region=region,
            category="progress.completion.icon",
            unavailable_warning=("{count} 个探索完成度图标不可用，已使用占位图"),
            max_workers=PROGRESS_IMAGE_WORKERS,
        )
        png = render_progress_completion_card(completion=completion, asset_images=images)
        image_artifact = _write_image_artifact(
            args,
            name="progress/completion",
            filename=f"progress-completion_{_safe_filename(uid)}.png",
            description="探索完成度卡片图片",
            content=png,
        )
        artifacts.append(image_artifact)
        warnings.extend(image_warnings)
        render_data.update(
            {
                "render": "progress/completion",
                "artifact_sha256": image_artifact["sha256"],
            }
        )
    if render_text_enabled(args):
        text_artifact = _write_text_artifact(
            args,
            name="progress/completion-text",
            filename=f"progress-completion_{_safe_filename(uid)}.txt",
            content=render_progress_completion_text(uid=uid, completion=completion),
            description="探索完成度文本",
        )
        artifacts.append(text_artifact)
        _record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
        pagination=result.pagination,
    )


def _exploration_render_result(
    args: argparse.Namespace,
    *,
    provider,
    result: CommandResult,
    completion_result: CommandResult | None,
    uid: str,
    region: str,
    cookie: str,
    credential_source: str,
    storage_backend: str | None,
) -> CommandResult:
    exploration = _mapping_data(result, "exploration", "progress.exploration")
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data: dict[str, object] = {"uid": uid}
    if render_image_enabled(args):
        if completion_result is None:
            raise AssertionError("completion_result is required for exploration image render")
        completion = _mapping_data(
            completion_result,
            "completion",
            "progress.exploration.completion",
        )
        summary, title_images, title_avatar_url, title_warnings = _player_title_render_context(
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
        image_artifact = _write_image_artifact(
            args,
            name="progress/exploration",
            filename=f"progress-exploration_{_safe_filename(uid)}.png",
            description="世界探索进度卡片图片",
            content=png,
        )
        artifacts.append(image_artifact)
        warnings.extend([*completion_result.warnings, *title_warnings])
        render_data.update(
            {
                "render": "progress/exploration",
                "artifact_sha256": image_artifact["sha256"],
            }
        )
    if render_text_enabled(args):
        text_artifact = _write_text_artifact(
            args,
            name="progress/exploration-text",
            filename=f"progress-exploration_{_safe_filename(uid)}.txt",
            content=render_progress_exploration_text(uid=uid, exploration=exploration),
            description="世界探索进度文本",
        )
        artifacts.append(text_artifact)
        _record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
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
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data: dict[str, object] = {"uid": uid}
    if render_image_enabled(args):
        summary, title_images, title_avatar_url, title_warnings = _player_title_render_context(
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
        image_artifact = _write_image_artifact(
            args,
            name="progress/collection",
            filename=f"progress-collection_{_safe_filename(uid)}.png",
            description="收集进度卡片图片",
            content=png,
        )
        artifacts.append(image_artifact)
        warnings.extend(title_warnings)
        render_data.update(
            {
                "render": "progress/collection",
                "artifact_sha256": image_artifact["sha256"],
            }
        )
    if render_text_enabled(args):
        text_artifact = _write_text_artifact(
            args,
            name="progress/collection-text",
            filename=f"progress-collection_{_safe_filename(uid)}.txt",
            content=render_progress_collection_text(uid=uid, collection=collection),
            description="收集进度文本",
        )
        artifacts.append(text_artifact)
        _record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
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
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data: dict[str, object] = {"uid": uid, "count": len(achievements)}
    if render_image_enabled(args):
        summary, title_images, title_avatar_url, title_warnings = _player_title_render_context(
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
            unavailable_warning="{count} 个成就图标不可用，已使用占位图",
            max_workers=PROGRESS_IMAGE_WORKERS,
        )
        png = render_progress_achievements_card(
            uid=uid,
            summary=summary,
            achievements=achievements,
            asset_images={**title_images, **achievement_images},
            title_avatar_url=title_avatar_url,
        )
        image_artifact = _write_image_artifact(
            args,
            name="progress/achievements",
            filename=f"progress-achievements_{_safe_filename(uid)}.png",
            description="成就分类进度卡片图片",
            content=png,
        )
        artifacts.append(image_artifact)
        warnings.extend([*title_warnings, *achievement_warnings])
        render_data.update(
            {
                "render": "progress/achievements",
                "artifact_sha256": image_artifact["sha256"],
            }
        )
    if render_text_enabled(args):
        text_artifact = _write_text_artifact(
            args,
            name="progress/achievements-text",
            filename=f"progress-achievements_{_safe_filename(uid)}.txt",
            content=render_progress_achievements_text(
                uid=uid,
                achievements=achievements,
                query=result.data.get("query"),
            ),
            description="成就分类进度文本",
        )
        artifacts.append(text_artifact)
        _record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
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
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data: dict[str, object] = {"uid": uid, "deck_count": gcg.get("deck_count")}
    if render_image_enabled(args):
        if not has_gcg_covers(gcg):
            raise CliError(
                "NO_RESULT",
                "七圣召唤图片渲染需要已启用的卡组封面。",
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
            unavailable_warning="{count} 个七圣召唤卡片图片不可用，已使用占位图",
            max_workers=PROGRESS_IMAGE_WORKERS,
        )
        png = render_progress_gcg_card(uid=uid, gcg=gcg, asset_images=images)
        image_artifact = _write_image_artifact(
            args,
            name="progress/gcg",
            filename=f"progress-gcg_{_safe_filename(uid)}.png",
            description="七圣召唤概览卡片图片",
            content=png,
        )
        artifacts.append(image_artifact)
        warnings.extend(image_warnings)
        render_data.update(
            {
                "render": "progress/gcg",
                "artifact_sha256": image_artifact["sha256"],
            }
        )
    if render_text_enabled(args):
        text_artifact = _write_text_artifact(
            args,
            name="progress/gcg-text",
            filename=f"progress-gcg_{_safe_filename(uid)}.txt",
            content=render_progress_gcg_text(uid=uid, gcg=gcg),
            description="七圣召唤进度文本",
        )
        artifacts.append(text_artifact)
        _record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
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
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data: dict[str, object] = {
        "uid": uid,
        "deck_id": deck.get("id", result.data.get("deck_id")),
        "deck_name": deck.get("name"),
    }
    if render_image_enabled(args):
        if not deck:
            raise CliError(
                "NO_RESULT",
                "没有匹配请求的七圣召唤卡组。",
                EXIT_NO_RESULT,
                {"uid": uid, "deck_id": result.data.get("deck_id")},
                source=result.source,
            )
        summary, title_images, title_avatar_url, title_warnings = _player_title_render_context(
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
            unavailable_warning="{count} 个七圣召唤卡组图片不可用，已使用占位图",
            max_workers=PROGRESS_IMAGE_WORKERS,
        )
        png = render_progress_gcg_deck_card(
            uid=uid,
            summary=summary,
            deck=deck,
            asset_images={**title_images, **card_images},
            title_avatar_url=title_avatar_url,
        )
        image_artifact = _write_image_artifact(
            args,
            name="progress/gcg-deck",
            filename=f"progress-gcg-deck_{_safe_filename(uid)}.png",
            description="七圣召唤卡组卡片图片",
            content=png,
        )
        artifacts.append(image_artifact)
        warnings.extend([*title_warnings, *card_warnings])
        render_data.update(
            {
                "render": "progress/gcg-deck",
                "artifact_sha256": image_artifact["sha256"],
            }
        )
    if render_text_enabled(args):
        text_artifact = _write_text_artifact(
            args,
            name="progress/gcg-deck-text",
            filename=f"progress-gcg-deck_{_safe_filename(uid)}.txt",
            content=render_progress_gcg_deck_text(uid=uid, data=result.data),
            description="七圣召唤卡组进度文本",
        )
        artifacts.append(text_artifact)
        _record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
        pagination=result.pagination,
    )


def _guide_render_result(
    args: argparse.Namespace,
    result: CommandResult,
    kind: str,
) -> CommandResult:
    text_artifact = _write_text_artifact(
        args,
        name=f"progress/{kind}-guide-text",
        filename=f"progress-{kind}-guide.txt",
        content=render_progress_guide_status_text(result.data),
        description=f" {kind} 攻略支持状态文本",
    )
    data = render_result_data(
        args,
        result.data,
        {
            "render": f"progress/{kind}-guide-text",
            "artifact_sha256": text_artifact["sha256"],
        },
    )
    return CommandResult(
        data=data,
        artifacts=[text_artifact],
        source=result.source,
        warnings=result.warnings,
        pagination=result.pagination,
    )


def _write_text_artifact(
    args: argparse.Namespace,
    *,
    name: str,
    filename: str,
    content: str,
    description: str,
) -> dict[str, object]:
    return ArtifactManager(args.request_id, args.output_dir).write_text(
        name=name,
        filename=filename,
        content=content,
        description=description,
        kind="text",
    )


def _record_text_artifact(
    render_data: dict[str, object],
    text_artifact: Mapping[str, object],
    *,
    image_enabled: bool,
) -> None:
    if image_enabled:
        render_data["text_artifact_sha256"] = text_artifact["sha256"]
        return
    render_data.update(
        {
            "render": text_artifact["name"],
            "artifact_sha256": text_artifact["sha256"],
        }
    )


def _mapping_sequence(value: object) -> list[Mapping[str, object]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _first_mapping(value: object) -> Mapping[str, object]:
    values = _mapping_sequence(value)
    return values[0] if values else {}
