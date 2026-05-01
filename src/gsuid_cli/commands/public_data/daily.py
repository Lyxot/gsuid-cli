from __future__ import annotations

import argparse

from gsuid_cli.commands import player as player_commands
from gsuid_cli.commands._shared import _cookie_context
from gsuid_cli.commands._shared import _provider as _auth_provider
from gsuid_cli.commands.auth import _uid_and_region
from gsuid_cli.commands.public_data._common import (
    _append_url,
    _optional_bool,
    _optional_text,
    _provider,
    _safe_filename,
)
from gsuid_cli.commands.render_assets import fetch_render_images
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.errors import EXIT_UPSTREAM, CliError
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.core.render import render_image_enabled, render_result_data
from gsuid_cli.providers.public import DAY_NAMES
from gsuid_cli.renderers.daily.materials import render_daily_materials_card
from gsuid_cli.renderers.daily.note import render_daily_note_card

DAILY_MATERIAL_ICON_WORKERS = 8
DAILY_NOTE_AVATAR_WORKERS = 5

CAPABILITIES = [
    {
        "command": "daily.materials",
        "description": "List daily talent and weapon material domains.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "all"],
        "cache": "use",
    },
    {
        "command": "daily.note",
        "description": "Show current resin, commissions, expeditions, and teapot status.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "all"],
        "cache": "off",
    },
    {
        "command": "daily.signin",
        "description": "Claim or report the MYS daily sign-in status.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "daily.bbs-coin",
        "description": "Report BBS coin task support status.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
]


def daily_materials_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).daily_materials(
        day=args.day,
        date=args.date,
        require_upgrade=render_image_enabled(args),
    )
    if not render_image_enabled(args):
        return result
    return _daily_materials_render_result(args, result)


def daily_note_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    provider = _auth_provider(args, region)
    result = provider.daily_note(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    if not render_image_enabled(args):
        return result
    return _daily_note_render_result(
        args,
        provider=provider,
        result=result,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def daily_signin_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    return _auth_provider(args, region).daily_signin(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def daily_bbs_coin_command(args: argparse.Namespace) -> CommandResult:
    uid, region = _uid_and_region(args)
    ensure_supported_region(region)
    return CommandResult(
        data={
            "uid": uid,
            "available": False,
            "tasks": [],
            "points_received": None,
            "failures": [],
            "source_limitations": [
                "BBS coin automation requires a stable MYS task provider not configured in this CLI"
            ],
        },
        warnings=["daily BBS coin task data is not available from configured sources"],
    )


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    daily = groups.add_parser("daily", help="Show daily data.")
    commands = daily.add_subparsers(dest="daily_command", required=True, metavar="<command>")

    note = commands.add_parser("note", help="Show current daily account status.")
    note.add_argument("--uid", dest="command_uid")
    note.set_defaults(handler=daily_note_command, command_name="daily.note")

    signin = commands.add_parser("signin", help="Claim or report MYS daily sign-in status.")
    signin.add_argument("--uid", dest="command_uid")
    signin.set_defaults(handler=daily_signin_command, command_name="daily.signin")

    bbs_coin = commands.add_parser("bbs-coin", help="Report BBS coin task support status.")
    bbs_coin.add_argument("--uid", dest="command_uid")
    bbs_coin.set_defaults(handler=daily_bbs_coin_command, command_name="daily.bbs-coin")

    materials = commands.add_parser("materials", help="List daily material domains.")
    selectors = materials.add_mutually_exclusive_group()
    selectors.add_argument("--date")
    selectors.add_argument("--day", choices=sorted(DAY_NAMES))
    materials.set_defaults(handler=daily_materials_command, command_name="daily.materials")


def _daily_materials_render_result(
    args: argparse.Namespace,
    result: CommandResult,
) -> CommandResult:
    domains = result.data.get("domains")
    if not isinstance(domains, list):
        raise CliError(
            "UPSTREAM_INVALID_RESPONSE",
            "Provider returned daily material data without renderable domains.",
            EXIT_UPSTREAM,
            {"command": "daily.materials"},
            source=result.source,
        )
    renderable_domains = [domain for domain in domains if isinstance(domain, dict)]
    day = str(result.data.get("day") or args.day or "unknown")
    icon_images, icon_warnings = fetch_render_images(
        args,
        _daily_materials_icon_urls(renderable_domains),
        provider="ambr",
        region="cn",
        category="daily.materials.icon",
        unavailable_warning="{count} daily materials icons unavailable; rendered placeholders",
        max_workers=DAILY_MATERIAL_ICON_WORKERS,
    )
    png = render_daily_materials_card(day=day, domains=renderable_domains, icon_images=icon_images)
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="daily/materials",
        filename=f"daily-materials_{_safe_filename(day)}.png",
        media_type="image/png",
        content=png,
        description="GenshinUID-style daily materials card",
        kind="image",
    )
    render_data = {
        "day": day,
        "render": "daily/materials",
        "artifact_sha256": artifact["sha256"],
    }
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *icon_warnings],
        pagination=result.pagination,
    )


