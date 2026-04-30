from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime

from gsuid_cli.commands._shared import (
    _cookie_context,
    _mapping_data,
    _provider,
    _safe_filename,
)
from gsuid_cli.commands.render_assets import fetch_render_images
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.providers.enka import EnkaProvider
from gsuid_cli.renderers.player.calendar import (
    player_calendar_icon_urls,
    render_player_calendar_card,
)
from gsuid_cli.renderers.player.characters import (
    character_mys_image_urls,
    character_namecard_url,
    character_portrait_url,
    render_player_characters_card,
    weapon_icon_url,
)
from gsuid_cli.renderers.player.diary import render_player_diary_card
from gsuid_cli.renderers.player.inventory import (
    player_inventory_icon_urls,
    render_player_inventory_card,
)
from gsuid_cli.renderers.player.summary import (
    ENKA_UI_BASE,
    player_profile_picture_url,
    player_summary_genshinuid_resource_urls,
    player_summary_mys_icon_urls,
    render_player_summary_card,
)

PLAYER_CHARACTER_IMAGE_WORKERS = 8
PLAYER_SUMMARY_ICON_WORKERS = 8
PLAYER_PROFILE_IMAGE_WORKERS = 2
PLAYER_INVENTORY_ICON_WORKERS = 12
PLAYER_CALENDAR_ICON_WORKERS = 12
PROFILE_PICTURE_CONFIG_URL = "https://cdn.jsdelivr.net/gh/DimbreathBot/AnimeGameData@master/ExcelBinOutput/ProfilePictureExcelConfigData.json"

