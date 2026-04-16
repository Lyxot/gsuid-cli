from __future__ import annotations

import io
import json

from gsuid_cli.cli import run
from gsuid_cli.core.models import CommandResult


def test_meta_doctor_storage_reports_checks(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    artifacts = home / "artifacts"
    artifacts.mkdir(parents=True)
    monkeypatch.setenv("GSUID_HOME", str(home))

    code, payload, stderr = _run_json(["meta", "doctor", "--check", "storage"])

    assert code == 0
    assert stderr == ""
    assert payload["command"] == "meta.doctor"
    assert payload["data"]["status"] == "ok"
    assert {check["name"] for check in payload["data"]["checks"]} == {
        "storage.home",
        "storage.state_parent",
        "storage.artifacts",
    }


def test_cache_clear_scope_removes_only_selected_files(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    asset_file = home / "cache" / "assets" / "icon.1234.png"
    asset_metadata = home / "cache" / "assets" / "icon.1234.metadata.json"
    asset_lock = home / "cache" / "assets" / ".1234.lock"
    asset_file.parent.mkdir(parents=True)
    asset_file.write_text("asset", encoding="utf-8")
    asset_metadata.write_text("{}", encoding="utf-8")
    asset_lock.write_text("", encoding="utf-8")
    monkeypatch.setenv("GSUID_HOME", str(home))

    code, payload, stderr = _run_json(["cache", "clear", "--scope", "assets"])

    assert code == 0
    assert stderr == ""
    assert payload["command"] == "cache.clear"
    assert payload["data"]["removed_files"] == 2
    assert not asset_file.exists()
    assert not asset_metadata.exists()
    assert asset_lock.exists()


def test_cache_clear_artifacts_ignores_global_output_dir(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    output = tmp_path / "output"
    home_artifact = home / "artifacts" / "old.png"
    output_file = output / "keep.txt"
    home_artifact.parent.mkdir(parents=True)
    output.mkdir()
    home_artifact.write_text("old", encoding="utf-8")
    output_file.write_text("keep", encoding="utf-8")
    monkeypatch.setenv("GSUID_HOME", str(home))

    code, payload, stderr = _run_json(
        ["--output-dir", str(output), "cache", "clear", "--scope", "artifacts"]
    )

    assert code == 0
    assert stderr == ""
    assert payload["data"]["removed_files"] == 1
    assert not home_artifact.exists()
    assert output_file.exists()


def test_source_limited_missing_commands_return_structured_results(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    commands = [
        ["player", "inventory", "--uid", "100000001"],
        ["player", "calendar", "--uid", "100000001"],
        ["player", "register-time", "--uid", "100000001"],
        ["daily", "bbs-coin", "--uid", "100000001"],
        ["challenge", "hard-rank"],
        ["progress", "achievement-guide", "--query", "commission"],
        ["progress", "commission-guide", "--query", "anna"],
    ]

    for argv in commands:
        code, payload, stderr = _run_json(argv)

        assert code == 0
        assert stderr == ""
        assert payload["ok"] is True
        assert payload["warnings"]
        assert payload["data"]["source_limitations"]


def test_progress_gcg_deck_uses_provider(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("GSUID_COOKIE", "cookie")
    captured = {}

    class FakeProvider:
        def progress_gcg_deck(self, **kwargs: object) -> CommandResult:
            captured.update(kwargs)
            return CommandResult(
                data={
                    "uid": kwargs["uid"],
                    "deck_id": kwargs["deck_id"],
                    "decks": [{"id": 7, "name": "deck"}],
                    "count": 1,
                },
                source={"provider": "mys", "region": "cn", "cached": False, "fetched_at": "now"},
            )

    monkeypatch.setattr(
        "gsuid_cli.commands.progress.provider_for_region",
        lambda *_: FakeProvider(),
    )

    code, payload, stderr = _run_json(
        ["progress", "gcg-deck", "--uid", "100000001", "--deck-id", "7"]
    )

    assert code == 0
    assert stderr == ""
    assert payload["command"] == "progress.gcg-deck"
    assert payload["data"]["count"] == 1
    assert captured["deck_id"] == 7
    assert captured["cookie"] == "cookie"


def _run_json(argv: list[str]) -> tuple[int, dict[str, object], str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    return code, json.loads(stdout.getvalue()), stderr.getvalue()
