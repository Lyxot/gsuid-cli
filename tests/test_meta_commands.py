from __future__ import annotations

import ast
import io
import json
from pathlib import Path

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
    assert {
        "meta.version",
        "meta.paths",
        "meta.capabilities",
        "meta.schema",
        "meta.errors",
    }.issubset(commands)
    assert {"profile.init", "account.add", "auth.cookie.set"}.issubset(commands)
    assert {"batch.run", "batch.plan", "monitor.once"}.issubset(commands)
    assert "auth.qrcode.login" in commands
    assert {"wiki.character", "events.list", "codes.list", "daily.materials"}.issubset(commands)
    assert {
        "wiki.food",
        "wiki.talent",
        "wiki.constellation",
        "wiki.character-materials",
        "wiki.weapon-materials",
    }.issubset(commands)
    assert {"guide.character", "guide.route", "recommend.build", "map.find"}.issubset(commands)
    assert {"announcements.list", "rerun.list", "misc.primogems-plan"}.issubset(commands)
    assert "resources.sync" in commands
    assert {"daily.note", "daily.signin", "player.summary", "player.characters"}.issubset(commands)
    assert {"challenge.abyss", "challenge.theater", "challenge.hard"}.issubset(commands)
    assert {"progress.completion", "progress.exploration", "progress.gcg"}.issubset(commands)
    assert {"gacha.refresh", "gacha.summary", "gacha.import", "gacha.export"}.issubset(commands)
    assert {"panel.refresh", "panel.list", "panel.show", "panel.compare"}.issubset(commands)
    assert {"rank.summary", "rank.list", "rank.character", "rank.artifact"}.issubset(commands)
    capability_by_command = {command["command"]: command for command in payload["data"]["commands"]}
    assert "image" in capability_by_command["daily.note"]["render"]
    assert "image" in capability_by_command["challenge.abyss"]["render"]
    assert "image" in capability_by_command["panel.show"]["render"]
    assert capability_by_command["map.find"]["cache"] == "off"
    assert "data" in capability_by_command["map.find"]["render"]
    assert payload["data"]["regions"] == ["cn"]


def test_invalid_command_returns_json_error_envelope() -> None:
    code, payload, stderr = _run_json(["--request-id", "req-bad", "meta", "missing"])

    assert code == 1
    assert stderr == ""
    assert payload["ok"] is False
    assert payload["command"] == "meta.missing"
    assert payload["request_id"] == "req-bad"
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_meta_schema_for_command() -> None:
    code, payload, stderr = _run_json(
        ["--request-id", "req-schema", "meta", "schema", "--command", "meta.version"]
    )

    assert code == 0
    assert stderr == ""
    assert payload["data"]["command"] == "meta.version"
    assert payload["data"]["success"]["properties"]["command"]["const"] == "meta.version"
    assert payload["data"]["error"]["properties"]["ok"]["const"] is False


def test_meta_errors_catalog() -> None:
    code, payload, stderr = _run_json(["--request-id", "req-errors", "meta", "errors"])

    assert code == 0
    assert stderr == ""
    by_code = {error["code"]: error for error in payload["data"]["errors"]}
    assert by_code["AUTH_REQUIRED"]["exit_code"] == 2
    assert by_code["NETWORK_TIMEOUT"]["retryable"] is True
    assert _emitted_error_codes().issubset(by_code)


def _emitted_error_codes() -> set[str]:
    codes = {"NETWORK_TIMEOUT", "NETWORK_ERROR", "UPSTREAM_HTTP_ERROR"}
    root = Path(__file__).resolve().parents[1] / "src" / "gsuid_cli"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else getattr(node.func, "attr", None)
            )
            if name != "CliError":
                continue
            code = node.args[0]
            if isinstance(code, ast.Constant) and isinstance(code.value, str):
                codes.add(code.value)
    return codes - {"<dynamic>"}


def _run_json(argv: list[str]) -> tuple[int, dict[str, object], str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    return code, json.loads(stdout.getvalue()), stderr.getvalue()
