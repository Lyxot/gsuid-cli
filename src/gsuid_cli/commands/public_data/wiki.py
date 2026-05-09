from __future__ import annotations

import argparse
from collections.abc import Mapping

from gsuid_cli.commands.public_data._common import (
    _optional_text,
    _positive,
    _provider,
    _safe_filename,
)
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, CliError
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.render import render_image_enabled, render_result_data, render_text_enabled
from gsuid_cli.providers.assets import fetch_render_images
from gsuid_cli.renderers.wiki.picwiki import (
    render_wiki_artifact_card,
    render_wiki_character_materials_card,
    render_wiki_constellation_card,
    render_wiki_food_card,
    render_wiki_weapon_card,
    wiki_asset_urls,
)
from gsuid_cli.renderers.wiki.text import (
    render_wiki_character_materials_text,
    render_wiki_constellation_text,
    render_wiki_lookup_text,
    render_wiki_talent_text,
    render_wiki_weapon_materials_text,
)

WIKI_IMAGE_WORKERS = 8
WIKI_LOOKUP_IMAGE_KINDS = {"artifact", "food", "weapon"}

CAPABILITIES = [
    {
        "command": "wiki.character",
        "description": "查询公开的角色数据。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "wiki.weapon",
        "description": "查询公开的武器数据。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "wiki.artifact",
        "description": "查询公开的圣遗物套装数据。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "wiki.enemy",
        "description": "查询公开的怪物数据。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "wiki.food",
        "description": "查询公开的食物数据。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "wiki.talent",
        "description": "查询公开的角色天赋数据。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "wiki.constellation",
        "description": "查询公开的角色命座数据。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "wiki.character-materials",
        "description": "显示角色突破材料数据。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "wiki.weapon-materials",
        "description": "显示武器突破材料数据。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
]

_HELPS = {
    str(c.get("command", "")): str(c.get("description", ""))
    for c in CAPABILITIES
    if isinstance(c, dict)
}


def wiki_command(args: argparse.Namespace) -> CommandResult:
    result = _provider(args).wiki_lookup(kind=args.wiki_kind, query=_wiki_query(args))
    if getattr(args, "level", None) is not None:
        _apply_level_request(result, _positive(args.level, "level"))
    if render_image_enabled(args) and args.wiki_kind not in WIKI_LOOKUP_IMAGE_KINDS:
        if not render_text_enabled(args):
            return result
    if render_image_enabled(args) or render_text_enabled(args):
        return _wiki_render_result(args, result, args.wiki_kind)
    return result


def _apply_level_request(result: CommandResult, level: int) -> None:
    item = result.data.get("item")
    if not isinstance(item, dict):
        result.data["requested_level"] = level
        result.warnings.append("由于缺少 wiki 物品数据，无法应用等级数据")
        return
    result.data["requested_level"] = level
    item["requested_level"] = level
    level_info = _level_info(item, level)
    if level_info:
        item["level_info"] = level_info
        result.data["item"] = item
        result.warnings.append(
            "等级请求与公开的突破数据匹配；"
            "当前数据源不提供精确的成长曲线属性"
        )
        return
    result.warnings.append("当前公开数据源不提供特定等级的属性")


def _level_info(item: dict[str, object], level: int) -> dict[str, object] | None:
    promote = item.get("upgrade")
    if isinstance(promote, dict):
        promote = promote.get("promote")
    rows = [row for row in promote if isinstance(row, dict)] if isinstance(promote, list) else []
    if not rows:
        return None
    sorted_rows = sorted(rows, key=lambda row: _number(row.get("unlockMaxLevel")))
    selected = next(
        (row for row in sorted_rows if _number(row.get("unlockMaxLevel")) >= level),
        sorted_rows[-1],
    )
    add_props = selected.get("addProps")
    return {
        "level": level,
        "promote_level": selected.get("promoteLevel"),
        "unlock_max_level": selected.get("unlockMaxLevel"),
        "required_player_level": selected.get("requiredPlayerLevel"),
        "add_props": add_props if isinstance(add_props, dict) else {},
    }


def talent_command(args: argparse.Namespace) -> CommandResult:
    provider = _provider(args)
    result = provider.character_talent(
        character=args.character,
        talent=_positive(args.talent, "talent"),
    )
    if not render_text_enabled(args):
        return result
    _enrich_talent_material_names(provider, result)
    return _wiki_text_render_result(
        args,
        result=result,
        render_name="wiki/talent-text",
        filename=f"wiki-talent_{_safe_filename(args.character)}_{args.talent}.txt",
        content=render_wiki_talent_text(result.data),
        description=" wiki 天赋文本",
        render_data={"character": args.character, "talent": args.talent},
    )


def constellation_command(args: argparse.Namespace) -> CommandResult:
    provider = _provider(args)
    constellation = (
        _positive(args.constellation, "constellation") if args.constellation is not None else None
    )
    result = provider.character_constellation(
        character=args.character,
        constellation=constellation,
    )
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return result
    full = (
        provider.wiki_lookup(kind="character", query=args.character)
        if render_image_enabled(args)
        else None
    )
    return _wiki_render_result(
        args,
        result,
        "constellation",
        item_result=full,
        constellation=constellation,
    )


def character_materials_command(args: argparse.Namespace) -> CommandResult:
    provider = _provider(args)
    result = provider.character_materials(character=args.character)
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return result
    if render_text_enabled(args):
        _enrich_material_command_names(provider, result, kind="character")
    full = (
        provider.wiki_lookup(kind="character", query=args.character)
        if render_image_enabled(args)
        else None
    )
    return _wiki_render_result(args, result, "character-materials", item_result=full)


def weapon_materials_command(args: argparse.Namespace) -> CommandResult:
    provider = _provider(args)
    result = provider.weapon_materials(weapon=args.weapon)
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return result
    if render_text_enabled(args):
        _enrich_material_command_names(provider, result, kind="weapon")
    full = (
        provider.wiki_lookup(kind="weapon", query=args.weapon)
        if render_image_enabled(args)
        else None
    )
    return _wiki_render_result(
        args,
        result,
        "weapon",
        item_result=full,
        output_render="weapon-materials",
    )


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    wiki = groups.add_parser("wiki", help="查询公开的 wiki 数据。")
    commands = wiki.add_subparsers(dest="wiki_command", required=True, metavar="<command>")
    for kind in ("character", "weapon", "artifact", "enemy", "food"):
        command = commands.add_parser(kind, help=f"查询 {kind}。")
        command.add_argument("query", nargs="?")
        command.add_argument("--name")
        if kind in {"character", "weapon"}:
            command.add_argument("--level", type=int)
        command.set_defaults(handler=wiki_command, command_name=f"wiki.{kind}", wiki_kind=kind)

    talent = commands.add_parser("talent", help="查询角色天赋。")
    talent.add_argument("--character", required=True)
    talent.add_argument("--talent", type=int, required=True)
    talent.set_defaults(handler=talent_command, command_name="wiki.talent")

    constellation = commands.add_parser("constellation", help="查询角色命座。")
    constellation.add_argument("--character", required=True)
    constellation.add_argument("--constellation", type=int)
    constellation.set_defaults(handler=constellation_command, command_name="wiki.constellation")

    character_materials = commands.add_parser(
        "character-materials",
        help=_HELPS["wiki.character-materials"],
    )
    character_materials.add_argument("--character", required=True)
    character_materials.set_defaults(
        handler=character_materials_command,
        command_name="wiki.character-materials",
    )

    weapon_materials = commands.add_parser("weapon-materials", help=_HELPS["wiki.weapon-materials"])
    weapon_materials.add_argument("--weapon", required=True)
    weapon_materials.set_defaults(
        handler=weapon_materials_command,
        command_name="wiki.weapon-materials",
    )


def _enrich_talent_material_names(provider, result: CommandResult) -> None:
    names = _material_names_by_id(provider, result)
    talent = result.data.get("talent")
    if not isinstance(talent, dict):
        return
    enriched = dict(talent)
    enriched["promote_materials"] = _named_promote_materials(talent.get("promote"), names)
    result.data["talent"] = enriched


def _enrich_material_command_names(provider, result: CommandResult, *, kind: str) -> None:
    names = _material_names_by_id(provider, result)
    enriched = {
        "ascension_materials": _named_material_entries(result.data.get("ascension"), names),
    }
    if kind == "character":
        enriched["talent_materials"] = _named_talent_materials(
            result.data.get("talents"),
            names,
        )
    result.data.update(enriched)


def _material_names_by_id(provider, result: CommandResult) -> dict[str, str]:
    try:
        return provider.material_names_by_id()
    except CliError:
        result.warnings.append("wiki 材料名称不可用；文本使用后备标签")
        return {}


def _named_talent_materials(value: object, names: Mapping[str, str]) -> list[dict[str, object]]:
    rows = [row for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []
    result = []
    for row in rows:
        promote_materials = _named_promote_materials(row.get("promote"), names)
        if not promote_materials:
            continue
        result.append(
            {
                "index": row.get("index"),
                "name": row.get("name"),
                "type": row.get("type"),
                "promote_materials": promote_materials,
            }
        )
    return result


def _named_promote_materials(
    value: object,
    names: Mapping[str, str],
) -> dict[str, list[dict[str, object]]]:
    promote = value if isinstance(value, Mapping) else {}
    result: dict[str, list[dict[str, object]]] = {}
    for level, row in promote.items():
        if not isinstance(row, Mapping):
            continue
        entries = _named_material_entries(row.get("costItems"), names)
        if entries:
            result[str(level)] = entries
    return result


def _named_material_entries(value: object, names: Mapping[str, str]) -> list[dict[str, object]]:
    if not isinstance(value, Mapping):
        return []
    entries = []
    for item_id, count in value.items():
        text_id = str(item_id)
        entries.append(
            {
                "id": text_id,
                "name": names.get(text_id),
                "count": count,
            }
        )
    entries.sort(key=lambda entry: str(entry.get("name") or entry.get("id") or ""))
    return entries


def _wiki_render_result(
    args: argparse.Namespace,
    result: CommandResult,
    render_kind: str,
    *,
    item_result: CommandResult | None = None,
    constellation: int | None = None,
    output_render: str | None = None,
) -> CommandResult:
    output_render = output_render or render_kind
    image_enabled = render_image_enabled(args) and render_kind in _image_render_kinds()
    text_enabled = render_text_enabled(args)
    item_source = item_result or result
    item = _wiki_item(item_source, render_kind) if image_enabled else _text_item(result)
    item_name = _render_item_name(result, item, output_render)
    suffix = f"_c{constellation}" if render_kind == "constellation" and constellation else ""
    artifacts: list[dict[str, object]] = []
    render_data: dict[str, object] = {"name": item_name}
    if constellation is not None:
        render_data["requested_constellation"] = constellation
    warnings = list(result.warnings)
    if image_enabled:
        image_item = _wiki_item(item_source, render_kind)
        asset_images, asset_warnings = fetch_render_images(
            args,
            wiki_asset_urls(render_kind, image_item),
            provider="wiki-assets",
            region="cn",
            category=f"wiki.{render_kind}.asset",
            unavailable_warning="{count} 张 wiki 图片资源不可用，已使用占位图",
            max_workers=WIKI_IMAGE_WORKERS,
        )
        png = _render_wiki_png(render_kind, image_item, asset_images, constellation=constellation)
        image_artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
            name=f"wiki/{output_render}",
            filename=f"wiki-{output_render}_{_safe_filename(item_name)}{suffix}.png",
            media_type="image/png",
            content=png,
            description=f"wiki {output_render} 卡片图片",
            kind="image",
        )
        artifacts.append(image_artifact)
        warnings.extend(asset_warnings)
        render_data.update(
            {
                "render": f"wiki/{output_render}",
                "artifact_sha256": image_artifact["sha256"],
            }
        )
    if text_enabled:
        text_render_name = f"wiki/{output_render}-text"
        text_artifact = ArtifactManager(args.request_id, args.output_dir).write_text(
            name=text_render_name,
            filename=f"wiki-{output_render}_{_safe_filename(item_name)}{suffix}.txt",
            content=_render_wiki_text_content(output_render, result, item),
            description=f" wiki {output_render} 文本",
            kind="text",
        )
        artifacts.append(text_artifact)
        if image_enabled:
            render_data["text_artifact_sha256"] = text_artifact["sha256"]
        else:
            render_data.update(
                {
                    "render": text_render_name,
                    "artifact_sha256": text_artifact["sha256"],
                }
            )
    data = render_result_data(args, result.data, render_data)
    if item_result is not None:
        warnings.extend(item_result.warnings)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
        pagination=result.pagination,
    )