def _daily_materials_icon_urls(domains: list[object]) -> list[str]:
    urls: list[str] = []
    for domain in domains:
        if not isinstance(domain, dict):
            continue
        _append_url(urls, domain.get("domain_icon_url"))
        items = domain.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                _append_url(urls, item.get("icon_url"))
    return urls


def _daily_note_render_result(
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
    note = result.data.get("note")
    if not isinstance(note, dict):
        raise CliError(
            "UPSTREAM_INVALID_RESPONSE",
            "Provider returned daily note data without a renderable note object.",
            EXIT_UPSTREAM,
            {"command": "daily.note"},
            source=result.source,
        )

    nickname, level, header_warnings = _daily_note_header(args)
    signed, sign_warnings = _daily_note_sign_status(
        provider=provider,
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    avatar_images, avatar_warnings = fetch_render_images(
        args,
        _expedition_avatar_urls(note),
        provider="mys",
        region=region,
        category="daily.note.avatar",
        unavailable_warning="daily note expedition avatar unavailable; rendered placeholder",
        max_workers=DAILY_NOTE_AVATAR_WORKERS,
    )
    png = render_daily_note_card(
        uid=uid,
        note=note,
        nickname=nickname,
        level=level,
        signed=signed,
        expedition_avatar_images=avatar_images,
    )
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="daily/note",
        filename=f"daily-note_{_safe_filename(uid)}.png",
        media_type="image/png",
        content=png,
        description="GenshinUID-style daily note card",
        kind="image",
    )
    render_data = {
        "uid": uid,
        "render": "daily/note",
        "artifact_sha256": artifact["sha256"],
    }
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *header_warnings, *sign_warnings, *avatar_warnings],
        pagination=result.pagination,
    )


def _daily_note_header(
    args: argparse.Namespace,
) -> tuple[str | None, object | None, list[str]]:
    summary_args = argparse.Namespace(**vars(args))
    summary_args.command_name = "player.summary"
    summary_args.render = "data"
    try:
        result = player_commands.summary_command(summary_args)
    except CliError:
        return None, None, ["daily note player header data is unavailable; rendered fallback title"]

    summary = result.data.get("summary")
    if not isinstance(summary, dict):
        return None, None, ["daily note player header data is unavailable; rendered fallback title"]
    role = summary.get("role")
    if not isinstance(role, dict):
        return None, None, ["daily note player header data is unavailable; rendered fallback title"]
    nickname = _optional_text(role.get("nickname"))
    level = role.get("level")
    warnings = list(result.warnings)
    if nickname is None or level in (None, ""):
        warnings.append("daily note player header data is unavailable; rendered fallback title")
    return nickname, level, warnings


def _daily_note_sign_status(
    *,
    provider,
    uid: str,
    cookie: str,
    region: str,
    credential_source: str,
    storage_backend: str | None,
) -> tuple[bool | None, list[str]]:
    if not hasattr(provider, "daily_signin_status"):
        return None, ["daily note sign-in status is unavailable; rendered fallback sign state"]
    try:
        result = provider.daily_signin_status(
            uid=uid,
            cookie=cookie,
            region=region,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )
    except CliError:
        return None, ["daily note sign-in status is unavailable; rendered fallback sign state"]
    signed = _signed_from_signin_result(result.data)
    if signed is None:
        return None, ["daily note sign-in status is unavailable; rendered fallback sign state"]
    return signed, result.warnings


def _signed_from_signin_result(data: dict[str, object]) -> bool | None:
    already_signed = _optional_bool(data.get("already_signed"))
    signed = _optional_bool(data.get("signed"))
    if already_signed is True or signed is True:
        return True
    if already_signed is False and signed is False:
        return False
    return None


def _expedition_avatar_urls(note: dict[str, object]) -> list[str]:
    expeditions = note.get("expeditions")
    if not isinstance(expeditions, list):
        return []
    urls: list[str] = []
    for expedition in expeditions:
        if isinstance(expedition, dict):
            _append_url(urls, expedition.get("avatar_side_icon"))
    return urls
