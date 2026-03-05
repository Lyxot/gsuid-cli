from __future__ import annotations

import argparse

from gsuid_cli.commands.auth import _credential, _uid_and_region
from gsuid_cli.commands.rendering import maybe_render_image
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.providers import provider_for_region
from gsuid_cli.renderers.cards import render_abyss_summary

CAPABILITIES = [
    {
        "command": "challenge.abyss",
        "description": "Show authenticated Spiral Abyss data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "off",
    },
    {
        "command": "challenge.theater",
        "description": "Show authenticated Imaginarium Theater data.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "challenge.hard",
        "description": "Show authenticated hard challenge data from player index.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
]


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    challenge = groups.add_parser("challenge", help="Show authenticated challenge data.")
    commands = challenge.add_subparsers(
        dest="challenge_command", required=True, metavar="<command>"
    )

    abyss = commands.add_parser("abyss", help="Show Spiral Abyss data.")
    _add_uid(abyss)
    _add_season(abyss)
    abyss.add_argument("--floor", type=int)
    abyss.set_defaults(handler=abyss_command, command_name="challenge.abyss")

    theater = commands.add_parser("theater", help="Show Imaginarium Theater data.")
    _add_uid(theater)
    _add_season(theater)
    theater.set_defaults(handler=theater_command, command_name="challenge.theater")

    hard = commands.add_parser("hard", help="Show hard challenge data.")
    _add_uid(hard)
    _add_season(hard)
    hard.set_defaults(handler=hard_command, command_name="challenge.hard")


def abyss_command(args: argparse.Namespace) -> CommandResult:
    _validate_floor(args.floor)
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    result = _provider(args, region).challenge_abyss(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
        season=args.season,
        floor=args.floor,
    )
    return maybe_render_image(
        args,
        result,
        renderer=render_abyss_summary,
        name="abyss_summary",
        filename=f"abyss_{uid}_{args.season}.png",
        description="Rendered Spiral Abyss summary card",
    )


def theater_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    return _provider(args, region).challenge_theater(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
        season=args.season,
    )


def hard_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    return _provider(args, region).challenge_hard(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
        season=args.season,
    )


def _add_uid(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--uid", dest="command_uid")


def _add_season(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--season", choices=("current", "previous"), default="current")


def _validate_floor(floor: int | None) -> None:
    if floor is None:
        return
    if floor not in {9, 10, 11, 12}:
        raise CliError(
            "INVALID_ARGUMENT",
            "floor must be one of 9, 10, 11, or 12",
            EXIT_INVALID_INPUT,
            {"floor": floor},
        )


def _provider(args: argparse.Namespace, region: str):
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
