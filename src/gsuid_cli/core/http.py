from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from gsuid_cli.core.cache import AssetCache, HttpCache, cache_key, sanitized_url
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


@dataclass(frozen=True)
class ProviderResponse:
    payload: dict[str, object]
    source: dict[str, object]
    status_code: int


@dataclass(frozen=True)
class ProviderBytesResponse:
    content: bytes
    media_type: str
    source: dict[str, object]
    status_code: int


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
        self._assets: AssetCache | None = None
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
        if method == "GET" and self.cache is not None and self.cache_policy in {"use", "only"}:
            cached = self.cache.get(key) if self.cache_policy == "use" else self.cache.require(key)
            if cached is not None:
                return ProviderResponse(
                    payload=cached.payload,
                    source=_source(provider, region, True, cached.fetched_at),
                    status_code=cached.status_code,
                )

        if self.cache_policy == "only":
            raise CliError(
                "CACHE_MISS",
                "No in-memory provider response is available for this request.",
                EXIT_CACHE,
                _request_details(provider, region, category, method, url, params),
            )

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
                message="Provider request timed out.",
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
                message="Provider request failed.",
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
                message="Provider returned an HTTP error.",
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
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise _upstream_error(
                code="UPSTREAM_INVALID_RESPONSE",
                message="Provider returned a non-JSON response.",
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
            ) from exc

        if not isinstance(payload, dict):
            raise _upstream_error(
                code="UPSTREAM_INVALID_RESPONSE",
                message="Provider returned an unexpected JSON shape.",
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
            )

        if method == "GET" and self.cache is not None and self.cache_policy in {"use", "refresh"}:
            self.cache.set(
                key,
                payload=payload,
                fetched_at=fetched_at,
                status_code=response.status_code,
            )

        return ProviderResponse(
            payload=payload,
            source=_source(provider, region, False, fetched_at),
            status_code=response.status_code,
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
    ) -> ProviderBytesResponse:
        method = method.upper()
        key = cache_key(method, url, params=params)
        asset_cache = (
            self._asset_cache() if method == "GET" and self.cache_policy != "off" else None
        )
        details = _request_details(provider, region, category, method, url, params)
        if asset_cache is not None:
            with asset_cache.locked(key):
                if self.cache_policy in {"use", "only"}:
                    cached = (
                        asset_cache.get(key)
                        if self.cache_policy == "use"
                        else asset_cache.require(key, details=details)
                    )
                    if cached is not None:
                        return ProviderBytesResponse(
                            content=cached.content,
                            media_type=cached.media_type,
                            source=_source(
                                provider,
                                region,
                                True,
                                _metadata_text(cached.metadata, "fetched_at"),
                            ),
                            status_code=_metadata_status_code(cached.metadata),
                        )

                if self.cache_policy == "only":
                    raise CliError(
                        "CACHE_MISS",
                        "No cached asset is available for this request.",
                        EXIT_CACHE,
                        details,
                    )

                return self._request_bytes_uncached(
                    method,
                    url,
                    provider=provider,
                    region=region,
                    category=category,
                    params=params,
                    headers=headers,
                    expected_media_types=expected_media_types,
                    asset_cache=asset_cache,
                    asset_key=key,
                )

        if self.cache_policy == "only":
            raise CliError(
                "CACHE_MISS",
                "No cached asset is available for this request.",
                EXIT_CACHE,
                details,
            )
        return self._request_bytes_uncached(
            method,
            url,
            provider=provider,
            region=region,
            category=category,
            params=params,
            headers=headers,
            expected_media_types=expected_media_types,
            asset_cache=None,
            asset_key=None,
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
    ) -> ProviderBytesResponse:
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.request(method, url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            attempted_at = utc_now()
            if asset_cache is not None and asset_key is not None:
                asset_cache.record_failure(
                    asset_key,
                    url=url,
                    params=params,
                    error_code="NETWORK_TIMEOUT",
                    message="Provider request timed out.",
                    attempted_at=attempted_at,
                )
            raise _network_error(
                code="NETWORK_TIMEOUT",
                message="Provider request timed out.",
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
                    url=url,
                    params=params,
                    error_code="NETWORK_ERROR",
                    message="Provider request failed.",
                    attempted_at=attempted_at,
                )
            raise _network_error(
                code="NETWORK_ERROR",
                message="Provider request failed.",
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
                    url=url,
                    params=params,
                    error_code="UPSTREAM_HTTP_ERROR",
                    message="Provider returned an HTTP error.",
                    attempted_at=fetched_at,
                    status_code=response.status_code,
                )
            raise _upstream_error(
                code="UPSTREAM_HTTP_ERROR",
                message="Provider returned an HTTP error.",
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
                    url=url,
                    params=params,
                    error_code="UPSTREAM_INVALID_RESPONSE",
                    message="Provider returned an unexpected media type.",
                    attempted_at=fetched_at,
                    status_code=response.status_code,
                )
            details = _request_details(provider, region, category, method, url, params)
            details["media_type"] = media_type
            details["expected_media_types"] = list(expected_media_types)
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "Provider returned an unexpected media type.",
                EXIT_UPSTREAM,
                details,
                retryable=False,
                source=_source(provider, region, False, fetched_at),
            )
        if asset_cache is not None and asset_key is not None:
            asset_cache.store_success(
                asset_key,
                url=url,
                params=params,
                media_type=media_type,
                content=response.content,
                status_code=response.status_code,
                fetched_at=fetched_at,
            )
        return ProviderBytesResponse(
            content=response.content,
            media_type=media_type,
            source=_source(provider, region, False, fetched_at),
            status_code=response.status_code,
        )

    def _asset_cache(self) -> AssetCache:
        if self._assets is None:
            self._assets = AssetCache(self.output_dir)
        return self._assets


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

    message = str(payload.get("message") or "Provider rejected the request.")
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
            "The cookie is expired or rejected by the provider.",
            EXIT_AUTH,
            details,
            retryable=False,
            source=source,
        )

    if _is_verification_retcode(retcode):
        raise CliError(
            "UPSTREAM_VERIFICATION_REQUIRED",
            "Provider requires device or challenge verification before returning this data.",
            EXIT_UPSTREAM,
            details,
            retryable=False,
            source=source,
        )

    raise CliError(
        "UPSTREAM_REJECTED",
        "Provider rejected the request.",
        EXIT_UPSTREAM,
        details,
        retryable=False,
        source=source,
    )


def _source(provider: str, region: str, cached: bool, fetched_at: str | None) -> dict[str, object]:
    return {
        "provider": provider,
        "region": region,
        "cached": cached,
        "fetched_at": fetched_at,
    }


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
    return CliError(
        code,
        message,
        EXIT_NETWORK,
        _request_details(provider, region, category, method, url, params),
        retryable=retryable,
        source=_source(provider, region, False, None),
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
) -> CliError:
    details = _request_details(provider, region, category, method, url, params)
    details["status_code"] = status_code
    if debug:
        details["body_preview"] = body[:200]
    return CliError(
        code,
        message,
        EXIT_UPSTREAM,
        details,
        retryable=retryable,
        source=_source(provider, region, False, None),
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
