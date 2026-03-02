from __future__ import annotations

import argparse
import platform
import subprocess
from pathlib import Path

from gsuid_cli import __version__
from gsuid_cli.commands import account, auth, challenge, player, profile, progress, public_data
from gsuid_cli.core.config import resolve_paths
from gsuid_cli.core.envelope import SCHEMA

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
    command_capabilities = (
        CAPABILITIES
        + profile.CAPABILITIES
        + account.CAPABILITIES
        + auth.CAPABILITIES
        + public_data.CAPABILITIES
        + player.CAPABILITIES
        + challenge.CAPABILITIES
        + progress.CAPABILITIES
    )
    commands = [dict(command, implemented=True) for command in command_capabilities]
    return {
        "schema": SCHEMA,
        "regions": ["cn"],
        "formats": ["json", "text"],
        "default_format": "json",
        "commands": commands,
    }


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
