from __future__ import annotations

import argparse
import json
import re
from functools import lru_cache
from pathlib import Path

from gsuid_cli.commands._text import (
    helps_from,
    record_primary_image,
    record_text_artifact,
    safe_filename_part,
    write_image_artifact,
    write_text_artifact,
)
from gsuid_cli.commands.auth import _credential, _uid_and_region
from gsuid_cli.core.errors import EXIT_NO_RESULT, CliError
from gsuid_cli.core.http import HttpClient, raise_for_retcode
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import normalize_region
from gsuid_cli.core.render import render_image_enabled, render_result_data, render_text_enabled
from gsuid_cli.providers import provider_for_region
from gsuid_cli.providers.akasha import AkashaProvider
from gsuid_cli.providers.assets import fetch_render_images
from gsuid_cli.providers.mys import (
    ELEMENT_ID_BY_NAME,
    _payload_data,
    server_for_uid,
)
from gsuid_cli.renderers.common import asset_path
from gsuid_cli.renderers.rank.image import (
    artifact_rank_asset_urls,
    character_rank_asset_urls,
    render_artifact_rank,
    render_character_rank,
    render_user_rank_list,
    user_rank_asset_urls,
)
from gsuid_cli.renderers.rank.text import (
    render_rank_artifact_text,
    render_rank_character_text,
    render_rank_list_text,
)

RANK_IMAGE_WORKERS = 12
DATA_PATH = asset_path("panel", "data")
CROWN_ITEM_ID = 104319
CONSTELLATION_SKILL_BONUS_RE = re.compile(r"<color=[^>]+>(.*?)</color>的技能等级提高3级")

