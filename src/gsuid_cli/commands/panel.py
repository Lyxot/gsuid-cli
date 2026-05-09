from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from gsuid_cli.commands._text import safe_filename_part
from gsuid_cli.commands.account import _validate_uid
from gsuid_cli.commands.auth import _credential, _uid_and_region
from gsuid_cli.commands.panel_cache import (
    PANEL_DATA,
    artifact_entries,
    avatar_summaries,
    avatars,
    cache_source,
    find_avatar,
    load_panel_cache,
    normalized_avatar,
    player_summary,
    save_panel_cache,
)
from gsuid_cli.commands.panel_enrichment import _panel_with_weapon_effect, _with_avatar_names
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.config import resolve_paths
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.render import render_image_enabled, render_result_data, render_text_enabled
from gsuid_cli.core.state import state_db
from gsuid_cli.providers import provider_for_region
from gsuid_cli.providers.assets import fetch_render_images
from gsuid_cli.providers.enka import EnkaProvider
from gsuid_cli.renderers.panel import (
    panel_artifacts_asset_urls,
    panel_asset_urls,
    panel_graduation_asset_urls,
    panel_reference_metrics,
    panel_showcase_asset_urls,
    render_panel_artifacts_library,
    render_panel_artifacts_text,
    render_panel_compare_cards,
    render_panel_compare_text,
    render_panel_graduation,
    render_panel_graduation_text,
    render_panel_list_text,
    render_panel_refresh_text,
    render_panel_save_text,
    render_panel_show_card,
    render_panel_show_text,
    render_panel_showcase,
    render_panel_showcase_text,
)

PANEL_IMAGE_WORKERS = 12
MYS_PROP_IDS = {
    "1": "1",
    "2": "2",
    "3": "3",
    "4": "4",
    "5": "5",
    "6": "6",
    "7": "7",
    "8": "8",
    "9": "9",
    "20": "20",
    "22": "22",
    "23": "23",
    "26": "26",
    "28": "28",
    "30": "30",
    "40": "40",
    "41": "41",
    "42": "42",
    "43": "43",
    "44": "44",
    "45": "45",
    "46": "46",
    "50": "50",
    "51": "51",
    "52": "52",
    "53": "53",
    "54": "54",
    "55": "55",
    "56": "56",
    "2000": "2000",
    "2001": "2001",
    "2002": "2002",
}
MYS_PERCENT_PROP_IDS = {
    "3",
    "6",
    "9",
    "20",
    "22",
    "23",
    "26",
    "30",
    "40",
    "41",
    "42",
    "43",
    "44",
    "45",
    "46",
    "50",
    "51",
    "52",
    "53",
    "54",
    "55",
    "56",
}

