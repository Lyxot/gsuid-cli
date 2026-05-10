from __future__ import annotations

import argparse

from gsuid_cli.commands.public_data._common import (
    _image_ext,
    _limit,
    _mapping_data,
    _optional_text,
    _provider,
    _safe_filename,
)
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, EXIT_NO_RESULT, CliError
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.render import render_image_enabled, render_result_data, render_text_enabled
from gsuid_cli.providers.assets import fetch_render_images
from gsuid_cli.providers.public import PRIMOGEMS_PLAN_ASSET_DIR, PublicDataProvider
from gsuid_cli.renderers.guide import (
    guide_abyss_image_urls,
    guide_theater_image_urls,
    render_guide_abyss_card,
    render_guide_theater_card,
)
from gsuid_cli.renderers.guide_text import (
    render_guide_abyss_text,
    render_guide_theater_text,
    render_recommend_build_text,
    render_recommend_holder_text,
    render_rerun_list_text,
)
from gsuid_cli.renderers.recommend import (
    render_recommend_build_card,
    render_recommend_holder_card,
)
from gsuid_cli.renderers.rerun import render_rerun_list, rerun_asset_urls

WIKI_IMAGE_WORKERS = 8

CAPABILITIES = [
    {
        "command": "guide.character",
        "description": "显示角色攻略内容。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "all"],
    },
    {
        "command": "guide.reference-panel",
        "description": "显示角色的参考面板。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "all"],
    },
    {
        "command": "guide.route",
        "description": "获取材料讨伐路线图。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "all"],
    },
    {
        "command": "guide.abyss",
        "description": "显示深境螺旋攻略数据。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "guide.theater",
        "description": "显示幻想真境剧诗攻略数据。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "recommend.build",
        "description": "显示角色养成建议。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "recommend.holder",
        "description": "显示武器或圣遗物的建议使用者。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "map.find",
        "description": "获取资源分布图。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "all"],
    },
    {
        "command": "rerun.list",
        "description": "列出祈愿池复刻信息。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "misc.primogems-plan",
        "description": "显示原石获取预估图。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "all"],
    },
]

_HELPS = {str(c["command"]): str(c["description"]) for c in CAPABILITIES}


def guide_character_command(args: argparse.Namespace) -> CommandResult:
    provider = _provider(args)
    result = provider.guide_character(character=args.name)
    if not render_image_enabled(args):
        return result
    character = _optional_text(result.data.get("character")) or args.name
    return _guide_image_result(
        args, result, provider=provider, kind="character", character=character
    )


def reference_panel_command(args: argparse.Namespace) -> CommandResult:
    provider = _provider(args)
    result = provider.reference_panel(character=args.character)
    if not render_image_enabled(args):
        return result
    character = _optional_text(result.data.get("character")) or args.character
    return _guide_image_result(
        args, result, provider=provider, kind="reference-panel", character=character
    )


def guide_route_command(args: argparse.Namespace) -> CommandResult:
    return _map_artifact_command(
        args,
        command="guide.route",
        item=args.material,
        map_name=args.map,
        artifact_name="guide_route",
    )


def guide_abyss_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).guide_abyss(version=args.version, floor=args.floor)
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return result
    return _guide_abyss_render_result(args, result)


def guide_theater_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).guide_theater(version=args.version)
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return result
    return _guide_theater_render_result(args, result)


def recommend_build_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).recommend_build(character=args.character)
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return result
    return _recommend_render_result(args, result, "build")


def recommend_holder_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).recommend_holder(item=args.item)
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return result
    return _recommend_render_result(args, result, "holder")


def map_find_command(args: argparse.Namespace) -> CommandResult:
    return _map_artifact_command(
        args,
        command="map.find",
        item=args.item,
        map_name=args.map,
        artifact_name="map",
    )


def rerun_list_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).rerun_list(limit=_limit(args.limit))
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return result
    return _rerun_render_result(args, result)


def primogems_plan_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).primogems_plan(version=args.version)
    if not render_image_enabled(args):
        return result
    return _primogems_plan_render_result(args, result)


