from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from gsuid_cli.commands._text import command_text_result, safe_filename_part
from gsuid_cli.core.cache import AssetCache, HttpCache
from gsuid_cli.core.config import resolve_paths
from gsuid_cli.core.models import CommandResult
from gsuid_cli.renderers.utility_text import render_cache_clear_text, render_cache_size_text

CACHE_SCOPES = ("http", "assets", "icons", "maps", "wiki", "artifacts", "all")
ASSET_SCOPES = {"assets", "icons", "maps", "wiki"}

CAPABILITIES = [
    {
        "command": "cache.clear",
        "description": "Clear local cache and artifact files by scope.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "cache.size",
        "description": "Show local cache and artifact disk usage by scope.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
]


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    cache = groups.add_parser("cache", help="Manage local cache files.")
    commands = cache.add_subparsers(dest="cache_command", required=True, metavar="<command>")

    clear = commands.add_parser("clear", help="Clear local cache files.")
    clear.add_argument("--scope", choices=CACHE_SCOPES, default="all")
    clear.set_defaults(handler=clear_command, command_name="cache.clear")

    size = commands.add_parser("size", help="Show local cache and artifact disk usage.")
    size.add_argument("--scope", choices=CACHE_SCOPES, default="all")
    size.set_defaults(handler=size_command, command_name="cache.size")


def clear_command(args: argparse.Namespace) -> CommandResult:
    selected = _selected_targets(args.scope)
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


def size_command(args: argparse.Namespace) -> CommandResult:
    selected = _selected_targets(args.scope)
    entries = [_path_size(name, path) for name, path in selected.items()]
    total_bytes = sum(int(item["bytes"]) for item in entries)
    result = CommandResult(
        data={
            "scope": args.scope,
            "entries": entries,
            "bytes": total_bytes,
            "size": _format_bytes(total_bytes),
            "files": sum(int(item["files"]) for item in entries),
            "dirs": sum(int(item["dirs"]) for item in entries),
        }
    )
    return command_text_result(
        args,
        result,
        name="cache/size-text",
        filename=f"cache-size_{safe_filename_part(args.scope)}.txt",
        content=render_cache_size_text(result.data),
        description="适合命令行阅读的缓存大小文本",
    )


def _selected_targets(scope: str) -> dict[str, Path]:
    paths = resolve_paths(None)
    targets = {
        "http": paths.cache / "http",
        "assets": paths.cache / "assets",
        "icons": paths.cache / "icons",
        "maps": paths.cache / "maps",
        "wiki": paths.cache / "wiki",
        "artifacts": paths.home / "artifacts",
    }
    return targets if scope == "all" else {scope: targets[scope]}


def _clear_path(name: str, path: Path) -> dict[str, object]:
    if name in ASSET_SCOPES:
        removed_files, removed_dirs = AssetCache(usage=name).clear()
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        return {
            "scope": name,
            "path": str(path),
            "removed_files": removed_files,
            "removed_dirs": removed_dirs,
        }
    if name == "http":
        removed_files, removed_dirs = HttpCache().clear()
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


def _path_size(name: str, path: Path) -> dict[str, object]:
    total = _sum_bytes(path)
    return {
        "scope": name,
        "path": str(path),
        "bytes": total,
        "size": _format_bytes(total),
        "files": _count_files(path, include_symlinks=False),
        "dirs": _count_dirs(path),
    }


def _count_files(path: Path, *, include_symlinks: bool = True) -> int:
    if not path.exists():
        return 0
    return len([item for item in path.rglob("*") if _is_counted_file(item, include_symlinks)])


def _is_counted_file(path: Path, include_symlinks: bool) -> bool:
    if path.is_symlink():
        return include_symlinks
    return path.is_file()


def _count_dirs(path: Path) -> int:
    if not path.exists():
        return 0
    return len([item for item in path.rglob("*") if not item.is_symlink() and item.is_dir()])


def _sum_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(
        item.stat().st_size for item in path.rglob("*") if not item.is_symlink() and item.is_file()
    )


def _format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GiB"
