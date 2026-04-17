from __future__ import annotations

import argparse
import hashlib
import re
from collections.abc import Mapping
from datetime import UTC, datetime

from gsuid_cli.commands.auth import _credential, _uid_and_region
from gsuid_cli.commands.render_assets import fetch_render_images
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.providers import provider_for_region
from gsuid_cli.renderers.player.characters import (
    character_mys_image_urls,
    character_namecard_url,
    character_portrait_url,
    render_player_characters_card,
    weapon_icon_url,
)

PLAYER_CHARACTER_IMAGE_WORKERS = 8

CAPABILITIES = [
    {
        "command": "player.summary",
        "description": "Show authenticated player profile summary data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "player.characters",
        "description": "Show authenticated player character details.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "off",
    },
    {
        "command": "player.inventory",
        "description": "Report inventory data support status.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "player.calendar",
        "description": "Report player calendar data support status.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "player.diary",
        "description": "Show authenticated monthly traveler diary data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "player.register-time",
        "description": "Report registration-time data support status.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
]


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    player = groups.add_parser("player", help="Show authenticated player data.")
    commands = player.add_subparsers(dest="player_command", required=True, metavar="<command>")

    summary = commands.add_parser("summary", help="Show player summary data.")
    summary.add_argument("--uid", dest="command_uid")
    summary.set_defaults(handler=summary_command, command_name="player.summary")

    characters = commands.add_parser("characters", help="Show player character details.")
    characters.add_argument("--uid", dest="command_uid")
    characters.set_defaults(handler=characters_command, command_name="player.characters")

    inventory = commands.add_parser("inventory", help="Report inventory data support status.")
    inventory.add_argument("--uid", dest="command_uid")
    inventory.set_defaults(handler=inventory_command, command_name="player.inventory")

    calendar = commands.add_parser("calendar", help="Report player calendar data support status.")
    calendar.add_argument("--uid", dest="command_uid")
    calendar.set_defaults(handler=calendar_command, command_name="player.calendar")

    diary = commands.add_parser("diary", help="Show monthly traveler diary data.")
    diary.add_argument("--uid", dest="command_uid")
    diary.add_argument("--month", help="Diary month in YYYY-MM format.")
    diary.set_defaults(handler=diary_command, command_name="player.diary")

    register_time = commands.add_parser(
        "register-time",
        help="Report registration-time data support status.",
    )
    register_time.add_argument("--uid", dest="command_uid")
    register_time.set_defaults(handler=register_time_command, command_name="player.register-time")


def summary_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    return _provider(args, region).player_summary(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def characters_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    result = _provider(args, region).player_characters(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    if args.render == "data":
        return result
    return _characters_render_result(args, result=result, uid=uid, region=region)


def inventory_command(args: argparse.Namespace) -> CommandResult:
    return _source_limited_player_command(
        args,
        field="inventory",
        message="inventory item counts are not exposed by the configured MYS provider",
    )


def calendar_command(args: argparse.Namespace) -> CommandResult:
    return _source_limited_player_command(
        args,
        field="calendar",
        message="personal calendar data is not exposed by the configured MYS provider",
    )


def diary_command(args: argparse.Namespace) -> CommandResult:
    _validate_month_arg(args.month)
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    return _provider(args, region).player_diary(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
        month=args.month,
    )


def register_time_command(args: argparse.Namespace) -> CommandResult:
    return _source_limited_player_command(
        args,
        field="register_time",
        message="registration time is not exposed by the configured MYS provider",
    )


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


def _source_limited_player_command(
    args: argparse.Namespace,
    *,
    field: str,
    message: str,
) -> CommandResult:
    uid, region = _uid_and_region(args)
    ensure_supported_region(region)
    return CommandResult(
        data={
            "uid": uid,
            "available": False,
            field: [] if field in {"inventory", "calendar"} else None,
            "source_limitations": [message],
        },
        warnings=[message],
    )


def _validate_month_arg(month: str | None) -> None:
    if month is None:
        return
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise CliError(
            "INVALID_ARGUMENT",
            "month must use YYYY-MM format",
            EXIT_INVALID_INPUT,
            {"month": month},
        )
    year_text, month_text = month.split("-", 1)
    current_year = datetime.now(UTC).year
    if int(year_text) != current_year:
        raise CliError(
            "INVALID_ARGUMENT",
            "month must be in the current ledger year",
            EXIT_INVALID_INPUT,
            {"month": month, "supported_year": current_year},
        )
    month_number = int(month_text)
    if month_number < 1 or month_number > 12:
        raise CliError(
            "INVALID_ARGUMENT",
            "month must use a month from 01 to 12",
            EXIT_INVALID_INPUT,
            {"month": month},
        )


def _characters_render_result(
    args: argparse.Namespace,
    *,
    result: CommandResult,
    uid: str,
    region: str,
) -> CommandResult:
    characters_value = result.data.get("characters")
    if not isinstance(characters_value, list):
        raise CliError(
            "UPSTREAM_INVALID_RESPONSE",
            "Provider returned player character data without renderable characters.",
            EXIT_UPSTREAM,
            {"command": "player.characters"},
            source=result.source,
        )
    characters = [character for character in characters_value if isinstance(character, Mapping)]
    genshinuid_images, resource_warnings = fetch_render_images(
        args,
        _player_character_genshinuid_resource_urls(characters),
        provider="genshinuid",
        region=region,
        category="player.characters.resource",
        unavailable_warning=(
            "{count} player character GenshinUID resources unavailable; "
            "rendered fallbacks where possible"
        ),
        max_workers=PLAYER_CHARACTER_IMAGE_WORKERS,
    )
    fallback_images, fallback_warnings = fetch_render_images(
        args,
        _player_character_mys_fallback_urls(characters, genshinuid_images),
        provider="mys",
        region=region,
        category="player.characters.fallback",
        unavailable_warning=(
            "{count} player character fallback images unavailable; rendered placeholders"
        ),
        max_workers=PLAYER_CHARACTER_IMAGE_WORKERS,
    )
    png = render_player_characters_card(
        characters=characters,
        asset_images={**fallback_images, **genshinuid_images},
    )
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="player/characters",
        filename=f"player-characters_{_safe_filename(uid)}.png",
        media_type="image/png",
        content=png,
        description="GenshinUID-style player character list card",
        kind="image",
    )
    render_data = {
        "uid": uid,
        "render": "player/characters",
        "character_count": len(characters),
        "artifact_sha256": artifact["sha256"],
    }
    data = {**result.data, **render_data} if args.render == "both" else render_data
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *resource_warnings, *fallback_warnings],
        pagination=result.pagination,
    )


def _player_character_genshinuid_resource_urls(
    characters: list[Mapping[str, object]],
) -> list[str]:
    urls: list[str] = []
    for character in characters:
        _append_url(urls, character_portrait_url(character))
        _append_url(urls, character_namecard_url(character))
        weapon = character.get("weapon")
        if isinstance(weapon, Mapping):
            _append_url(urls, weapon_icon_url(weapon))
    return urls


def _player_character_mys_fallback_urls(
    characters: list[Mapping[str, object]],
    resource_images: Mapping[str, bytes],
) -> list[str]:
    urls: list[str] = []
    for character in characters:
        if character_portrait_url(character) not in resource_images:
            for url in character_mys_image_urls(character):
                _append_url(urls, url)
        weapon = character.get("weapon")
        if isinstance(weapon, Mapping) and weapon_icon_url(weapon) not in resource_images:
            _append_url(urls, weapon.get("icon"))
    return urls


def _append_url(urls: list[str], value: object) -> None:
    url = _optional_text(value)
    if url and url not in urls:
        urls.append(url)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    if safe:
        return safe[:80]
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]
