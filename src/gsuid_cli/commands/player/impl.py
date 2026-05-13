from __future__ import annotations

import argparse
import re
from collections.abc import Mapping
from datetime import UTC, datetime

from gsuid_cli.commands._shared import (
    _cookie_context,
    _mapping_data,
    _provider,
)
from gsuid_cli.commands._text import (
    helps_from,
    record_primary_image,
    record_text_artifact,
    safe_filename_part,
    write_image_artifact,
    write_text_artifact,
)
from gsuid_cli.commands.player import assets as player_assets
from gsuid_cli.commands.player.assets import PLAYER_SUMMARY_ICON_WORKERS
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.render import render_image_enabled, render_result_data, render_text_enabled
from gsuid_cli.providers.assets import fetch_render_images
from gsuid_cli.providers.enka import EnkaProvider
from gsuid_cli.renderers.player.calendar import (
    player_calendar_icon_urls,
    render_player_calendar_card,
)
from gsuid_cli.renderers.player.characters import render_player_characters_card
from gsuid_cli.renderers.player.diary import render_player_diary_card
from gsuid_cli.renderers.player.inventory import (
    player_inventory_icon_urls,
    render_player_inventory_card,
)
from gsuid_cli.renderers.player.summary import (
    ENKA_UI_BASE,
    player_summary_genshinuid_resource_urls,
    player_summary_mys_icon_urls,
    render_player_summary_card,
)
from gsuid_cli.renderers.player.text import (
    render_player_calendar_text,
    render_player_characters_text,
    render_player_diary_text,
    render_player_inventory_text,
    render_player_register_time_text,
    render_player_summary_text,
)
from gsuid_cli.text import t as _t

PLAYER_INVENTORY_ICON_WORKERS = 12
PLAYER_CALENDAR_ICON_WORKERS = 12

CAPABILITIES = [
    {
        "command": "player.summary",
        "description": _t("gsuid.commands.player.impl.60_23.9d971bf8"),
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "player.characters",
        "description": _t("gsuid.commands.player.impl.67_23.39101516"),
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "player.inventory",
        "description": _t("gsuid.commands.player.impl.74_23.226033dc"),
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
        "coverage": "owned_character_ascension_and_equipped_weapon_materials",
    },
    {
        "command": "player.calendar",
        "description": _t("gsuid.commands.player.impl.82_23.a7d8495b"),
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "player.diary",
        "description": _t("gsuid.commands.player.impl.89_23.eafd4190"),
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "player.register-time",
        "description": _t("gsuid.commands.player.impl.96_23.8ef33cb5"),
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
        "availability": "upstream-limited",
        "limitations": [_t("gsuid.commands.player.impl.101_24.2a70c3d2")],
    },
]

