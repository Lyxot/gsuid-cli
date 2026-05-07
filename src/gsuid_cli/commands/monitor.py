from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from gsuid_cli.commands._text import command_text_result
from gsuid_cli.core.config import resolve_paths
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, CliError
from gsuid_cli.core.models import CommandResult
from gsuid_cli.renderers.utility_text import render_monitor_once_text

CAPABILITIES = [
    {
        "command": "monitor.once",
        "description": "Run one local health check pass with caller thresholds.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
]


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    monitor = groups.add_parser("monitor", help="Run local health checks.")
    commands = monitor.add_subparsers(dest="monitor_command", required=True, metavar="<command>")

    once = commands.add_parser("once", help="Run one local health check pass.")
    once.add_argument("--min-free-mb", type=int, default=100)
    once.add_argument("--max-asset-cache-files", type=int)
    once.add_argument("--max-artifact-files", type=int)
    once.set_defaults(handler=once_command, command_name="monitor.once")


def once_command(args: argparse.Namespace) -> CommandResult:
    _validate_threshold("min-free-mb", args.min_free_mb, allow_zero=True)
    _validate_threshold("max-asset-cache-files", args.max_asset_cache_files, allow_zero=True)
    _validate_threshold("max-artifact-files", args.max_artifact_files, allow_zero=True)

    paths = resolve_paths(args.output_dir)
    free_mb = _free_mb(paths.home)
    checks = [
        _check_minimum(
            "storage.free_mb",
            free_mb,
            args.min_free_mb,
            f"{free_mb} MiB free",
        )
    ]
    if args.max_asset_cache_files is not None:
        count = _asset_file_count(paths.cache_assets)
        checks.append(
            _check_maximum(
                "cache.asset_files",
                count,
                args.max_asset_cache_files,
                f"{count} cached asset files",
            )
        )
    if args.max_artifact_files is not None:
        count = _file_count(paths.artifacts)
        checks.append(
            _check_maximum(
                "artifacts.files",
                count,
                args.max_artifact_files,
                f"{count} artifact files",
            )
        )

    status = "ok" if all(check["status"] == "ok" for check in checks) else "warn"
    result = CommandResult(
        data={
            "status": status,
            "checks": checks,
            "thresholds": {
                "min_free_mb": args.min_free_mb,
                "max_asset_cache_files": args.max_asset_cache_files,
                "max_artifact_files": args.max_artifact_files,
            },
        },
        warnings=[check["message"] for check in checks if check["status"] != "ok"],
    )
    return command_text_result(
        args,
        result,
        name="monitor/once-text",
        filename="monitor-once.txt",
        content=render_monitor_once_text(result.data),
        description="适合命令行阅读的健康检查文本",
    )


def _validate_threshold(name: str, value: int | None, *, allow_zero: bool) -> None:
    if value is None:
        return
    minimum = 0 if allow_zero else 1
    if value < minimum:
        raise CliError(
            "INVALID_ARGUMENT",
            f"{name} must be at least {minimum}",
            EXIT_INVALID_INPUT,
            {name.replace("-", "_"): value},
        )


def _check_minimum(name: str, value: int, threshold: int, message: str) -> dict[str, object]:
    return {
        "name": name,
        "status": "ok" if value >= threshold else "warn",
        "value": value,
        "threshold": threshold,
        "message": message,
    }


def _check_maximum(name: str, value: int, threshold: int, message: str) -> dict[str, object]:
    return {
        "name": name,
        "status": "ok" if value <= threshold else "warn",
        "value": value,
        "threshold": threshold,
        "message": message,
    }


def _free_mb(path: Path) -> int:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    usage = shutil.disk_usage(probe)
    return usage.free // (1024 * 1024)


def _file_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len([item for item in path.rglob("*") if item.is_file()])


def _asset_file_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len(
        [
            item
            for item in path.iterdir()
            if item.is_file()
            and not item.name.startswith(".")
            and not item.name.endswith(".metadata.json")
        ]
    )