def _wiki_text_render_result(
    args: argparse.Namespace,
    *,
    result: CommandResult,
    render_name: str,
    filename: str,
    content: str,
    description: str,
    render_data: dict[str, object],
) -> CommandResult:
    artifact = ArtifactManager(args.request_id, args.output_dir).write_text(
        name=render_name,
        filename=filename,
        content=content,
        description=description,
        kind="text",
    )
    data = render_result_data(
        args,
        result.data,
        {
            **render_data,
            "render": render_name,
            "artifact_sha256": artifact["sha256"],
        },
    )
    return CommandResult(
        data=data,
        artifacts=[artifact],
        source=result.source,
        warnings=result.warnings,
        pagination=result.pagination,
    )


def _wiki_item(result: CommandResult, render_kind: str) -> dict[str, object]:
    item = result.data.get("item")
    if isinstance(item, dict):
        return item
    raise CliError(
        "UPSTREAM_INVALID_RESPONSE",
        "数据源返回的 wiki 数据缺少可渲染的物品对象。",
        EXIT_INVALID_INPUT,
        {"command": f"wiki.{render_kind}"},
        source=result.source,
    )


def _text_item(result: CommandResult) -> dict[str, object]:
    item = result.data.get("item")
    return item if isinstance(item, dict) else {}


