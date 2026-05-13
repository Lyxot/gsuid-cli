from __future__ import annotations

import argparse
from collections.abc import Mapping

from gsuid_cli.commands._shared import (
    _add_uid,
    _cookie_context,
    _mapping_data,
    _provider,
)
from gsuid_cli.commands._text import (
    helps_from,
    record_primary_image,
    record_text_artifact,
    safe_filename_part,
    write_image_artifact,
    write_text_artifact,
)
from gsuid_cli.commands.player.impl import (
    ENKA_UI_BASE,
    _player_profile_image_assets,
    _player_profile_title_avatar_url,
    _summary_role_avatar_url,
)
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, EXIT_NO_RESULT, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region, normalize_region
from gsuid_cli.core.render import render_image_enabled, render_result_data, render_text_enabled
from gsuid_cli.providers.akasha import AkashaProvider
from gsuid_cli.providers.assets import fetch_render_images
from gsuid_cli.renderers.challenge.abyss import (
    challenge_abyss_image_urls,
    render_challenge_abyss_card,
)
from gsuid_cli.renderers.challenge.hard import (
    challenge_hard_image_urls,
    render_challenge_hard_card,
)
from gsuid_cli.renderers.challenge.text import (
    render_challenge_abyss_text,
    render_challenge_hard_rank_text,
    render_challenge_hard_text,
    render_challenge_theater_text,
)
from gsuid_cli.renderers.challenge.theater import (
    challenge_theater_image_urls,
    render_challenge_theater_card,
)

CHALLENGE_IMAGE_WORKERS = 12

