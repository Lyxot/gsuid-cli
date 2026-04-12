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
    cache,
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
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.schemas import command_envelope_schema, error_envelope_schema
from gsuid_cli.core.secrets import SecretStore

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
    {
        "command": "meta.doctor",
        "description": "Run local diagnostics for storage, credentials, resources, or network.",
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

    doctor = commands.add_parser("doctor", help="Run local diagnostics.")
    doctor.add_argument(
        "--check",
        choices=("network", "storage", "credentials", "resources", "all"),
        default="all",
    )
    doctor.set_defaults(handler=doctor_command, command_name="meta.doctor")


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
        "formats": ["json", "pretty-json", "text"],
        "default_format": "json",
        "global_options": _global_options(),
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


def doctor_command(args: argparse.Namespace) -> dict[str, object]:
    selected = (
        ("storage", "credentials", "resources", "network") if args.check == "all" else (args.check,)
    )
    checks = []
    for name in selected:
        checks.extend(_doctor_checks(name, args))
    status = "ok" if all(check["status"] == "ok" for check in checks) else "warn"
    return {"status": status, "check": args.check, "checks": checks, "count": len(checks)}


def _capabilities() -> list[dict[str, object]]:
    return (
        CAPABILITIES
        + profile.CAPABILITIES
        + account.CAPABILITIES
        + auth.CAPABILITIES
        + batch.CAPABILITIES
        + cache.CAPABILITIES
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


def _global_options() -> list[dict[str, object]]:
    return [
        {
            "name": "--profile",
            "value": "NAME",
            "default": "default",
            "placement": "anywhere",
            "description": "Local profile name.",
        },
        {
            "name": "--uid",
            "value": "UID",
            "default": None,
            "placement": "anywhere",
            "description": "Target Genshin UID. Overrides profile default.",
        },
        {
            "name": "--region",
            "value": "cn|os",
            "default": "cn",
            "placement": "anywhere",
            "description": "Target API region.",
        },
        {
            "name": "--format",
            "value": "json|pretty-json|text",
            "default": "json",
            "placement": "anywhere",
            "description": "Output format.",
        },
        {
            "name": "--render",
            "value": "data|image|both",
            "default": "data",
            "placement": "anywhere",
            "description": "Data/artifact preference.",
        },
        {
            "name": "--output-dir",
            "value": "PATH",
            "default": "$GSUID_HOME/artifacts",
            "placement": "anywhere",
            "description": "Artifact output directory.",
        },
        {
            "name": "--cache",
            "value": "use|refresh|only|off",
            "default": "use",
            "placement": "anywhere",
            "description": "Cache policy.",
        },
        {
            "name": "--timeout",
            "value": "SECONDS",
            "default": 20,
            "placement": "anywhere",
            "description": "HTTP timeout.",
        },
        {
            "name": "--request-id",
            "value": "ID",
            "default": "generated UUID",
            "placement": "anywhere",
            "description": "Caller-supplied request id.",
        },
        {
            "name": "--quiet",
            "value": None,
            "default": False,
            "placement": "anywhere",
            "description": "Suppress non-result stderr logs.",
        },
        {
            "name": "--debug",
            "value": None,
            "default": False,
            "placement": "anywhere",
            "description": "Include debug diagnostics in error details.",
        },
    ]


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


def _doctor_checks(name: str, args: argparse.Namespace) -> list[dict[str, object]]:
    if name == "storage":
        return _storage_checks(args)
    if name == "credentials":
        return [_credential_check()]
    if name == "resources":
        return _resource_checks(args)
    return [_network_check(args)]


def _storage_checks(args: argparse.Namespace) -> list[dict[str, object]]:
    paths = resolve_paths(args.output_dir)
    return [
        _path_check("storage.home", paths.home),
        _path_check("storage.state_parent", paths.state.parent),
        _path_check("storage.artifacts", paths.artifacts),
    ]


def _resource_checks(args: argparse.Namespace) -> list[dict[str, object]]:
    paths = resolve_paths(args.output_dir)
    return [
        {
            "name": "resources.cache",
            "status": "ok" if paths.cache_resources.exists() else "warn",
            "message": "resource cache directory exists"
            if paths.cache_resources.exists()
            else "resource cache directory has not been created yet",
            "details": {
                "path": str(paths.cache_resources),
                "file_count": _file_count(paths.cache_resources),
            },
        }
    ]


def _credential_check() -> dict[str, object]:
    try:
        backend = SecretStore().backend_name()
    except CliError as exc:
        return {
            "name": "credentials.keyring",
            "status": "warn",
            "message": exc.message,
            "details": exc.details,
        }
    return {
        "name": "credentials.keyring",
        "status": "ok",
        "message": "keyring backend is available",
        "details": {"backend": backend},
    }


def _network_check(args: argparse.Namespace) -> dict[str, object]:
    try:
        response = HttpClient(
            timeout=args.timeout,
            cache_policy="off",
            output_dir=args.output_dir,
            debug=args.debug,
        ).request_json(
            "GET",
            "https://api.ambr.top/v2/chs/avatar",
            provider="ambr",
            region=args.region,
            category="meta.doctor.network",
        )
    except CliError as exc:
        return {
            "name": "network.ambr",
            "status": "warn",
            "message": exc.message,
            "details": exc.details,
        }
    return {
        "name": "network.ambr",
        "status": "ok",
        "message": "public data endpoint is reachable",
        "details": {"status_code": response.status_code, "source": response.source},
    }


def _path_check(name: str, path: Path) -> dict[str, object]:
    return {
        "name": name,
        "status": "ok" if path.exists() else "warn",
        "message": "path exists" if path.exists() else "path does not exist",
        "details": {"path": str(path), "exists": path.exists()},
    }


def _file_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len([item for item in path.rglob("*") if item.is_file()])
