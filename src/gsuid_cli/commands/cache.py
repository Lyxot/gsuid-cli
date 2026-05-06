from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from gsuid_cli.commands._text import command_text_result, safe_filename_part
from gsuid_cli.core.cache import AssetCache
from gsuid_cli.core.config import resolve_paths
from gsuid_cli.core.models import CommandResult
from gsuid_cli.renderers.utility_text import render_cache_clear_text

CAPABILITIES = [
    {
        "command": "cache.clear",
        "description": "Clear local cache and artifact files by scope.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
        "cache": "off",
    },
]


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    cache = groups.add_parser("cache", help="Manage local cache files.")
    commands = cache.add_subparsers(dest="cache_command", required=True, metavar="<command>")

    clear = commands.add_parser("clear", help="Clear local cache files.")
    clear.add_argument(
        "--scope",
        choices=("assets", "artifacts", "all"),
        default="all",
    )
    clear.set_defaults(handler=clear_command, command_name="cache.clear")


def clear_command(args: argparse.Namespace) -> CommandResult:
    paths = resolve_paths(None)
    targets = {
        "assets": paths.cache_assets,
        "artifacts": paths.home / "artifacts",
    }
    selected = targets if args.scope == "all" else {args.scope: targets[args.scope]}
    cleared = [_clear_path(name, path) for name, path in selected.items()]
    result = CommandResult(
        data={
            "scope": args.scope,
            "cleared": cleared,
            "removed_files": sum(int(item["removed_files"]) for item in cleared),
            "removed_dirs": sum(int(item["removed_dirs"]) for item in cleared),
        }
    )
    return command_text_result(
        args,
        result,
        name="cache/clear-text",
        filename=f"cache-clear_{safe_filename_part(args.scope)}.txt",
        content=render_cache_clear_text(result.data),
        description="适合命令行阅读的缓存清理文本",
    )


def _clear_path(name: str, path: Path) -> dict[str, object]:
    if name == "assets":
        removed_files, removed_dirs = AssetCache().clear()
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        return {
            "scope": name,
            "path": str(path),
            "removed_files": removed_files,
            "removed_dirs": removed_dirs,
        }
    removed_files = _count_files(path)
    removed_dirs = _count_dirs(path)
    if path.exists():
        for item in path.iterdir():
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return {
        "scope": name,
        "path": str(path),
        "removed_files": removed_files,
        "removed_dirs": removed_dirs,
    }


def _count_files(path: Path) -> int:
    if not path.exists():
        return 0
    return len([item for item in path.rglob("*") if item.is_file()])


def _count_dirs(path: Path) -> int:
    if not path.exists():
        return 0
    return len([item for item in path.rglob("*") if item.is_dir()])