CAPABILITIES = [
    {
        "command": "panel.refresh",
        "description": "刷新面板数据。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "panel.list",
        "description": "列出已缓存的面板。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "panel.show",
        "description": "显示一个已缓存的面板。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "panel.compare",
        "description": "对比已缓存的面板。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "panel.save",
        "description": "保存已缓存面板的 JSON 产物。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "panel.artifacts",
        "description": "列出已缓存的圣遗物。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "panel.showcase",
        "description": "显示已缓存的展柜汇总。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "panel.graduation",
        "description": "汇总本地毕业度数据。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
]

_HELPS = {str(c["command"]): str(c["description"]) for c in CAPABILITIES}


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    panel = groups.add_parser("panel", help="管理 Enka 面板缓存。")
    commands = panel.add_subparsers(dest="panel_command", required=True, metavar="<command>")

    refresh = commands.add_parser("refresh", help=_HELPS["panel.refresh"])
    refresh.add_argument("--uid", dest="command_uid")
    refresh.add_argument("--source", choices=("auto", "enka", "mys"), default="auto")
    refresh.add_argument("--force", action="store_true")
    refresh.set_defaults(handler=refresh_command, command_name="panel.refresh")

    list_parser = commands.add_parser("list", help=_HELPS["panel.list"])
    list_parser.add_argument("--uid", dest="command_uid")
    list_parser.set_defaults(handler=list_command, command_name="panel.list")

    show = commands.add_parser("show", help=_HELPS["panel.show"])
    show.add_argument("--uid", dest="command_uid")
    show.add_argument("--character", required=True)
    show.add_argument("--constellation", type=int)
    show.add_argument("--weapon")
    show.add_argument("--artifact-source-character")
    show.set_defaults(handler=show_command, command_name="panel.show")

    compare = commands.add_parser("compare", help=_HELPS["panel.compare"])
    compare.add_argument("--uid", dest="command_uid")
    compare.add_argument("--build", action="append", required=True)
    compare.set_defaults(handler=compare_command, command_name="panel.compare")

    save = commands.add_parser("save", help=_HELPS["panel.save"])
    save.add_argument("--uid", dest="command_uid")
    save.add_argument("--character", required=True)
    save.add_argument("--name", required=True)
    save.add_argument("--output")
    save.set_defaults(handler=save_command, command_name="panel.save")

    artifacts = commands.add_parser("artifacts", help=_HELPS["panel.artifacts"])
    artifacts.add_argument("--uid", dest="command_uid")
    artifacts.add_argument("--page", type=int, default=1)
    artifacts.set_defaults(handler=artifacts_command, command_name="panel.artifacts")

    showcase = commands.add_parser("showcase", help=_HELPS["panel.showcase"])
    showcase.add_argument("--uid", dest="command_uid")
    showcase.set_defaults(handler=showcase_command, command_name="panel.showcase")

    graduation = commands.add_parser("graduation", help=_HELPS["panel.graduation"])
    graduation.add_argument("--uid", dest="command_uid")
    graduation.set_defaults(handler=graduation_command, command_name="panel.graduation")


def refresh_command(args: argparse.Namespace) -> CommandResult:
    uid, region = _uid_and_region(args)
    cache, source, source_meta, sources, warnings, cache_status = _refresh_panel_cache(
        args,
        uid=uid,
        region=region,
    )
    result = CommandResult(
        data={
            "uid": uid,
            "source": source,
            "requested_source": args.source,
            "player": player_summary(cache),
            "character_count": len(cache["avatars"]),
            "ttl": cache["ttl"],
            "cached_at": cache["fetched_at"],
            "cache": _cache_metadata(args, uid, status=cache_status),
            "failures": [],
        },
        warnings=warnings,
        source=source_meta,
        sources=sources,
    )
    return _panel_text_result(
        args,
        result,
        name="panel/refresh-text",
        filename=f"panel-refresh_{_safe_filename(uid)}.txt",
        content=render_panel_refresh_text(result.data),
    )


def list_command(args: argparse.Namespace) -> CommandResult:
    uid, _region = _uid_and_region(args)
    cache = _load(uid, args.output_dir)
    result = CommandResult(
        data={
            "uid": uid,
            "player": player_summary(cache),
            "characters": avatar_summaries(cache),
            "count": len(cache["avatars"]),
            "cached_at": cache["fetched_at"],
        },
        source=cache_source(cache),
    )
    return _panel_text_result(
        args,
        result,
        name="panel/list-text",
        filename=f"panel-list_{_safe_filename(uid)}.txt",
        content=render_panel_list_text(result.data),
    )


def showcase_command(args: argparse.Namespace) -> CommandResult:
    uid, _region = _uid_and_region(args)
    cache = _load(uid, args.output_dir)
    result = CommandResult(
        data={
            "uid": uid,
            "player": player_summary(cache),
            "showcase": avatar_summaries(cache),
            "count": len(cache["avatars"]),
            "cached_at": cache["fetched_at"],
        },
        source=cache_source(cache),
    )
    if not render_image_enabled(args):
        return _panel_text_result(
            args,
            result,
            name="panel/showcase-text",
            filename=f"panel-showcase_{_safe_filename(uid)}.txt",
            content=render_panel_showcase_text(result.data),
        )
    rendered = _showcase_render_result(args, result=result, uid=uid, cache=cache)
    return _panel_text_result(
        args,
        rendered,
        name="panel/showcase-text",
        filename=f"panel-showcase_{_safe_filename(uid)}.txt",
        content=render_panel_showcase_text(result.data),
    )


def show_command(args: argparse.Namespace) -> CommandResult:
    _validate_panel_overrides(args)
    uid, _region = _uid_and_region(args)
    cache = _load(uid, args.output_dir)
    avatar = find_avatar(cache, args.character)
    warnings = _override_warnings(args)
    panel = normalized_avatar(avatar)
    if render_image_enabled(args) or render_text_enabled(args):
        panel = _panel_with_weapon_effect(args, panel, avatar)
    data = {
        "uid": uid,
        "character": args.character,
        "panel": panel,
        "cached_at": cache["fetched_at"],
    }
    if render_text_enabled(args):
        data["reference"] = panel_reference_metrics(avatar, panel)
    overrides = _requested_overrides(args)
    if overrides:
        data["requested_overrides"] = overrides
    result = CommandResult(data=data, warnings=warnings, source=cache_source(cache))
    if not render_image_enabled(args):
        return _panel_text_result(
            args,
            result,
            name="panel/show-text",
            filename=f"panel-show_{_safe_filename(uid)}_{_safe_filename(args.character)}.txt",
            content=render_panel_show_text(result.data),
        )
    rendered = _show_render_result(args, result=result, uid=uid, cache=cache, avatar=avatar)
    return _panel_text_result(
        args,
        rendered,
        name="panel/show-text",
        filename=f"panel-show_{_safe_filename(uid)}_{_safe_filename(args.character)}.txt",
        content=render_panel_show_text(result.data),
    )


def _show_render_result(
    args: argparse.Namespace,
    *,
    result: CommandResult,
    uid: str,
    cache: dict[str, object],
    avatar: dict[str, object],
) -> CommandResult:
    panel = result.data.get("panel")
    if not isinstance(panel, dict):
        raise CliError(
            "UPSTREAM_INVALID_RESPONSE",
            "面板数据中不包含可渲染的角色面板。",
            EXIT_INVALID_INPUT,
            {"command": "panel.show"},
            source=result.source,
        )
    panel = _panel_with_weapon_effect(args, panel, avatar)
    asset_images, image_warnings = fetch_render_images(
        args,
        panel_asset_urls(avatar, panel),
        provider="panel",
        region="cn",
        category="panel.show.asset",
            unavailable_warning="{count} 个角色面板图片不可用，已使用占位图",
        max_workers=PANEL_IMAGE_WORKERS,
    )
    png = render_panel_show_card(
        uid=uid,
        avatar=avatar,
        panel=panel,
        cached_at=str(cache.get("fetched_at") or ""),
        asset_images=asset_images,
    )
    character_name = str(panel.get("name") or result.data.get("character") or "panel")
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="panel/show",
        filename=f"panel-show_{_safe_filename(uid)}_{_safe_filename(character_name)}.png",
        media_type="image/png",
        content=png,
        description="角色面板卡片图片",
        kind="image",
    )
    render_data = {
        "uid": uid,
        "character": character_name,
        "render": "panel/show",
        "artifact_sha256": artifact["sha256"],
    }
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *image_warnings],
        pagination=result.pagination,
    )


