from __future__ import annotations

import argparse
import hashlib

from gsuid_cli.commands.auth import _credential, _uid_and_region
from gsuid_cli.commands.rendering import maybe_render_image
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.providers import provider_for_region
from gsuid_cli.providers.public import DAY_NAMES, PublicDataProvider
from gsuid_cli.renderers.cards import render_daily_note

CAPABILITIES = [
    {
        "command": "wiki.character",
        "description": "Look up public character data.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "wiki.weapon",
        "description": "Look up public weapon data.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "wiki.artifact",
        "description": "Look up public artifact set data.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "wiki.enemy",
        "description": "Look up public enemy data.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "wiki.food",
        "description": "Look up public food data.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "wiki.talent",
        "description": "Look up public character talent data.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "wiki.constellation",
        "description": "Look up public character constellation data.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "wiki.character-materials",
        "description": "Show public character material data.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "wiki.weapon-materials",
        "description": "Show public weapon material data.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "events.list",
        "description": "List public event announcements.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "events.banners",
        "description": "List public event banner artwork URLs.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
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
        "command": "daily.materials",
        "description": "List daily talent and weapon material domains.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "daily.note",
        "description": "Show current resin, commissions, expeditions, and teapot status.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
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
    {
        "command": "guide.character",
        "description": "Show public character guide facts.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "guide.reference-panel",
        "description": "Report public reference-panel availability for a character.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "guide.route",
        "description": "Fetch a public material route map artifact.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "off",
    },
    {
        "command": "guide.abyss",
        "description": "Report public abyss guide availability.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "guide.theater",
        "description": "Report public theater guide availability.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "recommend.build",
        "description": "Report public build recommendation availability.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "recommend.holder",
        "description": "Report public holder recommendation availability.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "announcements.list",
        "description": "List public event announcement rows.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "announcements.show",
        "description": "Show one public event announcement row.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "map.find",
        "description": "Fetch a public MiniGG material map artifact.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "off",
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


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    _register_wiki(groups)
    _register_events(groups)
    _register_codes(groups)
    _register_daily(groups)
    _register_guides(groups)
    _register_recommend(groups)
    _register_announcements(groups)
    _register_map(groups)
    _register_rerun(groups)
    _register_misc(groups)


def wiki_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).wiki_lookup(kind=args.wiki_kind, query=_wiki_query(args))
    if getattr(args, "level", None) is not None:
        result.data["requested_level"] = args.level
        result.warnings.append("level-specific stats are not implemented; returned base wiki data")
    return result


def events_list_command(args: argparse.Namespace) -> CommandResult:
    return _provider(args).events_list(include_all=args.all, limit=_limit(args.limit))


def events_banners_command(args: argparse.Namespace) -> CommandResult:
    return _provider(args).event_banners(include_all=args.all, limit=_limit(args.limit))


def codes_list_command(args: argparse.Namespace) -> CommandResult:
    return _provider(args).codes_list()


def daily_materials_command(args: argparse.Namespace) -> CommandResult:
    return _provider(args).daily_materials(day=args.day, date=args.date)


def talent_command(args: argparse.Namespace) -> CommandResult:
    return _provider(args).character_talent(
        character=args.character, talent=_positive(args.talent, "talent")
    )


def constellation_command(args: argparse.Namespace) -> CommandResult:
    return _provider(args).character_constellation(
        character=args.character,
        constellation=_positive(args.constellation, "constellation")
        if args.constellation is not None
        else None,
    )


def character_materials_command(args: argparse.Namespace) -> CommandResult:
    return _provider(args).character_materials(character=args.character)


def weapon_materials_command(args: argparse.Namespace) -> CommandResult:
    return _provider(args).weapon_materials(weapon=args.weapon)


def guide_character_command(args: argparse.Namespace) -> CommandResult:
    return _provider(args).guide_character(character=args.name)


def reference_panel_command(args: argparse.Namespace) -> CommandResult:
    return _provider(args).reference_panel(character=args.character)


def guide_route_command(args: argparse.Namespace) -> CommandResult:
    return _map_artifact_command(
        args,
        command="guide.route",
        item=args.material,
        map_name=args.map,
        artifact_name="guide_route",
    )


def guide_abyss_command(args: argparse.Namespace) -> CommandResult:
    return _provider(args).guide_abyss(version=args.version, floor=args.floor)


def guide_theater_command(args: argparse.Namespace) -> CommandResult:
    return _provider(args).guide_theater(version=args.version)


def recommend_build_command(args: argparse.Namespace) -> CommandResult:
    return _provider(args).recommend_build(character=args.character)


def recommend_holder_command(args: argparse.Namespace) -> CommandResult:
    return _provider(args).recommend_holder(item=args.item)


def announcements_list_command(args: argparse.Namespace) -> CommandResult:
    return _provider(args).announcements_list(limit=_limit(args.limit))


def announcements_show_command(args: argparse.Namespace) -> CommandResult:
    return _provider(args).announcement_show(announcement_id=args.id)


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


def daily_note_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    result = _auth_provider(args, region).daily_note(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    return maybe_render_image(
        args,
        result,
        renderer=render_daily_note,
        name="daily_note",
        filename=f"daily_note_{uid}.png",
        description="Rendered daily note card",
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


def _register_wiki(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    wiki = groups.add_parser("wiki", help="Look up public wiki data.")
    commands = wiki.add_subparsers(dest="wiki_command", required=True, metavar="<command>")
    for kind in ("character", "weapon", "artifact", "enemy", "food"):
        command = commands.add_parser(kind, help=f"Look up a {kind}.")
        command.add_argument("query", nargs="?")
        command.add_argument("--name")
        if kind in {"character", "weapon"}:
            command.add_argument("--level", type=int)
        command.set_defaults(handler=wiki_command, command_name=f"wiki.{kind}", wiki_kind=kind)

    talent = commands.add_parser("talent", help="Look up a character talent.")
    talent.add_argument("--character", required=True)
    talent.add_argument("--talent", type=int, required=True)
    talent.set_defaults(handler=talent_command, command_name="wiki.talent")

    constellation = commands.add_parser("constellation", help="Look up character constellations.")
    constellation.add_argument("--character", required=True)
    constellation.add_argument("--constellation", type=int)
    constellation.set_defaults(handler=constellation_command, command_name="wiki.constellation")

    character_materials = commands.add_parser(
        "character-materials",
        help="Show character material data.",
    )
    character_materials.add_argument("--character", required=True)
    character_materials.set_defaults(
        handler=character_materials_command,
        command_name="wiki.character-materials",
    )

    weapon_materials = commands.add_parser("weapon-materials", help="Show weapon material data.")
    weapon_materials.add_argument("--weapon", required=True)
    weapon_materials.set_defaults(
        handler=weapon_materials_command,
        command_name="wiki.weapon-materials",
    )


def _register_events(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    events = groups.add_parser("events", help="Show public event data.")
    commands = events.add_subparsers(dest="events_command", required=True, metavar="<command>")

    list_parser = commands.add_parser("list", help="List active and upcoming events.")
    _add_event_args(list_parser)
    list_parser.set_defaults(handler=events_list_command, command_name="events.list")

    banners = commands.add_parser("banners", help="List event banner artwork URLs.")
    _add_event_args(banners)
    banners.set_defaults(handler=events_banners_command, command_name="events.banners")


def _register_codes(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    codes = groups.add_parser("codes", help="Show public redeem-code data.")
    commands = codes.add_subparsers(dest="codes_command", required=True, metavar="<command>")
    list_parser = commands.add_parser("list", help="List active redeem-code rows.")
    list_parser.set_defaults(handler=codes_list_command, command_name="codes.list")


def _register_daily(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
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


def _register_guides(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
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

    abyss = commands.add_parser("abyss", help="Show abyss guide availability.")
    abyss.add_argument("--version")
    abyss.add_argument("--floor", type=int, choices=(11, 12))
    abyss.set_defaults(handler=guide_abyss_command, command_name="guide.abyss")

    theater = commands.add_parser("theater", help="Show theater guide availability.")
    theater.add_argument("--version")
    theater.set_defaults(handler=guide_theater_command, command_name="guide.theater")


def _register_recommend(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
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


def _register_announcements(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
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
    show.add_argument("--id", required=True)
    show.set_defaults(handler=announcements_show_command, command_name="announcements.show")


def _register_map(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    map_group = groups.add_parser("map", help="Fetch public map artifacts.")
    commands = map_group.add_subparsers(dest="map_command", required=True, metavar="<command>")
    find = commands.add_parser("find", help="Fetch a material map artifact.")
    find.add_argument("--item", required=True)
    find.add_argument("--map", choices=("teyvat", "chasm", "enkanomiya"), default="teyvat")
    find.set_defaults(handler=map_find_command, command_name="map.find")


def _register_rerun(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    rerun = groups.add_parser("rerun", help="Show public rerun data.")
    commands = rerun.add_subparsers(dest="rerun_command", required=True, metavar="<command>")
    list_parser = commands.add_parser("list", help="List banner rows for rerun analysis.")
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.set_defaults(handler=rerun_list_command, command_name="rerun.list")


def _register_misc(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    misc = groups.add_parser("misc", help="Show miscellaneous public data.")
    commands = misc.add_subparsers(dest="misc_command", required=True, metavar="<command>")
    primogems = commands.add_parser("primogems-plan", help="Show primogem estimate availability.")
    primogems.add_argument("--version")
    primogems.set_defaults(handler=primogems_plan_command, command_name="misc.primogems-plan")


def _add_event_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--all", action="store_true", help="Include expired events.")
    parser.add_argument("--limit", type=int, default=20)


def _limit(value: int) -> int:
    if value <= 0:
        raise CliError(
            "INVALID_ARGUMENT",
            "limit must be greater than 0",
            EXIT_INVALID_INPUT,
            {"limit": value},
        )
    return value


def _positive(value: int, name: str) -> int:
    if value <= 0:
        raise CliError(
            "INVALID_ARGUMENT",
            f"{name} must be greater than 0",
            EXIT_INVALID_INPUT,
            {name: value},
        )
    return value


def _map_artifact_command(
    args: argparse.Namespace,
    *,
    command: str,
    item: str,
    map_name: str,
    artifact_name: str,
) -> CommandResult:
    response = _uncached_provider(args).map_image(
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


def _image_ext(media_type: str) -> str:
    if media_type == "image/jpeg":
        return "jpg"
    if media_type == "image/png":
        return "png"
    return "bin"


def _safe_filename(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    safe = safe.strip("_")[:60] or "item"
    return f"{safe}_{digest}"


def _wiki_query(args: argparse.Namespace) -> str:
    query = args.name or args.query
    if not query:
        raise CliError(
            "INVALID_ARGUMENT",
            "name is required",
            EXIT_INVALID_INPUT,
            {"command": args.command_name},
        )
    return query


def _provider(args: argparse.Namespace) -> PublicDataProvider:
    ensure_supported_region(args.region)
    return PublicDataProvider(
        HttpClient(
            timeout=args.timeout,
            cache_policy=args.cache,
            output_dir=args.output_dir,
            debug=args.debug,
        )
    )


def _uncached_provider(args: argparse.Namespace) -> PublicDataProvider:
    ensure_supported_region(args.region)
    return PublicDataProvider(
        HttpClient(
            timeout=args.timeout,
            cache_policy="off",
            output_dir=args.output_dir,
            debug=args.debug,
        )
    )


def _auth_provider(args: argparse.Namespace, region: str):
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
