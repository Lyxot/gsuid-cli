from __future__ import annotations

import argparse
from datetime import datetime

from gsuid_cli.commands._text import (
    helps_from,
    record_primary_image,
    record_text_artifact,
    safe_filename_part,
    write_image_artifact,
    write_text_artifact,
)
from gsuid_cli.commands.public_data._common import (
    _limit,
    _mapping_data,
    _optional_text,
    _provider,
)
from gsuid_cli.core.errors import EXIT_NO_RESULT, CliError
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.render import render_image_enabled, render_result_data, render_text_enabled
from gsuid_cli.providers.assets import fetch_render_images
from gsuid_cli.renderers.events.image import (
    announcement_detail_image_urls,
    event_image_urls,
    render_announcement_detail_card,
    render_announcements_list_card,
    render_events_card,
)
from gsuid_cli.renderers.events.text import (
    render_announcement_detail_text,
    render_announcements_list_text,
    render_codes_text,
    render_events_text,
)

EVENT_IMAGE_WORKERS = 6
LATEST_ANNOUNCEMENT_SCAN_LIMIT = 10000

CAPABILITIES = [
    {
        "command": "events.list",
        "description": "列出正在进行和即将开始的活动。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "events.banners",
        "description": "列出活动横幅图片 URL。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "codes.list",
        "description": "列出当前可用的兑换码。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "announcements.list",
        "description": "列出公开的游戏公告。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "announcements.show",
        "description": "显示单条公开的公告。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
]

_HELPS = helps_from(CAPABILITIES)


def events_list_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).events_list(include_all=args.all, limit=_limit(args.limit))
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return result
    return _events_render_result(args, result, "events")


def events_banners_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).event_banners(include_all=args.all, limit=_limit(args.limit))
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return result
    return _events_render_result(args, result, "banners")


def codes_list_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).codes_list()
    if not render_text_enabled(args):
        return result
    return _text_render_result(
        args,
        result=result,
        render_name="codes/list-text",
        filename="codes-list.txt",
        content=render_codes_text(result.data),
        description="兑换码列表",
    )


def announcements_list_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).announcements_list(limit=_limit(args.limit))
    if not (render_image_enabled(args) or render_text_enabled(args)):
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
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return result
    return _announcement_detail_render_result(args, result)