def _compare_render_result(
    args: argparse.Namespace,
    *,
    result: CommandResult,
    render_builds: list[dict[str, object]],
) -> CommandResult:
    urls: list[str] = []
    for build in render_builds:
        avatar = build["avatar"]
        panel = build["panel"]
        if not isinstance(avatar, dict) or not isinstance(panel, dict):
            continue
        panel = _panel_with_weapon_effect(args, panel, avatar)
        build["panel"] = panel
        urls.extend(panel_asset_urls(avatar, panel))

    asset_images, image_warnings = fetch_render_images(
        args,
        urls,
        provider="panel",
        region="cn",
        category="panel.compare.asset",
        unavailable_warning="{count} 个面板对比图片不可用，已使用占位图",
        max_workers=PANEL_IMAGE_WORKERS,
    )

    cards: list[bytes] = []
    for build in render_builds:
        avatar = build["avatar"]
        panel = build["panel"]
        cache = build["cache"]
        if (
            not isinstance(avatar, dict)
            or not isinstance(panel, dict)
            or not isinstance(cache, dict)
        ):
            continue
        cards.append(
            render_panel_show_card(
                uid=str(build["uid"]),
                avatar=avatar,
                panel=panel,
                cached_at=str(cache.get("fetched_at") or ""),
                asset_images=asset_images,
            )
        )

    png = render_panel_compare_cards(cards)
    names = "_".join(_safe_filename(str(build["character"])) for build in render_builds)
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="panel/compare",
        filename=f"panel-compare_{_safe_filename(names)}.png",
        media_type="image/png",
        content=png,
        description="面板对比图片",
        kind="image",
    )
    render_data = {
        "render": "panel/compare",
        "build_count": len(render_builds),
        "artifact_sha256": artifact["sha256"],
    }
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *image_warnings],
        pagination=result.pagination,
    )


def _artifacts_render_result(
    args: argparse.Namespace,
    *,
    result: CommandResult,
    uid: str,
    cache: dict[str, object],
) -> CommandResult:
    raw_avatars = avatars(cache)
    panels = [normalized_avatar(avatar) for avatar in raw_avatars]
    asset_images, image_warnings = fetch_render_images(
        args,
        panel_artifacts_asset_urls(raw_avatars, panels, page=args.page),
        provider="panel",
        region="cn",
        category="panel.artifacts.asset",
        unavailable_warning="{count} 个圣遗物图片不可用，已使用占位图",
        max_workers=PANEL_IMAGE_WORKERS,
    )
    png = render_panel_artifacts_library(
        uid=uid,
        avatars=raw_avatars,
        panels=panels,
        page=args.page,
        asset_images=asset_images,
    )
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="panel/artifacts",
        filename=f"panel-artifacts_{_safe_filename(uid)}_p{args.page}.png",
        media_type="image/png",
        content=png,
        description="圣遗物仓库图片",
        kind="image",
    )
    render_data = {
        "uid": uid,
        "page": args.page,
        "render": "panel/artifacts",
        "artifact_sha256": artifact["sha256"],
    }
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *image_warnings],
        pagination=result.pagination,
    )


def _showcase_render_result(
    args: argparse.Namespace,
    *,
    result: CommandResult,
    uid: str,
    cache: dict[str, object],
) -> CommandResult:
    raw_avatars = avatars(cache)
    panels = [normalized_avatar(avatar) for avatar in raw_avatars]
    asset_images, image_warnings = fetch_render_images(
        args,
        panel_showcase_asset_urls(raw_avatars, panels),
        provider="panel",
        region="cn",
        category="panel.showcase.asset",
        unavailable_warning="{count} 个展柜图片不可用，已使用占位图",
        max_workers=PANEL_IMAGE_WORKERS,
    )
    png = render_panel_showcase(
        uid=uid,
        player=player_summary(cache),
        avatars=raw_avatars,
        panels=panels,
        asset_images=asset_images,
    )
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="panel/showcase",
        filename=f"panel-showcase_{_safe_filename(uid)}.png",
        media_type="image/png",
        content=png,
        description="展柜汇总图片",
        kind="image",
    )
    render_data = {
        "uid": uid,
        "render": "panel/showcase",
        "artifact_sha256": artifact["sha256"],
    }
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *image_warnings],
        pagination=result.pagination,
    )


def _graduation_render_result(
    args: argparse.Namespace,
    *,
    result: CommandResult,
    uid: str,
    region: str,
    cache: dict[str, object],
) -> CommandResult:
    raw_avatars = avatars(cache)
    panels = [normalized_avatar(avatar) for avatar in raw_avatars]
    player, title_warnings = _graduation_title_player(args, uid=uid, region=region, cache=cache)
    asset_images, image_warnings = fetch_render_images(
        args,
        panel_graduation_asset_urls(raw_avatars, panels),
        provider="panel",
        region="cn",
        category="panel.graduation.asset",
        unavailable_warning="{count} 个毕业度图片不可用，已使用占位图",
        max_workers=PANEL_IMAGE_WORKERS,
    )
    png = render_panel_graduation(
        uid=uid,
        player=player,
        avatars=raw_avatars,
        panels=panels,
        asset_images=asset_images,
    )
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="panel/graduation",
        filename=f"panel-graduation_{_safe_filename(uid)}.png",
        media_type="image/png",
        content=png,
        description="毕业度汇总图片",
        kind="image",
    )
    render_data = {
        "uid": uid,
        "render": "panel/graduation",
        "artifact_sha256": artifact["sha256"],
    }
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *title_warnings, *image_warnings],
        pagination=result.pagination,
    )


def _graduation_title_player(
    args: argparse.Namespace,
    *,
    uid: str,
    region: str,
    cache: dict[str, object],
) -> tuple[dict[str, object], list[str]]:
    player = player_summary(cache)
    credential_args = argparse.Namespace(**vars(args))
    credential_args.credential_kind = "cookie"
    try:
        cookie, credential_source, storage_backend = _credential(credential_args, uid)
        provider = provider_for_region(
            region,
            HttpClient(
                timeout=args.timeout,
                cache_policy="off",
                output_dir=args.output_dir,
                debug=args.debug,
            ),
        )
        summary_result = provider.player_summary(
            uid=uid,
            cookie=cookie,
            region=region,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )
    except CliError as exc:
        if exc.code == "AUTH_REQUIRED":
            return player, []
        return player, [
            "panel graduation title MYS enrichment unavailable; rendered Enka title data"
        ]

    summary = _dict(summary_result.data.get("summary"))
    stats = _dict(summary.get("stats"))
    challenge = _dict(summary.get("challenge"))
    enriched = dict(player)
    _merge_spiral_abyss(enriched, stats.get("spiral_abyss"))
    role_combat = _dict(challenge.get("role_combat")) or _dict(stats.get("role_combat"))
    if role_combat:
        enriched["theater"] = role_combat
    hard_challenge = _dict(challenge.get("hard_challenge")) or _dict(stats.get("hard_challenge"))
    if hard_challenge:
        enriched["stygian_index"] = hard_challenge.get("difficulty")
        enriched["hard_name"] = hard_challenge.get("name")
    return enriched, list(summary_result.warnings)


