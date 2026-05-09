from __future__ import annotations

import json
from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

import httpx

from gsuid_cli.core.cache import AssetCache, CachedResponse, HttpCache, cache_key, sanitized_url
from gsuid_cli.core.cache_policy import (
    CacheRule,
    asset_cache_usage,
    cache_expires_at,
    cache_is_fresh,
    cache_rule_for,
    cache_version_for,
)
from gsuid_cli.core.errors import (
    EXIT_AUTH,
    EXIT_CACHE,
    EXIT_NETWORK,
    EXIT_UPSTREAM,
    CliError,
)
from gsuid_cli.core.time import utc_now

AUTH_RETCODES = {-100, 10001, 10102}
VERIFICATION_RETCODES = {10035, 5003, 10041, 1034}
GAME_VERSION_BUILD_URL = (
    "https://api-takumi.mihoyo.com/downloader/sophon_chunk/api/getBuild"
    "?branch=main&package_id=8xfMve0uwQ&password=CW8GbLNU8f&plat_app=ddxf5qt290cg"
)
GAME_VERSION_PROVIDER = "sophon"
GAME_VERSION_CATEGORY = "cache.game-version"
_SOURCE_CAPTURE: ContextVar[_SourceCapture | None] = ContextVar(
    "gsuid_source_capture",
    default=None,
)


@dataclass
class _SourceCapture:
    sources: list[dict[str, object]] = field(default_factory=list)
    lock: Lock = field(default_factory=Lock)

    def add(self, source: dict[str, object]) -> None:
        with self.lock:
            self.sources.append(source)

    def snapshot(self) -> list[dict[str, object]]:
        with self.lock:
            return list(self.sources)


@dataclass(frozen=True)
class ProviderResponse:
    payload: dict[str, object]
    source: dict[str, object]
    status_code: int
    cookies: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderBytesResponse:
    content: bytes
    media_type: str
    source: dict[str, object]
    status_code: int


def begin_source_capture() -> Token[_SourceCapture | None]:
    return _SOURCE_CAPTURE.set(_SourceCapture())


def end_source_capture(token: Token[_SourceCapture | None]) -> list[dict[str, object]]:
    capture = _SOURCE_CAPTURE.get()
    sources = capture.snapshot() if capture is not None else []
    _SOURCE_CAPTURE.reset(token)
    return sources