def _render_item_name(
    result: CommandResult,
    item: dict[str, object],
    output_render: str,
) -> str:
    if output_render == "constellation":
        return (
            _optional_text(result.data.get("character"))
            or _optional_text(item.get("name"))
            or output_render
        )
    if output_render == "character-materials":
        return (
            _optional_text(result.data.get("character"))
            or _optional_text(item.get("name"))
            or output_render
        )
    if output_render == "weapon-materials":
        return (
            _optional_text(result.data.get("weapon"))
            or _optional_text(item.get("name"))
            or output_render
        )
    return _optional_text(item.get("name")) or output_render


def _render_wiki_text_content(
    output_render: str,
    result: CommandResult,
    item: dict[str, object],
) -> str:
    if output_render in {"character", "weapon", "artifact", "enemy", "food"}:
        return render_wiki_lookup_text(output_render, item)
    if output_render == "constellation":
        return render_wiki_constellation_text(result.data)
    if output_render == "character-materials":
        return render_wiki_character_materials_text(result.data)
    if output_render == "weapon-materials":
        return render_wiki_weapon_materials_text(result.data)
    raise CliError(
        "INVALID_ARGUMENT",
        "此命令未实现 wiki 文本渲染器。",
        EXIT_INVALID_INPUT,
        {"render": output_render},
    )