def _merge_spiral_abyss(player: dict[str, object], value: object) -> None:
    if not isinstance(value, str):
        return
    match = re.fullmatch(r"\s*(\d+)-(\d+)\s*", value)
    if match is None:
        return
    player["abyss_floor"] = int(match.group(1))
    player["abyss_chamber"] = int(match.group(2))


def compare_command(args: argparse.Namespace) -> CommandResult:
    default_uid, _region = _uid_and_region(args)
    build_specs = args.build or []
    if len(build_specs) < 2:
        raise CliError(
            "INVALID_ARGUMENT",
            "panel compare requires at least two --build values",
            EXIT_INVALID_INPUT,
            {"build_count": len(build_specs)},
        )
    render_builds = [_load_render_build(spec, default_uid, args.output_dir) for spec in build_specs]
    builds = [_build_data(build) for build in render_builds]
    baseline = builds[0]
    result = CommandResult(
        data={
            "baseline": baseline,
            "builds": builds,
            "deltas": [_build_delta(baseline, build) for build in builds[1:]],
        },
        source=baseline["source"],
    )
    if not render_image_enabled(args):
        return _panel_text_result(
            args,
            result,
            name="panel/compare-text",
            filename=f"panel-compare_{safe_filename_part('_'.join(build_specs))}.txt",
            content=render_panel_compare_text(result.data),
        )
    rendered = _compare_render_result(args, result=result, render_builds=render_builds)
    return _panel_text_result(
        args,
        rendered,
        name="panel/compare-text",
        filename=f"panel-compare_{safe_filename_part('_'.join(build_specs))}.txt",
        content=render_panel_compare_text(result.data),
    )


def save_command(args: argparse.Namespace) -> CommandResult:
    uid, _region = _uid_and_region(args)
    cache = _load(uid, args.output_dir)
    avatar = find_avatar(cache, args.character)
    data = {
        "uid": uid,
        "name": args.name,
        "character": args.character,
        "panel": normalized_avatar(avatar),
        "cached_at": cache["fetched_at"],
    }
    content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    artifact = _write_panel(args, uid, args.name, content)
    result = CommandResult(
        data={
            "uid": uid,
            "saved": True,
            "name": args.name,
            "character": data["panel"]["name"],
            "path": artifact["path"],
        },
        artifacts=[artifact],
        source=cache_source(cache),
    )
    return _panel_text_result(
        args,
        result,
        name="panel/save-text",
        filename=f"panel-save_{_safe_filename(uid)}_{_safe_filename(args.name)}.txt",
        content=render_panel_save_text(result.data),
    )


def artifacts_command(args: argparse.Namespace) -> CommandResult:
    _validate_page(args.page)
    uid, _region = _uid_and_region(args)
    cache = _load(uid, args.output_dir)
    artifacts = _artifact_entries_by_score(cache)
    page_size = 20
    start = (args.page - 1) * page_size
    page_items = artifacts[start : start + page_size]
    total_pages = (len(artifacts) + page_size - 1) // page_size if artifacts else 0
    result = CommandResult(
        data={
            "uid": uid,
            "page": args.page,
            "page_size": page_size,
            "total_pages": total_pages,
            "artifacts": page_items,
            "count": len(page_items),
            "total_count": len(artifacts),
            "scoring_rule": "crit_value = crit_rate * 2 + crit_damage",
        },
        source=cache_source(cache),
    )
    if not render_image_enabled(args):
        return _panel_text_result(
            args,
            result,
            name="panel/artifacts-text",
            filename=f"panel-artifacts_{_safe_filename(uid)}_p{args.page}.txt",
            content=render_panel_artifacts_text(result.data),
        )
    rendered = _artifacts_render_result(args, result=result, uid=uid, cache=cache)
    return _panel_text_result(
        args,
        rendered,
        name="panel/artifacts-text",
        filename=f"panel-artifacts_{_safe_filename(uid)}_p{args.page}.txt",
        content=render_panel_artifacts_text(result.data),
    )


def graduation_command(args: argparse.Namespace) -> CommandResult:
    uid, region = _uid_and_region(args)
    cache = _load(uid, args.output_dir)
    raw_avatars = avatars(cache)
    rows = [_graduation_row(raw_avatar) for raw_avatar in raw_avatars]
    rows.sort(key=lambda row: _number(row["artifact_score"]), reverse=True)
    result = CommandResult(
        data={
            "uid": uid,
            "characters": rows,
            "count": len(rows),
        },
        source=cache_source(cache),
    )
    if not render_image_enabled(args):
        return _panel_text_result(
            args,
            result,
            name="panel/graduation-text",
            filename=f"panel-graduation_{_safe_filename(uid)}.txt",
            content=render_panel_graduation_text(result.data),
        )
    rendered = _graduation_render_result(
        args,
        result=result,
        uid=uid,
        region=region,
        cache=cache,
    )
    return _panel_text_result(
        args,
        rendered,
        name="panel/graduation-text",
        filename=f"panel-graduation_{_safe_filename(uid)}.txt",
        content=render_panel_graduation_text(result.data),
    )


def _graduation_row(avatar: dict[str, object]) -> dict[str, object]:
    panel = normalized_avatar(avatar)
    metrics = panel_reference_metrics(avatar, panel)
    percent = metrics.get("graduation_percent")
    return {
        "avatar_id": panel["avatar_id"],
        "name": panel["name"],
        "level": panel["level"],
        "artifact_score": panel["artifact_score"],
        "graduation_score": round(_number(percent), 2) if _is_number(percent) else None,
        "reference": metrics,
    }


def _artifact_entries_by_score(cache: dict[str, object]) -> list[dict[str, object]]:
    artifacts = artifact_entries(cache)
    artifacts.sort(key=lambda item: _number(item.get("score")), reverse=True)
    return artifacts