CAPABILITIES = [
    {
        "command": "rank.list",
        "description": "显示指定 UID 的排行列表。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "rank.character",
        "description": "显示角色排行榜。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "rank.artifact",
        "description": "显示圣遗物排行榜。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
]

_HELPS = helps_from(CAPABILITIES)


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    rank = groups.add_parser("rank", help="显示 Akasha 排行榜。")
    commands = rank.add_subparsers(dest="rank_command", required=True, metavar="<command>")

    list_parser = commands.add_parser("list", help=_HELPS["rank.list"])
    list_parser.add_argument("--uid", dest="command_uid")
    list_parser.set_defaults(handler=list_command, command_name="rank.list")

    character = commands.add_parser("character", help=_HELPS["rank.character"])
    character.add_argument("--uid", dest="command_uid")
    character.add_argument("--character", required=True)
    character.add_argument("--nearby", action="store_true")
    character.set_defaults(handler=character_command, command_name="rank.character")

    artifact = commands.add_parser("artifact", help=_HELPS["rank.artifact"])
    artifact.add_argument(
        "--sort",
        default="双爆",
        help="Akasha 圣遗物排序方式，例如：双爆, 暴击率, crit-rate, recharge。",
    )
    artifact.set_defaults(handler=artifact_command, command_name="rank.artifact")


def list_command(args: argparse.Namespace) -> CommandResult:
    uid, region = _uid_and_region(args)
    result = _provider(args).user_rank(uid=uid, region=region)
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return result
    return _list_render_result(args, result=result, uid=uid, region=region)


def character_command(args: argparse.Namespace) -> CommandResult:
    character_id = _character_id(args.character)
    region = normalize_region(args.region)
    selected_uid: str | None = None
    tag = "前20"
    calculation_id: str | None = None
    combo: float | None = None
    base_source: dict[str, object] | None = None
    if args.nearby:
        selected_uid, region = _uid_and_region(args)
        user_rank = _provider(args).user_rank(uid=selected_uid, region=region)
        base_source = user_rank.source
        user_character = _find_user_character(user_rank.data, character_id, selected_uid)
        calculation_id = str(user_character.get("calculation_id") or "")
        combo = _number(user_character.get("result")) + 0.01
        tag = "角色附近"

    result = _provider(args).character_leaderboard(
        character_id=character_id,
        region=region,
        calculation_id=calculation_id,
        combo=combo,
    )
    data = {
        **result.data,
        "character": _character_name(character_id),
        "tag": tag,
        "selected_uid": selected_uid,
    }
    result = CommandResult(data=data, source=result.source or base_source)
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return result
    return _character_render_result(
        args,
        result=result,
        character_id=character_id,
        tag=tag,
        selected_uid=selected_uid,
        region=region,
    )


def artifact_command(args: argparse.Namespace) -> CommandResult:
    region = normalize_region(args.region)
    result = _provider(args).artifact_leaderboard(sort_by=args.sort, region=region)
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return result
    return _artifact_render_result(args, result=result, region=region)


def _list_render_result(
    args: argparse.Namespace,
    *,
    result: CommandResult,
    uid: str,
    region: str,
) -> CommandResult:
    characters = _list_of_dicts(result.data.get("characters"))
    player, title_warnings = _rank_list_title_context(
        args,
        uid=uid,
        region=region,
        player=_dict(result.data.get("player")),
        characters=characters,
    )
    artifacts: list[dict[str, object]] = []
    warnings = [*result.warnings, *title_warnings]
    result_data = {**result.data, "player": player}
    render_data: dict[str, object] = {"uid": uid, "character_count": len(characters)}
    if render_image_enabled(args):
        images, image_warnings = fetch_render_images(
            args,
            [*_player_asset_urls(player), *user_rank_asset_urls(characters)],
            provider="akasha",
            region=region,
            category="rank.list.asset",
            unavailable_warning="{count} 张 Akasha 排行图片不可用，已使用占位图",
            max_workers=RANK_IMAGE_WORKERS,
        )
        png = render_user_rank_list(
            uid=uid,
            player=player,
            characters=characters,
            asset_images=images,
        )
        image_artifact = write_image_artifact(
            args,
            name="rank/list",
            filename=f"rank-list_{safe_filename_part(uid)}.png",
            content=png,
            description="Akasha 排名列表图片",
        )
        artifacts.append(image_artifact)
        warnings.extend(image_warnings)
        record_primary_image(render_data, image_artifact)
    if render_text_enabled(args):
        text_artifact = write_text_artifact(
            args,
            name="rank/list-text",
            filename=f"rank-list_{safe_filename_part(uid)}.txt",
            content=render_rank_list_text(result_data),
            description="适合命令行阅读的 Akasha 排名列表文本",
        )
        artifacts.append(text_artifact)
        record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    data = render_result_data(args, result_data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
    )


def _rank_list_title_context(
    args: argparse.Namespace,
    *,
    uid: str,
    region: str,
    player: dict[str, object],
    characters: list[dict[str, object]],
) -> tuple[dict[str, object], list[str]]:
    credential_args = argparse.Namespace(**vars(args))
    credential_args.credential_kind = "cookie"
    try:
        cookie, credential_source, storage_backend = _credential(credential_args, uid)
        provider = provider_for_region(
            region,
            HttpClient(
                timeout=args.timeout,
                cache_policy="off",
                output_dir=args.output_dir,
                debug=args.debug,
            ),
        )
        summary_result = provider.player_summary(
            uid=uid,
            cookie=cookie,
            region=region,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )
        characters_result = provider.player_characters(
            uid=uid,
            cookie=cookie,
            region=region,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )
    except CliError as exc:
        if exc.code == "AUTH_REQUIRED":
            return player, []
        return player, ["排名列表米游社标题数据不可用，已使用 Akasha 标题数据"]

    summary = _dict(summary_result.data.get("summary"))
    mys_characters = _list_of_dicts(characters_result.data.get("characters"))
    enriched = dict(player)
    stats = _dict(summary.get("stats"))
    if avatar_count := int(_number(stats.get("avatar_number"))):
        enriched["owned_character_count"] = avatar_count
    warnings = [*summary_result.warnings, *characters_result.warnings]
    crown_stat = "0/0"
    try:
        details = _mys_character_details(
            provider,
            uid=uid,
            cookie=cookie,
            region=region,
            characters=mys_characters,
        )
        crown_stat = _crown_title_stat(
            provider,
            uid=uid,
            cookie=cookie,
            region=region,
            details=details,
        )
    except CliError:
        warnings.append("排名列表皇冠标题数据不可用，已显示为 0/0")
    enriched["title_stats"] = _title_stats_from_mys(
        summary,
        mys_characters,
        characters,
        crown_stat=crown_stat,
    )
    return enriched, warnings


def _title_stats_from_mys(
    summary: dict[str, object],
    mys_characters: list[dict[str, object]],
    rank_characters: list[dict[str, object]],
    *,
    crown_stat: str,
) -> list[object]:
    star4 = [item for item in mys_characters if int(_number(item.get("rarity"))) == 4]
    star5 = [item for item in mys_characters if int(_number(item.get("rarity"))) == 5]
    full_star4 = sum(
        1 for item in star4 if int(_number(item.get("actived_constellation_num"))) >= 6
    )
    star5_weapons = sum(
        1 for item in mys_characters if int(_number(_dict(item.get("weapon")).get("rarity"))) == 5
    )
    fetter_full = sum(1 for item in mys_characters if int(_number(item.get("fetter"))) >= 10)
    high_score = sum(1 for item in rank_characters if _stat_cv(item) >= 210)
    useful = sum(1 for item in rank_characters if _stat_cv(item) >= 180)
    return [
        crown_stat,
        f"{fetter_full}/{len(mys_characters)}",
        f"{full_star4}/{len(star4)}",
        f"{len(star5)}/{_total_star_count('5')}",
        f"{len(star4)}/{_total_star_count('4')}",
        f"{star5_weapons}/{_total_weapon_count('5')}",
        high_score,
        useful,
    ]


def _mys_character_details(
    provider: object,
    *,
    uid: str,
    cookie: str,
    region: str,
    characters: list[dict[str, object]],
) -> list[dict[str, object]]:
    character_ids = [
        int(_number(character.get("id")))
        for character in characters
        if _number(character.get("id"))
    ]
    if not character_ids:
        return []
    result = provider.character_details(
        uid=uid,
        cookie=cookie,
        region=region,
        character_ids=character_ids,
        category="rank.list.character-detail",
    )
    return _list_of_dicts(result.data.get("details"))


def _crown_title_stat(
    provider: object,
    *,
    uid: str,
    cookie: str,
    region: str,
    details: list[dict[str, object]],
) -> str:
    crown_cost = _crown_cost_from_character_details(details)
    crown_owned = _crown_owned_from_calculator(
        provider,
        uid=uid,
        cookie=cookie,
        region=region,
        details=details,
    )
    return f"{crown_cost}/{crown_cost + crown_owned}"


def _crown_cost_from_character_details(details: list[dict[str, object]]) -> int:
    crown_cost = 0
    for character in details:
        bonuses = _constellation_skill_bonuses(character)
        for skill in _list_of_dicts(character.get("skills")):
            if int(_number(skill.get("skill_type"))) != 1:
                continue
            skill_name = str(skill.get("name") or "")
            base_level = int(_number(skill.get("level"))) - bonuses.get(skill_name, 0)
            if base_level >= 10:
                crown_cost += 1
    return crown_cost


def _constellation_skill_bonuses(character: dict[str, object]) -> dict[str, int]:
    bonuses: dict[str, int] = {}
    for constellation in _list_of_dicts(character.get("constellations")):
        if int(_number(constellation.get("pos"))) not in (3, 5):
            continue
        if not constellation.get("is_actived"):
            continue
        match = CONSTELLATION_SKILL_BONUS_RE.search(str(constellation.get("effect") or ""))
        if not match:
            continue
        skill_name = match.group(1)
        bonuses[skill_name] = bonuses.get(skill_name, 0) + 3
    return bonuses


def _crown_owned_from_calculator(
    provider: object,
    *,
    uid: str,
    cookie: str,
    region: str,
    details: list[dict[str, object]],
) -> int:
    items = _crown_compute_items(details)
    if not items:
        return 0
    body = {
        "items": items,
        "region": server_for_uid(uid),
        "uid": uid,
    }
    response = provider._inventory_compute_response(cookie=cookie, region=region, body=body)
    raise_for_retcode(
        response.payload,
        provider="mys",
        region=region,
        category="rank.list.crown-calculate",
        source=response.source,
        debug=provider.http.debug,
    )
    data = _payload_data(response.payload, "rank.list.crown-calculate", response.source)
    return _crown_owned_from_calculator_data(data)


def _crown_owned_from_calculator_data(data: dict[str, object]) -> int:
    material_consume = _dict(data.get("overall_material_consume"))
    items = [
        *_list_of_dicts(data.get("overall_consume")),
        *_list_of_dicts(material_consume.get("avatar_skill_consume")),
    ]
    for item in items:
        if int(_number(item.get("id"))) == CROWN_ITEM_ID:
            return max(int(_number(item.get("num"))) - int(_number(item.get("lack_num"))), 0)
    return 0


def _crown_compute_items(details: list[dict[str, object]]) -> list[dict[str, object]]:
    skill_map = _json_map("avatarId2SkillList_mapping_6.5.0.json")
    items: list[dict[str, object]] = []
    for character in details:
        base = _dict(character.get("base"))
        avatar_id = str(base.get("id") or "")
        skills = _crown_compute_skills(_dict(skill_map.get(avatar_id)))
        if not avatar_id.isdigit() or len(skills) != 3:
            continue
        items.append(
            {
                "avatar_id": int(avatar_id),
                "avatar_level_current": 1,
                "avatar_level_target": 90,
                "element_attr_id": ELEMENT_ID_BY_NAME.get(str(base.get("element")), 0),
                "level": int(_number(base.get("rarity")) or 5),
                "name": str(base.get("name") or ""),
                "skill_list": skills,
            }
        )
    return items


def _crown_compute_skills(skills: dict[str, object]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for skill_id, name in skills.items():
        skill_id_text = str(skill_id)
        if not skill_id_text.endswith(("1", "2", "9")):
            continue
        result.append(
            {
                "id": skill_id_text,
                "group_id": skill_id_text,
                "name": str(name),
                "max_level": 10,
                "levelRange": [1, 10],
                "level_current": 1,
                "level_target": 10,
            }
        )
        if len(result) == 3:
            break
    return result


def _character_render_result(
    args: argparse.Namespace,
    *,
    result: CommandResult,
    character_id: str,
    tag: str,
    selected_uid: str | None,
    region: str,
) -> CommandResult:
    entries = _list_of_dicts(result.data.get("entries"))
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data: dict[str, object] = {"character": _character_name(character_id)}
    if render_image_enabled(args):
        images, image_warnings = fetch_render_images(
            args,
            character_rank_asset_urls(character_id, entries),
            provider="akasha",
            region=region,
            category="rank.character.asset",
            unavailable_warning=("{count} 张 Akasha 角色排行图片不可用，已使用占位图"),
            max_workers=RANK_IMAGE_WORKERS,
        )
        png = render_character_rank(
            character_id=character_id,
            tag=tag,
            total_count=int(_number(result.data.get("total_count"))),
            entries=entries,
            selected_uid=selected_uid,
            asset_images=images,
        )
        image_artifact = write_image_artifact(
            args,
            name="rank/character",
            filename=f"rank-character_{safe_filename_part(_character_name(character_id))}.png",
            content=png,
            description="Akasha 角色排行榜图片",
        )
        artifacts.append(image_artifact)
        warnings.extend(image_warnings)
        record_primary_image(render_data, image_artifact)
    if render_text_enabled(args):
        text_artifact = write_text_artifact(
            args,
            name="rank/character-text",
            filename=f"rank-character_{safe_filename_part(_character_name(character_id))}.txt",
            content=render_rank_character_text(result.data),
            description="适合命令行阅读的 Akasha 角色排行榜文本",
        )
        artifacts.append(text_artifact)
        record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
    )


def _artifact_render_result(
    args: argparse.Namespace,
    *,
    result: CommandResult,
    region: str,
) -> CommandResult:
    artifacts = _list_of_dicts(result.data.get("artifacts"))
    output_artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data: dict[str, object] = {"sort": result.data.get("sort")}
    if render_image_enabled(args):
        images, image_warnings = fetch_render_images(
            args,
            artifact_rank_asset_urls(artifacts),
            provider="akasha",
            region=region,
            category="rank.artifact.asset",
            unavailable_warning=("{count} 张 Akasha 圣遗物排行图片不可用，已使用占位图"),
            max_workers=RANK_IMAGE_WORKERS,
        )
        png = render_artifact_rank(
            sort_label=str(result.data.get("sort") or "双爆"),
            artifacts=artifacts,
            asset_images=images,
        )
        sort_filename = safe_filename_part(str(result.data.get("sort") or "crit"))
        image_artifact = write_image_artifact(
            args,
            name="rank/artifact",
            filename=f"rank-artifact_{sort_filename}.png",
            content=png,
            description="Akasha 圣遗物排行榜图片",
        )
        output_artifacts.append(image_artifact)
        warnings.extend(image_warnings)
        record_primary_image(render_data, image_artifact)
    if render_text_enabled(args):
        sort_text_filename = safe_filename_part(str(result.data.get("sort") or "crit"))
        text_artifact = write_text_artifact(
            args,
            name="rank/artifact-text",
            filename=f"rank-artifact_{sort_text_filename}.txt",
            content=render_rank_artifact_text(result.data),
            description="适合命令行阅读的 Akasha 圣遗物排行榜文本",
        )
        output_artifacts.append(text_artifact)
        record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=output_artifacts,
        source=result.source,
        warnings=warnings,
    )


