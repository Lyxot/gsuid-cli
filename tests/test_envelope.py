from __future__ import annotations

from gsuid_cli.core.envelope import error_envelope, success_envelope
from gsuid_cli.core.errors import CliError


def test_success_envelope_shape() -> None:
    payload = success_envelope(
        command="meta.version",
        request_id="req-1",
        duration_ms=12,
        data={"version": "0.1.0"},
        region="cn",
        generated_at="2026-04-29T10:30:00Z",
    )

    assert payload == {
        "ok": True,
        "schema": "gsuid.cli/v1",
        "command": "meta.version",
        "request_id": "req-1",
        "generated_at": "2026-04-29T10:30:00Z",
        "duration_ms": 12,
        "warnings": [],
        "data": {"version": "0.1.0"},
        "artifacts": [],
        "source": {
            "provider": "local",
            "region": "cn",
            "cached": False,
            "fetched_at": "2026-04-29T10:30:00Z",
        },
        "pagination": None,
    }


def test_error_envelope_shape() -> None:
    error = CliError(
        "INVALID_ARGUMENT",
        "missing command",
        1,
        {"argument": "command"},
        retryable=False,
    )
    payload = error_envelope(
        command="unknown",
        request_id="req-2",
        duration_ms=3,
        error=error,
        region="cn",
        generated_at="2026-04-29T10:30:00Z",
    )

    assert payload["ok"] is False
    assert payload["schema"] == "gsuid.cli/v1"
    assert payload["error"] == {
        "code": "INVALID_ARGUMENT",
        "message": "missing command",
        "details": {"argument": "command"},
        "retryable": False,
    }
    assert payload["source"]["fetched_at"] is None
