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


def test_qrcode_start_can_render_artifact(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.auth.provider_for_region", _qrcode_provider())

    code, payload = _run_json(
        [
            "--request-id",
            "req-qrcode",
            "--render",
            "image",
            "auth",
            "qrcode",
            "start",
        ]
    )

    assert code == 0
    assert payload["command"] == "auth.qrcode.start"
    assert payload["data"]["ticket"] == "ticket-1"
    assert payload["artifacts"][0]["name"] == "qrcode_login"
    assert payload["artifacts"][0]["media_type"] == "image/png"
    assert (tmp_path / "home" / "artifacts").exists()


def test_qrcode_complete_stores_credentials_without_printing_secrets(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.auth.provider_for_region", _qrcode_provider())

    code, payload = _run_json(
        [
            "auth",
            "qrcode",
            "complete",
            "--uid",
            "100000001",
            "--ticket",
            "ticket-1",
            "--device",
            "device-1",
        ]
    )

    assert code == 0
    assert payload["data"]["stored"] is True
    raw_payload = json.dumps(payload, ensure_ascii=False)
    assert "cookie-secret" not in raw_payload
    assert "stoken-secret" not in raw_payload

    code, payload = _run_json(["auth", "stoken", "test", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["validity_status"] == "available"


def test_qrcode_login_shows_terminal_code_and_stores_credentials(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.auth.provider_for_region", _qrcode_provider())

    code, payload, stderr = _run_json_with_stderr(
        [
            "auth",
            "qrcode",
            "login",
            "--uid",
            "100000001",
            "--poll-interval",
            "0.01",
            "--login-timeout",
            "1",
        ]
    )

    assert code == 0
    assert payload["command"] == "auth.qrcode.login"
    assert payload["data"]["stored"] is True
    assert "Scan this QR code" in stderr
    assert "QR login status: confirmed" in stderr
    assert "█" in stderr

    raw_payload = json.dumps(payload, ensure_ascii=False)
    assert "cookie-secret" not in raw_payload
    assert "stoken-secret" not in raw_payload

    code, payload = _run_json(["auth", "stoken", "test", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["validity_status"] == "available"


def test_redact_secret_never_returns_short_secret() -> None:
    assert redact_secret("short") == "[REDACTED]"
    assert redact_secret("123456789") == "1234...6789"


def _run_json(argv: list[str]) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    assert stderr.getvalue() == ""
    return code, json.loads(stdout.getvalue())


def _run_json_with_stderr(argv: list[str]) -> tuple[int, dict[str, object], str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    return code, json.loads(stdout.getvalue()), stderr.getvalue()


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


def _qrcode_provider():
    class FakeProvider:
        def __init__(self, _http_client) -> None:
            self.poll_count = 0

        def create_qrcode_session(self, *, region: str) -> CommandResult:
            return CommandResult(
                data={
                    "app_id": "2",
                    "ticket": "ticket-1",
                    "device": "device-1",
                    "url": "https://example.test/login?ticket=ticket-1",
                    "status": "created",
                },
                source={
                    "provider": "mys",
                    "region": region,
                    "cached": False,
                    "fetched_at": "2026-04-29T10:30:00Z",
                },
            )

        def poll_qrcode_session(
            self,
            *,
            app_id: str,
            ticket: str,
            device: str,
            region: str,
        ) -> CommandResult:
            self.poll_count += 1
            status = ("init", "scanned", "confirmed")[min(self.poll_count - 1, 2)]
            return CommandResult(
                data={
                    "app_id": app_id,
                    "ticket": ticket,
                    "device": device,
                    "status": status,
                    "account_id": "123456" if status == "confirmed" else None,
                    "confirmed": status == "confirmed",
                },
                source={
                    "provider": "mys",
                    "region": region,
                    "cached": False,
                    "fetched_at": "2026-04-29T10:30:00Z",
                },
            )

        def complete_qrcode_login(
            self,
            *,
            app_id: str,
            ticket: str,
            device: str,
            uid: str,
            region: str,
        ) -> CommandResult:
            return CommandResult(
                data={
                    "uid": uid,
                    "account_id": "123456",
                    "status": "stored",
                    "credential_types": ["cookie", "stoken"],
                    "cookie": "account_id=123456;cookie_token=cookie-secret",
                    "stoken": "stuid=123456;stoken=stoken-secret;mid=mid-secret",
                    "redacted": {
                        "cookie": "acco...cret",
                        "stoken": "stui...cret",
                    },
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
