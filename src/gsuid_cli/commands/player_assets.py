from __future__ import annotations

import argparse
import json
from collections.abc import Mapping

from gsuid_cli.commands._shared import _mapping_data
from gsuid_cli.core.errors import EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.providers.assets import AssetProvider, fetch_render_images
from gsuid_cli.providers.enka import EnkaProvider
from gsuid_cli.renderers.player.characters import (
    character_mys_image_urls,
    character_namecard_url,
    character_portrait_url,
    weapon_icon_url,
)
from gsuid_cli.renderers.player.summary import (
    ENKA_UI_BASE,
    player_profile_picture_url,
    player_summary_genshinuid_resource_urls,
)

PLAYER_CHARACTER_IMAGE_WORKERS = 8
PLAYER_SUMMARY_ICON_WORKERS = 8
PLAYER_PROFILE_IMAGE_WORKERS = 2
PROFILE_PICTURE_CONFIG_URL = "https://cdn.jsdelivr.net/gh/DimbreathBot/AnimeGameData@master/ExcelBinOutput/ProfilePictureExcelConfigData.json"


def _player_title_summary_context(
    *,
    provider,
    uid: str,
    region: str,
    cookie: str,
    credential_source: str,
    storage_backend: str | None,
    category_prefix: str,
) -> tuple[Mapping[str, object], list[str]]:
    summary_result = provider.player_summary(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
    )
    summary = _mapping_data(summary_result, "summary", f"{category_prefix}.summary")
    return summary, list(summary_result.warnings)


def _player_title_render_context(
    args: argparse.Namespace,
    *,
    provider,
    uid: str,
    region: str,
    cookie: str,
    credential_source: str,
    storage_backend: str | None,
    category_prefix: str,
    fetch_images=fetch_render_images,
    profile_title_avatar_url=None,
    profile_image_assets=None,
) -> tuple[Mapping[str, object], dict[str, bytes], str | None, list[str]]:
    summary, summary_warnings = _player_title_summary_context(
        provider=provider,
        uid=uid,
        region=region,
        cookie=cookie,
        credential_source=credential_source,
        storage_backend=storage_backend,
        category_prefix=category_prefix,
    )
    role_avatar_url = _summary_role_avatar_url(summary)
    if role_avatar_url:
        title_avatar_url, profile_warnings = None, []
    else:
        profile_title_avatar_url = profile_title_avatar_url or _player_profile_title_avatar_url
        title_avatar_url, profile_warnings = profile_title_avatar_url(args, uid, region)
    resource_urls = player_summary_genshinuid_resource_urls(summary)
    if title_avatar_url and not title_avatar_url.startswith(f"{ENKA_UI_BASE}/"):
        _append_url(resource_urls, title_avatar_url)
    resource_images, resource_warnings = fetch_images(
        args,
        resource_urls,
        provider="genshinuid",
        region=region,
        category=f"{category_prefix}.title.resource",
        unavailable_warning="{count} player title resources unavailable; rendered fallback avatar",
        max_workers=PLAYER_CHARACTER_IMAGE_WORKERS,
    )
    icon_images, icon_warnings = fetch_images(
        args,
        _player_title_mys_icon_urls(summary),
        provider="mys",
        region=region,
        category=f"{category_prefix}.title.icon",
        unavailable_warning="{count} player title icons unavailable; rendered fallback avatar",
        max_workers=PLAYER_SUMMARY_ICON_WORKERS,
    )
    profile_image_assets = profile_image_assets or _player_profile_image_assets
    profile_images, profile_image_warnings = profile_image_assets(args, title_avatar_url, region)
    return (
        summary,
        {**resource_images, **icon_images, **profile_images},
        title_avatar_url,
        [
            *summary_warnings,
            *profile_warnings,
            *resource_warnings,
            *icon_warnings,
            *profile_image_warnings,
        ],
    )


def _player_title_mys_icon_urls(summary: Mapping[str, object]) -> list[str]:
    role_avatar_url = _summary_role_avatar_url(summary)
    return [role_avatar_url] if role_avatar_url else []


def _player_profile_title_avatar_url(
    args: argparse.Namespace,
    uid: str,
    region: str,
    *,
    enka_provider_cls=EnkaProvider,
    http_client_cls=HttpClient,
    profile_picture_icons=None,
) -> tuple[str | None, list[str]]:
    try:
        result = enka_provider_cls(
            http_client_cls(
                timeout=args.timeout,
                cache_policy=args.cache,
                output_dir=args.output_dir,
                debug=args.debug,
            )
        ).profile(uid=uid, region=region)
    except CliError:
        return None, ["player profile unavailable; rendered title avatar fallback"]

    icons: Mapping[str, object] | None = None
    picture_id = _profile_picture_id(result.data)
    if picture_id:
        try:
            profile_picture_icons = profile_picture_icons or _profile_picture_icons
            icons = profile_picture_icons(args, region)
        except CliError:
            return None, ["player profile picture map unavailable; rendered title avatar fallback"]
    url = player_profile_picture_url(result.data, icons)
    if url is None:
        return None, ["player profile picture unavailable; rendered title avatar fallback"]
    return url, []


def _summary_role_avatar_url(summary: Mapping[str, object]) -> str | None:
    role = summary.get("role")
    if not isinstance(role, Mapping):
        return None
    value = role.get("avatar_icon")
    return str(value) if value not in (None, "") else None


