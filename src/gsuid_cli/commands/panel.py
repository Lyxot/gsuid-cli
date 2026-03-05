from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from gsuid_cli.commands.account import _validate_uid
from gsuid_cli.commands.auth import _uid_and_region
from gsuid_cli.commands.panel_cache import (
    avatar_summaries,
    cache_source,
    find_avatar,
    load_panel_cache,
    normalized_avatar,
    player_summary,
    save_panel_cache,
)
from gsuid_cli.commands.rendering import maybe_render_image
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.config import resolve_paths
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.state import state_db
from gsuid_cli.providers.enka import EnkaProvider
from gsuid_cli.providers.public import AMBR_BASE_URL
from gsuid_cli.renderers.cards import render_panel

CAPABILITIES = [
    {
        "command": "panel.refresh",
        "description": "Refresh Enka showcase panel data into the local cache.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "use",
    },
    {
        "command": "panel.list",
        "description": "List cached character panels for a UID.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "panel.show",
        "description": "Show one cached character panel.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "off",
    },
    {
        "command": "panel.compare",
        "description": "Compare cached panel stats for two or more builds.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "panel.save",
        "description": "Save one cached panel as a JSON artifact.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "panel.showcase",
        "description": "Show the cached public showcase summary.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
]


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    panel = groups.add_parser("panel", help="Manage Enka panel cache.")
    commands = panel.add_subparsers(dest="panel_command", required=True, metavar="<command>")

    refresh = commands.add_parser("refresh", help="Refresh panel data.")
    refresh.add_argument("--uid", dest="command_uid")
    refresh.add_argument("--source", choices=("auto", "enka", "mys"), default="auto")
    refresh.add_argument("--force", action="store_true")
    refresh.set_defaults(handler=refresh_command, command_name="panel.refresh")

    list_parser = commands.add_parser("list", help="List cached panels.")
    list_parser.add_argument("--uid", dest="command_uid")
    list_parser.set_defaults(handler=list_command, command_name="panel.list")

    show = commands.add_parser("show", help="Show a cached panel.")
    show.add_argument("--uid", dest="command_uid")
    show.add_argument("--character", required=True)
    show.add_argument("--constellation", type=int)
    show.add_argument("--weapon")
    show.add_argument("--artifact-source-character")
    show.set_defaults(handler=show_command, command_name="panel.show")

    compare = commands.add_parser("compare", help="Compare cached panels.")
    compare.add_argument("--uid", dest="command_uid")
    compare.add_argument("--build", action="append", required=True)
    compare.set_defaults(handler=compare_command, command_name="panel.compare")

    save = commands.add_parser("save", help="Save a cached panel JSON artifact.")
    save.add_argument("--uid", dest="command_uid")
    save.add_argument("--character", required=True)
    save.add_argument("--name", required=True)
    save.add_argument("--output")
    save.set_defaults(handler=save_command, command_name="panel.save")

    showcase = commands.add_parser("showcase", help="Show cached showcase summary.")
    showcase.add_argument("--uid", dest="command_uid")
    showcase.set_defaults(handler=showcase_command, command_name="panel.showcase")


def refresh_command(args: argparse.Namespace) -> CommandResult:
    uid, region = _uid_and_region(args)
    source = _refresh_source(args.source)
    result = _provider(args).profile(uid=uid, region=region)
    payload, warnings = _with_avatar_names(args, result.data)
    with state_db(args.output_dir) as conn:
        cache = save_panel_cache(conn, uid=uid, payload=payload, source=result.source)
    return CommandResult(
        data={
            "uid": uid,
            "source": source,
            "player": player_summary(cache),
            "character_count": len(cache["avatars"]),
            "ttl": cache["ttl"],
            "cached_at": cache["fetched_at"],
            "cache": _cache_metadata(args, uid),
            "failures": [],
        },
        warnings=warnings,
        source=result.source,
    )


def list_command(args: argparse.Namespace) -> CommandResult:
    uid, _region = _uid_and_region(args)
    cache = _load(uid, args.output_dir)
    return CommandResult(
        data={
            "uid": uid,
            "player": player_summary(cache),
            "characters": avatar_summaries(cache),
            "count": len(cache["avatars"]),
            "cached_at": cache["fetched_at"],
        },
        source=cache_source(cache),
    )


def showcase_command(args: argparse.Namespace) -> CommandResult:
    uid, _region = _uid_and_region(args)
    cache = _load(uid, args.output_dir)
    return CommandResult(
        data={
            "uid": uid,
            "player": player_summary(cache),
            "showcase": avatar_summaries(cache),
            "count": len(cache["avatars"]),
            "cached_at": cache["fetched_at"],
        },
        source=cache_source(cache),
    )


def show_command(args: argparse.Namespace) -> CommandResult:
    _validate_panel_overrides(args)
    uid, _region = _uid_and_region(args)
    cache = _load(uid, args.output_dir)
    avatar = find_avatar(cache, args.character)
    warnings = _override_warnings(args)
    data = {
        "uid": uid,
        "character": args.character,
        "panel": normalized_avatar(avatar),
        "cached_at": cache["fetched_at"],
    }
    overrides = _requested_overrides(args)
    if overrides:
        data["requested_overrides"] = overrides
    result = CommandResult(data=data, warnings=warnings, source=cache_source(cache))
    return maybe_render_image(
        args,
        result,
        renderer=render_panel,
        name="panel",
        filename=f"panel_{uid}_{_safe_filename(args.character)}.png",
        description="Rendered character panel card",
    )


def compare_command(args: argparse.Namespace) -> CommandResult:
    default_uid, _region = _uid_and_region(args)
    build_specs = args.build or []
    if len(build_specs) < 2:
        raise CliError(
            "INVALID_ARGUMENT",
            "panel compare requires at least two --build values",
            EXIT_INVALID_INPUT,
            {"build_count": len(build_specs)},
        )
    builds = [_load_build(spec, default_uid, args.output_dir) for spec in build_specs]
    baseline = builds[0]
    return CommandResult(
        data={
            "baseline": baseline,
            "builds": builds,
            "deltas": [_build_delta(baseline, build) for build in builds[1:]],
        },
        source=baseline["source"],
    )


def save_command(args: argparse.Namespace) -> CommandResult:
    uid, _region = _uid_and_region(args)
    cache = _load(uid, args.output_dir)
    avatar = find_avatar(cache, args.character)
    data = {
        "uid": uid,
        "name": args.name,
        "character": args.character,
        "panel": normalized_avatar(avatar),
        "cached_at": cache["fetched_at"],
    }
    content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    artifact = _write_panel(args, uid, args.name, content)
    return CommandResult(
        data={
            "uid": uid,
            "saved": True,
            "name": args.name,
            "character": data["panel"]["name"],
            "path": artifact["path"],
        },
        artifacts=[artifact],
        source=cache_source(cache),
    )


def _provider(args: argparse.Namespace) -> EnkaProvider:
    return EnkaProvider(
        HttpClient(
            timeout=args.timeout,
            cache_policy=_refresh_cache_policy(args),
            output_dir=args.output_dir,
            debug=args.debug,
        )
    )


def _refresh_cache_policy(args: argparse.Namespace) -> str:
    if args.cache in {"only", "off"}:
        return str(args.cache)
    if args.force or args.cache == "use":
        return "refresh"
    return str(args.cache)


def _cache_metadata(args: argparse.Namespace, uid: str) -> dict[str, object]:
    return {
        "backend": "sqlite",
        "path": str(resolve_paths(args.output_dir).state),
        "table": "panel_cache",
        "key": uid,
        "status": "updated",
    }


def _with_avatar_names(
    args: argparse.Namespace,
    payload: dict[str, object],
) -> tuple[dict[str, object], list[str]]:
    avatars = payload.get("avatarInfoList")
    if not isinstance(avatars, list):
        return payload, []
    avatar_dicts = [avatar for avatar in avatars if isinstance(avatar, dict)]
    if all(avatar.get("name") or avatar.get("route") for avatar in avatar_dicts):
        return payload, []

    try:
        names = _avatar_name_index(args)
    except CliError:
        return payload, ["character name enrichment failed; use avatar ids for panel lookup"]

    enriched = []
    changed = False
    for avatar in avatar_dicts:
        item = dict(avatar)
        info = names.get(str(item.get("avatarId") or item.get("id") or ""))
        if info:
            if not item.get("name") and info.get("name"):
                item["name"] = info["name"]
                changed = True
            if not item.get("route") and info.get("route"):
                item["route"] = info["route"]
                changed = True
        enriched.append(item)
    if not changed:
        return payload, []
    new_payload = dict(payload)
    new_payload["avatarInfoList"] = enriched
    return new_payload, []


def _avatar_name_index(args: argparse.Namespace) -> dict[str, dict[str, object]]:
    response = HttpClient(
        timeout=args.timeout,
        cache_policy=args.cache,
        output_dir=args.output_dir,
        debug=args.debug,
    ).request_json(
        "GET",
        f"{AMBR_BASE_URL}/api/v2/chs/avatar",
        provider="ambr",
        region="cn",
        category="panel.character_names",
    )
    data = response.payload.get("data")
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, dict):
        return {}
    index: dict[str, dict[str, object]] = {}
    for item in items.values():
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        if item_id:
            index[item_id] = item
    return index


