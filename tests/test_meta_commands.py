from __future__ import annotations

import io
import json

from gsuid_cli.cli import run


def test_meta_version_outputs_json_envelope() -> None:
    code, payload, stderr = _run_json(["--request-id", "req-version", "meta", "version"])

    assert code == 0
    assert stderr == ""
    assert payload["ok"] is True
    assert payload["command"] == "meta.version"
    assert payload["request_id"] == "req-version"
    assert payload["data"]["package"] == "gsuid-cli"
    assert payload["data"]["version"]


def test_meta_paths_respects_home_and_output_dir(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    output = tmp_path / "out"
    monkeypatch.setenv("GSUID_HOME", str(home))

    code, payload, _stderr = _run_json(
        ["--request-id", "req-paths", "--output-dir", str(output), "meta", "paths"]
    )

    assert code == 0
    assert payload["command"] == "meta.paths"
    assert payload["data"]["home"] == str(home.resolve())
    assert payload["data"]["artifacts"] == str(output.resolve())
    assert payload["data"]["config"] == str((home / "config.toml").resolve())


def test_meta_capabilities_lists_implemented_commands() -> None:
    code, payload, _stderr = _run_json(["--request-id", "req-caps", "meta", "capabilities"])

    assert code == 0
    commands = {command["command"] for command in payload["data"]["commands"]}
    assert {"meta.version", "meta.paths", "meta.capabilities"}.issubset(commands)
    assert {"profile.init", "account.add", "auth.cookie.set"}.issubset(commands)
    assert "auth.qrcode.login" in commands
    assert {"wiki.character", "events.list", "codes.list", "daily.materials"}.issubset(commands)
    assert {"daily.note", "daily.signin", "player.summary", "player.characters"}.issubset(commands)
    assert payload["data"]["regions"] == ["cn"]


def test_invalid_command_returns_json_error_envelope() -> None:
    code, payload, stderr = _run_json(["--request-id", "req-bad", "meta", "missing"])

    assert code == 1
    assert stderr == ""
    assert payload["ok"] is False
    assert payload["command"] == "meta.missing"
    assert payload["request_id"] == "req-bad"
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def _run_json(argv: list[str]) -> tuple[int, dict[str, object], str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    return code, json.loads(stdout.getvalue()), stderr.getvalue()
