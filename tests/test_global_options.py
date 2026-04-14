from __future__ import annotations

import io
import json

from gsuid_cli.cli import run
from gsuid_cli.core.models import CommandResult


def test_pretty_json_and_request_id_work_after_command_tokens() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(
        ["meta", "version", "--request-id=req-pretty", "--format=pretty-json"],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert stderr.getvalue() == ""
    raw = stdout.getvalue()
    assert raw.startswith("{\n")
    assert '\n  "ok": true' in raw
    payload = json.loads(raw)
    assert payload["request_id"] == "req-pretty"
    assert payload["command"] == "meta.version"


def test_empty_cli_shows_root_help() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run([], stdout=stdout, stderr=stderr)

    assert code == 0
    assert stderr.getvalue() == ""
    assert "usage: gsuid" in stdout.getvalue()
    assert "<group>" in stdout.getvalue()


def test_group_only_cli_shows_group_help() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(["meta"], stdout=stdout, stderr=stderr)

    assert code == 0
    assert stderr.getvalue() == ""
    assert "usage: gsuid meta" in stdout.getvalue()
    assert "capabilities" in stdout.getvalue()


def test_invalid_global_format_still_returns_json_error() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(["--format", "uigf-v4"], stdout=stdout, stderr=stderr)

    assert code == 1
    assert stderr.getvalue() == ""
    payload = json.loads(stdout.getvalue())
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_group_only_with_invalid_global_value_returns_json_error() -> None:
    code, payload, stderr = _run_json(["meta", "--region", "bad"])

    assert code == 1
    assert stderr == ""
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_group_only_with_invalid_timeout_returns_json_error() -> None:
    code, payload, stderr = _run_json(["meta", "--timeout", "0"])

    assert code == 1
    assert stderr == ""
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_output_dir_works_between_group_and_command(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    output = tmp_path / "artifacts"

    code, payload, stderr = _run_json(
        ["meta", "--request-id", "req-paths", "paths", "--output-dir", str(output)]
    )

    assert code == 0
    assert stderr == ""
    assert payload["request_id"] == "req-paths"
    assert payload["data"]["artifacts"] == str(output.resolve())


def test_profile_and_uid_work_after_command_tokens(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    code, _payload, _stderr = _run_json(["profile", "init", "--name", "alt"])
    assert code == 0
    code, _payload, _stderr = _run_json(
        ["account", "add", "--uid", "100000001", "--profile", "alt", "--default"]
    )
    assert code == 0

    code, payload, stderr = _run_json(["player", "inventory", "--profile", "alt"])

    assert code == 0
    assert stderr == ""
    assert payload["data"]["uid"] == "100000001"


def test_cache_timeout_region_and_debug_reach_provider(monkeypatch) -> None:
    class FakePublicDataProvider:
        def __init__(self, http_client):
            self.http_client = http_client

        def wiki_lookup(self, *, kind: str, query: str) -> CommandResult:
            return CommandResult(
                data={
                    "kind": kind,
                    "query": query,
                    "timeout": self.http_client.timeout,
                    "cache_policy": self.http_client.cache_policy,
                    "debug": self.http_client.debug,
                }
            )

    monkeypatch.setattr("gsuid_cli.commands.public_data.PublicDataProvider", FakePublicDataProvider)

    code, payload, stderr = _run_json(
        [
            "wiki",
            "character",
            "--name",
            "Amber",
            "--cache",
            "off",
            "--timeout",
            "7",
            "--debug",
            "--region",
            "cn",
        ]
    )

    assert code == 0
    assert stderr == ""
    assert payload["source"]["region"] == "cn"
    assert payload["data"]["timeout"] == 7
    assert payload["data"]["cache_policy"] == "off"
    assert payload["data"]["debug"] is True


def test_quiet_suppresses_interactive_qrcode_logs(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    class FakeQrProvider:
        def create_qrcode_session(self, *, region: str) -> CommandResult:
            return CommandResult(
                data={
                    "app_id": "2",
                    "ticket": "ticket",
                    "device": "device",
                    "url": "https://example.test/qr",
                },
                source=_source(region),
            )

        def poll_qrcode_session(
            self,
            *,
            app_id: str,
            ticket: str,
            device: str,
            region: str,
        ) -> CommandResult:
            return CommandResult(
                data={"app_id": app_id, "ticket": ticket, "device": device, "status": "confirmed"},
                source=_source(region),
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
                    "account_id": "account",
                    "status": "complete",
                    "credential_types": ["cookie", "stoken"],
                    "redacted": {"cookie": "cook...", "stoken": "stok..."},
                    "cookie": "account_id=account;cookie_token=secret",
                    "stoken": "stuid=account;stoken=secret",
                    "app_id": app_id,
                    "ticket": ticket,
                    "device": device,
                },
                source=_source(region),
            )

    monkeypatch.setattr(
        "gsuid_cli.commands.auth.provider_for_region",
        lambda _region, _http_client: FakeQrProvider(),
    )

    code, payload, stderr = _run_json(
        [
            "auth",
            "qrcode",
            "login",
            "--uid",
            "100000001",
            "--quiet",
            "--poll-interval",
            "0.01",
            "--login-timeout",
            "1",
        ]
    )

    assert code == 0
    assert stderr == ""
    assert payload["data"]["uid"] == "100000001"
    assert payload["data"]["stored"] is True


def _source(region: str) -> dict[str, object]:
    return {
        "provider": "mys",
        "region": region,
        "cached": False,
        "fetched_at": "2026-04-29T00:00:00Z",
    }


def _run_json(argv: list[str]) -> tuple[int, dict[str, object], str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    return code, json.loads(stdout.getvalue()), stderr.getvalue()
