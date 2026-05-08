from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, timezone
from urllib.parse import urlsplit

CN_TZ = timezone(timedelta(hours=8))
DAILY_RESET = time(hour=4, tzinfo=CN_TZ)
GAME_VERSION_TAG_REFRESH = time(hour=6, tzinfo=CN_TZ)


@dataclass(frozen=True)
class CacheRule:
    name: str
    ttl_seconds: int | None = None
    daily_expires_at: time | None = None
    cacheable: bool = True
    persist: bool = True
    versioned: bool = False


NO_STORE = CacheRule("no-store", cacheable=False)
SHORT_PRIVATE = CacheRule("private-short", ttl_seconds=60, persist=False)
SHORT_PUBLIC = CacheRule("public-short", ttl_seconds=5 * 60)
PUBLIC_DYNAMIC = CacheRule("public-dynamic", ttl_seconds=6 * 60 * 60)
GAME_VERSION = CacheRule("game-version", versioned=True)
GAME_VERSION_TAG = CacheRule("game-version-tag", daily_expires_at=GAME_VERSION_TAG_REFRESH)
DAILY_RESET_RULE = CacheRule("daily-reset", daily_expires_at=DAILY_RESET)


def cache_rule_for(
    *,
    method: str,
    provider: str,
    category: str,
    response_kind: str,
) -> CacheRule:
    if method.upper() != "GET":
        return NO_STORE

    if _action_category(category):
        return NO_STORE

    if category == "cache.game-version":
        return GAME_VERSION_TAG

    if category in {"daily.materials", "daily.materials.upgrade"}:
        return DAILY_RESET_RULE

    if _private_category(category):
        return SHORT_PRIVATE

    if category.startswith("rank.") or provider == "akasha":
        return SHORT_PUBLIC

    if category == "panel.refresh" or provider == "enka":
        return SHORT_PUBLIC

    if response_kind == "asset":
        return GAME_VERSION

    if category.startswith(("codes.", "events.", "announcements.", "rerun.")):
        return PUBLIC_DYNAMIC

    if category == "meta.doctor.network":
        return SHORT_PUBLIC

    if _public_version_category(category) or provider in {
        "ambr",
        "fandom",
        "genshinuid",
        "hakush",
        "lelaer",
        "minigg",
    }:
        return GAME_VERSION

    return PUBLIC_DYNAMIC


def cache_expires_at(fetched_at: str, rule: CacheRule) -> str | None:
    if not rule.cacheable:
        return None
    fetched = _parse_utc(fetched_at)
    if fetched is None:
        return None
    if rule.daily_expires_at is not None:
        return _format_utc(_next_daily_expiration(fetched, rule.daily_expires_at))
    if rule.ttl_seconds is not None:
        return _format_utc(fetched + timedelta(seconds=rule.ttl_seconds))
    return None


def cache_version_for(rule: CacheRule, current_game_version: str | None) -> str | None:
    if rule.versioned:
        return current_game_version
    return None


def asset_cache_usage(*, provider: str, category: str, url: str | None = None) -> str:
    if provider == "minigg" or category.startswith("map."):
        return "maps"
    url_usage = _asset_url_usage(url)
    if url_usage is not None:
        return url_usage
    if _icon_category(category):
        return "icons"
    if provider in {
        "ambr",
        "announcement-assets",
        "event-assets",
        "genshinuid",
        "genshinuid-resource",
        "guide-assets",
        "hakush",
        "rerun-assets",
        "wiki-assets",
    } or category.startswith(
        (
            "announcements.",
            "daily.materials",
            "events.",
            "guide.",
            "recommend.",
            "rerun.",
            "wiki.",
        )
    ):
        return "wiki"
    return "assets"


def _asset_url_usage(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    if parts.scheme == "genshinuid":
        if parts.netloc == "wiki":
            return "wiki"
        if parts.netloc == "resource":
            segments = [segment for segment in parts.path.split("/") if segment]
            if segments and segments[0] in {"achi_icon", "icon", "monster_icon"}:
                return "icons"
            return "assets"
    path = parts.path
    if "/assets/UI/" in path or "/assets/UI/" in url:
        return "icons"
    if _icon_path(path):
        return "icons"
    return None


def _icon_category(category: str) -> bool:
    return "icon" in category or category.endswith(".avatar") or "profile_picture" in category


def _icon_path(path: str) -> bool:
    filename = path.rsplit("/", 1)[-1].lower()
    return "icon" in filename or "/icon/" in path.lower()


def cache_is_fresh(
    *,
    fetched_at: str,
    expires_at: str | None,
    cache_version: str | None,
    current_cache_version: str | None,
    rule: CacheRule,
    now: str,
) -> bool:
    if not rule.cacheable:
        return False
    if rule.versioned and (not current_cache_version or cache_version != current_cache_version):
        return False
    fetched = _parse_utc(fetched_at)
    now_dt = _parse_utc(now)
    if fetched is None or now_dt is None:
        return False
    expires = (
        _parse_utc(expires_at) if expires_at else _parse_utc(cache_expires_at(fetched_at, rule))
    )
    if expires is None:
        return True
    return now_dt < expires


def _action_category(category: str) -> bool:
    return category.startswith(
        (
            "auth.",
            "device.",
            "daily.bbs-coin",
            "daily.signin",
            "gacha.authkey.refresh",
        )
    )


def _private_category(category: str) -> bool:
    return category.startswith(
        (
            "daily.note",
            "player.",
            "challenge.",
            "progress.",
            "gacha.refresh",
        )
    )


def _public_version_category(category: str) -> bool:
    return category.startswith(
        (
            "wiki.",
            "guide.",
            "recommend.",
        )
    )


def _next_daily_expiration(fetched: datetime, expire_at: time) -> datetime:
    local = fetched.astimezone(CN_TZ)
    expires = datetime.combine(local.date(), expire_at)
    if local >= expires:
        expires += timedelta(days=1)
    return expires.astimezone(UTC)


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