CAPABILITIES = [
    {
        "command": "challenge.abyss",
        "description": "显示深境螺旋数据。",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "challenge.theater",
        "description": "显示幻想真境剧诗数据。",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "challenge.hard",
        "description": "显示深罪旋曜挑战数据。",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "challenge.hard-rank",
        "description": "显示 Akasha 深罪旋曜排名。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
]

_HELPS = helps_from(CAPABILITIES)


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    challenge = groups.add_parser("challenge", help="显示挑战数据。")
    commands = challenge.add_subparsers(
        dest="challenge_command", required=True, metavar="<command>"
    )

    abyss = commands.add_parser("abyss", help=_HELPS["challenge.abyss"])
    _add_uid(abyss)
    _add_season(abyss)
    abyss.add_argument("--floor", type=int)
    abyss.set_defaults(handler=abyss_command, command_name="challenge.abyss")

    theater = commands.add_parser("theater", help=_HELPS["challenge.theater"])
    _add_uid(theater)
    _add_season(theater)
    theater.set_defaults(handler=theater_command, command_name="challenge.theater")

    hard = commands.add_parser("hard", help=_HELPS["challenge.hard"])
    _add_uid(hard)
    _add_season(hard)
    hard.set_defaults(handler=hard_command, command_name="challenge.hard")

    hard_rank = commands.add_parser(
        "hard-rank",
        help=_HELPS["challenge.hard-rank"],
    )
    hard_rank.set_defaults(handler=hard_rank_command, command_name="challenge.hard-rank")


def abyss_command(args: argparse.Namespace) -> CommandResult:
    _validate_floor(args.floor)
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    provider = _provider(args, region)
    result = provider.challenge_abyss(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
        season=args.season,
        floor=args.floor,
    )
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return result
    return _abyss_render_result(
        args,
        provider=provider,
        result=result,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def theater_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    provider = _provider(args, region)
    result = provider.challenge_theater(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
        season=args.season,
    )
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return result
    return _theater_render_result(
        args,
        provider=provider,
        result=result,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def hard_command(args: argparse.Namespace) -> CommandResult:
    uid, region, cookie, credential_source, storage_backend = _cookie_context(args)
    provider = _provider(args, region)
    result = provider.challenge_hard(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
        season=args.season,
    )
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return result
    return _hard_render_result(
        args,
        provider=provider,
        result=result,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )


def hard_rank_command(args: argparse.Namespace) -> CommandResult:
    region = normalize_region(args.region or "cn")
    ensure_supported_region(region)
    result = AkashaProvider(
        HttpClient(
            timeout=args.timeout,
            cache_policy=args.cache,
            output_dir=args.output_dir,
            debug=args.debug,
        )
    ).stygian_rank(region=region)
    if not render_text_enabled(args):
        return result
    return _hard_rank_render_result(args, result)


def _add_season(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--season", choices=("current", "previous"), default="current")


def _validate_floor(floor: int | None) -> None:
    if floor is None:
        return
    if floor not in {9, 10, 11, 12}:
        raise CliError(
            "INVALID_ARGUMENT",
            "floor must be one of 9, 10, 11, or 12",
            EXIT_INVALID_INPUT,
            {"floor": floor},
        )


def _abyss_render_result(
    args: argparse.Namespace,
    *,
    provider,
    result: CommandResult,
    uid: str,
    region: str,
    cookie: str,
    credential_source: str,
    storage_backend: str | None,
) -> CommandResult:
    abyss = _mapping_data(result, "abyss", "challenge.abyss")
    render_abyss = abyss
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data: dict[str, object] = {"uid": uid, "floor_count": abyss.get("floor_count")}
    if render_image_enabled(args):
        if not _has_abyss_floor_data(abyss):
            raise CliError(
                "NO_RESULT",
                "渲染深境螺旋图片至少需要一层挑战数据。",
                EXIT_NO_RESULT,
                {
                    "uid": uid,
                    "season": result.data.get("season"),
                    "floor": result.data.get("floor"),
                },
                source=result.source,
            )
        render_abyss, rank_warnings = _abyss_with_character_ranks(
            provider,
            abyss,
            uid=uid,
            region=region,
            cookie=cookie,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )
        summary, title_images, avatar_url, title_warnings = _challenge_title_context(
            args,
            provider,
            uid=uid,
            region=region,
            cookie=cookie,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )
        images, image_warnings = fetch_render_images(
            args,
            challenge_abyss_image_urls(
                render_abyss,
                summary,
                _fetchable_title_avatar_url(avatar_url),
            ),
            provider="mys",
            region=region,
            category="challenge.abyss.image",
            unavailable_warning="{count} 个深境螺旋挑战图片不可用，已使用占位图",
            max_workers=CHALLENGE_IMAGE_WORKERS,
        )
        png = render_challenge_abyss_card(
            uid=uid,
            abyss=render_abyss,
            summary=summary,
            asset_images={**images, **title_images},
            avatar_url=avatar_url,
        )
        image_artifact = write_image_artifact(
            args,
            name="challenge/abyss",
            filename=f"challenge-abyss_{safe_filename_part(uid)}.png",
            content=png,
            description="深境螺旋卡片图片",
        )
        artifacts.append(image_artifact)
        warnings.extend([*rank_warnings, *title_warnings, *image_warnings])
        record_primary_image(render_data, image_artifact)
    else:
        summary, title_warnings = _challenge_title_summary_context(
            provider,
            uid=uid,
            region=region,
            cookie=cookie,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )
        warnings.extend(title_warnings)
    if render_text_enabled(args):
        text_artifact = write_text_artifact(
            args,
            name="challenge/abyss-text",
            filename=f"challenge-abyss_{safe_filename_part(uid)}.txt",
            content=render_challenge_abyss_text(uid=uid, abyss=abyss, summary=summary),
            description="深境螺旋挑战文本",
        )
        artifacts.append(text_artifact)
        record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
        pagination=result.pagination,
    )


def _theater_render_result(
    args: argparse.Namespace,
    *,
    provider,
    result: CommandResult,
    uid: str,
    region: str,
    cookie: str,
    credential_source: str,
    storage_backend: str | None,
) -> CommandResult:
    theater = _mapping_data(result, "theater", "challenge.theater")
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data: dict[str, object] = {"uid": uid, "session_count": theater.get("count")}
    if render_image_enabled(args):
        summary, title_images, avatar_url, title_warnings = _challenge_title_context(
            args,
            provider,
            uid=uid,
            region=region,
            cookie=cookie,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )
        images, image_warnings = fetch_render_images(
            args,
            challenge_theater_image_urls(theater, summary, _fetchable_title_avatar_url(avatar_url)),
            provider="mys",
            region=region,
            category="challenge.theater.image",
            unavailable_warning=("{count} 个幻想真境剧诗图片不可用，已使用占位图"),
            max_workers=CHALLENGE_IMAGE_WORKERS,
        )
        png = render_challenge_theater_card(
            uid=uid,
            theater=theater,
            summary=summary,
            asset_images={**images, **title_images},
            avatar_url=avatar_url,
        )
        image_artifact = write_image_artifact(
            args,
            name="challenge/theater",
            filename=f"challenge-theater_{safe_filename_part(uid)}.png",
            content=png,
            description="幻想真境剧诗卡片图片",
        )
        artifacts.append(image_artifact)
        warnings.extend([*title_warnings, *image_warnings])
        record_primary_image(render_data, image_artifact)
    else:
        summary, title_warnings = _challenge_title_summary_context(
            provider,
            uid=uid,
            region=region,
            cookie=cookie,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )
        warnings.extend(title_warnings)
    if render_text_enabled(args):
        text_artifact = write_text_artifact(
            args,
            name="challenge/theater-text",
            filename=f"challenge-theater_{safe_filename_part(uid)}.txt",
            content=render_challenge_theater_text(uid=uid, theater=theater, summary=summary),
            description="幻想真境剧诗挑战文本",
        )
        artifacts.append(text_artifact)
        record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
        pagination=result.pagination,
    )


def _hard_render_result(
    args: argparse.Namespace,
    *,
    provider,
    result: CommandResult,
    uid: str,
    region: str,
    cookie: str,
    credential_source: str,
    storage_backend: str | None,
) -> CommandResult:
    hard = _mapping_data(result, "hard", "challenge.hard")
    artifacts: list[dict[str, object]] = []
    warnings = list(result.warnings)
    render_data: dict[str, object] = {"uid": uid}
    if render_image_enabled(args):
        summary, title_images, avatar_url, title_warnings = _challenge_title_context(
            args,
            provider,
            uid=uid,
            region=region,
            cookie=cookie,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )
        images, image_warnings = fetch_render_images(
            args,
            challenge_hard_image_urls(hard, summary, _fetchable_title_avatar_url(avatar_url)),
            provider="mys",
            region=region,
            category="challenge.hard.image",
            unavailable_warning="{count} 个深罪旋曜挑战图片不可用，已使用占位图",
            max_workers=CHALLENGE_IMAGE_WORKERS,
        )
        png = render_challenge_hard_card(
            uid=uid,
            hard=hard,
            summary=summary,
            asset_images={**images, **title_images},
            avatar_url=avatar_url,
        )
        image_artifact = write_image_artifact(
            args,
            name="challenge/hard",
            filename=f"challenge-hard_{safe_filename_part(uid)}.png",
            content=png,
            description="深罪旋曜挑战卡片图片",
        )
        artifacts.append(image_artifact)
        warnings.extend([*title_warnings, *image_warnings])
        record_primary_image(render_data, image_artifact)
    else:
        summary, title_warnings = _challenge_title_summary_context(
            provider,
            uid=uid,
            region=region,
            cookie=cookie,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )
        warnings.extend(title_warnings)
    if render_text_enabled(args):
        text_artifact = write_text_artifact(
            args,
            name="challenge/hard-text",
            filename=f"challenge-hard_{safe_filename_part(uid)}.txt",
            content=render_challenge_hard_text(uid=uid, hard=hard, summary=summary),
            description="深罪旋曜挑战文本",
        )
        artifacts.append(text_artifact)
        record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    data = render_result_data(args, result.data, render_data)
    return CommandResult(
        data=data,
        artifacts=artifacts,
        source=result.source,
        warnings=warnings,
        pagination=result.pagination,
    )


def _hard_rank_render_result(args: argparse.Namespace, result: CommandResult) -> CommandResult:
    text_artifact = write_text_artifact(
        args,
        name="challenge/hard-rank-text",
        filename="challenge-hard-rank.txt",
        content=render_challenge_hard_rank_text(result.data),
        description="深罪旋曜排名支持状态文本",
    )
    data = render_result_data(
        args,
        result.data,
        {
            "render": "challenge/hard-rank-text",
            "artifact_sha256": text_artifact["sha256"],
        },
    )
    return CommandResult(
        data=data,
        artifacts=[text_artifact],
        source=result.source,
        warnings=result.warnings,
        pagination=result.pagination,
    )


def _challenge_title_summary_context(
    provider,
    *,
    uid: str,
    region: str,
    cookie: str,
    credential_source: str,
    storage_backend: str | None,
) -> tuple[Mapping[str, object], list[str]]:
    if not hasattr(provider, "player_summary"):
        return {}, []
    try:
        result = provider.player_summary(
            uid=uid,
            cookie=cookie,
            region=region,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )
    except CliError as exc:
        return {}, [f"player title avatar unavailable for challenge render: {exc.code}"]
    summary = result.data.get("summary")
    if not isinstance(summary, Mapping):
        return {}, [*result.warnings, "player summary missing for challenge title render"]
    return summary, list(result.warnings)


def _challenge_title_context(
    args: argparse.Namespace,
    provider,
    *,
    uid: str,
    region: str,
    cookie: str,
    credential_source: str,
    storage_backend: str | None,
) -> tuple[Mapping[str, object], dict[str, bytes], str | None, list[str]]:
    summary, summary_warnings = _challenge_title_summary_context(
        provider,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    if not summary:
        return {}, {}, None, summary_warnings
    role_avatar_url = _summary_role_avatar_url(summary)
    if role_avatar_url:
        title_avatar_url, profile_warnings = None, []
    else:
        title_avatar_url, profile_warnings = _player_profile_title_avatar_url(args, uid, region)
    profile_images, profile_image_warnings = _player_profile_image_assets(
        args,
        title_avatar_url,
        region,
    )
    return (
        summary,
        profile_images,
        title_avatar_url,
        [
            *summary_warnings,
            *profile_warnings,
            *profile_image_warnings,
        ],
    )


def _abyss_with_character_ranks(
    provider,
    abyss: Mapping[str, object],
    *,
    uid: str,
    region: str,
    cookie: str,
    credential_source: str,
    storage_backend: str | None,
) -> tuple[Mapping[str, object], list[str]]:
    if not hasattr(provider, "player_characters"):
        return abyss, []
    try:
        result = provider.player_characters(
            uid=uid,
            cookie=cookie,
            region=region,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )
    except CliError as exc:
        return abyss, [f"abyss character constellation data unavailable: {exc.code}"]
    characters = result.data.get("characters")
    if not isinstance(characters, list):
        return abyss, list(result.warnings)
    ranks: dict[str, object] = {}
    for character in characters:
        if not isinstance(character, Mapping):
            continue
        character_id = character.get("id", character.get("avatar_id"))
        rank = character.get("actived_constellation_num", character.get("rank"))
        if character_id not in (None, "") and rank not in (None, ""):
            ranks[str(character_id)] = rank
    if not ranks:
        return abyss, list(result.warnings)
    return _copy_abyss_with_ranks(abyss, ranks), list(result.warnings)


def _copy_abyss_with_ranks(
    abyss: Mapping[str, object],
    ranks: Mapping[str, object],
) -> Mapping[str, object]:
    floors: list[dict[str, object]] = []
    for floor in _mapping_list(abyss.get("floors")):
        floor_copy = dict(floor)
        levels: list[dict[str, object]] = []
        for level in _mapping_list(floor.get("levels")):
            level_copy = dict(level)
            battles: list[dict[str, object]] = []
            for battle in _mapping_list(level.get("battles")):
                battle_copy = dict(battle)
                avatars: list[dict[str, object]] = []
                for avatar in _mapping_list(battle.get("avatars")):
                    avatar_copy = dict(avatar)
                    avatar_id = avatar_copy.get("id", avatar_copy.get("avatar_id"))
                    rank = ranks.get(str(avatar_id))
                    if rank not in (None, ""):
                        avatar_copy.setdefault("rank", rank)
                    avatars.append(avatar_copy)
                battle_copy["avatars"] = avatars
                battles.append(battle_copy)
            level_copy["battles"] = battles
            levels.append(level_copy)
        floor_copy["levels"] = levels
        floors.append(floor_copy)
    return {**abyss, "floors": floors}


def _fetchable_title_avatar_url(avatar_url: str | None) -> str | None:
    if avatar_url and avatar_url.startswith(f"{ENKA_UI_BASE}/"):
        return None
    return avatar_url


def _has_abyss_floor_data(abyss: Mapping[str, object]) -> bool:
    floors = abyss.get("floors")
    if not isinstance(floors, list):
        return False
    return any(isinstance(floor, Mapping) for floor in floors)


def _mapping_list(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]
