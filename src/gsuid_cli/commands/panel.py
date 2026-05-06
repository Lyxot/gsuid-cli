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
from gsuid_cli.commands.render_assets import fetch_render_images
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.config import resolve_paths
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.render import render_image_enabled, render_result_data, render_text_enabled
from gsuid_cli.core.state import state_db
from gsuid_cli.providers import provider_for_region
from gsuid_cli.providers.enka import EnkaProvider
from gsuid_cli.providers.public import AMBR_BASE_URL
from gsuid_cli.renderers.panel import (
    panel_artifacts_asset_urls,
    panel_asset_urls,
    panel_graduation_asset_urls,
    panel_showcase_asset_urls,
    render_panel_artifacts_library,
    render_panel_compare_cards,
    render_panel_graduation,
    render_panel_show_card,
    render_panel_showcase,
)
from gsuid_cli.renderers.panel_metrics import panel_reference_metrics
from gsuid_cli.renderers.panel_text import (
    render_panel_artifacts_text,
    render_panel_compare_text,
    render_panel_graduation_text,
    render_panel_list_text,
    render_panel_refresh_text,
    render_panel_save_text,
    render_panel_show_text,
    render_panel_showcase_text,
)

PANEL_IMAGE_WORKERS = 12

CAPABILITIES = [
    {
        "command": "panel.refresh",
        "description": "Refresh Enka showcase panel data into the local cache.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
        "cache": "use",
    },
    {
        "command": "panel.list",
        "description": "List cached character panels for a UID.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
        "cache": "off",
    },
    {
        "command": "panel.show",
        "description": "Show one cached character panel.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
        "cache": "off",
    },
    {
        "command": "panel.compare",
        "description": "Compare cached panel stats for two or more builds.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
        "cache": "off",
    },
    {
        "command": "panel.save",
        "description": "Save one cached panel as a JSON artifact.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
        "cache": "off",
    },
    {
        "command": "panel.artifacts",
        "description": "List cached artifacts for a UID.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
        "cache": "off",
    },
    {
        "command": "panel.showcase",
        "description": "Show the cached public showcase summary.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
        "cache": "off",
    },
    {
        "command": "panel.graduation",
        "description": "Summarize local cached graduation inputs and render GenshinUID-style rows.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
        "cache": "off",
    },
]


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    panel = groups.add_parser("panel", help="Manage Enka panel cache.")
    commands = panel.add_subparsers(dest="panel_command", required=True, metavar="<command>")

    refresh = commands.add_parser("refresh", help="Refresh panel data.")
    refresh.add_argument("--uid", dest="command_uid")
    refresh.add_argument("--source", choices=("auto", "enka", "mys"), default="auto")
    refresh.add_argument("--force", action="store_true")
    refresh.set_defaults(handler=refresh_command, command_name="panel.refresh")

    list_parser = commands.add_parser("list", help="List cached panels.")
    list_parser.add_argument("--uid", dest="command_uid")
    list_parser.set_defaults(handler=list_command, command_name="panel.list")

    show = commands.add_parser("show", help="Show a cached panel.")
    show.add_argument("--uid", dest="command_uid")
    show.add_argument("--character", required=True)
    show.add_argument("--constellation", type=int)
    show.add_argument("--weapon")
    show.add_argument("--artifact-source-character")
    show.set_defaults(handler=show_command, command_name="panel.show")

    compare = commands.add_parser("compare", help="Compare cached panels.")
    compare.add_argument("--uid", dest="command_uid")
    compare.add_argument("--build", action="append", required=True)
    compare.set_defaults(handler=compare_command, command_name="panel.compare")

    save = commands.add_parser("save", help="Save a cached panel JSON artifact.")
    save.add_argument("--uid", dest="command_uid")
    save.add_argument("--character", required=True)
    save.add_argument("--name", required=True)
    save.add_argument("--output")
    save.set_defaults(handler=save_command, command_name="panel.save")

    artifacts = commands.add_parser("artifacts", help="List cached artifacts.")
    artifacts.add_argument("--uid", dest="command_uid")
    artifacts.add_argument("--page", type=int, default=1)
    artifacts.set_defaults(handler=artifacts_command, command_name="panel.artifacts")

    showcase = commands.add_parser("showcase", help="Show cached showcase summary.")
    showcase.add_argument("--uid", dest="command_uid")
    showcase.set_defaults(handler=showcase_command, command_name="panel.showcase")

    graduation = commands.add_parser("graduation", help="Summarize local graduation inputs.")
    graduation.add_argument("--uid", dest="command_uid")
    graduation.set_defaults(handler=graduation_command, command_name="panel.graduation")


