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
        "description": "Show public character guide facts and GenshinUID guide image.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "all"],
        "cache": "use",
    },
    {
        "command": "guide.reference-panel",
        "description": "Show the GenshinUID reference-panel image for a character.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "all"],
        "cache": "use",
    },
    {
        "command": "guide.route",
        "description": "Fetch a public material route map artifact.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "all"],
        "cache": "use",
    },
    {
        "command": "guide.abyss",
        "description": "Show public abyss guide data and GenshinUID-style monster layout.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
        "cache": "use",
    },
    {
        "command": "guide.theater",
        "description": "Show public theater guide data and GenshinUID-style monster layout.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
        "cache": "use",
    },
    {
        "command": "recommend.build",
        "description": "Show GenshinUID character build recommendations.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
        "cache": "use",
    },
    {
        "command": "recommend.holder",
        "description": "Show GenshinUID holder recommendations for a weapon or artifact.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
        "cache": "use",
    },
    {
        "command": "map.find",
        "description": "Fetch a public MiniGG material map artifact.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "all"],
        "cache": "use",
    },
    {
        "command": "rerun.list",
        "description": "List rerun rows and render the GenshinUID return list.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
        "cache": "use",
    },
    {
        "command": "misc.primogems-plan",
        "description": "Show the GenshinUID static version-plan primogem image.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "all"],
        "cache": "use",
    },
]


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
            unavailable_warning=(
                "{count} guide abyss monster images unavailable; rendered placeholders"
            ),
            max_workers=WIKI_IMAGE_WORKERS,
        )
        png = render_guide_abyss_card(render_abyss, asset_images=asset_images)
        image_artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
            name="guide/abyss",
            filename=f"guide-abyss_{_safe_filename(str(name))}.png",
            media_type="image/png",
            content=png,
            description="GenshinUID-style abyss guide monster layout",
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
            description="Human-readable abyss guide text",
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
            unavailable_warning="{count} guide theater images unavailable; rendered placeholders",
            max_workers=WIKI_IMAGE_WORKERS,
        )
        png = render_guide_theater_card(theater, asset_images=asset_images)
        image_artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
            name="guide/theater",
            filename=f"guide-theater_{_safe_filename(name)}.png",
            media_type="image/png",
            content=png,
            description="GenshinUID-style theater guide monster layout",
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
            description="Human-readable theater guide text",
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
        description = "GenshinUID-style build recommendation card"
        text_content = render_recommend_build_text(result.data)
        text_description = "Human-readable build recommendation text"
    elif render_kind == "holder":
        name = _optional_text(result.data.get("item")) or "holder"
        render_name = "recommend/holder"
        description = "GenshinUID-style holder recommendation card"
        text_content = render_recommend_holder_text(result.data)
        text_description = "Human-readable holder recommendation text"
    else:
        raise CliError(
            "INVALID_ARGUMENT",
            "recommend renderer is not implemented for this command.",
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
            unavailable_warning="{count} rerun images unavailable; rendered placeholders",
            max_workers=WIKI_IMAGE_WORKERS,
        )
        png = render_rerun_list(result.data, asset_images=asset_images)
        image_artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
            name="rerun/list",
            filename=f"rerun-list_{_safe_filename(version)}.png",
            media_type="image/png",
            content=png,
            description="GenshinUID-style rerun return list",
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
            description="Human-readable rerun list text",
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
            "No bundled GenshinUID primogem plan image matches the requested version.",
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
            "Bundled GenshinUID primogem plan image is missing.",
            EXIT_NO_RESULT,
            {"version": selected_version, "path": str(image_path)},
            source=result.source,
        ) from exc
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="misc/primogems-plan",
        filename=f"primogems-plan_{_safe_filename(selected_version)}.png",
        media_type="image/png",
        content=content,
        description="GenshinUID static version-plan primogem image",
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
