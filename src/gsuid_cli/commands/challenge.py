from __future__ import annotations

import argparse
from collections.abc import Mapping

from gsuid_cli.commands._shared import (
    _add_uid,
    _cookie_context,
    _mapping_data,
    _provider,
    _safe_filename,
)
from gsuid_cli.commands.player import (
    ENKA_UI_BASE,
    _player_profile_image_assets,
    _player_profile_title_avatar_url,
    _summary_role_avatar_url,
)
from gsuid_cli.commands.render_assets import fetch_render_images
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, EXIT_NO_RESULT, CliError
from gsuid_cli.core.models import CommandResult
from gsuid_cli.renderers.challenge.abyss import (
    challenge_abyss_image_urls,
    render_challenge_abyss_card,
)
from gsuid_cli.renderers.challenge.hard import (
    challenge_hard_image_urls,
    render_challenge_hard_card,
)
from gsuid_cli.renderers.challenge.theater import (
    challenge_theater_image_urls,
    render_challenge_theater_card,
)

CHALLENGE_IMAGE_WORKERS = 12

CAPABILITIES = [
    {
        "command": "challenge.abyss",
        "description": "Show authenticated Spiral Abyss data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "off",
    },
    {
        "command": "challenge.theater",
        "description": "Show authenticated Imaginarium Theater data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "off",
    },
    {
        "command": "challenge.hard",
        "description": "Show authenticated Stygian Onslaught hard challenge data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "off",
    },
    {
        "command": "challenge.hard-rank",
        "description": "Report hard challenge ranking support status.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
]


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    challenge = groups.add_parser("challenge", help="Show authenticated challenge data.")
    commands = challenge.add_subparsers(
        dest="challenge_command", required=True, metavar="<command>"
    )

    abyss = commands.add_parser("abyss", help="Show Spiral Abyss data.")
    _add_uid(abyss)
    _add_season(abyss)
    abyss.add_argument("--floor", type=int)
    abyss.set_defaults(handler=abyss_command, command_name="challenge.abyss")

    theater = commands.add_parser("theater", help="Show Imaginarium Theater data.")
    _add_uid(theater)
    _add_season(theater)
    theater.set_defaults(handler=theater_command, command_name="challenge.theater")

    hard = commands.add_parser("hard", help="Show hard challenge data.")
    _add_uid(hard)
    _add_season(hard)
    hard.set_defaults(handler=hard_command, command_name="challenge.hard")

    hard_rank = commands.add_parser(
        "hard-rank",
        help="Report hard challenge ranking support status.",
    )
    hard_rank.set_defaults(handler=hard_rank_command, command_name="challenge.hard-rank")


def abyss_command(args: argparse.Namespace) -> CommandResult:
    _validate_floor(args.floor)
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    provider = _provider(args, region)
    result = provider.challenge_abyss(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
        season=args.season,
        floor=args.floor,
    )
    if args.render == "data":
        return result
    return _abyss_render_result(
        args,
        provider=provider,
        result=result,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def theater_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    provider = _provider(args, region)
    result = provider.challenge_theater(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
        season=args.season,
    )
    if args.render == "data":
        return result
    return _theater_render_result(
        args,
        provider=provider,
        result=result,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def hard_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    provider = _provider(args, region)
    result = provider.challenge_hard(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
        season=args.season,
    )
    if args.render == "data":
        return result
    return _hard_render_result(
        args,
        provider=provider,
        result=result,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def hard_rank_command(_args: argparse.Namespace) -> CommandResult:
    message = "hard challenge global ranking is not available from configured sources"
    return CommandResult(
        data={
            "available": False,
            "entries": [],
            "count": 0,
            "source_limitations": [message],
        },
        warnings=[message],
    )


def _add_season(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--season", choices=("current", "previous"), default="current")


def _validate_floor(floor: int | None) -> None:
    if floor is None:
        return
    if floor not in {9, 10, 11, 12}:
        raise CliError(
            "INVALID_ARGUMENT",
            "floor must be one of 9, 10, 11, or 12",
            EXIT_INVALID_INPUT,
            {"floor": floor},
        )


def _abyss_render_result(
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
    abyss = _mapping_data(result, "abyss", "challenge.abyss")
    if not _has_abyss_floor_data(abyss):
        raise CliError(
            "NO_RESULT",
            "Abyss image render requires at least one challenge floor.",
            EXIT_NO_RESULT,
            {
                "uid": uid,
                "season": result.data.get("season"),
                "floor": result.data.get("floor"),
            },
            source=result.source,
        )
    summary, title_images, avatar_url, title_warnings = _challenge_title_context(
        args,
        provider,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    images, image_warnings = fetch_render_images(
        args,
        challenge_abyss_image_urls(abyss, summary, _fetchable_title_avatar_url(avatar_url)),
        provider="mys",
        region=region,
        category="challenge.abyss.image",
        unavailable_warning="{count} challenge abyss images unavailable; rendered placeholders",
        max_workers=CHALLENGE_IMAGE_WORKERS,
    )
    png = render_challenge_abyss_card(
        uid=uid,
        abyss=abyss,
        summary=summary,
        asset_images={**images, **title_images},
        avatar_url=avatar_url,
    )
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="challenge/abyss",
        filename=f"challenge-abyss_{_safe_filename(uid)}.png",
        media_type="image/png",
        content=png,
        description="GenshinUID-style Spiral Abyss card",
        kind="image",
    )
    render_data = {
        "uid": uid,
        "render": "challenge/abyss",
        "floor_count": abyss.get("floor_count"),
        "artifact_sha256": artifact["sha256"],
    }
    data = {**result.data, **render_data} if args.render == "both" else render_data
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *title_warnings, *image_warnings],
        pagination=result.pagination,
    )


def _theater_render_result(
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
    theater = _mapping_data(result, "theater", "challenge.theater")
    summary, title_images, avatar_url, title_warnings = _challenge_title_context(
        args,
        provider,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    images, image_warnings = fetch_render_images(
        args,
        challenge_theater_image_urls(theater, summary, _fetchable_title_avatar_url(avatar_url)),
        provider="mys",
        region=region,
        category="challenge.theater.image",
        unavailable_warning="{count} challenge theater images unavailable; rendered placeholders",
        max_workers=CHALLENGE_IMAGE_WORKERS,
    )
    png = render_challenge_theater_card(
        uid=uid,
        theater=theater,
        summary=summary,
        asset_images={**images, **title_images},
        avatar_url=avatar_url,
    )
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="challenge/theater",
        filename=f"challenge-theater_{_safe_filename(uid)}.png",
        media_type="image/png",
        content=png,
        description="GenshinUID-style Imaginarium Theater card",
        kind="image",
    )
    render_data = {
        "uid": uid,
        "render": "challenge/theater",
        "session_count": theater.get("count"),
        "artifact_sha256": artifact["sha256"],
    }
    data = {**result.data, **render_data} if args.render == "both" else render_data
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *title_warnings, *image_warnings],
        pagination=result.pagination,
    )


def _hard_render_result(
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
    hard = _mapping_data(result, "hard", "challenge.hard")
    summary, title_images, avatar_url, title_warnings = _challenge_title_context(
        args,
        provider,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    images, image_warnings = fetch_render_images(
        args,
        challenge_hard_image_urls(hard, summary, _fetchable_title_avatar_url(avatar_url)),
        provider="mys",
        region=region,
        category="challenge.hard.image",
        unavailable_warning="{count} challenge hard images unavailable; rendered placeholders",
        max_workers=CHALLENGE_IMAGE_WORKERS,
    )
    png = render_challenge_hard_card(
        uid=uid,
        hard=hard,
        summary=summary,
        asset_images={**images, **title_images},
        avatar_url=avatar_url,
    )
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="challenge/hard",
        filename=f"challenge-hard_{_safe_filename(uid)}.png",
        media_type="image/png",
        content=png,
        description="GenshinUID-style hard challenge card",
        kind="image",
    )
    render_data = {
        "uid": uid,
        "render": "challenge/hard",
        "artifact_sha256": artifact["sha256"],
    }
    data = {**result.data, **render_data} if args.render == "both" else render_data
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *title_warnings, *image_warnings],
        pagination=result.pagination,
    )


def _challenge_title_context(
    args: argparse.Namespace,
    provider,
    *,
    uid: str,
    region: str,
    cookie: str,
    credential_source: str,
    storage_backend: str | None,
) -> tuple[Mapping[str, object], dict[str, bytes], str | None, list[str]]:
    if not hasattr(provider, "player_summary"):
        return {}, {}, None, []
    try:
        result = provider.player_summary(
            uid=uid,
            cookie=cookie,
            region=region,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )
    except CliError as exc:
        return {}, {}, None, [f"player title avatar unavailable for challenge render: {exc.code}"]
    summary = result.data.get("summary")
    if not isinstance(summary, Mapping):
        return {}, {}, None, [*result.warnings, "player summary missing for challenge title render"]
    role_avatar_url = _summary_role_avatar_url(summary)
    if role_avatar_url:
        title_avatar_url, profile_warnings = None, []
    else:
        title_avatar_url, profile_warnings = _player_profile_title_avatar_url(args, uid, region)
    profile_images, profile_image_warnings = _player_profile_image_assets(
        args,
        title_avatar_url,
        region,
    )
    return (
        summary,
        profile_images,
        title_avatar_url,
        [
            *result.warnings,
            *profile_warnings,
            *profile_image_warnings,
        ],
    )


def _fetchable_title_avatar_url(avatar_url: str | None) -> str | None:
    if avatar_url and avatar_url.startswith(f"{ENKA_UI_BASE}/"):
        return None
    return avatar_url


def _has_abyss_floor_data(abyss: Mapping[str, object]) -> bool:
    floors = abyss.get("floors")
    if not isinstance(floors, list):
        return False
    return any(isinstance(floor, Mapping) for floor in floors)


