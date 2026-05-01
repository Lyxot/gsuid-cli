from __future__ import annotations

from gsuid_cli.core.errors import CliError
from gsuid_cli.core.time import utc_now

SCHEMA = "gsuid.cli/v1"


def success_envelope(
    *,
    command: str,
    request_id: str,
    duration_ms: int,
    data: dict[str, object],
    region: str,
    warnings: list[str] | None = None,
    artifacts: list[dict[str, object]] | None = None,
    source: dict[str, object] | None = None,
    sources: list[dict[str, object]] | None = None,
    pagination: dict[str, object] | None = None,
    generated_at: str | None = None,
) -> dict[str, object]:
    generated_at = generated_at or utc_now()
    primary_source = source or _primary_source(
        sources,
        fallback=_source(region=region, fetched_at=generated_at),
    )
    return {
        "ok": True,
        "schema": SCHEMA,
        "command": command,
        "request_id": request_id,
        "generated_at": generated_at,
        "duration_ms": duration_ms,
        "warnings": warnings or [],
        "data": data,
        "artifacts": artifacts or [],
        "sources": _sources(sources, primary_source),
        "pagination": pagination,
    }


def error_envelope(
    *,
    command: str,
    request_id: str,
    duration_ms: int,
    error: CliError,
    region: str,
    warnings: list[str] | None = None,
    sources: list[dict[str, object]] | None = None,
    generated_at: str | None = None,
) -> dict[str, object]:
    primary_source = error.source or _primary_source(
        sources,
        fallback=_source(region=region, fetched_at=None),
    )
    return {
        "ok": False,
        "schema": SCHEMA,
        "command": command,
        "request_id": request_id,
        "generated_at": generated_at or utc_now(),
        "duration_ms": duration_ms,
        "warnings": warnings or [],
        "error": {
            "code": error.code,
            "message": error.message,
            "details": error.details,
            "retryable": error.retryable,
        },
        "artifacts": [],
        "sources": _sources(sources, primary_source),
    }


def _source(*, region: str, fetched_at: str | None) -> dict[str, object]:
    return {
        "provider": "local",
        "region": region,
        "cached": False,
        "fetched_at": fetched_at,
    }


def _primary_source(
    sources: list[dict[str, object]] | None,
    *,
    fallback: dict[str, object],
) -> dict[str, object]:
    return sources[0] if sources else fallback


def _sources(
    sources: list[dict[str, object]] | None,
    primary_source: dict[str, object],
) -> list[dict[str, object]]:
    if not sources:
        return [primary_source]
    seen: set[tuple[tuple[str, str], ...]] = set()
    result: list[dict[str, object]] = []
    for source in [primary_source, *sources]:
        key = tuple(sorted((str(k), str(v)) for k, v in source.items()))
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result
