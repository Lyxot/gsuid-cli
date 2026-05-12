from __future__ import annotations

import io
import json
from pathlib import Path

from helpers import UUIDV7_RE, run_json_with_stderr as _run_json

from gsuid_cli.cli import _write_payload, run
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


def test_default_render_data_shows_data_and_sources() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(["meta", "version", "--request-id=req-compact"], stdout=stdout, stderr=stderr)

    assert code == 0
    assert stderr.getvalue() == ""
    payload = json.loads(stdout.getvalue())
    assert payload["ok"] is True
    assert payload["command"] == "meta.version"
    assert payload["data"]["package"] == "gsuid-cli"
    assert payload["sources"][0]["provider"] == "local"


def test_non_data_render_hides_data_and_sources() -> None:
    for render in ("image", "text"):
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["meta", "version", "--request-id=req-compact", f"--render={render}"],
            stdout=stdout,
            stderr=stderr,
        )

        assert code == 0
        assert stderr.getvalue() == ""
        payload = json.loads(stdout.getvalue())
        assert payload["ok"] is True
        assert payload["command"] == "meta.version"
        assert "data" not in payload
        assert "sources" not in payload


def test_render_all_shows_data_and_sources() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(["meta", "version", "--render=all"], stdout=stdout, stderr=stderr)

    assert code == 0
    assert stderr.getvalue() == ""
    payload = json.loads(stdout.getvalue())
    assert payload["data"]["package"] == "gsuid-cli"
    assert payload["sources"][0]["provider"] == "local"


def test_repeated_render_values_can_include_data(tmp_path) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(
        [
            "--output-dir",
            str(tmp_path),
            "--render",
            "image",
            "--render",
            "data",
            "meta",
            "version",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert stderr.getvalue() == ""
    payload = json.loads(stdout.getvalue())
    assert payload["data"]["package"] == "gsuid-cli"
    assert payload["sources"][0]["provider"] == "local"
    assert list(tmp_path.glob("*/*/debug-envelope.json")) == []


def test_debug_restores_data_sources_and_writes_debug_artifact(tmp_path) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(
        [
            "--debug",
            "--output-dir",
            str(tmp_path),
            "--request-id=req-debug",
            "meta",
            "version",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert stderr.getvalue() == ""
    payload = json.loads(stdout.getvalue())
    assert payload["data"]["package"] == "gsuid-cli"
    assert payload["sources"][0]["provider"] == "local"
    debug_artifact = next(a for a in payload["artifacts"] if a["kind"] == "debug")
    assert debug_artifact["kind"] == "debug"
    debug_payload = json.loads(Path(debug_artifact["path"]).read_text(encoding="utf-8"))
    assert debug_payload["data"]["package"] == "gsuid-cli"
    assert debug_payload["sources"][0]["provider"] == "local"


def test_plain_format_prints_direct_result_data() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(["meta", "version", "--format=plain", "--render=data"], stdout=stdout, stderr=stderr)

    assert code == 0
    assert stderr.getvalue() == ""
    payload = json.loads(stdout.getvalue())
    assert payload["package"] == "gsuid-cli"
    assert "ok" not in payload


def test_plain_format_ignores_non_render_text_artifacts(tmp_path) -> None:
    artifact_path = tmp_path / "debug.txt"
    artifact_path.write_text("debug details", encoding="utf-8")
    stdout = io.StringIO()
    stderr = io.StringIO()

    _write_payload(
        {
            "ok": True,
            "warnings": [],
            "data": {"package": "gsuid-cli"},
            "artifacts": [
                {
                    "kind": "text",
                    "name": "debug-envelope",
                    "path": str(artifact_path),
                }
            ],
        },
        "plain",
        stdout,
        stderr,
    )

    assert stderr.getvalue() == ""
    payload = json.loads(stdout.getvalue())
    assert payload == {"package": "gsuid-cli"}
    assert "debug details" not in stdout.getvalue()


def test_plain_format_image_without_text_has_no_blank_line(tmp_path) -> None:
    image_path = tmp_path / "result.png"
    image_path.write_bytes(b"png")
    stdout = io.StringIO()
    stderr = io.StringIO()

    _write_payload(
        {
            "ok": True,
            "warnings": [],
            "data": {"package": "gsuid-cli"},
            "artifacts": [
                {
                    "kind": "image",
                    "name": "result-image",
                    "path": str(image_path),
                }
            ],
        },
        "plain",
        stdout,
        stderr,
    )

    assert stderr.getvalue() == ""
    assert stdout.getvalue() == f"图片已保存至: {image_path}\n"


def test_debug_plain_format_still_writes_debug_artifact(tmp_path) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(
        [
            "--debug",
            "--format=plain",
            "--render=data",
            "--output-dir",
            str(tmp_path),
            "--request-id=req-debug-plain",
            "meta",
            "version",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert stderr.getvalue() == ""
    payload = json.loads(stdout.getvalue())
    assert payload["package"] == "gsuid-cli"
    debug_artifacts = list(tmp_path.glob("*/*/debug-envelope.json"))
    assert len(debug_artifacts) == 1
    assert UUIDV7_RE.fullmatch(debug_artifacts[0].parent.name)


def test_text_format_name_is_rejected() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(["--format", "text", "meta", "version"], stdout=stdout, stderr=stderr)

    assert code == 1
    assert stderr.getvalue() == ""
    payload = json.loads(stdout.getvalue())
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_render_both_name_is_rejected() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(["--render", "both", "meta", "version"], stdout=stdout, stderr=stderr)

    assert code == 1
    assert stderr.getvalue() == ""
    payload = json.loads(stdout.getvalue())
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


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
    monkeypatch.setenv("GSUID_COOKIE", "cookie")

    class FakeProvider:
        def player_inventory(self, **kwargs: object) -> CommandResult:
            return CommandResult(
                data={
                    "uid": kwargs["uid"],
                    "credential_source": kwargs["credential_source"],
                    "inventory": {"count": 0},
                },
                source={"provider": "mys", "region": "cn", "cached": False, "fetched_at": "now"},
            )

    monkeypatch.setattr("gsuid_cli.commands._shared.provider_for_region", lambda *_: FakeProvider())

    code, _payload, _stderr = _run_json(["profile", "init", "--name", "alt"])
    assert code == 0
    code, _payload, _stderr = _run_json(
        ["account", "add", "--uid", "100000001", "--profile", "alt", "--default"]
    )
    assert code == 0

    code, payload, stderr = _run_json(["player", "inventory", "--render=data", "--profile", "alt"])

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

    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", FakePublicDataProvider
    )

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
    assert payload["sources"][0]["region"] == "cn"
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