def _refresh_source(source: str) -> str:
    if source == "mys":
        raise CliError(
            "INVALID_ARGUMENT",
            "MYS panel refresh is not implemented; use --source enka or --source auto.",
            EXIT_INVALID_INPUT,
            {"source": source},
        )
    return "enka"


def _load(uid: str, output_dir: str | None) -> dict[str, object]:
    with state_db(output_dir) as conn:
        return load_panel_cache(conn, uid)


def _load_build(spec: str, default_uid: str, output_dir: str | None) -> dict[str, object]:
    uid, character = _parse_build_spec(spec, default_uid)
    cache = _load(uid, output_dir)
    avatar = normalized_avatar(find_avatar(cache, character))
    return {
        "uid": uid,
        "character": character,
        "panel": avatar,
        "source": cache_source(cache),
    }


def _parse_build_spec(spec: str, default_uid: str) -> tuple[str, str]:
    if ":" in spec:
        uid, character = spec.split(":", 1)
        uid = _validate_uid(uid)
    else:
        uid, character = default_uid, spec
    if not character:
        raise CliError(
            "INVALID_ARGUMENT",
            "build spec must include a character name or avatar id",
            EXIT_INVALID_INPUT,
            {"build": spec},
        )
    return uid, character


def _build_delta(baseline: dict[str, object], build: dict[str, object]) -> dict[str, object]:
    base_panel = baseline["panel"]
    compare_panel = build["panel"]
    if not isinstance(base_panel, dict) or not isinstance(compare_panel, dict):
        return {"uid": build["uid"], "character": build["character"], "fight_props": {}}
    base_props = base_panel.get("fight_props")
    compare_props = compare_panel.get("fight_props")
    if not isinstance(base_props, dict) or not isinstance(compare_props, dict):
        prop_delta = {}
    else:
        prop_delta = {
            key: _number(compare_props[key]) - _number(base_props[key])
            for key in sorted(compare_props.keys() & base_props.keys())
            if _is_number(compare_props[key]) and _is_number(base_props[key])
        }
    return {
        "uid": build["uid"],
        "character": build["character"],
        "artifact_score": round(
            _number(compare_panel.get("artifact_score"))
            - _number(base_panel.get("artifact_score")),
            2,
        ),
        "fight_props": prop_delta,
    }