_HELPS = helps_from(CAPABILITIES)


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    player = groups.add_parser("player", help=_t("gsuid.commands.player.impl.109_46.1a329f56"))
    commands = player.add_subparsers(dest="player_command", required=True, metavar="<command>")

    summary = commands.add_parser("summary", help=_HELPS["player.summary"])
    summary.add_argument("--uid", dest="command_uid")
    summary.set_defaults(handler=summary_command, command_name="player.summary")

    characters = commands.add_parser("characters", help=_HELPS["player.characters"])
    characters.add_argument("--uid", dest="command_uid")
    characters.set_defaults(handler=characters_command, command_name="player.characters")

    inventory = commands.add_parser(
        "inventory",
        help=_HELPS["player.inventory"],
    )
    inventory.add_argument("--uid", dest="command_uid")
    inventory.set_defaults(handler=inventory_command, command_name="player.inventory")

    calendar = commands.add_parser("calendar", help=_HELPS["player.calendar"])
    calendar.add_argument("--uid", dest="command_uid")
    calendar.set_defaults(handler=calendar_command, command_name="player.calendar")

    diary = commands.add_parser("diary", help=_HELPS["player.diary"])
    diary.add_argument("--uid", dest="command_uid")
    diary.add_argument("--month", help="Diary month in YYYY-MM format.")
    diary.set_defaults(handler=diary_command, command_name="player.diary")

    register_time = commands.add_parser(
        "register-time",
        help=_HELPS["player.register-time"],
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
    if not (render_image_enabled(args) or render_text_enabled(args)):
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
    if not (render_image_enabled(args) or render_text_enabled(args)):
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
    if not (render_image_enabled(args) or render_text_enabled(args)):
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
    if not (render_image_enabled(args) or render_text_enabled(args)):
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
    if not (render_image_enabled(args) or render_text_enabled(args)):
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
    result = _provider(args, region).player_register_time(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    if not render_text_enabled(args):
        return result
    return _register_time_render_result(args, result=result, uid=uid)


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
            _t("gsuid.commands.player.impl.310_12.ca2e8d06"),
            EXIT_UPSTREAM,
            {"command": "player.characters"},
            source=result.source,
        )
    characters = [character for character in characters_value if isinstance(character, Mapping)]
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data: dict[str, object] = {"uid": uid, "character_count": len(characters)}
    if render_image_enabled(args):
        asset_images, image_warnings = _player_character_asset_images(args, characters, region)
        png = render_player_characters_card(characters=characters, asset_images=asset_images)
        image_artifact = write_image_artifact(
            args,
            name="player/characters",
            filename=f"player-characters_{safe_filename_part(uid)}.png",
            content=png,
            description=_t("gsuid.commands.player.impl.327_24.b420a5fd"),
        )
        artifacts.append(image_artifact)
        warnings.extend(image_warnings)
        record_primary_image(render_data, image_artifact)
    if render_text_enabled(args):
        text_artifact = write_text_artifact(
            args,
            name="player/characters-text",
            filename=f"player-characters_{safe_filename_part(uid)}.txt",
            content=render_player_characters_text(result.data),
            description=_t("gsuid.commands.player.impl.338_24.e72d0917"),
        )
        artifacts.append(text_artifact)
        record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
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
            _t("gsuid.commands.player.impl.367_12.27f00965"),
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
    artifacts: list[dict[str, object]] = []
    warnings = [*result.warnings, *characters_result.warnings]
    render_data: dict[str, object] = {"uid": uid, "character_count": len(characters)}
    if render_image_enabled(args):
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
            unavailable_warning=_t("gsuid.commands.player.impl.409_32.efd2300e"),
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
        image_artifact = write_image_artifact(
            args,
            name="player/summary",
            filename=f"player-summary_{safe_filename_part(uid)}.png",
            content=png,
            description=_t("gsuid.commands.player.impl.427_24.8c9255e5"),
        )
        artifacts.append(image_artifact)
        warnings.extend(
            [
                *profile_warnings,
                *character_warnings,
                *summary_warnings,
                *profile_image_warnings,
            ]
        )
        record_primary_image(render_data, image_artifact)
    if render_text_enabled(args):
        text_artifact = write_text_artifact(
            args,
            name="player/summary-text",
            filename=f"player-summary_{safe_filename_part(uid)}.txt",
            content=render_player_summary_text(
                uid=uid,
                summary=summary,
                characters=characters,
            ),
            description=_t("gsuid.commands.player.impl.449_24.95dfd421"),
        )
        artifacts.append(text_artifact)
        record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
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
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data: dict[str, object] = {"uid": uid, "item_count": inventory.get("count")}
    if render_image_enabled(args):
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
            unavailable_warning=_t("gsuid.commands.player.impl.495_32.1333bdc3"),
            max_workers=PLAYER_INVENTORY_ICON_WORKERS,
        )
        png = render_player_inventory_card(
            uid=uid,
            summary=summary,
            inventory=inventory,
            asset_images={**title_images, **inventory_images},
            title_avatar_url=title_avatar_url,
        )
        image_artifact = write_image_artifact(
            args,
            name="player/inventory",
            filename=f"player-inventory_{safe_filename_part(uid)}.png",
            content=png,
            description=_t("gsuid.commands.player.impl.510_24.759cad91"),
        )
        artifacts.append(image_artifact)
        warnings.extend([*title_warnings, *inventory_warnings])
        record_primary_image(render_data, image_artifact)
    else:
        summary, title_warnings = _player_title_summary_context(
            provider=provider,
            uid=uid,
            region=region,
            cookie=cookie,
            credential_source=credential_source,
            storage_backend=storage_backend,
            category_prefix="player.inventory",
        )
        warnings.extend(title_warnings)
    if render_text_enabled(args):
        text_artifact = write_text_artifact(
            args,
            name="player/inventory-text",
            filename=f"player-inventory_{safe_filename_part(uid)}.txt",
            content=render_player_inventory_text(uid=uid, summary=summary, inventory=inventory),
            description=_t("gsuid.commands.player.impl.532_24.4a367244"),
        )
        artifacts.append(text_artifact)
        record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
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
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    counts = calendar.get("counts") if isinstance(calendar.get("counts"), Mapping) else {}
    render_data: dict[str, object] = {
        "uid": uid,
        "act_count": counts.get("act_list"),
    }
    if render_image_enabled(args):
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
            unavailable_warning=_t("gsuid.commands.player.impl.582_32.ed5033d3"),
            max_workers=PLAYER_CALENDAR_ICON_WORKERS,
        )
        png = render_player_calendar_card(
            uid=uid,
            summary=summary,
            calendar=calendar,
            asset_images={**title_images, **calendar_images},
            title_avatar_url=title_avatar_url,
        )
        image_artifact = write_image_artifact(
            args,
            name="player/calendar",
            filename=f"player-calendar_{safe_filename_part(uid)}.png",
            content=png,
            description=_t("gsuid.commands.player.impl.597_24.da726ebb"),
        )
        artifacts.append(image_artifact)
        warnings.extend([*title_warnings, *calendar_warnings])
        record_primary_image(render_data, image_artifact)
    else:
        summary, title_warnings = _player_title_summary_context(
            provider=provider,
            uid=uid,
            region=region,
            cookie=cookie,
            credential_source=credential_source,
            storage_backend=storage_backend,
            category_prefix="player.calendar",
        )
        warnings.extend(title_warnings)
    if render_text_enabled(args):
        text_artifact = write_text_artifact(
            args,
            name="player/calendar-text",
            filename=f"player-calendar_{safe_filename_part(uid)}.txt",
            content=render_player_calendar_text(uid=uid, summary=summary, calendar=calendar),
            description=_t("gsuid.commands.player.impl.619_24.85318d91"),
        )
        artifacts.append(text_artifact)
        record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
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
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data: dict[str, object] = {
        "uid": uid,
        "month": diary.get("month"),
    }
    if render_image_enabled(args):
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
        image_artifact = write_image_artifact(
            args,
            name="player/diary",
            filename=f"player-diary_{safe_filename_part(uid)}.png",
            content=png,
            description=_t("gsuid.commands.player.impl.674_24.524e081a"),
        )
        artifacts.append(image_artifact)
        warnings.extend(title_warnings)
        record_primary_image(render_data, image_artifact)
    else:
        summary, title_warnings = _player_title_summary_context(
            provider=provider,
            uid=uid,
            region=region,
            cookie=cookie,
            credential_source=credential_source,
            storage_backend=storage_backend,
            category_prefix="player.diary",
        )
        warnings.extend(title_warnings)
    if render_text_enabled(args):
        text_artifact = write_text_artifact(
            args,
            name="player/diary-text",
            filename=f"player-diary_{safe_filename_part(uid)}.txt",
            content=render_player_diary_text(uid=uid, summary=summary, diary=diary),
            description=_t("gsuid.commands.player.impl.696_24.cfa5d880"),
        )
        artifacts.append(text_artifact)
        record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
        pagination=result.pagination,
    )