def _panel_text_result(
    args: argparse.Namespace,
    result: CommandResult,
    *,
    name: str,
    filename: str,
    content: str,
) -> CommandResult:
    if not render_text_enabled(args):
        return result
    text_artifact = ArtifactManager(args.request_id, args.output_dir).write_text(
        name=name,
        filename=filename,
        content=content,
        description="面板文本",
        kind="text",
    )
    artifacts = [*result.artifacts, text_artifact]
    if any(artifact.get("kind") == "image" for artifact in result.artifacts):
        data = {**result.data, "text_artifact_sha256": text_artifact["sha256"]}
    else:
        data = render_result_data(
            args,
            result.data,
            {"render": name, "artifact_sha256": text_artifact["sha256"]},
        )
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        sources=result.sources,
        warnings=result.warnings,
        pagination=result.pagination,
    )


def _refresh_panel_cache(
    args: argparse.Namespace,
    *,
    uid: str,
    region: str,
) -> tuple[
    dict[str, object],
    str,
    dict[str, object] | None,
    list[dict[str, object]],
    list[str],
    str,
]:
    requested = str(args.source)
    if requested == "enka":
        return _save_refresh_result(
            args,
            uid=uid,
            result=_provider(args).profile(uid=uid, region=region),
            source="enka",
        )
    if requested == "mys":
        mys_result = _mys_panel_profile(args, uid=uid, region=region)
        existing = _existing_enka_cache(uid, args.output_dir)
        if existing is not None:
            merged_result, source, changed = _merge_panel_result(
                CommandResult(data=_panel_payload(existing), source=cache_source(existing)),
                mys_result,
            )
            if not changed:
                existing_source = str(existing.get("source_provider") or "enka")
                warning = "保留已有面板缓存，MYS 备份未发现等级、命座或武器差异。"
                return (
                    existing,
                    existing_source,
                    cache_source(existing),
                    _result_source_list(mys_result),
                    [*mys_result.warnings, warning],
                    "unchanged",
                )
            return _save_refresh_result(args, uid=uid, result=merged_result, source=source)
        return _save_refresh_result(args, uid=uid, result=mys_result, source="mys")

    enka_result: CommandResult | None = None
    enka_error: CliError | None = None
    mys_result: CommandResult | None = None
    mys_error: CliError | None = None

    try:
        enka_result = _provider(args).profile(uid=uid, region=region)
    except CliError as exc:
        enka_error = exc
    try:
        mys_result = _mys_panel_profile(args, uid=uid, region=region)
    except CliError as exc:
        mys_error = exc

    if enka_result is not None and mys_result is None:
        warnings = [*enka_result.warnings]
        if mys_error is not None and mys_error.code != "AUTH_REQUIRED":
            warnings.append(f"MYS 备份不可用，已保留 Enka 面板: {mys_error.message}")
        return _save_refresh_result(
            args,
            uid=uid,
            result=CommandResult(
                data=enka_result.data,
                source=enka_result.source,
                sources=enka_result.sources,
                warnings=warnings,
                artifacts=enka_result.artifacts,
                pagination=enka_result.pagination,
            ),
            source="enka",
        )
    if enka_result is None and mys_result is not None:
        warnings = [*mys_result.warnings]
        if enka_error is not None:
            warnings.append(f"Enka 面板不可用，已使用 MYS 备份: {enka_error.message}")
        return _save_refresh_result(
            args,
            uid=uid,
            result=CommandResult(
                data=mys_result.data,
                source=mys_result.source,
                sources=mys_result.sources,
                warnings=warnings,
                artifacts=mys_result.artifacts,
                pagination=mys_result.pagination,
            ),
            source="mys",
        )
    if enka_result is not None and mys_result is not None:
        merged_result, source, changed = _merge_panel_result(enka_result, mys_result)
        if changed:
            return _save_refresh_result(args, uid=uid, result=merged_result, source=source)
        return _save_refresh_result(
            args,
            uid=uid,
            result=CommandResult(
                data=enka_result.data,
                source=enka_result.source,
                sources=[*enka_result.sources, *_result_source_list(mys_result)],
                warnings=[*enka_result.warnings, *mys_result.warnings],
                artifacts=enka_result.artifacts,
                pagination=enka_result.pagination,
            ),
            source="enka",
        )

    if enka_error is not None:
        raise enka_error
    if mys_error is not None:
        raise mys_error
    raise CliError(
        "UPSTREAM_INVALID_RESPONSE",
        "没有任何面板数据源返回数据。",
        EXIT_UPSTREAM,
        {"uid": uid, "source": args.source},
    )


def _save_refresh_result(
    args: argparse.Namespace,
    *,
    uid: str,
    result: CommandResult,
    source: str,
) -> tuple[
    dict[str, object],
    str,
    dict[str, object] | None,
    list[dict[str, object]],
    list[str],
    str,
]:
    payload, name_warnings = _with_avatar_names(args, result.data)
    with state_db(args.output_dir) as conn:
        cache = save_panel_cache(conn, uid=uid, payload=payload, source=result.source)
    return (
        cache,
        source,
        result.source,
        result.sources,
        [*result.warnings, *name_warnings],
        "updated",
    )


def _existing_enka_cache(uid: str, output_dir: str | None) -> dict[str, object] | None:
    try:
        cache = _load(uid, output_dir)
    except CliError as exc:
        if exc.code == "NO_RESULT":
            return None
        raise
    return cache if str(cache.get("source_provider") or "") in {"enka", "enka+mys"} else None