CAPABILITIES = [
    {
        "command": "player.summary",
        "description": "Show authenticated player profile summary data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
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
        "description": "Show owned-character and equipped-weapon material counts.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "off",
        "coverage": "owned_character_ascension_and_equipped_weapon_materials",
    },
    {
        "command": "player.calendar",
        "description": "Show authenticated player activity calendar data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "off",
    },
    {
        "command": "player.diary",
        "description": "Show authenticated monthly traveler diary data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "off",
    },
    {
        "command": "player.register-time",
        "description": "Attempt to show Genshin account registration time.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
        "availability": "upstream-limited",
        "limitations": [
            "Uses the legacy MYS anniversary endpoint, which may return provider retcode -502."
        ],
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

    inventory = commands.add_parser(
        "inventory",
        help="Show owned-character and equipped-weapon material counts.",
    )
    inventory.add_argument("--uid", dest="command_uid")
    inventory.set_defaults(handler=inventory_command, command_name="player.inventory")

    calendar = commands.add_parser("calendar", help="Show player activity calendar data.")
    calendar.add_argument("--uid", dest="command_uid")
    calendar.set_defaults(handler=calendar_command, command_name="player.calendar")

    diary = commands.add_parser("diary", help="Show monthly traveler diary data.")
    diary.add_argument("--uid", dest="command_uid")
    diary.add_argument("--month", help="Diary month in YYYY-MM format.")
    diary.set_defaults(handler=diary_command, command_name="player.diary")

    register_time = commands.add_parser(
        "register-time",
        help="Attempt to show Genshin account registration time.",
    )
    register_time.add_argument("--uid", dest="command_uid")
    register_time.set_defaults(handler=register_time_command, command_name="player.register-time")


def summary_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    provider = _provider(args, region)
    result = provider.player_summary(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    if args.render == "data":
        return result
    return _summary_render_result(
        args,
        provider=provider,
        result=result,
        uid=uid,
        region=region,
        cookie=cookie,
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
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    provider = _provider(args, region)
    result = provider.player_inventory(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    if args.render == "data":
        return result
    return _inventory_render_result(
        args,
        provider=provider,
        result=result,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def calendar_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    provider = _provider(args, region)
    result = provider.player_calendar(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    if args.render == "data":
        return result
    return _calendar_render_result(
        args,
        provider=provider,
        result=result,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def diary_command(args: argparse.Namespace) -> CommandResult:
    _validate_month_arg(args.month)
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    provider = _provider(args, region)
    result = provider.player_diary(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
        month=args.month,
    )
    if args.render == "data":
        return result
    return _diary_render_result(
        args,
        provider=provider,
        result=result,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def register_time_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    return _provider(args, region).player_register_time(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
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
    asset_images, image_warnings = _player_character_asset_images(args, characters, region)
    png = render_player_characters_card(characters=characters, asset_images=asset_images)
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
        warnings=[*result.warnings, *image_warnings],
        pagination=result.pagination,
    )


def _summary_render_result(
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
    summary = result.data.get("summary")
    if not isinstance(summary, Mapping):
        raise CliError(
            "UPSTREAM_INVALID_RESPONSE",
            "Provider returned player summary data without a renderable summary.",
            EXIT_UPSTREAM,
            {"command": "player.summary"},
            source=result.source,
        )
    characters_result = provider.player_characters(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    characters_value = characters_result.data.get("characters")
    characters = (
        [character for character in characters_value if isinstance(character, Mapping)]
        if isinstance(characters_value, list)
        else []
    )
    role_avatar_url = _summary_role_avatar_url(summary)
    if role_avatar_url:
        title_avatar_url, profile_warnings = None, []
    else:
        title_avatar_url, profile_warnings = _player_profile_title_avatar_url(args, uid, region)
    extra_resource_urls = player_summary_genshinuid_resource_urls(summary)
    if title_avatar_url and not title_avatar_url.startswith(f"{ENKA_UI_BASE}/"):
        _append_url(extra_resource_urls, title_avatar_url)
    character_images, character_warnings = _player_character_asset_images(
        args,
        characters,
        region,
        extra_genshinuid_urls=extra_resource_urls,
    )
    summary_icons, summary_warnings = fetch_render_images(
        args,
        player_summary_mys_icon_urls(summary),
        provider="mys",
        region=region,
        category="player.summary.icon",
        unavailable_warning="{count} player summary icons unavailable; rendered placeholders",
        max_workers=PLAYER_SUMMARY_ICON_WORKERS,
    )
    profile_images, profile_image_warnings = _player_profile_image_assets(
        args, title_avatar_url, region
    )
    png = render_player_summary_card(
        uid=uid,
        summary=summary,
        characters=characters,
        asset_images={**character_images, **summary_icons, **profile_images},
        title_avatar_url=title_avatar_url,
    )
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="player/summary",
        filename=f"player-summary_{_safe_filename(uid)}.png",
        media_type="image/png",
        content=png,
        description="GenshinUID-style full player role-info card",
        kind="image",
    )
    render_data = {
        "uid": uid,
        "render": "player/summary",
        "character_count": len(characters),
        "artifact_sha256": artifact["sha256"],
    }
    data = {**result.data, **render_data} if args.render == "both" else render_data
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[
            *result.warnings,
            *characters_result.warnings,
            *profile_warnings,
            *character_warnings,
            *summary_warnings,
            *profile_image_warnings,
        ],
        pagination=result.pagination,
    )


def _inventory_render_result(
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
    inventory = _mapping_data(result, "inventory", "player.inventory")
    summary, title_images, title_avatar_url, title_warnings = _player_title_render_context(
        args,
        provider=provider,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
        category_prefix="player.inventory",
    )
    inventory_images, inventory_warnings = fetch_render_images(
        args,
        player_inventory_icon_urls(inventory),
        provider="mys",
        region=region,
        category="player.inventory.icon",
        unavailable_warning="{count} player inventory icons unavailable; rendered placeholders",
        max_workers=PLAYER_INVENTORY_ICON_WORKERS,
    )
    png = render_player_inventory_card(
        uid=uid,
        summary=summary,
        inventory=inventory,
        asset_images={**title_images, **inventory_images},
        title_avatar_url=title_avatar_url,
    )
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="player/inventory",
        filename=f"player-inventory_{_safe_filename(uid)}.png",
        media_type="image/png",
        content=png,
        description="GenshinUID-style player inventory card",
        kind="image",
    )
    render_data = {
        "uid": uid,
        "render": "player/inventory",
        "item_count": inventory.get("count"),
        "artifact_sha256": artifact["sha256"],
    }
    data = {**result.data, **render_data} if args.render == "both" else render_data
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *title_warnings, *inventory_warnings],
        pagination=result.pagination,
    )


def _calendar_render_result(
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
    calendar = _mapping_data(result, "calendar", "player.calendar")
    summary, title_images, title_avatar_url, title_warnings = _player_title_render_context(
        args,
        provider=provider,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
        category_prefix="player.calendar",
    )
    calendar_images, calendar_warnings = fetch_render_images(
        args,
        player_calendar_icon_urls(calendar),
        provider="mys",
        region=region,
        category="player.calendar.icon",
        unavailable_warning="{count} player calendar icons unavailable; rendered placeholders",
        max_workers=PLAYER_CALENDAR_ICON_WORKERS,
    )
    png = render_player_calendar_card(
        uid=uid,
        summary=summary,
        calendar=calendar,
        asset_images={**title_images, **calendar_images},
        title_avatar_url=title_avatar_url,
    )
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="player/calendar",
        filename=f"player-calendar_{_safe_filename(uid)}.png",
        media_type="image/png",
        content=png,
        description="GenshinUID-style player activity calendar card",
        kind="image",
    )
    counts = calendar.get("counts") if isinstance(calendar.get("counts"), Mapping) else {}
    render_data = {
        "uid": uid,
        "render": "player/calendar",
        "act_count": counts.get("act_list"),
        "artifact_sha256": artifact["sha256"],
    }
    data = {**result.data, **render_data} if args.render == "both" else render_data
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *title_warnings, *calendar_warnings],
        pagination=result.pagination,
    )


def _diary_render_result(
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
    diary = _mapping_data(result, "diary", "player.diary")
    summary, title_images, title_avatar_url, title_warnings = _player_title_render_context(
        args,
        provider=provider,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
        category_prefix="player.diary",
    )
    png = render_player_diary_card(
        uid=uid,
        summary=summary,
        diary=diary,
        asset_images=title_images,
        title_avatar_url=title_avatar_url,
    )
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="player/diary",
        filename=f"player-diary_{_safe_filename(uid)}.png",
        media_type="image/png",
        content=png,
        description="GenshinUID-style monthly traveler diary card",
        kind="image",
    )
    render_data = {
        "uid": uid,
        "render": "player/diary",
        "month": diary.get("month"),
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


def _player_title_render_context(
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
    summary_result = provider.player_summary(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    summary = _mapping_data(summary_result, "summary", f"{category_prefix}.summary")
    role_avatar_url = _summary_role_avatar_url(summary)
    if role_avatar_url:
        title_avatar_url, profile_warnings = None, []
    else:
        title_avatar_url, profile_warnings = _player_profile_title_avatar_url(args, uid, region)
    resource_urls = player_summary_genshinuid_resource_urls(summary)
    if title_avatar_url and not title_avatar_url.startswith(f"{ENKA_UI_BASE}/"):
        _append_url(resource_urls, title_avatar_url)
    resource_images, resource_warnings = fetch_render_images(
        args,
        resource_urls,
        provider="genshinuid",
        region=region,
        category=f"{category_prefix}.title.resource",
        unavailable_warning="{count} player title resources unavailable; rendered fallback avatar",
        max_workers=PLAYER_CHARACTER_IMAGE_WORKERS,
    )
    icon_images, icon_warnings = fetch_render_images(
        args,
        _player_title_mys_icon_urls(summary),
        provider="mys",
        region=region,
        category=f"{category_prefix}.title.icon",
        unavailable_warning="{count} player title icons unavailable; rendered fallback avatar",
        max_workers=PLAYER_SUMMARY_ICON_WORKERS,
    )
    profile_images, profile_image_warnings = _player_profile_image_assets(
        args, title_avatar_url, region
    )
    return (
        summary,
        {**resource_images, **icon_images, **profile_images},
        title_avatar_url,
        [
            *summary_result.warnings,
            *profile_warnings,
            *resource_warnings,
            *icon_warnings,
            *profile_image_warnings,
        ],
    )


def _player_title_mys_icon_urls(summary: Mapping[str, object]) -> list[str]:
    role_avatar_url = _summary_role_avatar_url(summary)
    return [role_avatar_url] if role_avatar_url else []


def _player_profile_title_avatar_url(
    args: argparse.Namespace, uid: str, region: str
) -> tuple[str | None, list[str]]:
    try:
        result = EnkaProvider(
            HttpClient(
                timeout=args.timeout,
                cache_policy=args.cache,
                output_dir=args.output_dir,
                debug=args.debug,
            )
        ).profile(uid=uid, region=region)
    except CliError:
        return None, ["player profile unavailable; rendered title avatar fallback"]

    icons: Mapping[str, object] | None = None
    picture_id = _profile_picture_id(result.data)
    if picture_id:
        try:
            icons = _profile_picture_icons(args, region)
        except CliError:
            return None, ["player profile picture map unavailable; rendered title avatar fallback"]
    url = player_profile_picture_url(result.data, icons)
    if url is None:
        return None, ["player profile picture unavailable; rendered title avatar fallback"]
    return url, []


def _summary_role_avatar_url(summary: Mapping[str, object]) -> str | None:
    role = summary.get("role")
    if not isinstance(role, Mapping):
        return None
    value = role.get("avatar_icon")
    return str(value) if value not in (None, "") else None


def _profile_picture_icons(args: argparse.Namespace, region: str) -> Mapping[str, object]:
    response = HttpClient(
        timeout=args.timeout,
        cache_policy=args.cache,
        output_dir=args.output_dir,
        debug=args.debug,
    ).request_bytes(
        "GET",
        PROFILE_PICTURE_CONFIG_URL,
        provider="animegamedata",
        region=region,
        category="player.summary.profile_picture_config",
        expected_media_types=("application/json", "text/plain"),
    )
    try:
        payload = json.loads(response.content)
    except ValueError as exc:
        raise CliError(
            "UPSTREAM_INVALID_RESPONSE",
            "Profile picture config returned invalid JSON.",
            EXIT_UPSTREAM,
            {"provider": "animegamedata", "category": "player.summary.profile_picture_config"},
            source=response.source,
        ) from exc
    if not isinstance(payload, list):
        raise CliError(
            "UPSTREAM_INVALID_RESPONSE",
            "Profile picture config returned an unexpected shape.",
            EXIT_UPSTREAM,
            {"provider": "animegamedata", "category": "player.summary.profile_picture_config"},
            source=response.source,
        )
    icons: dict[str, object] = {}
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        picture_id = item.get("id")
        icon_path = item.get("iconPath")
        if picture_id in (None, "") or not isinstance(icon_path, str) or not icon_path:
            continue
        icons[str(picture_id)] = {"iconPath": icon_path}
    if not icons:
        raise CliError(
            "UPSTREAM_INVALID_RESPONSE",
            "Profile picture config did not contain renderable icons.",
            EXIT_UPSTREAM,
            {"provider": "animegamedata", "category": "player.summary.profile_picture_config"},
            source=response.source,
        )
    return icons


def _profile_picture_id(profile: Mapping[str, object]) -> str | None:
    player_info = profile.get("playerInfo")
    if not isinstance(player_info, Mapping):
        return None
    profile_picture = player_info.get("profilePicture")
    if not isinstance(profile_picture, Mapping):
        return None
    value = profile_picture.get("id")
    return str(value) if value not in (None, "") else None


def _player_profile_image_assets(
    args: argparse.Namespace, title_avatar_url: str | None, region: str
) -> tuple[dict[str, bytes], list[str]]:
    if not title_avatar_url or not title_avatar_url.startswith(f"{ENKA_UI_BASE}/"):
        return {}, []
    return fetch_render_images(
        args,
        [title_avatar_url],
        provider="enka",
        region=region,
        category="player.summary.profile_picture",
        unavailable_warning="player profile picture unavailable; rendered title avatar fallback",
        max_workers=PLAYER_PROFILE_IMAGE_WORKERS,
    )


def _player_character_asset_images(
    args: argparse.Namespace,
    characters: list[Mapping[str, object]],
    region: str,
    *,
    extra_genshinuid_urls: list[str] | None = None,
) -> tuple[dict[str, bytes], list[str]]:
    genshinuid_urls = _player_character_genshinuid_resource_urls(characters)
    for url in extra_genshinuid_urls or []:
        _append_url(genshinuid_urls, url)
    genshinuid_images, resource_warnings = fetch_render_images(
        args,
        genshinuid_urls,
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
    return {**fallback_images, **genshinuid_images}, [*resource_warnings, *fallback_warnings]


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


