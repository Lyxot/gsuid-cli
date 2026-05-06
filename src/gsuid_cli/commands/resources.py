from __future__ import annotations

import argparse

from gsuid_cli.commands._text import command_text_result, safe_filename_part
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.providers.public import PublicDataProvider
from gsuid_cli.renderers.utility_text import render_resources_sync_text

CAPABILITIES = [
    {
        "command": "resources.sync",
        "description": "Fetch public resource metadata and warm process-local JSON cache.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
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
    result = PublicDataProvider(
        HttpClient(
            timeout=args.timeout,
            cache_policy="refresh",
            output_dir=args.output_dir,
            debug=args.debug,
        )
    ).sync_resources(scope=args.scope)
    return command_text_result(
        args,
        result,
        name="resources/sync-text",
        filename=f"resources-sync_{safe_filename_part(args.scope)}.txt",
        content=render_resources_sync_text(result.data),
        description="适合命令行阅读的资源同步文本",
    )
