from __future__ import annotations

import io
import json

from gsuid_cli.cli import run
from gsuid_cli.core.secrets import redact_secret


def test_cookie_keyring_lifecycle(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    secret = "ltoken=abcdef123456; cookie_token=qwerty9876"

    code, payload = _run_json(["auth", "cookie", "set", "--uid", "100000001", "--cookie", secret])

    assert code == 0
    assert payload["data"]["credential_type"] == "cookie"
    assert payload["data"]["source"] == "keyring"
    assert payload["data"]["redacted"] != secret

    code, payload = _run_json(["auth", "cookie", "test", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["validity_status"] == "available"
    assert payload["data"]["source"] == "keyring"

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
