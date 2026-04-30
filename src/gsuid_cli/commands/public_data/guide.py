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
from gsuid_cli.commands.render_assets import fetch_render_images
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, CliError
from gsuid_cli.core.models import CommandResult
from gsuid_cli.providers.public import PublicDataProvider
from gsuid_cli.renderers.guide import (
    guide_abyss_image_urls,
    guide_theater_image_urls,
    render_guide_abyss_card,
    render_guide_theater_card,
)
from gsuid_cli.renderers.recommend import (
    render_recommend_build_card,
    render_recommend_holder_card,
)

WIKI_IMAGE_WORKERS = 8

CAPABILITIES = [
    {
        "command": "guide.character",
        "description": "Show public character guide facts and GenshinUID guide image.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "use",
    },
    {
        "command": "guide.reference-panel",
        "description": "Show the GenshinUID reference-panel image for a character.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "use",
    },
    {
        "command": "guide.route",
        "description": "Fetch a public material route map artifact.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "use",
    },
    {
        "command": "guide.abyss",
        "description": "Show public abyss guide data and GenshinUID-style monster layout.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "use",
    },
    {
        "command": "guide.theater",
        "description": "Show public theater guide data and GenshinUID-style monster layout.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "use",
    },
    {
        "command": "recommend.build",
        "description": "Show GenshinUID character build recommendations.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "use",
    },
    {
        "command": "recommend.holder",
        "description": "Show GenshinUID holder recommendations for a weapon or artifact.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "use",
    },
    {
        "command": "map.find",
        "description": "Fetch a public MiniGG material map artifact.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "use",
    },
    {
        "command": "rerun.list",
        "description": "List wish-banner rows for rerun analysis.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "misc.primogems-plan",
        "description": "Report public primogem estimate availability.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
]


def guide_character_command(args: argparse.Namespace) -> CommandResult:
    provider = _provider(args)
    result = provider.guide_character(character=args.name)
    if args.render == "data":
        return result
    character = _optional_text(result.data.get("character")) or args.name
    return _guide_image_result(
        args, result, provider=provider, kind="character", character=character
    )


def reference_panel_command(args: argparse.Namespace) -> CommandResult:
    provider = _provider(args)
    result = provider.reference_panel(character=args.character)
    if args.render == "data":
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
    if args.render == "data":
        return result
    return _guide_abyss_render_result(args, result)


def guide_theater_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).guide_theater(version=args.version)
    if args.render == "data":
        return result
    return _guide_theater_render_result(args, result)


def recommend_build_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).recommend_build(character=args.character)
    if args.render == "data":
        return result
    return _recommend_render_result(args, result, "build")


def recommend_holder_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).recommend_holder(item=args.item)
    if args.render == "data":
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
    return _provider(args).rerun_list(limit=_limit(args.limit))


def primogems_plan_command(args: argparse.Namespace) -> CommandResult:
    return _provider(args).primogems_plan(version=args.version)