def _validate_panel_overrides(args: argparse.Namespace) -> None:
    if args.constellation is not None and not 0 <= args.constellation <= 6:
        raise CliError(
            "INVALID_ARGUMENT",
            "constellation must be between 0 and 6",
            EXIT_INVALID_INPUT,
            {"constellation": args.constellation},
        )


def _requested_overrides(args: argparse.Namespace) -> dict[str, object]:
    overrides: dict[str, object] = {}
    if args.constellation is not None:
        overrides["constellation"] = args.constellation
    if args.weapon:
        overrides["weapon"] = args.weapon
    if args.artifact_source_character:
        overrides["artifact_source_character"] = args.artifact_source_character
    return overrides


def _override_warnings(args: argparse.Namespace) -> list[str]:
    if _requested_overrides(args):
        return ["typed panel overrides are recorded but not applied yet"]
    return []


def _write_panel(
    args: argparse.Namespace,
    uid: str,
    name: str,
    content: bytes,
) -> dict[str, object]:
    filename = f"panel_{uid}_{_safe_filename(name)}.json"
    if args.output:
        path = Path(args.output).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return _artifact_for_path(path, content)
    return ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="panel",
        filename=filename,
        media_type="application/json",
        content=content,
        description="Saved character panel",
        kind="json",
    )


def _artifact_for_path(path: Path, content: bytes) -> dict[str, object]:
    return {
        "kind": "json",
        "name": "panel",
        "path": str(path),
        "media_type": "application/json",
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "description": "Saved character panel",
    }


def _safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)[:80]


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _number(value: object) -> float:
    return float(value) if _is_number(value) else 0.0
