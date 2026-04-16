from __future__ import annotations

import argparse

from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.providers.public import PublicDataProvider

CAPABILITIES = [
    {
        "command": "resources.sync",
        "description": "Fetch public resource metadata and warm process-local JSON cache.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "memory",
    },
]


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    resources = groups.add_parser("resources", help="Manage local public resources.")
    commands = resources.add_subparsers(
        dest="resources_command",
        required=True,
        metavar="<command>",
    )

    sync = commands.add_parser("sync", help="Fetch public resource metadata.")
    sync.add_argument("--scope", choices=("wiki", "icons", "maps", "all"), default="all")
    sync.set_defaults(handler=sync_command, command_name="resources.sync")


def sync_command(args: argparse.Namespace) -> CommandResult:
    ensure_supported_region(args.region)
    return PublicDataProvider(
        HttpClient(
            timeout=args.timeout,
            cache_policy="refresh",
            output_dir=args.output_dir,
            debug=args.debug,
        )
    ).sync_resources(scope=args.scope)
