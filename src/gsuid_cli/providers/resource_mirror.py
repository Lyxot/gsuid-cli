from __future__ import annotations

import concurrent.futures
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from filelock import FileLock

from gsuid_cli.core.config import resolve_paths
from gsuid_cli.core.errors import EXIT_NETWORK, CliError

GENSHINUID_LOGICAL_BASE = "genshinuid://"
GENSHINUID_LOGICAL_SCHEME = "genshinuid"
GENSHINUID_MIRROR_CACHE_SECONDS = 6 * 60 * 60

GENSHINUID_RESOURCE_MIRRORS: dict[str, str] = {
    "[CNJS]": "http://cn-js-nj-1.lcf.icu:13214",
    "[TW]": "http://tw-taipei-1.lcf.icu:20532",
    "[SG]": "http://sg-1.lcf.icu:12588",
    "[US]": "http://us-lax-2.lcf.icu:12588",
    "[Azure SG]": "https://sg-2.qxqx.cf",
    "[Oracle KR]": "https://kr.qxqx.cf",
    "[Oracle JP]": "https://jp.qxqx.cf",
    "[MiniGG]": "http://file.minigg.cn/sayu-bot",
    "[Lulu]": "http://lulush.microgg.cn",
    "[TakeyaYuki]": "https://gscore.focalors.com",
    "[Elysia]": "https://silverwing.elysia.beauty",
}


@dataclass(frozen=True)
class ResourceMirrorResolution:
    logical_url: str
    url: str
    tag: str
    base_url: str
    cached: bool


@dataclass(frozen=True)
class _MirrorProbe:
    tag: str
    base_url: str
    elapsed: float


@dataclass(frozen=True)
class _MirrorSelection:
    tag: str
    base_url: str
    cached: bool


def resolve_genshinuid_resource_url(
    url: str,
    *,
    timeout: float,
    cache_policy: str,
    output_dir: str | None,
    transport: httpx.BaseTransport | None = None,
) -> ResourceMirrorResolution | None:
    if not is_genshinuid_resource_url(url) or cache_policy == "only":
        return None
    mirror = _select_genshinuid_mirror(
        timeout=timeout,
        cache_policy=cache_policy,
        output_dir=output_dir,
        transport=transport,
    )
    return ResourceMirrorResolution(
        logical_url=url,
        url=_mirror_url(mirror.base_url, url),
        tag=mirror.tag,
        base_url=mirror.base_url,
        cached=mirror.cached,
    )


def is_genshinuid_resource_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == GENSHINUID_LOGICAL_SCHEME and bool(parts.netloc)


def _select_genshinuid_mirror(
    *,
    timeout: float,
    cache_policy: str,
    output_dir: str | None,
    transport: httpx.BaseTransport | None,
) -> _MirrorSelection:
    cache_path = _mirror_cache_path(output_dir)
    if cache_policy not in {"off", "refresh"}:
        cached = _read_cached_mirror(cache_path)
        if cached is not None:
            return cached

    with FileLock(str(cache_path.with_suffix(".lock"))):
        if cache_policy not in {"off", "refresh"}:
            cached = _read_cached_mirror(cache_path)
            if cached is not None:
                return cached

        selected = _find_fastest_mirror(timeout=timeout, transport=transport)
        if selected is None:
            raise CliError(
                "NETWORK_ERROR",
                "No GenshinUID resource mirror is reachable.",
                EXIT_NETWORK,
                {
                    "provider": "genshinuid-resource",
                    "category": "resource.mirror",
                    "mirror_count": len(GENSHINUID_RESOURCE_MIRRORS),
                },
                retryable=True,
            )
        selection = _MirrorSelection(
            tag=selected.tag,
            base_url=selected.base_url,
            cached=False,
        )
        if cache_policy != "off":
            _write_cached_mirror(cache_path, selection)
        return selection


def _find_fastest_mirror(
    *,
    timeout: float,
    transport: httpx.BaseTransport | None,
) -> _MirrorProbe | None:
    mirrors = list(GENSHINUID_RESOURCE_MIRRORS.items())
    if transport is not None:
        with httpx.Client(timeout=_probe_timeout(timeout), transport=transport) as client:
            probes = [
                probe
                for tag, base_url in mirrors
                if (probe := _probe_mirror(client, tag, base_url)) is not None
            ]
        return min(probes, key=lambda item: item.elapsed) if probes else None

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(mirrors)) as executor:
        futures = [
            executor.submit(_probe_mirror_once, tag, base_url, timeout) for tag, base_url in mirrors
        ]
        probes = [
            probe
            for future in concurrent.futures.as_completed(futures)
            if (probe := future.result()) is not None
        ]
    return min(probes, key=lambda item: item.elapsed) if probes else None


def _probe_mirror_once(tag: str, base_url: str, timeout: float) -> _MirrorProbe | None:
    with httpx.Client(timeout=_probe_timeout(timeout)) as client:
        return _probe_mirror(client, tag, base_url)


def _probe_mirror(client: httpx.Client, tag: str, base_url: str) -> _MirrorProbe | None:
    try:
        start = time.monotonic()
        response = client.get(base_url)
        elapsed = time.monotonic() - start
    except httpx.RequestError:
        return None
    if response.status_code == 200 and "Index of /" in response.text:
        return _MirrorProbe(tag=tag, base_url=base_url.rstrip("/"), elapsed=elapsed)
    return None


def _probe_timeout(timeout: float) -> httpx.Timeout:
    value = max(float(timeout), 0.1)
    return httpx.Timeout(
        connect=min(value, 3.0),
        read=min(value, 5.0),
        write=min(value, 3.0),
        pool=min(value, 3.0),
    )


def _mirror_url(base_url: str, logical_url: str) -> str:
    parts = urlsplit(logical_url)
    suffix = f"/GenshinUID/{parts.netloc}{parts.path}"
    url = f"{base_url.rstrip('/')}{suffix}"
    if parts.query:
        url = f"{url}?{parts.query}"
    return url


def _mirror_cache_path(output_dir: str | None) -> Path:
    path = resolve_paths(output_dir).cache / "http" / "resource-mirror.genshinuid.json"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def _read_cached_mirror(path: Path) -> _MirrorSelection | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    tag = raw.get("tag")
    base_url = raw.get("base_url")
    expires_at = _parse_utc(raw.get("expires_at"))
    if not isinstance(tag, str) or not isinstance(base_url, str) or expires_at is None:
        return None
    if datetime.now(UTC) >= expires_at:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return None
    return _MirrorSelection(
        tag=tag,
        base_url=base_url,
        cached=True,
    )


def _write_cached_mirror(path: Path, selection: _MirrorSelection) -> None:
    now = datetime.now(UTC)
    payload = {
        "provider": "genshinuid-resource",
        "tag": selection.tag,
        "base_url": selection.base_url,
        "fetched_at": _format_utc(now),
        "expires_at": _format_utc(now + timedelta(seconds=GENSHINUID_MIRROR_CACHE_SECONDS)),
        "cache_policy": "resource-mirror",
    }
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
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