class HttpClient:
    def __init__(
        self,
        *,
        timeout: float,
        cache_policy: str = "use",
        output_dir: str | None = None,
        debug: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.timeout = timeout
        self.cache_policy = cache_policy
        self.output_dir = output_dir
        self.cache = HttpCache(output_dir) if cache_policy != "off" else None
        self._assets: dict[str, AssetCache] = {}
        self.debug = debug
        self.transport = transport

    def request_json(
        self,
        method: str,
        url: str,
        *,
        provider: str,
        region: str,
        category: str,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> ProviderResponse:
        method = method.upper()
        key = cache_key(method, url, params=params, body=json_body)
        rule = cache_rule_for(
            method=method,
            provider=provider,
            category=category,
            response_kind="json",
        )
        cache_enabled = method == "GET" and self.cache is not None and rule.cacheable
        current_cache_version: str | None = None
        if cache_enabled and self.cache_policy in {"use", "only"}:
            cached = self.cache.get(key)
            if cached is not None:
                current_cache_version = self._current_cache_version(
                    rule,
                    required=self.cache_policy == "only",
                )
            if cached is not None and _cached_json_is_fresh(
                cached,
                rule,
                current_cache_version=current_cache_version,
            ):
                return ProviderResponse(
                    payload=cached.payload,
                    source=_record_source(
                        _source(
                            provider,
                            region,
                            True,
                            cached.fetched_at,
                            category=category,
                            status_code=cached.status_code,
                            retcode=cached.payload.get("retcode"),
                        )
                    ),
                    status_code=cached.status_code,
                )
            if cached is not None and _staleness_is_known(rule, current_cache_version):
                self.cache.delete(key)
            if self.cache_policy == "only":
                raise _cache_miss(provider, region, category, method, url, params)

        if self.cache_policy == "only":
            raise _cache_miss(provider, region, category, method, url, params)

        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                request_headers = dict(headers or {})
                if json_body is not None:
                    request_headers.setdefault("Content-Type", "application/json")
                response = client.request(
                    method,
                    url,
                    params=params,
                    headers=request_headers,
                    content=_json_body_content(json_body) if json_body is not None else None,
                )
        except httpx.TimeoutException as exc:
            raise _network_error(
                code="NETWORK_TIMEOUT",
                message="数据源请求超时。",
                provider=provider,
                region=region,
                category=category,
                method=method,
                url=url,
                params=params,
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise _network_error(
                code="NETWORK_ERROR",
                message="数据源请求失败。",
                provider=provider,
                region=region,
                category=category,
                method=method,
                url=url,
                params=params,
                retryable=True,
            ) from exc

        fetched_at = utc_now()
        if response.status_code >= 400:
            raise _upstream_error(
                code="UPSTREAM_HTTP_ERROR",
                message="数据源返回了 HTTP 错误。",
                provider=provider,
                region=region,
                category=category,
                method=method,
                url=url,
                params=params,
                status_code=response.status_code,
                body=response.text,
                retryable=response.status_code >= 500,
                debug=self.debug,
                fetched_at=fetched_at,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise _upstream_error(
                code="UPSTREAM_INVALID_RESPONSE",
                message="数据源返回了非 JSON 响应。",
                provider=provider,
                region=region,
                category=category,
                method=method,
                url=url,
                params=params,
                status_code=response.status_code,
                body=response.text,
                retryable=False,
                debug=self.debug,
                fetched_at=fetched_at,
            ) from exc

        if not isinstance(payload, dict):
            raise _upstream_error(
                code="UPSTREAM_INVALID_RESPONSE",
                message="数据源返回了非预期的 JSON 数据格式。",
                provider=provider,
                region=region,
                category=category,
                method=method,
                url=url,
                params=params,
                status_code=response.status_code,
                body=response.text,
                retryable=False,
                debug=self.debug,
                fetched_at=fetched_at,
            )

        if cache_enabled and self.cache_policy in {"use", "refresh"}:
            current_cache_version = current_cache_version or self._current_cache_version(
                rule,
                required=False,
            )
            cache_version = cache_version_for(rule, current_cache_version)
            if not rule.versioned or cache_version is not None:
                self.cache.set(
                    key,
                    url=url,
                    params=params,
                    payload=payload,
                    fetched_at=fetched_at,
                    status_code=response.status_code,
                    expires_at=cache_expires_at(fetched_at, rule),
                    cache_policy=rule.name,
                    cache_version=cache_version,
                    persist=rule.persist,
                )

        return ProviderResponse(
            payload=payload,
            source=_record_source(
                _source(
                    provider,
                    region,
                    False,
                    fetched_at,
                    category=category,
                    status_code=response.status_code,
                    retcode=payload.get("retcode"),
                )
            ),
            status_code=response.status_code,
            cookies=dict(response.cookies.items()),
        )

    def request_bytes(
        self,
        method: str,
        url: str,
        *,
        provider: str,
        region: str,
        category: str,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        expected_media_types: tuple[str, ...] | None = None,
        cache_url: str | None = None,
        url_resolver: Callable[[], tuple[str, dict[str, object] | None]] | None = None,
    ) -> ProviderBytesResponse:
        method = method.upper()
        cache_identity_url = cache_url or url
        key = cache_key(method, cache_identity_url, params=params)
        rule = cache_rule_for(
            method=method,
            provider=provider,
            category=category,
            response_kind="asset",
        )
        usage = asset_cache_usage(provider=provider, category=category, url=cache_identity_url)
        asset_cache = (
            self._asset_cache(usage)
            if method == "GET" and self.cache_policy != "off" and rule.cacheable
            else None
        )
        current_cache_version: str | None = None
        details = _request_details(provider, region, category, method, cache_identity_url, params)
        if asset_cache is not None:
            with asset_cache.locked(key):
                if self.cache_policy in {"use", "only"}:
                    cached = asset_cache.get(key)
                    if cached is not None:
                        current_cache_version = self._current_cache_version(
                            rule,
                            required=self.cache_policy == "only",
                        )
                    if cached is not None and _cached_asset_is_fresh(
                        cached.metadata,
                        rule,
                        current_cache_version=current_cache_version,
                    ):
                        return ProviderBytesResponse(
                            content=cached.content,
                            media_type=cached.media_type,
                            source=_record_source(
                                _source(
                                    provider,
                                    region,
                                    True,
                                    _metadata_text(cached.metadata, "fetched_at"),
                                    category=category,
                                    status_code=_metadata_status_code(cached.metadata),
                                )
                            ),
                            status_code=_metadata_status_code(cached.metadata),
                        )
                    if cached is not None and _staleness_is_known(rule, current_cache_version):
                        asset_cache.delete(key)
                    if self.cache_policy == "only":
                        raise _cache_miss(
                            provider, region, category, method, cache_identity_url, params
                        )

                if self.cache_policy != "only":
                    request_url, source_extra = _resolved_byte_url(url, url_resolver)
                    return self._request_bytes_uncached(
                        method,
                        request_url,
                        provider=provider,
                        region=region,
                        category=category,
                        params=params,
                        headers=headers,
                        expected_media_types=expected_media_types,
                        asset_cache=asset_cache,
                        asset_key=key,
                        asset_url=cache_identity_url,
                        asset_rule=rule,
                        source_extra=source_extra,
                        asset_cache_version=cache_version_for(
                            rule,
                            current_cache_version
                            or self._current_cache_version(rule, required=False),
                        ),
                    )
        elif self.cache_policy != "only":
            request_url, source_extra = _resolved_byte_url(url, url_resolver)
            return self._request_bytes_uncached(
                method,
                request_url,
                provider=provider,
                region=region,
                category=category,
                params=params,
                headers=headers,
                expected_media_types=expected_media_types,
                asset_cache=None,
                asset_key=None,
                asset_url=cache_identity_url,
                asset_rule=None,
                source_extra=source_extra,
                asset_cache_version=None,
            )

        raise _cache_miss(
            provider, region, category, method, cache_identity_url, params, details=details
        )

    def _request_bytes_uncached(
        self,
        method: str,
        url: str,
        *,
        provider: str,
        region: str,
        category: str,
        params: dict[str, object] | None,
        headers: dict[str, str] | None,
        expected_media_types: tuple[str, ...] | None,
        asset_cache: AssetCache | None,
        asset_key: str | None,
        asset_url: str,
        asset_rule: CacheRule | None,
        source_extra: dict[str, object] | None,
        asset_cache_version: str | None,
    ) -> ProviderBytesResponse:
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.request(method, url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            attempted_at = utc_now()
            if asset_cache is not None and asset_key is not None:
                asset_cache.record_failure(
                    asset_key,
                    url=asset_url,
                    params=params,
                    error_code="NETWORK_TIMEOUT",
                    message="数据源请求超时。",
                    attempted_at=attempted_at,
                )
            raise _network_error(
                code="NETWORK_TIMEOUT",
                message="数据源请求超时。",
                provider=provider,
                region=region,
                category=category,
                method=method,
                url=url,
                params=params,
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            attempted_at = utc_now()
            if asset_cache is not None and asset_key is not None:
                asset_cache.record_failure(
                    asset_key,
                    url=asset_url,
                    params=params,
                    error_code="NETWORK_ERROR",
                    message="数据源请求失败。",
                    attempted_at=attempted_at,
                )
            raise _network_error(
                code="NETWORK_ERROR",
                message="数据源请求失败。",
                provider=provider,
                region=region,
                category=category,
                method=method,
                url=url,
                params=params,
                retryable=True,
            ) from exc

        fetched_at = utc_now()
        if response.status_code >= 400:
            if asset_cache is not None and asset_key is not None:
                asset_cache.record_failure(
                    asset_key,
                    url=asset_url,
                    params=params,
                    error_code="UPSTREAM_HTTP_ERROR",
                    message="数据源返回了 HTTP 错误。",
                    attempted_at=fetched_at,
                    status_code=response.status_code,
                )
            raise _upstream_error(
                code="UPSTREAM_HTTP_ERROR",
                message="数据源返回了 HTTP 错误。",
                provider=provider,
                region=region,
                category=category,
                method=method,
                url=url,
                params=params,
                status_code=response.status_code,
                body=response.text,
                retryable=response.status_code >= 500,
                debug=self.debug,
                fetched_at=fetched_at,
            )

        media_type = (
            response.headers.get("content-type", "application/octet-stream")
            .split(";")[0]
            .strip()
            .lower()
        )
        if expected_media_types and not _media_type_matches(media_type, expected_media_types):
            if asset_cache is not None and asset_key is not None:
                asset_cache.record_failure(
                    asset_key,
                    url=asset_url,
                    params=params,
                    error_code="UPSTREAM_INVALID_RESPONSE",
                    message="数据源返回了非预期的媒体类型。",
                    attempted_at=fetched_at,
                    status_code=response.status_code,
                )
            details = _request_details(provider, region, category, method, url, params)
            details["media_type"] = media_type
            details["expected_media_types"] = list(expected_media_types)
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "数据源返回了非预期的媒体类型。",
                EXIT_UPSTREAM,
                details,
                retryable=False,
                source=_record_source(
                    _source(
                        provider,
                        region,
                        False,
                        fetched_at,
                        category=category,
                        status_code=response.status_code,
                    )
                ),
            )
        if (
            asset_cache is not None
            and asset_key is not None
            and asset_rule is not None
            and (not asset_rule.versioned or asset_cache_version is not None)
        ):
            asset_cache.store_success(
                asset_key,
                url=asset_url,
                params=params,
                media_type=media_type,
                content=response.content,
                status_code=response.status_code,
                fetched_at=fetched_at,
                expires_at=cache_expires_at(fetched_at, asset_rule),
                cache_policy=asset_rule.name,
                cache_version=asset_cache_version,
            )
        return ProviderBytesResponse(
            content=response.content,
            media_type=media_type,
            source=_record_source(
                _source_with_extra(
                    _source(
                        provider,
                        region,
                        False,
                        fetched_at,
                        category=category,
                        status_code=response.status_code,
                    ),
                    source_extra,
                )
            ),
            status_code=response.status_code,
        )

    def _asset_cache(self, usage: str) -> AssetCache:
        if usage not in self._assets:
            self._assets[usage] = AssetCache(self.output_dir, usage=usage)
        return self._assets[usage]

    def _current_cache_version(self, rule: CacheRule, *, required: bool) -> str | None:
        if not rule.versioned:
            return None
        try:
            return self._current_game_version_tag()
        except CliError:
            if required:
                raise
            return None

    def _current_game_version_tag(self) -> str:
        if self.cache is None:
            raise _cache_miss(
                GAME_VERSION_PROVIDER,
                "cn",
                GAME_VERSION_CATEGORY,
                "GET",
                GAME_VERSION_BUILD_URL,
                None,
            )
        method = "GET"
        rule = cache_rule_for(
            method=method,
            provider=GAME_VERSION_PROVIDER,
            category=GAME_VERSION_CATEGORY,
            response_kind="json",
        )
        key = cache_key(method, GAME_VERSION_BUILD_URL)
        if self.cache_policy in {"use", "only"}:
            cached = self.cache.get(key)
            if cached is not None and _cached_json_is_fresh(
                cached,
                rule,
                current_cache_version=None,
            ):
                tag = _game_version_tag(cached.payload)
                if tag is not None:
                    return tag
            if cached is not None:
                self.cache.delete(key)
            if self.cache_policy == "only":
                raise _cache_miss(
                    GAME_VERSION_PROVIDER,
                    "cn",
                    GAME_VERSION_CATEGORY,
                    method,
                    GAME_VERSION_BUILD_URL,
                    None,
                )

        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.request(method, GAME_VERSION_BUILD_URL)
        except httpx.TimeoutException as exc:
            raise _game_version_error(
                "NETWORK_TIMEOUT",
                "Provider request timed out.",
                EXIT_NETWORK,
                method=method,
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise _game_version_error(
                "NETWORK_ERROR",
                "Provider request failed.",
                EXIT_NETWORK,
                method=method,
                retryable=True,
            ) from exc

        fetched_at = utc_now()
        if response.status_code >= 400:
            raise _game_version_error(
                "UPSTREAM_HTTP_ERROR",
                "Provider returned an HTTP error.",
                EXIT_UPSTREAM,
                method=method,
                status_code=response.status_code,
                body=response.text,
                debug=self.debug,
                retryable=response.status_code >= 500,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise _game_version_error(
                "UPSTREAM_INVALID_RESPONSE",
                "Provider returned a non-JSON response.",
                EXIT_UPSTREAM,
                method=method,
                status_code=response.status_code,
                body=response.text,
                debug=self.debug,
                retryable=False,
            ) from exc
        if not isinstance(payload, dict):
            raise _game_version_error(
                "UPSTREAM_INVALID_RESPONSE",
                "Provider returned an unexpected JSON shape.",
                EXIT_UPSTREAM,
                method=method,
                status_code=response.status_code,
                body=response.text,
                debug=self.debug,
                retryable=False,
            )
        tag = _game_version_tag(payload)
        if tag is None:
            raise _game_version_error(
                "UPSTREAM_INVALID_RESPONSE",
                "数据源响应中未包含游戏版本标识。",
                EXIT_UPSTREAM,
                method=method,
                status_code=response.status_code,
                body=response.text,
                debug=self.debug,
                retryable=False,
            )

        if self.cache_policy in {"use", "refresh"}:
            self.cache.set(
                key,
                url=GAME_VERSION_BUILD_URL,
                params=None,
                payload=payload,
                fetched_at=fetched_at,
                status_code=response.status_code,
                expires_at=cache_expires_at(fetched_at, rule),
                cache_policy=rule.name,
                cache_version=None,
            )
        return tag


def raise_for_retcode(
    payload: dict[str, object],
    *,
    provider: str,
    region: str,
    category: str,
    source: dict[str, object],
    debug: bool = False,
) -> None:
    retcode = payload.get("retcode")
    if retcode in (0, "0", None):
        return

    message = str(payload.get("message") or "数据源拒绝了请求。")
    details: dict[str, object] = {
        "provider": provider,
        "region": region,
        "category": category,
        "retcode": retcode,
        "message": message,
    }
    if debug:
        details["payload_keys"] = sorted(str(key) for key in payload)

    if _is_auth_retcode(retcode):
        raise CliError(
            "AUTH_EXPIRED",
            "Cookie 已过期或被数据源拒绝。",
            EXIT_AUTH,
            details,
            retryable=False,
            source=source,
        )

    if _is_verification_retcode(retcode):
        raise CliError(
            "UPSTREAM_VERIFICATION_REQUIRED",
            "数据源在返回此数据前需要进行设备或验证码挑战验证。",
            EXIT_UPSTREAM,
            details,
            retryable=False,
            source=source,
        )

    raise CliError(
        "UPSTREAM_REJECTED",
        "数据源拒绝了请求。",
        EXIT_UPSTREAM,
        details,
        retryable=False,
        source=source,
    )


def _source(
    provider: str,
    region: str,
    cached: bool,
    fetched_at: str | None,
    *,
    category: str | None = None,
    status_code: int | None = None,
    retcode: object = None,
) -> dict[str, object]:
    source: dict[str, object] = {
        "provider": provider,
        "region": region,
        "cached": cached,
        "fetched_at": fetched_at,
    }
    if category is not None:
        source["category"] = category
    if status_code is not None:
        source["status_code"] = status_code
    if retcode is not None:
        source["retcode"] = retcode
    return source


def _record_source(source: dict[str, object]) -> dict[str, object]:
    capture = _SOURCE_CAPTURE.get()
    if capture is not None:
        capture.add(source)
    return source


def _source_with_extra(
    source: dict[str, object],
    extra: dict[str, object] | None,
) -> dict[str, object]:
    if extra:
        source.update(extra)
    return source


def _resolved_byte_url(
    url: str,
    url_resolver: Callable[[], tuple[str, dict[str, object] | None]] | None,
) -> tuple[str, dict[str, object] | None]:
    if url_resolver is None:
        return url, None
    return url_resolver()


def _metadata_text(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if isinstance(value, str):
        return value
    return None


def _metadata_status_code(metadata: dict[str, object]) -> int:
    value = metadata.get("status_code")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 200


def _game_version_tag(payload: dict[str, object]) -> str | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    tag = data.get("tag")
    if not isinstance(tag, str) or not tag.strip():
        return None
    return tag.strip()


def _game_version_error(
    code: str,
    message: str,
    exit_code: int,
    *,
    method: str,
    status_code: int | None = None,
    body: str | None = None,
    debug: bool = False,
    retryable: bool,
) -> CliError:
    details = _request_details(
        GAME_VERSION_PROVIDER,
        "cn",
        GAME_VERSION_CATEGORY,
        method,
        GAME_VERSION_BUILD_URL,
        None,
    )
    if status_code is not None:
        details["status_code"] = status_code
    if debug and body is not None:
        details["body_preview"] = body[:200]
    return CliError(code, message, exit_code, details, retryable=retryable)


def _cached_json_is_fresh(
    cached: CachedResponse,
    rule: CacheRule,
    *,
    current_cache_version: str | None,
) -> bool:
    return cache_is_fresh(
        fetched_at=cached.fetched_at,
        expires_at=cached.expires_at,
        cache_version=cached.cache_version,
        current_cache_version=current_cache_version,
        rule=rule,
        now=utc_now(),
    )


def _cached_asset_is_fresh(
    metadata: dict[str, object],
    rule: CacheRule,
    *,
    current_cache_version: str | None,
) -> bool:
    fetched_at = _metadata_text(metadata, "fetched_at")
    if fetched_at is None:
        return False
    return cache_is_fresh(
        fetched_at=fetched_at,
        expires_at=_metadata_text(metadata, "expires_at"),
        cache_version=_metadata_text(metadata, "cache_version"),
        current_cache_version=current_cache_version,
        rule=rule,
        now=utc_now(),
    )


def _staleness_is_known(rule: CacheRule, current_cache_version: str | None) -> bool:
    return not rule.versioned or current_cache_version is not None


def _media_type_matches(media_type: str, expected_media_types: tuple[str, ...]) -> bool:
    return any(
        media_type.startswith(expected) if expected.endswith("/") else media_type == expected
        for expected in expected_media_types
    )


def _network_error(
    *,
    code: str,
    message: str,
    provider: str,
    region: str,
    category: str,
    method: str,
    url: str,
    params: dict[str, object] | None,
    retryable: bool,
) -> CliError:
    source = _record_source(_source(provider, region, False, None, category=category))
    return CliError(
        code,
        message,
        EXIT_NETWORK,
        _request_details(provider, region, category, method, url, params),
        retryable=retryable,
        source=source,
    )


def _upstream_error(
    *,
    code: str,
    message: str,
    provider: str,
    region: str,
    category: str,
    method: str,
    url: str,
    params: dict[str, object] | None,
    status_code: int,
    body: str,
    retryable: bool,
    debug: bool,
    fetched_at: str | None,
) -> CliError:
    details = _request_details(provider, region, category, method, url, params)
    details["status_code"] = status_code
    if debug:
        details["body_preview"] = body[:200]
    source = _record_source(
        _source(
            provider,
            region,
            False,
            fetched_at,
            category=category,
            status_code=status_code,
        )
    )
    return CliError(
        code,
        message,
        EXIT_UPSTREAM,
        details,
        retryable=retryable,
        source=source,
    )


def _request_details(
    provider: str,
    region: str,
    category: str,
    method: str,
    url: str,
    params: dict[str, object] | None,
) -> dict[str, object]:
    return {
        "provider": provider,
        "region": region,
        "category": category,
        "method": method,
        "url": sanitized_url(url, params=params),
    }


def _cache_miss(
    provider: str,
    region: str,
    category: str,
    method: str,
    url: str,
    params: dict[str, object] | None,
    *,
    details: dict[str, object] | None = None,
) -> CliError:
    return CliError(
        "CACHE_MISS",
        "此请求没有可用的最新缓存数据源响应。",
        EXIT_CACHE,
        details or _request_details(provider, region, category, method, url, params),
    )


def _is_auth_retcode(retcode: Any) -> bool:
    try:
        return int(retcode) in AUTH_RETCODES
    except (TypeError, ValueError):
        return False


def _is_verification_retcode(retcode: Any) -> bool:
    try:
        return int(retcode) in VERIFICATION_RETCODES
    except (TypeError, ValueError):
        return False


def _json_body_content(body: dict[str, object]) -> bytes:
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
