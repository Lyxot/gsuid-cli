from __future__ import annotations

import ast
from pathlib import Path

from helpers import run_json_with_stderr as _run_json


def test_meta_version_outputs_json_envelope() -> None:
    code, payload, stderr = _run_json(["--request-id", "req-version", "meta", "version"])

    assert code == 0
    assert stderr == ""
    assert payload["ok"] is True
    assert payload["command"] == "meta.version"
    assert payload["request_id"] == "req-version"
    assert payload["data"]["package"] == "gsuid-cli"
    assert payload["data"]["version"]
    assert payload["sources"][0]["provider"] == "local"
    assert "source" not in payload


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
    assert payload["data"]["cache_assets"] == str((home / "cache" / "assets").resolve())
    assert set(payload["data"]) == {
        "home",
        "config",
        "state",
        "data",
        "cache",
        "cache_assets",
        "artifacts",
        "logs",
    }


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
        "meta.doctor",
    }.issubset(commands)
    assert {"profile.init", "account.add", "auth.cookie.set"}.issubset(commands)
    assert {"batch.run", "batch.plan", "cache.clear", "monitor.once"}.issubset(commands)
    assert {
        "auth.qrcode.login",
        "auth.device.set",
        "auth.device.test",
        "auth.device.delete",
    }.issubset(commands)
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
    assert {"daily.bbs-coin", "player.inventory", "player.calendar"}.issubset(commands)
    assert "player.register-time" in commands
    assert {"challenge.abyss", "challenge.theater", "challenge.hard"}.issubset(commands)
    assert "challenge.hard-rank" in commands
    assert {"progress.completion", "progress.exploration", "progress.gcg"}.issubset(commands)
    assert {"progress.achievement-guide", "progress.commission-guide"}.issubset(commands)
    assert "progress.gcg-deck" in commands
    assert {
        "gacha.refresh",
        "gacha.summary",
        "gacha.import",
        "gacha.export",
        "gacha.authkey.refresh",
    }.issubset(commands)
    assert {"panel.refresh", "panel.list", "panel.show", "panel.compare"}.issubset(commands)
    assert {"panel.artifacts", "panel.graduation"}.issubset(commands)
    assert {"rank.list", "rank.character", "rank.artifact"}.issubset(commands)
    assert "rank.summary" not in commands
    capability_by_command = {command["command"]: command for command in payload["data"]["commands"]}
    assert capability_by_command["daily.materials"]["render"] == ["data", "image", "all"]
    assert capability_by_command["daily.note"]["render"] == ["data", "image", "all"]
    assert capability_by_command["guide.character"]["render"] == ["data", "image", "all"]
    assert capability_by_command["guide.reference-panel"]["render"] == ["data", "image", "all"]
    assert capability_by_command["guide.abyss"]["render"] == ["data", "image", "all"]
    assert capability_by_command["guide.theater"]["render"] == ["data", "image", "all"]
    assert capability_by_command["recommend.build"]["render"] == ["data", "image", "all"]
    assert capability_by_command["recommend.holder"]["render"] == ["data", "image", "all"]
    assert capability_by_command["player.summary"]["render"] == ["data", "image", "all"]
    assert capability_by_command["player.characters"]["render"] == ["data", "image", "all"]
    assert capability_by_command["player.inventory"]["auth"] == "cookie"
    assert capability_by_command["player.inventory"]["render"] == ["data", "image", "all"]
    assert (
        capability_by_command["player.inventory"]["coverage"]
        == "owned_character_ascension_and_equipped_weapon_materials"
    )
    assert capability_by_command["player.calendar"]["auth"] == "cookie"
    assert capability_by_command["player.calendar"]["render"] == ["data", "image", "all"]
    assert capability_by_command["player.diary"]["render"] == ["data", "image", "all"]
    assert capability_by_command["player.register-time"]["auth"] == "cookie"
    assert capability_by_command["player.register-time"]["availability"] == "upstream-limited"
    assert capability_by_command["challenge.abyss"]["render"] == ["data", "image", "all"]
    assert capability_by_command["challenge.theater"]["render"] == ["data", "image", "all"]
    assert capability_by_command["challenge.hard"]["render"] == ["data", "image", "all"]
    assert capability_by_command["challenge.hard-rank"]["render"] == ["data"]
    assert capability_by_command["progress.completion"]["render"] == ["data", "image", "all"]
    assert capability_by_command["progress.exploration"]["render"] == ["data", "image", "all"]
    assert capability_by_command["progress.collection"]["render"] == ["data", "image", "all"]
    assert capability_by_command["progress.achievements"]["render"] == ["data", "image", "all"]
    assert capability_by_command["progress.gcg"]["render"] == ["data", "image", "all"]
    assert capability_by_command["progress.gcg-deck"]["render"] == ["data", "image", "all"]
    assert capability_by_command["progress.achievement-guide"]["render"] == ["data"]
    assert capability_by_command["progress.commission-guide"]["render"] == ["data"]
    assert capability_by_command["panel.show"]["render"] == ["data", "image", "all"]
    assert capability_by_command["panel.compare"]["render"] == ["data", "image", "all"]
    assert capability_by_command["panel.artifacts"]["render"] == ["data", "image", "all"]
    assert capability_by_command["panel.showcase"]["render"] == ["data", "image", "all"]
    assert capability_by_command["map.find"]["cache"] == "use"
    assert "data" in capability_by_command["map.find"]["render"]
    assert payload["data"]["regions"] == ["cn"]
    assert payload["data"]["formats"] == ["json", "pretty-json", "plain"]
    global_options = {option["name"]: option for option in payload["data"]["global_options"]}
    assert global_options["--uid"]["placement"] == "anywhere"
    assert global_options["--format"]["value"] == "json|pretty-json|plain"


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
    assert "data" not in payload["data"]["success"]["required"]
    assert "sources" not in payload["data"]["success"]["required"]
    assert "source" not in payload["data"]["success"]["properties"]
    assert payload["data"]["error"]["properties"]["ok"]["const"] is False
    assert "sources" not in payload["data"]["error"]["required"]
    assert "source" not in payload["data"]["error"]["properties"]


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
