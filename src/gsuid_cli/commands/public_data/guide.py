from __future__ import annotations

import argparse

from gsuid_cli.commands._text import (
    helps_from,
    record_primary_image,
    record_text_artifact,
    safe_filename_part,
    write_image_artifact,
    write_text_artifact,
)
from gsuid_cli.commands.public_data._common import (
    _image_ext,
    _limit,
    _mapping_data,
    _optional_text,
    _provider,
)
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, EXIT_NO_RESULT, CliError
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.render import render_image_enabled, render_result_data, render_text_enabled
from gsuid_cli.providers.assets import fetch_render_images
from gsuid_cli.providers.public import PRIMOGEMS_PLAN_ASSET_DIR, PublicDataProvider
from gsuid_cli.renderers.guide.image import (
    guide_abyss_image_urls,
    guide_theater_image_urls,
    render_guide_abyss_card,
    render_guide_theater_card,
)
from gsuid_cli.renderers.guide.text import (
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
from gsuid_cli.text import t as _t

WIKI_IMAGE_WORKERS = 8

CAPABILITIES = [
    {
        "command": "guide.character",
        "description": _t("gsuid.commands.public_data.guide.49_23.04633824"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "all"],
    },
    {
        "command": "guide.reference-panel",
        "description": _t("gsuid.commands.public_data.guide.56_23.ea246a71"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "all"],
    },
    {
        "command": "guide.route",
        "description": _t("gsuid.commands.public_data.guide.63_23.2defc29d"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "all"],
    },
    {
        "command": "guide.abyss",
        "description": _t("gsuid.commands.public_data.guide.70_23.b2d0ca14"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "guide.theater",
        "description": _t("gsuid.commands.public_data.guide.77_23.d240b5d8"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "recommend.build",
        "description": _t("gsuid.commands.public_data.guide.84_23.3410daf0"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "recommend.holder",
        "description": _t("gsuid.commands.public_data.guide.91_23.32bf1541"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "map.find",
        "description": _t("gsuid.commands.public_data.guide.98_23.2708cd03"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "all"],
    },
    {
        "command": "rerun.list",
        "description": _t("gsuid.commands.public_data.guide.105_23.90adada0"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "misc.primogems-plan",
        "description": _t("gsuid.commands.public_data.guide.112_23.88addaea"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "all"],
    },
]

_HELPS = helps_from(CAPABILITIES)


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
    guide = groups.add_parser("guide", help=_t("gsuid.commands.public_data.guide.207_44.81b59406"))
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
    recommend = groups.add_parser(
        "recommend", help=_t("gsuid.commands.public_data.guide.234_52.2a94c1d7")
    )
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
    map_group = groups.add_parser(
        "map", help=_t("gsuid.commands.public_data.guide.251_46.0bdd019e")
    )
    commands = map_group.add_subparsers(dest="map_command", required=True, metavar="<command>")
    find = commands.add_parser("find", help=_HELPS["map.find"])
    find.add_argument("--item", required=True)
    find.add_argument("--map", choices=("teyvat", "chasm", "enkanomiya"), default="teyvat")
    find.set_defaults(handler=map_find_command, command_name="map.find")


def register_rerun(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    rerun = groups.add_parser("rerun", help=_t("gsuid.commands.public_data.guide.260_44.20e56405"))
    commands = rerun.add_subparsers(dest="rerun_command", required=True, metavar="<command>")
    list_parser = commands.add_parser("list", help=_HELPS["rerun.list"])
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.set_defaults(handler=rerun_list_command, command_name="rerun.list")


def register_misc(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    misc = groups.add_parser("misc", help=_t("gsuid.commands.public_data.guide.268_42.aa7062a4"))
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
    artifact = write_image_artifact(
        args,
        name=render_name,
        filename=f"{render_name.replace('/', '-')}_{safe_filename_part(character)}."
        f"{_image_ext(response.media_type)}",
        media_type=response.media_type,
        content=response.content,
        description=_t("gsuid.commands.public_data.guide.292_20.238a6744", render_name),
    )
    render_data: dict[str, object] = {"character": character}
    record_primary_image(render_data, artifact)
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
            unavailable_warning=(_t("gsuid.commands.public_data.guide.332_33.7547eac6")),
            max_workers=WIKI_IMAGE_WORKERS,
        )
        png = render_guide_abyss_card(render_abyss, asset_images=asset_images)
        image_artifact = write_image_artifact(
            args,
            name="guide/abyss",
            filename=f"guide-abyss_{safe_filename_part(str(name))}.png",
            content=png,
            description=_t("gsuid.commands.public_data.guide.341_24.2dcf3754"),
        )
        artifacts.append(image_artifact)
        warnings.extend(asset_warnings)
        record_primary_image(render_data, image_artifact)
    if render_text_enabled(args):
        text_artifact = write_text_artifact(
            args,
            name="guide/abyss-text",
            filename=f"guide-abyss_{safe_filename_part(str(name))}.txt",
            content=render_guide_abyss_text(result.data),
            description=_t("gsuid.commands.public_data.guide.352_24.e170151c"),
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
            unavailable_warning=_t("gsuid.commands.challenge.364_33.67d18b00"),
            max_workers=WIKI_IMAGE_WORKERS,
        )
        png = render_guide_theater_card(theater, asset_images=asset_images)
        image_artifact = write_image_artifact(
            args,
            name="guide/theater",
            filename=f"guide-theater_{safe_filename_part(name)}.png",
            content=png,
            description=_t("gsuid.commands.public_data.guide.391_24.b3665b27"),
        )
        artifacts.append(image_artifact)
        warnings.extend(asset_warnings)
        record_primary_image(render_data, image_artifact)
    if render_text_enabled(args):
        text_artifact = write_text_artifact(
            args,
            name="guide/theater-text",
            filename=f"guide-theater_{safe_filename_part(name)}.txt",
            content=render_guide_theater_text(result.data),
            description=_t("gsuid.commands.public_data.guide.402_24.69666d4f"),
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


def _recommend_render_result(
    args: argparse.Namespace,
    result: CommandResult,
    render_kind: str,
) -> CommandResult:
    if render_kind == "build":
        name = _optional_text(result.data.get("character")) or "build"
        render_name = "recommend/build"
        description = _t("gsuid.commands.public_data.guide.424_22.5c7dcac6")
        text_content = render_recommend_build_text(result.data)
        text_description = _t("gsuid.commands.public_data.guide.426_27.4d28f3c5")
    elif render_kind == "holder":
        name = _optional_text(result.data.get("item")) or "holder"
        render_name = "recommend/holder"
        description = _t("gsuid.commands.public_data.guide.430_22.7c7ce9e3")
        text_content = render_recommend_holder_text(result.data)
        text_description = _t("gsuid.commands.public_data.guide.432_27.54751650")
    else:
        raise CliError(
            "INVALID_ARGUMENT",
            _t("gsuid.commands.public_data.guide.436_12.69f3d275"),
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
        image_artifact = write_image_artifact(
            args,
            name=render_name,
            filename=f"{render_name.replace('/', '-')}_{safe_filename_part(name)}.png",
            content=png,
            description=description,
        )
        artifacts.append(image_artifact)
        record_primary_image(render_data, image_artifact)
    if render_text_enabled(args):
        text_render_name = f"{render_name}-text"
        text_artifact = write_text_artifact(
            args,
            name=text_render_name,
            filename=f"{render_name.replace('/', '-')}_{safe_filename_part(name)}.txt",
            content=text_content,
            description=text_description,
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
            unavailable_warning=_t("gsuid.commands.public_data.guide.494_32.26739b58"),
            max_workers=WIKI_IMAGE_WORKERS,
        )
        png = render_rerun_list(result.data, asset_images=asset_images)
        image_artifact = write_image_artifact(
            args,
            name="rerun/list",
            filename=f"rerun-list_{safe_filename_part(version)}.png",
            content=png,
            description=_t("gsuid.commands.public_data.guide.503_24.d911a09f"),
        )
        artifacts.append(image_artifact)
        warnings.extend(asset_warnings)
        record_primary_image(render_data, image_artifact)
    if render_text_enabled(args):
        text_artifact = write_text_artifact(
            args,
            name="rerun/list-text",
            filename=f"rerun-list_{safe_filename_part(version)}.txt",
            content=render_rerun_list_text(result.data),
            description=_t("gsuid.commands.public_data.guide.514_24.f041c912"),
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


def _primogems_plan_render_result(args: argparse.Namespace, result: CommandResult) -> CommandResult:
    selected_version = _optional_text(result.data.get("selected_version"))
    if selected_version is None:
        raise CliError(
            "NO_RESULT",
            _t("gsuid.commands.public_data.guide.533_12.b441b1f0"),
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
            _t("gsuid.commands.public_data.guide.547_12.14eaebbb"),
            EXIT_NO_RESULT,
            {"version": selected_version, "path": str(image_path)},
            source=result.source,
        ) from exc
    artifact = write_image_artifact(
        args,
        name="misc/primogems-plan",
        filename=f"primogems-plan_{safe_filename_part(selected_version)}.png",
        content=content,
        description=_t("gsuid.commands.public_data.guide.557_20.8e915985"),
    )
    render_data: dict[str, object] = {
        "version": result.data.get("version"),
        "selected_version": selected_version,
    }
    record_primary_image(render_data, artifact)
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
        f"{artifact_name}_{safe_filename_part(map_name)}_"
        f"{safe_filename_part(item)}.{_image_ext(response.media_type)}"
    )
    artifact = write_image_artifact(
        args,
        name=artifact_name,
        filename=filename,
        media_type=response.media_type,
        content=response.content,
        description=_t("gsuid.commands.public_data.guide.292_20.238a6744", command),
    )
    return CommandResult(
        data={
            "item": item,
            "map": map_name,
            "matched_aliases": [],
            "marker_count": None,
            "bounds": None,
            "artifact_sha256": artifact["sha256"],
            "source_limitations": [_t("gsuid.commands.public_data.guide.607_35.ab9ac577")],
        },
        artifacts=[artifact],
        source=response.source,
    )