def _register_time_render_result(
    args: argparse.Namespace,
    *,
    result: CommandResult,
    uid: str,
) -> CommandResult:
    text_artifact = write_text_artifact(
        args,
        name="player/register-time-text",
        filename=f"player-register-time_{safe_filename_part(uid)}.txt",
        content=render_player_register_time_text(result.data),
        description=_t("gsuid.commands.player.impl.721_20.0e1f69b1"),
    )
    data = render_result_data(
        args,
        result.data,
        {
            "uid": uid,
            "render": "player/register-time-text",
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


def _player_title_summary_context(
    *,
    provider,
    uid: str,
    region: str,
    cookie: str,
    credential_source: str,
    storage_backend: str | None,
    category_prefix: str,
) -> tuple[Mapping[str, object], list[str]]:
    return player_assets._player_title_summary_context(
        provider=provider,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
        category_prefix=category_prefix,
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
    return player_assets._player_title_render_context(
        args,
        provider=provider,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
        category_prefix=category_prefix,
        fetch_images=fetch_render_images,
        profile_title_avatar_url=_player_profile_title_avatar_url,
        profile_image_assets=_player_profile_image_assets,
    )


def _player_title_mys_icon_urls(summary: Mapping[str, object]) -> list[str]:
    return player_assets._player_title_mys_icon_urls(summary)


def _player_profile_title_avatar_url(
    args: argparse.Namespace, uid: str, region: str
) -> tuple[str | None, list[str]]:
    return player_assets._player_profile_title_avatar_url(
        args,
        uid,
        region,
        enka_provider_cls=EnkaProvider,
        http_client_cls=HttpClient,
        profile_picture_icons=_profile_picture_icons,
    )


def _summary_role_avatar_url(summary: Mapping[str, object]) -> str | None:
    return player_assets._summary_role_avatar_url(summary)


def _profile_picture_icons(args: argparse.Namespace, region: str) -> Mapping[str, object]:
    return player_assets._profile_picture_icons(args, region, http_client_cls=HttpClient)


def _player_profile_image_assets(
    args: argparse.Namespace, title_avatar_url: str | None, region: str
) -> tuple[dict[str, bytes], list[str]]:
    return player_assets._player_profile_image_assets(
        args,
        title_avatar_url,
        region,
        fetch_images=fetch_render_images,
    )


def _player_character_asset_images(
    args: argparse.Namespace,
    characters: list[Mapping[str, object]],
    region: str,
    *,
    extra_genshinuid_urls: list[str] | None = None,
) -> tuple[dict[str, bytes], list[str]]:
    return player_assets._player_character_asset_images(
        args,
        characters,
        region,
        extra_genshinuid_urls=extra_genshinuid_urls,
        fetch_images=fetch_render_images,
    )


def _append_url(urls: list[str], value: object) -> None:
    player_assets._append_url(urls, value)
