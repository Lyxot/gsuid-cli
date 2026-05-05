from __future__ import annotations

import io
import json
from pathlib import Path

from helpers import run_json as _run_json
from helpers import run_json_with_stderr as _run_json_with_stderr

from gsuid_cli.cli import run
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.secrets import SecretStore, redact_secret


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
    assert payload["sources"][0]["provider"] == "mys"

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
    assert "请使用米游社APP扫码登录" in stderr
    assert "QR login status: confirmed" in stderr
    assert "█" in stderr

    raw_payload = json.dumps(payload, ensure_ascii=False)
    assert "cookie-secret" not in raw_payload
    assert "stoken-secret" not in raw_payload

    code, payload = _run_json(["auth", "stoken", "test", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["validity_status"] == "available"


def test_qrcode_login_render_image_artifact(monkeypatch, tmp_path) -> None:
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
            "--render",
            "image",
        ]
    )

    assert code == 0
    assert payload["data"]["render"] == "auth/qrcode/login"
    assert "请使用米游社APP扫码登录" in stderr
    assert "二维码图片已保存至:" in stderr
    artifact = payload["artifacts"][0]
    assert artifact["kind"] == "image"
    assert artifact["media_type"] == "image/png"
    assert Path(str(artifact["path"])).exists()
    raw_payload = json.dumps(payload, ensure_ascii=False)
    assert "cookie-secret" not in raw_payload
    assert "stoken-secret" not in raw_payload


def test_qrcode_login_render_image_quiet_prints_image_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.auth.provider_for_region", _qrcode_provider())

    code, payload, stderr = _run_json_with_stderr(
        [
            "--quiet",
            "auth",
            "qrcode",
            "login",
            "--uid",
            "100000001",
            "--poll-interval",
            "0.01",
            "--login-timeout",
            "1",
            "--render",
            "image",
        ]
    )

    assert code == 0
    assert payload["data"]["render"] == "auth/qrcode/login"
    assert "二维码图片已保存至:" in stderr
    assert "█" not in stderr
    artifact = payload["artifacts"][0]
    assert artifact["kind"] == "image"
    assert Path(str(artifact["path"])).exists()


