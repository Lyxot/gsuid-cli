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
    generated_at: str | None = None,
) -> dict[str, object]:
    generated_at = generated_at or utc_now()
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
        "source": _source(region=region, fetched_at=generated_at),
        "pagination": None,
    }


def error_envelope(
    *,
    command: str,
    request_id: str,
    duration_ms: int,
    error: CliError,
    region: str,
    warnings: list[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, object]:
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
        "source": _source(region=region, fetched_at=None),
    }


def _source(*, region: str, fetched_at: str | None) -> dict[str, object]:
    return {
        "provider": "local",
        "region": region,
        "cached": False,
        "fetched_at": fetched_at,
    }