def _provider(args: argparse.Namespace) -> AkashaProvider:
    return AkashaProvider(
        HttpClient(
            timeout=args.timeout,
            cache_policy="off",
            output_dir=args.output_dir,
            debug=args.debug,
        )
    )


def _find_user_character(data: dict[str, object], character_id: str, uid: str) -> dict[str, object]:
    for character in _list_of_dicts(data.get("characters")):
        if str(character.get("avatar_id")) == character_id:
            return character
    raise CliError(
        "NO_RESULT",
        f"此 UID 上没有 {_character_name(character_id)} 的 Akasha 排行数据。",
        EXIT_NO_RESULT,
        {"uid": uid, "character_id": character_id},
    )


def _character_id(query: str) -> str:
    if query.isdigit():
        return query
    needle = _normalize(query)
    for avatar_id, name in _json_map("avatarId2Name_mapping_6.5.0.json").items():
        if needle == _normalize(str(name)):
            return avatar_id
    for name, avatar_id in _json_map("enName2AvatarID_mapping_6.5.0.json").items():
        if needle == _normalize(str(name)):
            return str(avatar_id)
    aliases = _json_map("char_alias.json")
    for name, values in aliases.items():
        candidates = [name, *values] if isinstance(values, list) else [name]
        if needle in {_normalize(str(value)) for value in candidates}:
            return _character_id(str(name))
    raise CliError(
        "NO_RESULT",
        "没有找到与排行查询匹配的角色。",
        EXIT_NO_RESULT,
        {"query": query},
    )


def _character_name(character_id: str) -> str:
    return str(_json_map("avatarId2Name_mapping_6.5.0.json").get(str(character_id)) or character_id)


@lru_cache(maxsize=8)
def _json_map(filename: str) -> dict[str, object]:
    path = Path(DATA_PATH) / filename
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _stat_cv(character: dict[str, object]) -> float:
    return _number(_dict(character.get("stats")).get("critValue"))


def _total_star_count(star: str) -> int:
    return sum(
        1 for value in _json_map("avatarId2Star_mapping_6.5.0.json").values() if str(value) == star
    )


def _total_weapon_count(star: str) -> int:
    return sum(
        1
        for item in _json_map("weaponList_6.5.0.json").values()
        if str(_dict(item).get("rank")) == star
    )


def _player_asset_urls(player: dict[str, object]) -> list[str]:
    return [
        url
        for key in ("profile_picture_url", "namecard_url")
        if (url := str(player.get(key) or ""))
    ]


def _normalize(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