def test_device_set_binds_device_without_printing_raw_values(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.auth.provider_for_region", _device_provider())
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(
        [
            "auth",
            "device",
            "set",
            "--uid",
            "100000001",
            "--device-json",
            json.dumps({"fp": "fp-secret", "device_id": "device-secret"}),
        ]
    )

    assert code == 0
    assert payload["command"] == "auth.device.set"
    assert payload["data"]["stored"] is True
    raw_payload = json.dumps(payload, ensure_ascii=False)
    assert "fp-secret" not in raw_payload
    assert "device-secret" not in raw_payload

    code, account = _run_json(["account", "show", "--uid", "100000001"])
    assert code == 0
    assert account["data"]["account"]["has_device"] is True


def test_device_set_test_delete_lifecycle(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.auth.provider_for_region", _device_provider())
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")
    payload = json.dumps(
        {
            "fp": "fp-secret",
            "device_id": "device-secret",
            "device_info": "OnePlus/PHK110/OP5913L1",
        }
    )

    code, result = _run_json(
        ["auth", "device", "set", "--uid", "100000001", "--device-json", payload]
    )

    assert code == 0
    assert result["command"] == "auth.device.set"
    assert result["data"]["stored"] is True
    assert "fp-secret" not in json.dumps(result, ensure_ascii=False)

    code, result = _run_json(["auth", "device", "test", "--uid", "100000001"])

    assert code == 0
    assert result["command"] == "auth.device.test"
    assert result["data"]["validity_status"] == "available"
    assert result["data"]["device"]["brand"] == "OnePlus"
    assert "device-secret" not in json.dumps(result, ensure_ascii=False)

    code, result = _run_json(["auth", "device", "delete", "--uid", "100000001"])

    assert code == 0
    assert result["command"] == "auth.device.delete"
    assert result["data"]["deleted"] is True

    code, result = _run_json(["auth", "device", "test", "--uid", "100000001"])

    assert code == 2
    assert result["error"]["code"] == "AUTH_REQUIRED"


def test_gacha_url_auth_commands_fully_redact_url(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    secret = "https://example.test/getGachaLog?authkey=expired-secret"

    code, payload = _run_json(["auth", "gacha-url", "set", "--uid", "100000001", "--url", secret])

    assert code == 0
    raw = json.dumps(payload, ensure_ascii=False)
    assert payload["data"]["redacted"] == "[REDACTED_URL]"
    assert "expired-secret" not in raw
    assert "cret" not in raw

    code, payload = _run_json(["auth", "gacha-url", "test", "--uid", "100000001"])

    assert code == 0
    raw = json.dumps(payload, ensure_ascii=False)
    assert payload["data"]["redacted"] == "[REDACTED_URL]"
    assert "expired-secret" not in raw
    assert "cret" not in raw


def test_auth_credential_render_text_plain_hides_secret(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    secret = "https://example.test/getGachaLog?authkey=expired-secret"

    code, stdout, stderr = _run_plain(
        [
            "auth",
            "gacha-url",
            "set",
            "--uid",
            "100000001",
            "--url",
            secret,
            "--render",
            "text",
            "--format",
            "plain",
        ]
    )

    assert code == 0
    assert stderr == ""
    assert "认证凭据 - 祈愿链接" in stdout
    assert "状态: 已保存" in stdout
    assert "内容: 已隐藏" in stdout
    assert "expired-secret" not in stdout
    assert "authkey" not in stdout


def test_auth_qrcode_render_text_plain_hides_session_values(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.auth.provider_for_region", _qrcode_provider())

    code, stdout, stderr = _run_plain(
        ["auth", "qrcode", "start", "--render", "text", "--format", "plain"]
    )

    assert code == 0
    assert stderr == ""
    assert "扫码登录会话" in stdout
    assert "请使用米游社APP扫码登录" in stdout
    assert (
        "请在点击确认登录后立即执行: "
        "gsuid auth qrcode poll --app-id 2 --ticket ticket-1 --device device-1"
    ) in stdout
    assert "█" in stdout
    assert "状态: 已创建" in stdout
    assert "登录链接: 已隐藏" in stdout
    assert "会话凭据: 已隐藏" in stdout
    assert "https://example.test" not in stdout


def test_auth_qrcode_start_plain_default_prints_terminal_qr(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.auth.provider_for_region", _qrcode_provider())

    code, stdout, stderr = _run_plain(["auth", "qrcode", "start", "--format", "plain"])

    assert code == 0
    assert stderr == ""
    assert "请使用米游社APP扫码登录" in stdout
    assert (
        "请在点击确认登录后立即执行: "
        "gsuid auth qrcode poll --app-id 2 --ticket ticket-1 --device device-1"
    ) in stdout
    assert "█" in stdout
    assert "https://example.test" not in stdout


def test_auth_qrcode_start_render_text_image_plain_prints_prompt_and_path(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.auth.provider_for_region", _qrcode_provider())

    code, stdout, stderr = _run_plain(
        [
            "auth",
            "qrcode",
            "start",
            "--render",
            "text",
            "--render",
            "image",
            "--format",
            "plain",
        ]
    )

    assert code == 0
    assert stderr == ""
    assert "请使用米游社APP扫码登录" in stdout
    assert "gsuid auth qrcode poll --app-id 2 --ticket ticket-1 --device device-1" in stdout
    assert "https://example.test" not in stdout
    image_line = next(line for line in stdout.splitlines() if line.startswith("图片已保存至: "))
    assert Path(image_line.split(": ", 1)[1]).exists()


def test_auth_qrcode_start_plain_data_image_does_not_dump_session_values(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.auth.provider_for_region", _qrcode_provider())

    code, stdout, stderr = _run_plain(
        [
            "auth",
            "qrcode",
            "start",
            "--render",
            "data",
            "--render",
            "image",
            "--format",
            "plain",
        ]
    )

    assert code == 0
    assert stderr == ""
    assert "请使用米游社APP扫码登录" in stdout
    assert (
        "请在点击确认登录后立即执行: "
        "gsuid auth qrcode poll --app-id 2 --ticket ticket-1 --device device-1"
    ) in stdout
    assert "图片已保存至:" in stdout
    assert "https://example.test" not in stdout


def test_auth_qrcode_start_render_image_artifact(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.auth.provider_for_region", _qrcode_provider())

    code, payload = _run_json(["auth", "qrcode", "start", "--render", "image"])

    assert code == 0
    assert payload["data"]["render"] == "auth/qrcode/start"
    artifact = payload["artifacts"][0]
    assert artifact["kind"] == "image"
    assert artifact["media_type"] == "image/png"
    assert Path(str(artifact["path"])).exists()


def test_auth_qrcode_complete_text_artifact_hides_credentials(monkeypatch, tmp_path) -> None:
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
            "--render",
            "text",
        ]
    )

    assert code == 0
    assert payload["data"]["render"] == "auth/qrcode/complete-text"
    text = _artifact_text(payload)
    assert "扫码登录完成" in text
    assert "已保存凭据: Cookie、Stoken" in text
    assert "cookie-secret" not in text
    assert "stoken-secret" not in text
    assert "ticket-1" not in text
    assert "device-1" not in text


def test_redact_secret_never_returns_short_secret() -> None:
    assert redact_secret("short") == "[REDACTED]"
    assert redact_secret("123456789") == "1234...6789"


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


def _device_provider():
    class FakeProvider:
        def __init__(self, _http_client) -> None:
            pass

        def device_login(
            self,
            *,
            uid: str,
            cookie: str,
            region: str,
            credential_source: str,
            storage_backend: str | None,
            device_payload: dict[str, object],
        ) -> CommandResult:
            assert uid == "100000001"
            assert cookie == "account_id=1;cookie_token=secret"
            assert device_payload["fp"] == "fp-secret"
            return CommandResult(
                data={
                    "uid": uid,
                    "account_id": "1",
                    "status": "bound",
                    "credential_source": credential_source,
                    "credential_storage_backend": storage_backend,
                    "device_id": "device-secret",
                    "device_fp": "fp-secret",
                    "device_info": "OnePlus/PHK110/OP5913L1",
                    "device": {"brand": "OnePlus", "model": "PHK110"},
                    "generated_fp": False,
                    "redacted": {
                        "device_id": "devi...cret",
                        "device_fp": "fp-s...cret",
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


def _run_plain(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    return code, stdout.getvalue(), stderr.getvalue()


def _artifact_text(payload: dict[str, object]) -> str:
    artifact = payload["artifacts"][0]
    assert isinstance(artifact, dict)
    return open(str(artifact["path"]), encoding="utf-8").read()
