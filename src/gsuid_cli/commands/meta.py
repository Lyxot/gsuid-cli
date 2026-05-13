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
)
from gsuid_cli.commands._text import command_subject_text_result, helps_from
from gsuid_cli.core.config import resolve_paths
from gsuid_cli.core.envelope import SCHEMA
from gsuid_cli.core.errors import ERROR_CATALOG, EXIT_NO_RESULT, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.schemas import command_envelope_schema, error_envelope_schema
from gsuid_cli.core.secrets import SecretStore
from gsuid_cli.providers.public import PublicDataProvider
from gsuid_cli.renderers.utility_text import render_meta_command_text

CAPABILITIES = [
    {
        "command": "meta.version",
        "description": "显示版本元信息。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "meta.paths",
        "description": "显示解析后的本地路径。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "meta.capabilities",
        "description": "显示已实现的功能信息。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "meta.schema",
        "description": "显示 JSON 数据包的 schema 元信息。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "meta.errors",
        "description": "显示稳定的错误元信息。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "meta.doctor",
        "description": "运行本地诊断。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
]

_HELPS = helps_from(CAPABILITIES)


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    meta = groups.add_parser("meta", help="CLI 元信息和诊断。")
    commands = meta.add_subparsers(dest="meta_command", required=True, metavar="<command>")

    version = commands.add_parser("version", help=_HELPS["meta.version"])
    version.set_defaults(handler=version_command, command_name="meta.version")

    paths = commands.add_parser("paths", help=_HELPS["meta.paths"])
    paths.set_defaults(handler=paths_command, command_name="meta.paths")

    capabilities = commands.add_parser("capabilities", help=_HELPS["meta.capabilities"])
    capabilities.set_defaults(handler=capabilities_command, command_name="meta.capabilities")

    schema = commands.add_parser("schema", help=_HELPS["meta.schema"])
    schema.add_argument("--command")
    schema.set_defaults(handler=schema_command, command_name="meta.schema")

    errors = commands.add_parser("errors", help=_HELPS["meta.errors"])
    errors.set_defaults(handler=errors_command, command_name="meta.errors")

    doctor = commands.add_parser("doctor", help=_HELPS["meta.doctor"])
    doctor.add_argument(
        "--check",
        choices=("network", "storage", "credentials", "resources", "all"),
        default="all",
    )
    doctor.set_defaults(handler=doctor_command, command_name="meta.doctor")


def version_command(_args: argparse.Namespace) -> CommandResult | dict[str, object]:
    data = {
        "package": "gsuid-cli",
        "version": __version__,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "git_revision": _git_revision(),
    }
    return _meta_text_result(_args, data)


def paths_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    return _meta_text_result(args, resolve_paths(args.output_dir).to_json())


def capabilities_command(_args: argparse.Namespace) -> CommandResult | dict[str, object]:
    commands = [dict(command, implemented=True) for command in _capabilities()]
    data = {
        "schema": SCHEMA,
        "regions": ["auto", "cn", "os"],
        "formats": ["json", "pretty-json", "plain"],
        "default_format": "json",
        "global_options": _global_options(),
        "commands": commands,
    }
    return _meta_text_result(_args, data)


def schema_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    commands = [str(command["command"]) for command in _capabilities()]
    if args.command:
        if args.command not in commands:
            raise CliError(
                "NO_RESULT",
                "该命令没有可用的 schema。",
                EXIT_NO_RESULT,
                {"command": args.command},
            )
        data = {
            "schema": SCHEMA,
            "command": args.command,
            "success": command_envelope_schema(args.command),
            "error": error_envelope_schema(),
        }
        return _meta_text_result(args, data)
    data = {
        "schema": SCHEMA,
        "commands": {command: command_envelope_schema(command) for command in commands},
        "error": error_envelope_schema(),
        "count": len(commands),
    }
    return _meta_text_result(args, data)


def errors_command(_args: argparse.Namespace) -> CommandResult | dict[str, object]:
    return _meta_text_result(_args, {"errors": ERROR_CATALOG, "count": len(ERROR_CATALOG)})


def doctor_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    selected = (
        ("storage", "credentials", "resources", "network") if args.check == "all" else (args.check,)
    )
    checks = []
    for name in selected:
        checks.extend(_doctor_checks(name, args))
    status = "ok" if all(check["status"] == "ok" for check in checks) else "warn"
    return _meta_text_result(
        args,
        {"status": status, "check": args.check, "checks": checks, "count": len(checks)},
    )


def _meta_text_result(
    args: argparse.Namespace,
    data: dict[str, object],
) -> CommandResult | dict[str, object]:
    command = str(getattr(args, "command_name", "meta.capabilities"))
    action = command.rsplit(".", 1)[-1]
    subject = data.get("command") or data.get("check") or action
    return command_subject_text_result(
        args,
        data,
        subject=subject,
        render_fn=render_meta_command_text,
        description="适合命令行阅读的元信息文本",
    )


def _capabilities() -> list[dict[str, object]]:
    return (
        CAPABILITIES
        + profile.CAPABILITIES
        + account.CAPABILITIES
        + auth.CAPABILITIES
        + batch.CAPABILITIES
        + cache.CAPABILITIES
        + public_data.CAPABILITIES
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
            "description": "本地配置文件名称。",
        },
        {
            "name": "--uid",
            "value": "UID",
            "default": None,
            "placement": "anywhere",
            "description": "目标原神 UID。覆盖配置文件默认值。",
        },
        {
            "name": "--region",
            "value": "auto|cn|os",
            "default": "auto",
            "placement": "anywhere",
            "description": "目标 API 区服。",
        },
        {
            "name": "--format",
            "value": "json|pretty-json|plain",
            "default": "json",
            "placement": "anywhere",
            "description": "标准输出格式。",
        },
        {
            "name": "--render",
            "value": "data|image|text|all",
            "default": "data,text",
            "placement": "anywhere",
            "description": "逗号分隔的渲染模式。可重复使用。",
        },
        {
            "name": "--output-dir",
            "value": "PATH",
            "default": "$GSUID_HOME/artifacts",
            "placement": "anywhere",
            "description": "产物输出目录。",
        },
        {
            "name": "--cache",
            "value": "use|refresh|only|off",
            "default": "use",
            "placement": "anywhere",
            "description": "处理 JSON 和静态资源的缓存策略。",
        },
        {
            "name": "--timeout",
            "value": "SECONDS",
            "default": 20,
            "placement": "anywhere",
            "description": "HTTP 超时时间。",
        },
        {
            "name": "--request-id",
            "value": "ID",
            "default": "generated UUID",
            "placement": "anywhere",
            "description": "调用者提供的请求 ID。",
        },
        {
            "name": "--quiet",
            "value": None,
            "default": False,
            "placement": "anywhere",
            "description": "抑制非结果的 stderr 日志。",
        },
        {
            "name": "--debug",
            "value": None,
            "default": False,
            "placement": "anywhere",
            "description": "在错误详情中包含调试诊断信息。",
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
            "name": "resources.asset_cache",
            "status": "ok" if paths.cache_assets.exists() else "warn",
            "message": "asset cache directory exists"
            if paths.cache_assets.exists()
            else "asset cache directory has not been created yet",
            "details": {
                "path": str(paths.cache_assets),
                "file_count": _file_count(paths.cache_assets),
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
        response = PublicDataProvider(
            HttpClient(
                timeout=args.timeout,
                cache_policy="off",
                output_dir=args.output_dir,
                debug=args.debug,
            )
        ).health_check(
            region=args.region,
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