def register_events(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    events = groups.add_parser("events", help="显示公开的活动数据。")
    commands = events.add_subparsers(dest="events_command", required=True, metavar="<command>")

    list_parser = commands.add_parser("list", help=_HELPS["events.list"])
    _add_event_args(list_parser)
    list_parser.set_defaults(handler=events_list_command, command_name="events.list")

    banners = commands.add_parser("banners", help=_HELPS["events.banners"])
    _add_event_args(banners)
    banners.set_defaults(handler=events_banners_command, command_name="events.banners")


def register_codes(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    codes = groups.add_parser("codes", help="显示公开的兑换码数据。")
    commands = codes.add_subparsers(dest="codes_command", required=True, metavar="<command>")
    list_parser = commands.add_parser("list", help=_HELPS["codes.list"])
    list_parser.set_defaults(handler=codes_list_command, command_name="codes.list")


def register_announcements(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    announcements = groups.add_parser("announcements", help="显示公开的游戏公告。")
    commands = announcements.add_subparsers(
        dest="announcements_command",
        required=True,
        metavar="<command>",
    )

    list_parser = commands.add_parser("list", help=_HELPS["announcements.list"])
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.set_defaults(
        handler=announcements_list_command,
        command_name="announcements.list",
    )

    show = commands.add_parser("show", help=_HELPS["announcements.show"])
    selector = show.add_mutually_exclusive_group(required=True)
    selector.add_argument("--id")
    selector.add_argument("--latest", action="store_true", help="显示最新公告。")
    show.set_defaults(handler=announcements_show_command, command_name="announcements.show")


def _add_event_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--all", action="store_true", help="包含已结束的活动。")
    parser.add_argument("--limit", type=int, default=20)


def _events_render_result(
    args: argparse.Namespace,
    result: CommandResult,
    render_kind: str,
) -> CommandResult:
    key = "banners" if render_kind == "banners" else "events"
    command_segment = "banners" if render_kind == "banners" else "list"
    render_name = "events/banners" if render_kind == "banners" else "events/list"
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data: dict[str, object] = {}
    if render_image_enabled(args):
        asset_images, asset_warnings = fetch_render_images(
            args,
            event_image_urls(result.data, key),
            provider="event-assets",
            region="cn",
            category=f"events.{command_segment}.asset",
            unavailable_warning="{count} 个活动横幅图片不可用，已使用占位图",
            max_workers=EVENT_IMAGE_WORKERS,
        )
        png = render_events_card(result.data, kind=render_kind, asset_images=asset_images)
        image_artifact = write_image_artifact(
            args,
            name=render_name,
            filename=f"{render_name.replace('/', '-')}.png",
            content=png,
            description="活动列表卡片图片",
        )
        artifacts.append(image_artifact)
        warnings.extend(asset_warnings)
        record_primary_image(render_data, image_artifact)
    if render_text_enabled(args):
        text_render_name = f"{render_name}-text"
        text_artifact = write_text_artifact(
            args,
            name=text_render_name,
            filename=f"{render_name.replace('/', '-')}.txt",
            content=render_events_text(result.data, kind=render_kind),
            description="活动列表文本",
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


def _text_render_result(
    args: argparse.Namespace,
    *,
    result: CommandResult,
    render_name: str,
    filename: str,
    content: str,
    description: str,
) -> CommandResult:
    artifact = write_text_artifact(
        args,
        name=render_name,
        filename=filename,
        content=content,
        description=description,
    )
    data = render_result_data(
        args,
        result.data,
        {
            "render": render_name,
            "artifact_sha256": artifact["sha256"],
        },
    )
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=result.warnings,
        pagination=result.pagination,
    )


def _announcements_list_render_result(
    args: argparse.Namespace,
    result: CommandResult,
) -> CommandResult:
    artifacts: list[dict[str, object]] = []
    render_data: dict[str, object] = {}
    if render_image_enabled(args):
        png = render_announcements_list_card(result.data)
        image_artifact = write_image_artifact(
            args,
            name="announcements/list",
            filename="announcements-list.png",
            content=png,
            description="游戏公告列表卡片图片",
        )
        artifacts.append(image_artifact)
        record_primary_image(render_data, image_artifact)
    if render_text_enabled(args):
        text_render_name = "announcements/list-text"
        text_artifact = write_text_artifact(
            args,
            name=text_render_name,
            filename="announcements-list.txt",
            content=render_announcements_list_text(result.data),
            description="公告列表文本",
        )
        artifacts.append(text_artifact)
        record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=result.warnings,
        pagination=result.pagination,
    )


def _announcement_detail_render_result(
    args: argparse.Namespace,
    result: CommandResult,
) -> CommandResult:
    announcement = _mapping_data(result, "announcement", "announcements.show")
    ann_id = _optional_text(announcement.get("id")) or "announcement"
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data: dict[str, object] = {"id": ann_id}
    if render_image_enabled(args):
        asset_images, asset_warnings = fetch_render_images(
            args,
            announcement_detail_image_urls(announcement),
            provider="announcement-assets",
            region="cn",
            category="announcements.show.asset",
            unavailable_warning="{count} 张公告图片不可用，已在渲染时忽略",
            max_workers=EVENT_IMAGE_WORKERS,
        )
        png = render_announcement_detail_card(announcement, asset_images=asset_images)
        image_artifact = write_image_artifact(
            args,
            name="announcements/show",
            filename=f"announcements-show_{safe_filename_part(ann_id)}.png",
            content=png,
            description="公告详情卡片图片",
        )
        artifacts.append(image_artifact)
        warnings.extend(asset_warnings)
        record_primary_image(render_data, image_artifact)
    if render_text_enabled(args):
        text_render_name = "announcements/show-text"
        text_artifact = write_text_artifact(
            args,
            name=text_render_name,
            filename=f"announcements-show_{safe_filename_part(ann_id)}.txt",
            content=render_announcement_detail_text(announcement),
            description="公告详情文本",
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
        "找不到最新的公告。",
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
