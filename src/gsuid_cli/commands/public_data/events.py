from __future__ import annotations

import argparse
from datetime import datetime

from gsuid_cli.commands.public_data._common import (
    _limit,
    _mapping_data,
    _optional_text,
    _provider,
    _safe_filename,
)
from gsuid_cli.commands.render_assets import fetch_render_images
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.errors import EXIT_NO_RESULT, CliError
from gsuid_cli.core.models import CommandResult
from gsuid_cli.renderers.events import (
    announcement_detail_image_urls,
    event_image_urls,
    render_announcement_detail_card,
    render_announcements_list_card,
    render_events_card,
)

EVENT_IMAGE_WORKERS = 6
LATEST_ANNOUNCEMENT_SCAN_LIMIT = 10000

CAPABILITIES = [
    {
        "command": "events.list",
        "description": "List public event announcements.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "use",
    },
    {
        "command": "events.banners",
        "description": "List public event banner artwork URLs.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "use",
    },
    {
        "command": "codes.list",
        "description": "List public active redeem-code rows.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "announcements.list",
        "description": "List public game announcement rows.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "use",
    },
    {
        "command": "announcements.show",
        "description": "Show one public game announcement row.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "use",
    },
]


def events_list_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).events_list(include_all=args.all, limit=_limit(args.limit))
    if args.render == "data":
        return result
    return _events_render_result(args, result, "events")


def events_banners_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).event_banners(include_all=args.all, limit=_limit(args.limit))
    if args.render == "data":
        return result
    return _events_render_result(args, result, "banners")


def codes_list_command(args: argparse.Namespace) -> CommandResult:
    return _provider(args).codes_list()


def announcements_list_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).announcements_list(limit=_limit(args.limit))
    if args.render == "data":
        return result
    return _announcements_list_render_result(args, result)


def announcements_show_command(args: argparse.Namespace) -> CommandResult:
    provider = _provider(args)
    announcement_id = args.id
    warnings: list[str] = []
    if args.latest:
        latest = provider.announcements_list(limit=LATEST_ANNOUNCEMENT_SCAN_LIMIT)
        announcement_id, start_at = _latest_announcement(latest)
        warnings.extend(latest.warnings)
    result = provider.announcement_show(announcement_id=announcement_id)
    if args.latest:
        result.data["selected_announcement"] = {
            "mode": "latest",
            "id": announcement_id,
            "start_at": start_at,
        }
        result.warnings[:0] = warnings
    if args.render == "data":
        return result
    return _announcement_detail_render_result(args, result)


def register_events(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    events = groups.add_parser("events", help="Show public event data.")
    commands = events.add_subparsers(dest="events_command", required=True, metavar="<command>")

    list_parser = commands.add_parser("list", help="List active and upcoming events.")
    _add_event_args(list_parser)
    list_parser.set_defaults(handler=events_list_command, command_name="events.list")

    banners = commands.add_parser("banners", help="List event banner artwork URLs.")
    _add_event_args(banners)
    banners.set_defaults(handler=events_banners_command, command_name="events.banners")


def register_codes(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    codes = groups.add_parser("codes", help="Show public redeem-code data.")
    commands = codes.add_subparsers(dest="codes_command", required=True, metavar="<command>")
    list_parser = commands.add_parser("list", help="List active redeem-code rows.")
    list_parser.set_defaults(handler=codes_list_command, command_name="codes.list")


def register_announcements(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    announcements = groups.add_parser("announcements", help="Show public announcement rows.")
    commands = announcements.add_subparsers(
        dest="announcements_command",
        required=True,
        metavar="<command>",
    )

    list_parser = commands.add_parser("list", help="List public announcements.")
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.set_defaults(
        handler=announcements_list_command,
        command_name="announcements.list",
    )

    show = commands.add_parser("show", help="Show one public announcement.")
    selector = show.add_mutually_exclusive_group(required=True)
    selector.add_argument("--id")
    selector.add_argument("--latest", action="store_true", help="Show the newest announcement.")
    show.set_defaults(handler=announcements_show_command, command_name="announcements.show")


def _add_event_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--all", action="store_true", help="Include expired events.")
    parser.add_argument("--limit", type=int, default=20)


def _events_render_result(
    args: argparse.Namespace,
    result: CommandResult,
    render_kind: str,
) -> CommandResult:
    key = "banners" if render_kind == "banners" else "events"
    command_segment = "banners" if render_kind == "banners" else "list"
    asset_images, asset_warnings = fetch_render_images(
        args,
        event_image_urls(result.data, key),
        provider="event-assets",
        region="cn",
        category=f"events.{command_segment}.asset",
        unavailable_warning="{count} event banner images unavailable; rendered placeholders",
        max_workers=EVENT_IMAGE_WORKERS,
    )
    png = render_events_card(result.data, kind=render_kind, asset_images=asset_images)
    render_name = "events/banners" if render_kind == "banners" else "events/list"
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name=render_name,
        filename=f"{render_name.replace('/', '-')}.png",
        media_type="image/png",
        content=png,
        description="GenshinUID-style event list card",
        kind="image",
    )
    render_data = {
        "render": render_name,
        "artifact_sha256": artifact["sha256"],
    }
    data = {**result.data, **render_data} if args.render == "both" else render_data
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *asset_warnings],
        pagination=result.pagination,
    )