def register_guides(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    guide = groups.add_parser("guide", help="显示公开的攻略数据。")
    commands = guide.add_subparsers(dest="guide_command", required=True, metavar="<command>")

    character = commands.add_parser("character", help=_HELPS["guide.character"])
    character.add_argument("--name", required=True)
    character.set_defaults(handler=guide_character_command, command_name="guide.character")

    reference = commands.add_parser("reference-panel", help=_HELPS["guide.reference-panel"])
    reference.add_argument("--character", required=True)
    reference.set_defaults(handler=reference_panel_command, command_name="guide.reference-panel")

    route = commands.add_parser("route", help=_HELPS["guide.route"])
    route.add_argument("--material", required=True)
    route.add_argument("--map", choices=("teyvat", "chasm", "enkanomiya"), default="teyvat")
    route.set_defaults(handler=guide_route_command, command_name="guide.route")

    abyss = commands.add_parser("abyss", help=_HELPS["guide.abyss"])
    abyss.add_argument("--version")
    abyss.add_argument("--floor", type=int, choices=(11, 12))
    abyss.set_defaults(handler=guide_abyss_command, command_name="guide.abyss")

    theater = commands.add_parser("theater", help=_HELPS["guide.theater"])
    theater.add_argument("--version")
    theater.set_defaults(handler=guide_theater_command, command_name="guide.theater")


def register_recommend(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    recommend = groups.add_parser("recommend", help="显示建议数据。")
    commands = recommend.add_subparsers(
        dest="recommend_command",
        required=True,
        metavar="<command>",
    )

    build = commands.add_parser("build", help=_HELPS["recommend.build"])
    build.add_argument("--character", required=True)
    build.set_defaults(handler=recommend_build_command, command_name="recommend.build")

    holder = commands.add_parser("holder", help=_HELPS["recommend.holder"])
    holder.add_argument("--item", required=True)
    holder.set_defaults(handler=recommend_holder_command, command_name="recommend.holder")


def register_map(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    map_group = groups.add_parser("map", help="获取公开的地图图片。")
    commands = map_group.add_subparsers(dest="map_command", required=True, metavar="<command>")
    find = commands.add_parser("find", help=_HELPS["map.find"])
    find.add_argument("--item", required=True)
    find.add_argument("--map", choices=("teyvat", "chasm", "enkanomiya"), default="teyvat")
    find.set_defaults(handler=map_find_command, command_name="map.find")


def register_rerun(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    rerun = groups.add_parser("rerun", help="显示公开的复刻数据。")
    commands = rerun.add_subparsers(dest="rerun_command", required=True, metavar="<command>")
    list_parser = commands.add_parser("list", help=_HELPS["rerun.list"])
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.set_defaults(handler=rerun_list_command, command_name="rerun.list")


def register_misc(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    misc = groups.add_parser("misc", help="显示其他的公开数据。")
    commands = misc.add_subparsers(dest="misc_command", required=True, metavar="<command>")
    primogems = commands.add_parser("primogems-plan", help=_HELPS["misc.primogems-plan"])
    primogems.add_argument("--version")
    primogems.set_defaults(handler=primogems_plan_command, command_name="misc.primogems-plan")


def _guide_image_result(
    args: argparse.Namespace,
    result: CommandResult,
    *,
    provider: PublicDataProvider,
    kind: str,
    character: str,
) -> CommandResult:
    response = provider.guide_image(kind=kind, character=character)
    render_name = "guide/character" if kind == "character" else "guide/reference-panel"
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name=render_name,
        filename=f"{render_name.replace('/', '-')}_{_safe_filename(character)}."
        f"{_image_ext(response.media_type)}",
        media_type=response.media_type,
        content=response.content,
        description=f"{render_name} 图片",
        kind="image",
    )
    render_data = {
        "character": character,
        "render": render_name,
        "artifact_sha256": artifact["sha256"],
    }
    if kind == "reference-panel":
        render_data["available"] = True
        render_data["reference_panel"] = {
            "format": "image",
            "artifact_sha256": artifact["sha256"],
        }
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=response.source,
        warnings=result.warnings,
        pagination=result.pagination,
    )


def _guide_abyss_render_result(args: argparse.Namespace, result: CommandResult) -> CommandResult:
    abyss = _mapping_data(result, "abyss", "guide.abyss")
    render_abyss = dict(abyss)
    schedule = result.data.get("schedule")
    if isinstance(schedule, dict):
        render_abyss["version"] = schedule.get("show") or schedule.get("name")
    name = f"{result.data.get('version') or 'abyss'}_floor{abyss.get('floor') or args.floor or 12}"
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data: dict[str, object] = {
        "version": result.data.get("version"),
        "floor": abyss.get("floor"),
    }
    if render_image_enabled(args):
        asset_images, asset_warnings = fetch_render_images(
            args,
            guide_abyss_image_urls(abyss),
            provider="guide-assets",
            region="cn",
            category="guide.abyss.asset",
            unavailable_warning=("{count} 个深境螺旋怪物图片不可用，已使用占位图"),
            max_workers=WIKI_IMAGE_WORKERS,
        )
        png = render_guide_abyss_card(render_abyss, asset_images=asset_images)
        image_artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
            name="guide/abyss",
            filename=f"guide-abyss_{_safe_filename(str(name))}.png",
            media_type="image/png",
            content=png,
            description="深境螺旋怪物排布图片",
            kind="image",
        )
        artifacts.append(image_artifact)
        warnings.extend(asset_warnings)
        render_data.update(
            {
                "render": "guide/abyss",
                "artifact_sha256": image_artifact["sha256"],
            }
        )
    if render_text_enabled(args):
        text_artifact = ArtifactManager(args.request_id, args.output_dir).write_text(
            name="guide/abyss-text",
            filename=f"guide-abyss_{_safe_filename(str(name))}.txt",
            content=render_guide_abyss_text(result.data),
            description="深境螺旋攻略文本",
            kind="text",
        )
        artifacts.append(text_artifact)
        if render_image_enabled(args):
            render_data["text_artifact_sha256"] = text_artifact["sha256"]
        else:
            render_data.update(
                {
                    "render": "guide/abyss-text",
                    "artifact_sha256": text_artifact["sha256"],
                }
            )
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
        pagination=result.pagination,
    )


def _guide_theater_render_result(args: argparse.Namespace, result: CommandResult) -> CommandResult:
    theater = _mapping_data(result, "theater", "guide.theater")
    name = _optional_text(theater.get("event_id")) or _optional_text(result.data.get("version"))
    name = name or "theater"
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data: dict[str, object] = {
        "version": result.data.get("version"),
    }
    if render_image_enabled(args):
        asset_images, asset_warnings = fetch_render_images(
            args,
            guide_theater_image_urls(theater),
            provider="guide-assets",
            region="cn",
            category="guide.theater.asset",
            unavailable_warning="{count} 个幻想真境剧诗图片不可用，已使用占位图",
            max_workers=WIKI_IMAGE_WORKERS,
        )
        png = render_guide_theater_card(theater, asset_images=asset_images)
        image_artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
            name="guide/theater",
            filename=f"guide-theater_{_safe_filename(name)}.png",
            media_type="image/png",
            content=png,
            description="幻想真境剧诗怪物排布图片",
            kind="image",
        )
        artifacts.append(image_artifact)
        warnings.extend(asset_warnings)
        render_data.update(
            {
                "render": "guide/theater",
                "artifact_sha256": image_artifact["sha256"],
            }
        )
    if render_text_enabled(args):
        text_artifact = ArtifactManager(args.request_id, args.output_dir).write_text(
            name="guide/theater-text",
            filename=f"guide-theater_{_safe_filename(name)}.txt",
            content=render_guide_theater_text(result.data),
            description="幻想真境剧诗攻略文本",
            kind="text",
        )
        artifacts.append(text_artifact)
        if render_image_enabled(args):
            render_data["text_artifact_sha256"] = text_artifact["sha256"]
        else:
            render_data.update(
                {
                    "render": "guide/theater-text",
                    "artifact_sha256": text_artifact["sha256"],
                }
            )
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
        pagination=result.pagination,
    )


