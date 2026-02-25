from __future__ import annotations

import io
import json

from gsuid_cli.cli import run
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.secrets import redact_secret


def test_cookie_keyring_lifecycle(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.auth.provider_for_region", _provider("valid"))
    secret = "ltoken=abcdef123456; cookie_token=qwerty9876"

    code, payload = _run_json(["auth", "cookie", "set", "--uid", "100000001", "--cookie", secret])

    assert code == 0
    assert payload["data"]["credential_type"] == "cookie"
    assert payload["data"]["source"] == "keyring"
    assert payload["data"]["redacted"] != secret

    code, payload = _run_json(["auth", "cookie", "test", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["validity_status"] == "valid"
    assert payload["data"]["source"] == "keyring"
    assert payload["source"]["provider"] == "mys"

    code, payload = _run_json(["account", "add", "--uid", "100000001"])
    assert code == 0
    assert payload["data"]["account"]["has_cookie"] is True

    code, payload = _run_json(["auth", "cookie", "delete", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["deleted"] is True

    code, payload = _run_json(["auth", "cookie", "test", "--uid", "100000001"])

    assert code == 2
    assert payload["command"] == "auth.cookie.test"
    assert payload["error"]["code"] == "AUTH_REQUIRED"


def test_env_cookie_takes_priority_without_stored_secret(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("GSUID_COOKIE", "cookie_token=from-env")
    monkeypatch.setattr("gsuid_cli.commands.auth.provider_for_region", _provider("valid"))

    code, payload = _run_json(["auth", "cookie", "test", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["source"] == "environment"
    assert payload["data"]["storage_backend"] is None


def test_redact_secret_never_returns_short_secret() -> None:
    assert redact_secret("short") == "[REDACTED]"
    assert redact_secret("123456789") == "1234...6789"


def _run_json(argv: list[str]) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    assert stderr.getvalue() == ""
    return code, json.loads(stdout.getvalue())


def _provider(status: str):
    class FakeProvider:
        def __init__(self, _http_client) -> None:
            pass

        def validate_cookie(
            self,
            *,
            uid: str,
            cookie: str,
            region: str,
            credential_source: str,
            storage_backend: str | None,
        ) -> CommandResult:
            return CommandResult(
                data={
                    "uid": uid,
                    "credential_type": "cookie",
                    "source": credential_source,
                    "storage_backend": storage_backend,
                    "validity_status": status,
                    "redacted": redact_secret(cookie),
                    "provider_response": {"retcode": 0, "message": "OK"},
                },
                source={
                    "provider": "mys",
                    "region": region,
                    "cached": False,
                    "fetched_at": "2026-04-29T10:30:00Z",
                },
            )

    def provider_for_region(_region: str, http_client) -> FakeProvider:
        return FakeProvider(http_client)

    return provider_for_region