def _merge_panel_result(
    base_result: CommandResult,
    mys_result: CommandResult,
) -> tuple[CommandResult, str, bool]:
    payload, added, replaced = _merge_panel_payload(base_result.data, mys_result.data)
    changed = bool(added or replaced)
    if not changed:
        return (
            CommandResult(
                data=base_result.data,
                source=base_result.source,
                sources=[*base_result.sources, *_result_source_list(mys_result)],
                warnings=[*base_result.warnings, *mys_result.warnings],
                artifacts=base_result.artifacts,
                pagination=base_result.pagination,
            ),
            str((base_result.source or {}).get("provider") or "enka"),
            False,
        )
    warnings = [*base_result.warnings, *mys_result.warnings]
    if added:
        warnings.append(f"MYS 补充角色: {'、'.join(added)}")
    if replaced:
        warnings.append(f"MYS 替换过期角色: {'；'.join(replaced)}")
    return (
        CommandResult(
            data=payload,
            source=_combined_panel_source(base_result.source, mys_result.source),
            sources=[*_result_source_list(base_result), *_result_source_list(mys_result)],
            warnings=warnings,
            artifacts=base_result.artifacts,
            pagination=base_result.pagination,
        ),
        "enka+mys",
        True,
    )


def _merge_panel_payload(
    base_data: dict[str, object],
    mys_data: dict[str, object],
) -> tuple[dict[str, object], list[str], list[str]]:
    base_payload = _panel_payload(base_data)
    mys_payload = _panel_payload(mys_data)
    base_avatars = _list_of_dicts(base_payload.get("avatarInfoList"))
    mys_avatars = _avatar_map(_list_of_dicts(mys_payload.get("avatarInfoList")))
    merged_avatars: list[dict[str, object]] = []
    added: list[str] = []
    replaced: list[str] = []
    seen: set[str] = set()

    for avatar in base_avatars:
        avatar_id = _avatar_key(avatar)
        mys_avatar = mys_avatars.get(avatar_id)
        if avatar_id and mys_avatar is not None:
            seen.add(avatar_id)
            stale_reasons = _avatar_stale_reasons(avatar, mys_avatar)
            if stale_reasons:
                merged_avatars.append(mys_avatar)
                replaced.append(
                    f"{_avatar_display_name(mys_avatar, fallback=avatar_id)}（"
                    f"{'，'.join(stale_reasons)}）"
                )
                continue
        merged_avatars.append(avatar)

    for avatar_id, avatar in mys_avatars.items():
        if avatar_id in seen:
            continue
        merged_avatars.append(avatar)
        added.append(_avatar_display_name(avatar, fallback=avatar_id))

    payload = {**base_payload}
    if not _dict(payload.get("playerInfo")):
        payload["playerInfo"] = mys_payload.get("playerInfo")
    if payload.get("ttl") in (None, ""):
        payload["ttl"] = mys_payload.get("ttl")
    payload["avatarInfoList"] = merged_avatars
    return payload, added, replaced


def _panel_payload(data: dict[str, object]) -> dict[str, object]:
    if isinstance(data.get("avatarInfoList"), list):
        return dict(data)
    raw = _dict(data.get("raw"))
    payload = dict(raw) if raw else {}
    payload["uid"] = payload.get("uid") or data.get("uid")
    payload["ttl"] = payload.get("ttl") if payload.get("ttl") is not None else data.get("ttl")
    payload["playerInfo"] = (
        payload.get("playerInfo") or data.get("player_info") or data.get("playerInfo") or {}
    )
    payload["avatarInfoList"] = (
        payload.get("avatarInfoList") or data.get("avatars") or data.get("avatarInfoList") or []
    )
    return payload