def _recommend_render_result(
    args: argparse.Namespace,
    result: CommandResult,
    render_kind: str,
) -> CommandResult:
    if render_kind == "build":
        name = _optional_text(result.data.get("character")) or "build"
        render_name = "recommend/build"
        description = "养成建议卡片图片"
        text_content = render_recommend_build_text(result.data)
        text_description = "养成建议文本"
    elif render_kind == "holder":
        name = _optional_text(result.data.get("item")) or "holder"
        render_name = "recommend/holder"
        description = "建议使用者卡片图片"
        text_content = render_recommend_holder_text(result.data)
        text_description = "建议使用者文本"
    else:
        raise CliError(
            "INVALID_ARGUMENT",
            "此命令未实现推荐渲染器。",
            EXIT_INVALID_INPUT,
            {"render": render_kind},
        )
    artifacts: list[dict[str, object]] = []
    render_data: dict[str, object] = {
        "name": name,
    }
    if render_image_enabled(args):
        png = (
            render_recommend_build_card(result.data)
            if render_kind == "build"
            else render_recommend_holder_card(result.data)
        )
        image_artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
            name=render_name,
            filename=f"{render_name.replace('/', '-')}_{_safe_filename(name)}.png",
            media_type="image/png",
            content=png,
            description=description,
            kind="image",
        )
        artifacts.append(image_artifact)
        render_data.update(
            {
                "render": render_name,
                "artifact_sha256": image_artifact["sha256"],
            }
        )
    if render_text_enabled(args):
        text_render_name = f"{render_name}-text"
        text_artifact = ArtifactManager(args.request_id, args.output_dir).write_text(
            name=text_render_name,
            filename=f"{render_name.replace('/', '-')}_{_safe_filename(name)}.txt",
            content=text_content,
            description=text_description,
            kind="text",
        )
        artifacts.append(text_artifact)
        if render_image_enabled(args):
            render_data["text_artifact_sha256"] = text_artifact["sha256"]
        else:
            render_data.update(
                {
                    "render": text_render_name,
                    "artifact_sha256": text_artifact["sha256"],
                }
            )
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=result.warnings,
        pagination=result.pagination,
    )