def _announcements_list_render_result(
    args: argparse.Namespace,
    result: CommandResult,
) -> CommandResult:
    png = render_announcements_list_card(result.data)
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="announcements/list",
        filename="announcements-list.png",
        media_type="image/png",
        content=png,
        description="GenshinUID-style announcement list card",
        kind="image",
    )
    render_data = {
        "render": "announcements/list",
        "artifact_sha256": artifact["sha256"],
    }
    data = {**result.data, **render_data} if args.render == "both" else render_data
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=result.warnings,
        pagination=result.pagination,
    )


def _announcement_detail_render_result(
    args: argparse.Namespace,
    result: CommandResult,
) -> CommandResult:
    announcement = _mapping_data(result, "announcement", "announcements.show")
    asset_images, asset_warnings = fetch_render_images(
        args,
        announcement_detail_image_urls(announcement),
        provider="announcement-assets",
        region="cn",
        category="announcements.show.asset",
        unavailable_warning="{count} announcement images unavailable; omitted from render",
        max_workers=EVENT_IMAGE_WORKERS,
    )
    png = render_announcement_detail_card(announcement, asset_images=asset_images)
    ann_id = _optional_text(announcement.get("id")) or "announcement"
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="announcements/show",
        filename=f"announcements-show_{_safe_filename(ann_id)}.png",
        media_type="image/png",
        content=png,
        description="GenshinUID-style announcement detail card",
        kind="image",
    )
    render_data = {
        "id": ann_id,
        "render": "announcements/show",
        "artifact_sha256": artifact["sha256"],
    }
    data = {**result.data, **render_data} if args.render == "both" else render_data
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=[*result.warnings, *asset_warnings],
        pagination=result.pagination,
    )


def _latest_announcement(result: CommandResult) -> tuple[str, str]:
    rows = result.data.get("announcements")
    newest: tuple[datetime, str, str] | None = None
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            ann_id = _optional_text(row.get("id") or row.get("ann_id"))
            start_at = _optional_text(row.get("start_at"))
            start_time = _announcement_start_time(start_at)
            if ann_id and start_at and start_time is not None:
                candidate = (start_time, ann_id, start_at)
                if newest is None or candidate[0] > newest[0]:
                    newest = candidate
    if newest is not None:
        return newest[1], newest[2]
    raise CliError(
        "NO_RESULT",
        "No latest announcement is available.",
        EXIT_NO_RESULT,
        {"command": "announcements.show", "selector": "latest"},
        source=result.source,
    )


def _announcement_start_time(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("/", "-")
    try:
        return datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