def register_guides(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    guide = groups.add_parser("guide", help="Show public guide data.")
    commands = guide.add_subparsers(dest="guide_command", required=True, metavar="<command>")

    character = commands.add_parser("character", help="Show character guide facts.")
    character.add_argument("--name", required=True)
    character.set_defaults(handler=guide_character_command, command_name="guide.character")

    reference = commands.add_parser("reference-panel", help="Show reference panel availability.")
    reference.add_argument("--character", required=True)
    reference.set_defaults(handler=reference_panel_command, command_name="guide.reference-panel")

    route = commands.add_parser("route", help="Fetch a material route map artifact.")
    route.add_argument("--material", required=True)
    route.add_argument("--map", choices=("teyvat", "chasm", "enkanomiya"), default="teyvat")
    route.set_defaults(handler=guide_route_command, command_name="guide.route")

    abyss = commands.add_parser("abyss", help="Show abyss guide data.")
    abyss.add_argument("--version")
    abyss.add_argument("--floor", type=int, choices=(11, 12))
    abyss.set_defaults(handler=guide_abyss_command, command_name="guide.abyss")

    theater = commands.add_parser("theater", help="Show theater guide data.")
    theater.add_argument("--version")
    theater.set_defaults(handler=guide_theater_command, command_name="guide.theater")


def register_recommend(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    recommend = groups.add_parser("recommend", help="Show recommendation data.")
    commands = recommend.add_subparsers(
        dest="recommend_command",
        required=True,
        metavar="<command>",
    )

    build = commands.add_parser("build", help="Show character build recommendation availability.")
    build.add_argument("--character", required=True)
    build.set_defaults(handler=recommend_build_command, command_name="recommend.build")

    holder = commands.add_parser("holder", help="Show item holder recommendation availability.")
    holder.add_argument("--item", required=True)
    holder.set_defaults(handler=recommend_holder_command, command_name="recommend.holder")


def register_map(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    map_group = groups.add_parser("map", help="Fetch public map artifacts.")
    commands = map_group.add_subparsers(dest="map_command", required=True, metavar="<command>")
    find = commands.add_parser("find", help="Fetch a material map artifact.")
    find.add_argument("--item", required=True)
    find.add_argument("--map", choices=("teyvat", "chasm", "enkanomiya"), default="teyvat")
    find.set_defaults(handler=map_find_command, command_name="map.find")


def register_rerun(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    rerun = groups.add_parser("rerun", help="Show public rerun data.")
    commands = rerun.add_subparsers(dest="rerun_command", required=True, metavar="<command>")
    list_parser = commands.add_parser("list", help="List banner rows for rerun analysis.")
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.set_defaults(handler=rerun_list_command, command_name="rerun.list")


def register_misc(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    misc = groups.add_parser("misc", help="Show miscellaneous public data.")
    commands = misc.add_subparsers(dest="misc_command", required=True, metavar="<command>")
    primogems = commands.add_parser("primogems-plan", help="Show primogem estimate availability.")
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
        description=f"GenshinUID {render_name} image",
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
    data = {**result.data, **render_data} if args.render == "both" else render_data
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=response.source,
        warnings=result.warnings,
        pagination=result.pagination,
    )


def _guide_abyss_render_result(args: argparse.Namespace, result: CommandResult) -> CommandResult:
    abyss = _mapping_data(result, "abyss", "guide.abyss")
    asset_images, asset_warnings = fetch_render_images(
        args,
        guide_abyss_image_urls(abyss),
        provider="guide-assets",
        region="cn",
        category="guide.abyss.asset",
        unavailable_warning="{count} guide abyss monster images unavailable; rendered placeholders",
        max_workers=WIKI_IMAGE_WORKERS,
    )
    render_abyss = dict(abyss)
    schedule = result.data.get("schedule")
    if isinstance(schedule, dict):
        render_abyss["version"] = schedule.get("show") or schedule.get("name")
    png = render_guide_abyss_card(render_abyss, asset_images=asset_images)
    name = f"{result.data.get('version') or 'abyss'}_floor{abyss.get('floor') or args.floor or 12}"
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="guide/abyss",
        filename=f"guide-abyss_{_safe_filename(str(name))}.png",
        media_type="image/png",
        content=png,
        description="GenshinUID-style abyss guide monster layout",
        kind="image",
    )
    render_data = {
        "version": result.data.get("version"),
        "floor": abyss.get("floor"),
        "render": "guide/abyss",
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


def _guide_theater_render_result(args: argparse.Namespace, result: CommandResult) -> CommandResult:
    theater = _mapping_data(result, "theater", "guide.theater")
    asset_images, asset_warnings = fetch_render_images(
        args,
        guide_theater_image_urls(theater),
        provider="guide-assets",
        region="cn",
        category="guide.theater.asset",
        unavailable_warning="{count} guide theater images unavailable; rendered placeholders",
        max_workers=WIKI_IMAGE_WORKERS,
    )
    png = render_guide_theater_card(theater, asset_images=asset_images)
    name = _optional_text(theater.get("event_id")) or _optional_text(result.data.get("version"))
    name = name or "theater"
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="guide/theater",
        filename=f"guide-theater_{_safe_filename(name)}.png",
        media_type="image/png",
        content=png,
        description="GenshinUID-style theater guide monster layout",
        kind="image",
    )
    render_data = {
        "version": result.data.get("version"),
        "render": "guide/theater",
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


def _recommend_render_result(
    args: argparse.Namespace,
    result: CommandResult,
    render_kind: str,
) -> CommandResult:
    if render_kind == "build":
        png = render_recommend_build_card(result.data)
        name = _optional_text(result.data.get("character")) or "build"
        render_name = "recommend/build"
        description = "GenshinUID-style build recommendation card"
    elif render_kind == "holder":
        png = render_recommend_holder_card(result.data)
        name = _optional_text(result.data.get("item")) or "holder"
        render_name = "recommend/holder"
        description = "GenshinUID-style holder recommendation card"
    else:
        raise CliError(
            "INVALID_ARGUMENT",
            "recommend renderer is not implemented for this command.",
            EXIT_INVALID_INPUT,
            {"render": render_kind},
        )
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name=render_name,
        filename=f"{render_name.replace('/', '-')}_{_safe_filename(name)}.png",
        media_type="image/png",
        content=png,
        description=description,
        kind="image",
    )
    render_data = {
        "name": name,
        "render": render_name,
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
        description=f"{command} image artifact",
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
            "source_limitations": [
                "MiniGG map output is image-only; marker coordinates are not available"
            ],
        },
        artifacts=[artifact],
        source=response.source,
    )