def refresh_command(args: argparse.Namespace) -> CommandResult:
    uid, region = _uid_and_region(args)
    source = _refresh_source(args.source)
    provider_result = _provider(args).profile(uid=uid, region=region)
    payload, warnings = _with_avatar_names(args, provider_result.data)
    with state_db(args.output_dir) as conn:
        cache = save_panel_cache(conn, uid=uid, payload=payload, source=provider_result.source)
    result = CommandResult(
        data={
            "uid": uid,
            "source": source,
            "player": player_summary(cache),
            "character_count": len(cache["avatars"]),
            "ttl": cache["ttl"],
            "cached_at": cache["fetched_at"],
            "cache": _cache_metadata(args, uid),
            "failures": [],
        },
        warnings=warnings,
        source=provider_result.source,
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
            "Panel data did not contain a renderable character panel.",
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
        unavailable_warning="{count} panel images unavailable; rendered placeholders",
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
        description="GenshinUID-style Enka character panel card",
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
        unavailable_warning="{count} panel compare images unavailable; rendered placeholders",
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
        description="GenshinUID-style Enka panel comparison",
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
        unavailable_warning="{count} panel artifact images unavailable; rendered placeholders",
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
        description="GenshinUID-style Enka artifact warehouse",
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
        unavailable_warning="{count} panel showcase images unavailable; rendered placeholders",
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
        description="GenshinUID-style Enka showcase summary",
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
        unavailable_warning="{count} panel graduation images unavailable; rendered placeholders",
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
        description="GenshinUID-style Enka graduation summary",
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


def _panel_with_weapon_effect(
    args: argparse.Namespace,
    panel: dict[str, object],
    avatar: dict[str, object],
) -> dict[str, object]:
    weapon = panel.get("weapon")
    if not isinstance(weapon, dict) or weapon.get("effect"):
        return panel
    weapon_id = str(weapon.get("item_id") or "")
    if len(weapon_id) != 5 or not weapon_id.isdigit():
        return panel
    try:
        response = HttpClient(
            timeout=args.timeout,
            cache_policy=args.cache,
            output_dir=args.output_dir,
            debug=args.debug,
        ).request_json(
            "GET",
            f"{AMBR_BASE_URL}/api/v2/chs/weapon/{weapon_id}",
            provider="ambr",
            region="cn",
            category="panel.weapon_effect",
        )
    except CliError:
        return panel
    data = response.payload.get("data")
    if not isinstance(data, dict):
        return panel
    effect = _weapon_effect_text(data.get("affix"), _weapon_affix(avatar))
    if not effect:
        return panel
    next_weapon = {**weapon, "effect": effect}
    return {**panel, "weapon": next_weapon}


def _weapon_affix(avatar: dict[str, object]) -> int:
    equips = avatar.get("equipList")
    if not isinstance(equips, list):
        return 1
    for equip in equips:
        if not isinstance(equip, dict):
            continue
        weapon = equip.get("weapon")
        if not isinstance(weapon, dict):
            continue
        affix_map = weapon.get("affixMap")
        if isinstance(affix_map, dict) and affix_map:
            return min(max(int(_number(next(iter(affix_map.values())))) + 1, 1), 5)
    return 1


def _weapon_effect_text(affix: object, rank: int) -> str | None:
    if not isinstance(affix, dict):
        return None
    first = next((item for item in affix.values() if isinstance(item, dict)), None)
    if not isinstance(first, dict):
        return None
    upgrade = first.get("upgrade")
    if not isinstance(upgrade, dict):
        return None
    text = upgrade.get(str(max(min(rank, 5), 1) - 1))
    if not isinstance(text, str):
        return None
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<.*?>", "", text)
    return text.replace("@", "").replace("#", "").strip()


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
    characters = avatar_summaries(cache)
    rows = [
        {
            "avatar_id": character["avatar_id"],
            "name": character["name"],
            "level": character["level"],
            "artifact_score": character["artifact_score"],
            "graduation_score": None,
        }
        for character in characters
    ]
    rows.sort(key=lambda row: _number(row["artifact_score"]), reverse=True)
    message = "graduation scoring requires curated per-character targets not configured here"
    result = CommandResult(
        data={
            "uid": uid,
            "characters": rows,
            "count": len(rows),
            "source_limitations": [message],
        },
        warnings=[message],
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
        description="Human-readable panel text",
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
        warnings=result.warnings,
        pagination=result.pagination,
    )


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


def _cache_metadata(args: argparse.Namespace, uid: str) -> dict[str, object]:
    return {
        "backend": "sqlite",
        "path": str(resolve_paths(args.output_dir).state),
        "table": "panel_cache",
        "key": uid,
        "status": "updated",
    }


def _with_avatar_names(
    args: argparse.Namespace,
    payload: dict[str, object],
) -> tuple[dict[str, object], list[str]]:
    avatars = payload.get("avatarInfoList")
    if not isinstance(avatars, list):
        return payload, []
    avatar_dicts = [avatar for avatar in avatars if isinstance(avatar, dict)]
    if all(avatar.get("name") or avatar.get("route") for avatar in avatar_dicts):
        return payload, []

    try:
        names = _avatar_name_index(args)
    except CliError:
        return payload, ["character name enrichment failed; use avatar ids for panel lookup"]

    enriched = []
    changed = False
    for avatar in avatar_dicts:
        item = dict(avatar)
        info = names.get(str(item.get("avatarId") or item.get("id") or ""))
        if info:
            if not item.get("name") and info.get("name"):
                item["name"] = info["name"]
                changed = True
            if not item.get("route") and info.get("route"):
                item["route"] = info["route"]
                changed = True
        enriched.append(item)
    if not changed:
        return payload, []
    new_payload = dict(payload)
    new_payload["avatarInfoList"] = enriched
    return new_payload, []


def _avatar_name_index(args: argparse.Namespace) -> dict[str, dict[str, object]]:
    response = HttpClient(
        timeout=args.timeout,
        cache_policy=args.cache,
        output_dir=args.output_dir,
        debug=args.debug,
    ).request_json(
        "GET",
        f"{AMBR_BASE_URL}/api/v2/chs/avatar",
        provider="ambr",
        region="cn",
        category="panel.character_names",
    )
    data = response.payload.get("data")
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, dict):
        return {}
    index: dict[str, dict[str, object]] = {}
    for item in items.values():
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        if item_id:
            index[item_id] = item
    return index


def _refresh_source(source: str) -> str:
    if source == "mys":
        raise CliError(
            "INVALID_ARGUMENT",
            "MYS panel refresh is not implemented; use --source enka or --source auto.",
            EXIT_INVALID_INPUT,
            {"source": source},
        )
    return "enka"


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
        description="Saved character panel",
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
