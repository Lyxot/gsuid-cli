from __future__ import annotations

import argparse

from gsuid_cli.commands.auth import _credential, _uid_and_region
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.providers import provider_for_region
from gsuid_cli.providers.public import DAY_NAMES, PublicDataProvider

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
        "render": ["data"],
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
]


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    _register_wiki(groups)
    _register_events(groups)
    _register_codes(groups)
    _register_daily(groups)


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


def daily_note_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    return _auth_provider(args, region).daily_note(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
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


def _register_wiki(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    wiki = groups.add_parser("wiki", help="Look up public wiki data.")
    commands = wiki.add_subparsers(dest="wiki_command", required=True, metavar="<command>")
    for kind in ("character", "weapon", "artifact", "enemy"):
        command = commands.add_parser(kind, help=f"Look up a {kind}.")
        command.add_argument("query", nargs="?")
        command.add_argument("--name")
        if kind in {"character", "weapon"}:
            command.add_argument("--level", type=int)
        command.set_defaults(handler=wiki_command, command_name=f"wiki.{kind}", wiki_kind=kind)


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

    materials = commands.add_parser("materials", help="List daily material domains.")
    selectors = materials.add_mutually_exclusive_group()
    selectors.add_argument("--date")
    selectors.add_argument("--day", choices=sorted(DAY_NAMES))
    materials.set_defaults(handler=daily_materials_command, command_name="daily.materials")


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
