from __future__ import annotations

import argparse
import platform
import subprocess
from pathlib import Path

from gsuid_cli import __version__
from gsuid_cli.commands import (
    account,
    auth,
    batch,
    challenge,
    gacha,
    monitor,
    panel,
    player,
    profile,
    progress,
    public_data,
    rank,
    resources,
)
from gsuid_cli.core.config import resolve_paths
from gsuid_cli.core.envelope import SCHEMA
from gsuid_cli.core.errors import ERROR_CATALOG, EXIT_NO_RESULT, CliError
from gsuid_cli.core.schemas import command_envelope_schema, error_envelope_schema

CAPABILITIES = [
    {
        "command": "meta.version",
        "description": "Show package, Python, and git version metadata.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "meta.paths",
        "description": "Show resolved local storage paths.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "meta.capabilities",
        "description": "Show implemented command capabilities.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "meta.schema",
        "description": "Show JSON envelope schema metadata.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "meta.errors",
        "description": "Show stable machine-readable error metadata.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
]


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    meta = groups.add_parser("meta", help="CLI metadata and diagnostics.")
    commands = meta.add_subparsers(dest="meta_command", required=True, metavar="<command>")

    version = commands.add_parser("version", help="Show version metadata.")
    version.set_defaults(handler=version_command, command_name="meta.version")

    paths = commands.add_parser("paths", help="Show resolved local paths.")
    paths.set_defaults(handler=paths_command, command_name="meta.paths")

    capabilities = commands.add_parser("capabilities", help="Show implemented capabilities.")
    capabilities.set_defaults(handler=capabilities_command, command_name="meta.capabilities")

    schema = commands.add_parser("schema", help="Show JSON envelope schema metadata.")
    schema.add_argument("--command")
    schema.set_defaults(handler=schema_command, command_name="meta.schema")

    errors = commands.add_parser("errors", help="Show stable error metadata.")
    errors.set_defaults(handler=errors_command, command_name="meta.errors")


def version_command(_args: argparse.Namespace) -> dict[str, object]:
    return {
        "package": "gsuid-cli",
        "version": __version__,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "git_revision": _git_revision(),
    }


def paths_command(args: argparse.Namespace) -> dict[str, str]:
    return resolve_paths(args.output_dir).to_json()


def capabilities_command(_args: argparse.Namespace) -> dict[str, object]:
    commands = [dict(command, implemented=True) for command in _capabilities()]
    return {
        "schema": SCHEMA,
        "regions": ["cn"],
        "formats": ["json", "text"],
        "default_format": "json",
        "commands": commands,
    }


def schema_command(args: argparse.Namespace) -> dict[str, object]:
    commands = [str(command["command"]) for command in _capabilities()]
    if args.command:
        if args.command not in commands:
            raise CliError(
                "NO_RESULT",
                "No schema is available for this command.",
                EXIT_NO_RESULT,
                {"command": args.command},
            )
        return {
            "schema": SCHEMA,
            "command": args.command,
            "success": command_envelope_schema(args.command),
            "error": error_envelope_schema(),
        }
    return {
        "schema": SCHEMA,
        "commands": {command: command_envelope_schema(command) for command in commands},
        "error": error_envelope_schema(),
        "count": len(commands),
    }


def errors_command(_args: argparse.Namespace) -> dict[str, object]:
    return {"errors": ERROR_CATALOG, "count": len(ERROR_CATALOG)}


def _capabilities() -> list[dict[str, object]]:
    return (
        CAPABILITIES
        + profile.CAPABILITIES
        + account.CAPABILITIES
        + auth.CAPABILITIES
        + batch.CAPABILITIES
        + public_data.CAPABILITIES
        + resources.CAPABILITIES
        + monitor.CAPABILITIES
        + player.CAPABILITIES
        + challenge.CAPABILITIES
        + progress.CAPABILITIES
        + gacha.CAPABILITIES
        + panel.CAPABILITIES
        + rank.CAPABILITIES
    )


def _git_revision() -> str | None:
    repo = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