def _image_render_kinds() -> set[str]:
    return {"food", "artifact", "weapon", "character-materials", "constellation"}


def _render_wiki_png(
    render_kind: str,
    item: dict[str, object],
    asset_images: dict[str, bytes],
    *,
    constellation: int | None,
) -> bytes:
    if render_kind == "food":
        return render_wiki_food_card(item, asset_images=asset_images)
    if render_kind == "artifact":
        return render_wiki_artifact_card(item, asset_images=asset_images)
    if render_kind == "weapon":
        return render_wiki_weapon_card(item, asset_images=asset_images)
    if render_kind == "character-materials":
        return render_wiki_character_materials_card(item, asset_images=asset_images)
    if render_kind == "constellation":
        return render_wiki_constellation_card(
            item,
            constellation=constellation,
            asset_images=asset_images,
        )
    raise CliError(
        "INVALID_ARGUMENT",
        "此命令未实现 wiki 渲染器。",
        EXIT_INVALID_INPUT,
        {"render": render_kind},
    )


def _wiki_query(args: argparse.Namespace) -> str:
    query = args.name or args.query
    if not query:
        raise CliError(
            "INVALID_ARGUMENT",
            "需要提供 name 参数",
            EXIT_INVALID_INPUT,
            {"command": args.command_name},
        )
    return query


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