def _rerun_render_result(args: argparse.Namespace, result: CommandResult) -> CommandResult:
    version = _optional_text(result.data.get("version")) or "rerun"
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data: dict[str, object] = {
        "version": result.data.get("version"),
    }
    if render_image_enabled(args):
        asset_images, asset_warnings = fetch_render_images(
            args,
            rerun_asset_urls(result.data),
            provider="rerun-assets",
            region="cn",
            category="rerun.list.asset",
            unavailable_warning="{count} 张复刻图片不可用，已使用占位图",
            max_workers=WIKI_IMAGE_WORKERS,
        )
        png = render_rerun_list(result.data, asset_images=asset_images)
        image_artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
            name="rerun/list",
            filename=f"rerun-list_{_safe_filename(version)}.png",
            media_type="image/png",
            content=png,
            description="复刻列表卡片图片",
            kind="image",
        )
        artifacts.append(image_artifact)
        warnings.extend(asset_warnings)
        render_data.update(
            {
                "render": "rerun/list",
                "artifact_sha256": image_artifact["sha256"],
            }
        )
    if render_text_enabled(args):
        text_artifact = ArtifactManager(args.request_id, args.output_dir).write_text(
            name="rerun/list-text",
            filename=f"rerun-list_{_safe_filename(version)}.txt",
            content=render_rerun_list_text(result.data),
            description="复刻列表文本",
            kind="text",
        )
        artifacts.append(text_artifact)
        if render_image_enabled(args):
            render_data["text_artifact_sha256"] = text_artifact["sha256"]
        else:
            render_data.update(
                {
                    "render": "rerun/list-text",
                    "artifact_sha256": text_artifact["sha256"],
                }
            )
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
        pagination=result.pagination,
    )


def _primogems_plan_render_result(args: argparse.Namespace, result: CommandResult) -> CommandResult:
    selected_version = _optional_text(result.data.get("selected_version"))
    if selected_version is None:
        raise CliError(
            "NO_RESULT",
            "未找到匹配指定版本的预估原石获取图。",
            EXIT_NO_RESULT,
            {
                "version": result.data.get("version"),
                "available_versions": result.data.get("available_versions"),
            },
            source=result.source,
        )
    image_path = PRIMOGEMS_PLAN_ASSET_DIR / f"{selected_version}.png"
    try:
        content = image_path.read_bytes()
    except OSError as exc:
        raise CliError(
            "NO_RESULT",
            "内置的原石预估图丢失。",
            EXIT_NO_RESULT,
            {"version": selected_version, "path": str(image_path)},
            source=result.source,
        ) from exc
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="misc/primogems-plan",
        filename=f"primogems-plan_{_safe_filename(selected_version)}.png",
        media_type="image/png",
        content=content,
        description="版本原石预估图片",
        kind="image",
    )
    render_data = {
        "version": result.data.get("version"),
        "selected_version": selected_version,
        "render": "misc/primogems-plan",
        "artifact_sha256": artifact["sha256"],
    }
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=result.warnings,
        pagination=result.pagination,
    )


def _map_artifact_command(
    args: argparse.Namespace,
    *,
    command: str,
    item: str,
    map_name: str,
    artifact_name: str,
) -> CommandResult:
    response = _provider(args).map_image(
        item=item,
        map_name=map_name,
        category=command,
    )
    filename = (
        f"{artifact_name}_{_safe_filename(map_name)}_"
        f"{_safe_filename(item)}.{_image_ext(response.media_type)}"
    )
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name=artifact_name,
        filename=filename,
        media_type=response.media_type,
        content=response.content,
        description=f"{command} 图片",
        kind="image",
    )
    return CommandResult(
        data={
            "item": item,
            "map": map_name,
            "matched_aliases": [],
            "marker_count": None,
            "bounds": None,
            "artifact_sha256": artifact["sha256"],
            "source_limitations": ["MiniGG 地图输出仅包含图片；不可获取标记坐标信息"],
        },
        artifacts=[artifact],
        source=response.source,
    )