def _avatar_map(raw_avatars: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    for avatar in raw_avatars:
        avatar_id = _avatar_key(avatar)
        if avatar_id:
            rows[avatar_id] = avatar
    return rows


def _avatar_key(avatar: dict[str, object]) -> str:
    return str(avatar.get("avatarId") or avatar.get("id") or "")


def _avatar_stale_reasons(
    enka_avatar: dict[str, object],
    mys_avatar: dict[str, object],
) -> list[str]:
    enka = _avatar_compare_row(enka_avatar)
    mys = _avatar_compare_row(mys_avatar)
    reasons: list[str] = []
    for field, label in (
        ("level", "等级"),
        ("constellation", "命座"),
        ("weapon_name", "武器"),
        ("weapon_level", "武器等级"),
    ):
        left = enka.get(field)
        right = mys.get(field)
        if left in (None, "") or right in (None, "") or left == right:
            continue
        reasons.append(f"{label}不一致: Enka {left}，MYS {right}")
    return reasons


def _avatar_compare_row(avatar: dict[str, object]) -> dict[str, object]:
    panel = normalized_avatar(avatar)
    weapon = _dict(panel.get("weapon"))
    return {
        "name": panel.get("name"),
        "level": panel.get("level"),
        "constellation": panel.get("constellation"),
        "weapon_name": weapon.get("name"),
        "weapon_level": weapon.get("level"),
    }


def _avatar_display_name(avatar: dict[str, object], *, fallback: str) -> str:
    name = normalized_avatar(avatar).get("name")
    return str(name or fallback)


def _combined_panel_source(
    base_source: dict[str, object] | None,
    mys_source: dict[str, object] | None,
) -> dict[str, object]:
    source = dict(mys_source or base_source or {})
    source["provider"] = "enka+mys"
    source.setdefault("region", "cn")
    source["cached"] = False
    return source


def _result_source_list(result: CommandResult) -> list[dict[str, object]]:
    if result.source is None:
        return [*result.sources]
    return [*result.sources, result.source]


def _mys_panel_profile(args: argparse.Namespace, *, uid: str, region: str) -> CommandResult:
    credential_args = argparse.Namespace(**vars(args))
    credential_args.credential_kind = "cookie"
    cookie, credential_source, storage_backend = _credential(credential_args, uid)
    provider = provider_for_region(
        region,
        HttpClient(
            timeout=args.timeout,
            cache_policy=_refresh_cache_policy(args),
            output_dir=args.output_dir,
            debug=args.debug,
        ),
    )
    summary_result = provider.player_summary(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    character_ids = _summary_character_ids(summary_result.data)
    if not character_ids:
        characters_result = provider.player_characters(
            uid=uid,
            cookie=cookie,
            region=region,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )
        character_ids = _character_ids(characters_result.data.get("characters"))
    details_result = provider.character_details(
        uid=uid,
        cookie=cookie,
        region=region,
        character_ids=character_ids,
        category="panel.refresh.mys",
    )
    return CommandResult(
        data=_mys_panel_payload(uid, summary_result.data, details_result.data),
        source=details_result.source,
        warnings=[*summary_result.warnings, *details_result.warnings],
    )


def _summary_character_ids(data: dict[str, object]) -> list[int]:
    summary = _dict(data.get("summary"))
    return _character_ids(summary.get("avatars"))


def _character_ids(value: object) -> list[int]:
    ids: list[int] = []
    if not isinstance(value, list):
        return ids
    for item in value:
        if not isinstance(item, dict):
            continue
        character_id = _int(item.get("id") or item.get("avatar_id") or item.get("avatarId"))
        if character_id is not None:
            ids.append(character_id)
    return ids


def _mys_panel_payload(
    uid: str,
    summary_data: dict[str, object],
    details_data: dict[str, object],
) -> dict[str, object]:
    summary = _dict(summary_data.get("summary"))
    details = details_data.get("details")
    return {
        "uid": uid,
        "ttl": 300,
        "playerInfo": _mys_player_info(uid, summary),
        "avatarInfoList": [_mys_avatar(detail) for detail in details if isinstance(detail, dict)]
        if isinstance(details, list)
        else [],
    }


def _mys_player_info(uid: str, summary: dict[str, object]) -> dict[str, object]:
    role = _dict(summary.get("role"))
    stats = _dict(summary.get("stats"))
    return {
        "uid": uid,
        "nickname": role.get("nickname"),
        "level": role.get("level"),
        "region": role.get("region"),
        "worldLevel": stats.get("world_level") or stats.get("worldLevel"),
        "finishAchievementNum": stats.get("achievement_number") or stats.get("achievements"),
    }


def _mys_avatar(detail: dict[str, object]) -> dict[str, object]:
    base = _dict(detail.get("base")) or detail
    avatar_id = base.get("id") or detail.get("id") or detail.get("avatarId")
    return {
        "avatarId": avatar_id,
        "name": base.get("name") or detail.get("name"),
        "level": base.get("level") or detail.get("level"),
        "talentIdList": _active_talent_ids(detail.get("constellations")),
        "fetterInfo": {"expLevel": base.get("fetter") or detail.get("fetter")},
        "skillLevelMap": _skill_level_map(detail.get("skills")),
        "fightPropMap": _mys_fight_props(detail),
        "equipList": [_mys_weapon(detail.get("weapon")), *_mys_artifacts(detail.get("relics"))],
    }


def _active_talent_ids(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    return [
        talent_id
        for item in value
        if isinstance(item, dict) and item.get("is_actived") and (talent_id := _int(item.get("id")))
    ]


def _skill_level_map(value: object) -> dict[str, int]:
    levels: dict[str, int] = {}
    if not isinstance(value, list):
        return levels
    for item in value:
        if not isinstance(item, dict):
            continue
        skill_id = item.get("skill_id") or item.get("id")
        level = _int(item.get("level"))
        if skill_id not in (None, "") and level is not None:
            levels[str(skill_id)] = level
    return levels


def _mys_fight_props(detail: dict[str, object]) -> dict[str, object]:
    props: dict[str, object] = {}
    for group in ("base_properties", "extra_properties", "element_properties"):
        value = detail.get(group)
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            prop_id = MYS_PROP_IDS.get(str(item.get("property_type") or ""))
            if not prop_id:
                continue
            props[prop_id] = _mys_prop_value(item.get("final"), prop_id, fight_prop=True)
    return props


def _mys_weapon(value: object) -> dict[str, object]:
    weapon = _dict(value)
    main = _dict(weapon.get("main_property"))
    sub = _dict(weapon.get("sub_property"))
    stats = [_mys_stat(main, value_key="final")]
    if sub:
        stats.append(_mys_stat(sub, value_key="final"))
    return {
        "itemId": weapon.get("id"),
        "weapon": {"level": weapon.get("level"), "affixMap": {"1": _weapon_affix(weapon)}},
        "flat": {
            "itemType": "ITEM_WEAPON",
            "name": weapon.get("name"),
            "rankLevel": weapon.get("rarity"),
            "weaponStats": [stat for stat in stats if stat],
        },
    }


def _mys_artifacts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [_mys_artifact(item) for item in value if isinstance(item, dict)]


def _mys_artifact(relic: dict[str, object]) -> dict[str, object]:
    main = _dict(relic.get("main_property"))
    return {
        "itemId": relic.get("id"),
        "reliquary": {"level": (_int(relic.get("level")) or 0) + 1},
        "flat": {
            "itemType": "ITEM_RELIQUARY",
            "name": relic.get("name"),
            "icon": relic.get("icon") or _artifact_icon(relic.get("name")),
            "equipType": _artifact_slot(relic.get("pos_name")),
            "rankLevel": relic.get("rarity"),
            "setName": _dict(relic.get("set")).get("name"),
            "reliquaryMainstat": _mys_stat(main, value_key="value", main=True),
            "reliquarySubstats": [
                stat
                for stat in (
                    _mys_stat(item, value_key="value")
                    for item in _list_of_dicts(relic.get("sub_property_list"))
                )
                if stat
            ],
        },
    }


def _mys_stat(
    item: dict[str, object],
    *,
    value_key: str,
    main: bool = False,
) -> dict[str, object] | None:
    prop_id = MYS_PROP_IDS.get(str(item.get("property_type") or ""))
    if not prop_id:
        return None
    key = "mainPropId" if main else "appendPropId"
    return {
        key: prop_id,
        "statName": _prop_name(prop_id),
        "statValue": _mys_prop_value(item.get(value_key), prop_id, fight_prop=False),
    }


def _mys_prop_value(value: object, prop_id: str, *, fight_prop: bool) -> float:
    text = str(value or "").strip()
    is_percent = text.endswith("%")
    number = _number(text.removesuffix("%"))
    if fight_prop and (is_percent or prop_id in MYS_PERCENT_PROP_IDS):
        return round(number / 100, 6)
    return number


def _weapon_affix(weapon: dict[str, object]) -> int:
    affix = _int(weapon.get("affix_level"))
    if affix is None:
        return 0
    return max(affix - 1, 0)


def _artifact_slot(value: object) -> object:
    return {
        "生之花": "EQUIP_BRACER",
        "死之羽": "EQUIP_NECKLACE",
        "时之沙": "EQUIP_SHOES",
        "空之杯": "EQUIP_RING",
        "理之冠": "EQUIP_DRESS",
    }.get(str(value), value)


def _artifact_icon(name: object) -> str | None:
    if name in (None, ""):
        return None
    names = _text_map("icon2Name_mapping_6.5.0.json")
    for icon, mapped_name in names.items():
        if mapped_name == name:
            return str(icon)
    return None


def _prop_name(prop_id: str) -> str | None:
    value = _text_map("propId2Name_mapping.json").get(prop_id)
    return str(value) if value not in (None, "") else None


def _text_map(filename: str) -> dict[str, object]:
    path = PANEL_DATA / filename
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _provider(args: argparse.Namespace) -> EnkaProvider:
    return EnkaProvider(
        HttpClient(
            timeout=args.timeout,
            cache_policy=_refresh_cache_policy(args),
            output_dir=args.output_dir,
            debug=args.debug,
        )
    )


def _refresh_cache_policy(args: argparse.Namespace) -> str:
    if args.cache in {"only", "off"}:
        return str(args.cache)
    if args.force or args.cache == "use":
        return "refresh"
    return str(args.cache)


def _cache_metadata(
    args: argparse.Namespace, uid: str, *, status: str = "updated"
) -> dict[str, object]:
    return {
        "backend": "sqlite",
        "path": str(resolve_paths(args.output_dir).state),
        "table": "panel_cache",
        "key": uid,
        "status": status,
    }


def _load(uid: str, output_dir: str | None) -> dict[str, object]:
    with state_db(output_dir) as conn:
        return load_panel_cache(conn, uid)


def _load_render_build(spec: str, default_uid: str, output_dir: str | None) -> dict[str, object]:
    uid, character = _parse_build_spec(spec, default_uid)
    cache = _load(uid, output_dir)
    avatar = find_avatar(cache, character)
    return {
        "uid": uid,
        "character": character,
        "cache": cache,
        "avatar": avatar,
        "panel": normalized_avatar(avatar),
        "source": cache_source(cache),
    }


def _build_data(build: dict[str, object]) -> dict[str, object]:
    return {
        "uid": build["uid"],
        "character": build["character"],
        "panel": build["panel"],
        "source": build["source"],
    }


def _parse_build_spec(spec: str, default_uid: str) -> tuple[str, str]:
    if ":" in spec:
        uid, character = spec.split(":", 1)
        uid = _validate_uid(uid)
    else:
        uid, character = default_uid, spec
    if not character:
        raise CliError(
            "INVALID_ARGUMENT",
            "build spec must include a character name or avatar id",
            EXIT_INVALID_INPUT,
            {"build": spec},
        )
    return uid, character


def _build_delta(baseline: dict[str, object], build: dict[str, object]) -> dict[str, object]:
    base_panel = baseline["panel"]
    compare_panel = build["panel"]
    if not isinstance(base_panel, dict) or not isinstance(compare_panel, dict):
        return {"uid": build["uid"], "character": build["character"], "fight_props": {}}
    base_props = base_panel.get("fight_props")
    compare_props = compare_panel.get("fight_props")
    if not isinstance(base_props, dict) or not isinstance(compare_props, dict):
        prop_delta = {}
    else:
        prop_delta = {
            key: _number(compare_props[key]) - _number(base_props[key])
            for key in sorted(compare_props.keys() & base_props.keys())
            if _is_number(compare_props[key]) and _is_number(base_props[key])
        }
    return {
        "uid": build["uid"],
        "character": compare_panel.get("name") or build["character"],
        "artifact_score": round(
            _number(compare_panel.get("artifact_score"))
            - _number(base_panel.get("artifact_score")),
            2,
        ),
        "fight_props": prop_delta,
    }


def _validate_panel_overrides(args: argparse.Namespace) -> None:
    if args.constellation is not None and not 0 <= args.constellation <= 6:
        raise CliError(
            "INVALID_ARGUMENT",
            "constellation must be between 0 and 6",
            EXIT_INVALID_INPUT,
            {"constellation": args.constellation},
        )


def _validate_page(page: int) -> None:
    if page < 1:
        raise CliError(
            "INVALID_ARGUMENT",
            "page must be greater than 0",
            EXIT_INVALID_INPUT,
            {"page": page},
        )


def _requested_overrides(args: argparse.Namespace) -> dict[str, object]:
    overrides: dict[str, object] = {}
    if args.constellation is not None:
        overrides["constellation"] = args.constellation
    if args.weapon:
        overrides["weapon"] = args.weapon
    if args.artifact_source_character:
        overrides["artifact_source_character"] = args.artifact_source_character
    return overrides


def _override_warnings(args: argparse.Namespace) -> list[str]:
    if _requested_overrides(args):
        return ["typed panel overrides are recorded but not applied yet"]
    return []


def _write_panel(
    args: argparse.Namespace,
    uid: str,
    name: str,
    content: bytes,
) -> dict[str, object]:
    filename = f"panel_{uid}_{_safe_filename(name)}.json"
    if args.output:
        path = Path(args.output).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return _artifact_for_path(path, content)
    return ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="panel",
        filename=filename,
        media_type="application/json",
        content=content,
        description="已保存的角色面板",
        kind="json",
    )


def _artifact_for_path(path: Path, content: bytes) -> dict[str, object]:
    return {
        "kind": "json",
        "name": "panel",
        "path": str(path),
        "media_type": "application/json",
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "description": "Saved character panel",
    }


def _safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)[:80]


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _number(value: object) -> float:
    return float(value) if _is_number(value) else 0.0


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}