def _profile_picture_icons(
    args: argparse.Namespace,
    region: str,
    *,
    http_client_cls=HttpClient,
) -> Mapping[str, object]:
    response = AssetProvider(
        http_client_cls(
            timeout=args.timeout,
            cache_policy=args.cache,
            output_dir=args.output_dir,
            debug=args.debug,
        )
    ).json_bytes(
        PROFILE_PICTURE_CONFIG_URL,
        provider="animegamedata",
        region=region,
        category="player.summary.profile_picture_config",
    )
    try:
        payload = json.loads(response.content)
    except ValueError as exc:
        raise CliError(
            "UPSTREAM_INVALID_RESPONSE",
            "Profile picture config returned invalid JSON.",
            EXIT_UPSTREAM,
            {"provider": "animegamedata", "category": "player.summary.profile_picture_config"},
            source=response.source,
        ) from exc
    if not isinstance(payload, list):
        raise CliError(
            "UPSTREAM_INVALID_RESPONSE",
            "Profile picture config returned an unexpected shape.",
            EXIT_UPSTREAM,
            {"provider": "animegamedata", "category": "player.summary.profile_picture_config"},
            source=response.source,
        )
    icons: dict[str, object] = {}
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        picture_id = item.get("id")
        icon_path = item.get("iconPath")
        if picture_id in (None, "") or not isinstance(icon_path, str) or not icon_path:
            continue
        icons[str(picture_id)] = {"iconPath": icon_path}
    if not icons:
        raise CliError(
            "UPSTREAM_INVALID_RESPONSE",
            "Profile picture config did not contain renderable icons.",
            EXIT_UPSTREAM,
            {"provider": "animegamedata", "category": "player.summary.profile_picture_config"},
            source=response.source,
        )
    return icons


def _profile_picture_id(profile: Mapping[str, object]) -> str | None:
    player_info = profile.get("playerInfo")
    if not isinstance(player_info, Mapping):
        return None
    profile_picture = player_info.get("profilePicture")
    if not isinstance(profile_picture, Mapping):
        return None
    value = profile_picture.get("id")
    return str(value) if value not in (None, "") else None


def _player_profile_image_assets(
    args: argparse.Namespace,
    title_avatar_url: str | None,
    region: str,
    *,
    fetch_images=fetch_render_images,
) -> tuple[dict[str, bytes], list[str]]:
    if not title_avatar_url or not title_avatar_url.startswith(f"{ENKA_UI_BASE}/"):
        return {}, []
    return fetch_images(
        args,
        [title_avatar_url],
        provider="enka",
        region=region,
        category="player.summary.profile_picture",
        unavailable_warning="player profile picture unavailable; rendered title avatar fallback",
        max_workers=PLAYER_PROFILE_IMAGE_WORKERS,
    )


def _player_character_asset_images(
    args: argparse.Namespace,
    characters: list[Mapping[str, object]],
    region: str,
    *,
    extra_genshinuid_urls: list[str] | None = None,
    fetch_images=fetch_render_images,
) -> tuple[dict[str, bytes], list[str]]:
    genshinuid_urls = _player_character_genshinuid_resource_urls(characters)
    for url in extra_genshinuid_urls or []:
        _append_url(genshinuid_urls, url)
    genshinuid_images, resource_warnings = fetch_images(
        args,
        genshinuid_urls,
        provider="genshinuid",
        region=region,
        category="player.characters.resource",
        unavailable_warning=(
            "{count} player character GenshinUID resources unavailable; "
            "rendered fallbacks where possible"
        ),
        max_workers=PLAYER_CHARACTER_IMAGE_WORKERS,
    )
    fallback_images, fallback_warnings = fetch_images(
        args,
        _player_character_mys_fallback_urls(characters, genshinuid_images),
        provider="mys",
        region=region,
        category="player.characters.fallback",
        unavailable_warning=(
            "{count} player character fallback images unavailable; rendered placeholders"
        ),
        max_workers=PLAYER_CHARACTER_IMAGE_WORKERS,
    )
    return {**fallback_images, **genshinuid_images}, [*resource_warnings, *fallback_warnings]


def _player_character_genshinuid_resource_urls(
    characters: list[Mapping[str, object]],
) -> list[str]:
    urls: list[str] = []
    for character in characters:
        _append_url(urls, character_portrait_url(character))
        _append_url(urls, character_namecard_url(character))
        weapon = character.get("weapon")
        if isinstance(weapon, Mapping):
            _append_url(urls, weapon_icon_url(weapon))
    return urls


def _player_character_mys_fallback_urls(
    characters: list[Mapping[str, object]],
    resource_images: Mapping[str, bytes],
) -> list[str]:
    urls: list[str] = []
    for character in characters:
        if character_portrait_url(character) not in resource_images:
            for url in character_mys_image_urls(character):
                _append_url(urls, url)
        weapon = character.get("weapon")
        if isinstance(weapon, Mapping) and weapon_icon_url(weapon) not in resource_images:
            _append_url(urls, weapon.get("icon"))
    return urls


def _append_url(urls: list[str], value: object) -> None:
    url = _optional_text(value)
    if url and url not in urls:
        urls.append(url)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
