from __future__ import annotations

import io

import httpx
import pytest
from helpers import run_json_with_stderr as _run_json

from gsuid_cli.cli import run
from gsuid_cli.commands import challenge as challenge_commands
from gsuid_cli.commands import progress as progress_commands
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.secrets import SecretStore


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


def test_cache_clear_asset_bucket_scope_removes_only_that_bucket(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    maps_file = home / "cache" / "maps" / "map.1234.png"
    icons_file = home / "cache" / "icons" / "icon.1234.png"
    maps_file.parent.mkdir(parents=True)
    icons_file.parent.mkdir(parents=True)
    maps_file.write_text("map", encoding="utf-8")
    icons_file.write_text("icon", encoding="utf-8")
    monkeypatch.setenv("GSUID_HOME", str(home))

    code, payload, stderr = _run_json(["cache", "clear", "--scope", "maps"])

    assert code == 0
    assert stderr == ""
    assert payload["command"] == "cache.clear"
    assert payload["data"]["removed_files"] == 1
    assert not maps_file.exists()
    assert icons_file.exists()


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


def test_cache_clear_http_scope_removes_only_http_cache(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GSUID_HOME", str(home))
    asset_file = home / "cache" / "assets" / "icon.1234.png"
    asset_file.parent.mkdir(parents=True)
    asset_file.write_text("asset", encoding="utf-8")
    client = HttpClient(
        timeout=1,
        cache_policy="use",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"data": {}})),
    )
    client.request_json(
        "GET",
        "https://example.test/data.json",
        provider="ambr",
        region="cn",
        category="events.list",
    )

    code, payload, stderr = _run_json(["cache", "clear", "--scope", "http"])

    assert code == 0
    assert stderr == ""
    assert payload["data"]["removed_files"] == 1
    assert not list((home / "cache" / "http").glob("*.json"))
    assert asset_file.exists()


def test_cache_clear_render_text_plain(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    asset_file = home / "cache" / "assets" / "icon.1234.png"
    asset_file.parent.mkdir(parents=True)
    asset_file.write_text("asset", encoding="utf-8")
    monkeypatch.setenv("GSUID_HOME", str(home))

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(
        ["cache", "clear", "--scope", "assets", "--render", "text", "--format", "plain"],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert stderr.getvalue() == ""
    assert "缓存清理" in stdout.getvalue()
    assert "删除文件: 1" in stdout.getvalue()


def test_cache_size_reports_cache_and_artifact_usage(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    http_file = home / "cache" / "http" / "response.1.json"
    maps_file = home / "cache" / "maps" / "map.1234.png"
    artifact_file = home / "artifacts" / "old.png"
    for path in (http_file, maps_file, artifact_file):
        path.parent.mkdir(parents=True, exist_ok=True)
    http_file.write_bytes(b"1234")
    maps_file.write_bytes(b"abcdef")
    artifact_file.write_bytes(b"xyz")
    monkeypatch.setenv("GSUID_HOME", str(home))

    code, payload, stderr = _run_json(["cache", "size", "--scope", "all"])

    assert code == 0
    assert stderr == ""
    assert payload["command"] == "cache.size"
    assert payload["data"]["bytes"] == 13
    by_scope = {item["scope"]: item for item in payload["data"]["entries"]}
    assert by_scope["http"]["bytes"] == 4
    assert by_scope["maps"]["bytes"] == 6
    assert by_scope["artifacts"]["bytes"] == 3


def test_cache_size_render_text_plain(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    icon_file = home / "cache" / "icons" / "icon.1234.png"
    icon_file.parent.mkdir(parents=True)
    icon_file.write_bytes(b"icon")
    monkeypatch.setenv("GSUID_HOME", str(home))

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(
        ["cache", "size", "--scope", "icons", "--render", "text", "--format", "plain"],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert stderr.getvalue() == ""
    assert "缓存大小" in stdout.getvalue()
    assert "总大小: 4 B" in stdout.getvalue()


def test_cache_size_does_not_follow_symlinks(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    icons = home / "cache" / "icons"
    icons.mkdir(parents=True)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    try:
        (icons / "outside.bin").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are not available")
    monkeypatch.setenv("GSUID_HOME", str(home))

    code, payload, stderr = _run_json(["cache", "size", "--scope", "icons"])

    assert code == 0
    assert stderr == ""
    assert payload["data"]["bytes"] == 0
    assert payload["data"]["files"] == 0


def _fake_bbs_provider(_region: str, _http_client: HttpClient):
    class FakeProvider:
        def daily_bbs_coin(self, **kwargs: object) -> CommandResult:
            return CommandResult(
                data={
                    "uid": kwargs["uid"],
                    "available": True,
                    "tasks": [],
                    "actions": [],
                    "points_received": 10,
                    "failures": [],
                    "source": "mihoyo-bbs",
                },
                source={"provider": "mys", "region": "cn", "cached": False, "fetched_at": "now"},
            )

    return FakeProvider()


class _FakeHardRankProvider:
    def __init__(self, _http_client: HttpClient) -> None:
        pass

    def stygian_rank(self, *, region: str) -> CommandResult:
        return CommandResult(
            data={
                "available": True,
                "entries": [{"uid": "100000001", "nickname": "派蒙"}],
                "count": 1,
                "total_count": 1,
            },
            source={"provider": "akasha", "region": region, "cached": False, "fetched_at": "now"},
        )


class _FakeGuideProvider:
    def achievement_guide(self, *, query: str) -> CommandResult:
        return CommandResult(
            data={
                "query": query,
                "kind": "achievement",
                "available": True,
                "matches": [{"name": query, "book": "天地万象"}],
                "count": 1,
            },
            source={"provider": "genshinuid", "region": "cn", "cached": False, "fetched_at": "now"},
        )

    def commission_guide(self, *, query: str) -> CommandResult:
        return CommandResult(
            data={
                "query": query,
                "kind": "commission",
                "available": True,
                "matches": [{"name": query, "achievement": "Yo dala？"}],
                "count": 1,
            },
            source={"provider": "genshinuid", "region": "cn", "cached": False, "fetched_at": "now"},
        )


def test_stage_14_2_commands_return_structured_results(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands._shared.provider_for_region", _fake_bbs_provider)
    monkeypatch.setattr(challenge_commands, "AkashaProvider", _FakeHardRankProvider)
    monkeypatch.setattr(progress_commands, "_public_provider", lambda _args: _FakeGuideProvider())
    SecretStore().set_secret("stoken", "100000001", "stuid=1;stoken=secret")
    commands = [
        ["daily", "bbs-coin", "--uid", "100000001"],
        ["challenge", "hard-rank"],
        ["progress", "achievement-guide", "--query", "昨日重现"],
        ["progress", "commission-guide", "--query", "诗歌交流"],
    ]

    for argv in commands:
        code, payload, stderr = _run_json(argv)

        assert code == 0
        assert stderr == ""
        assert payload["ok"] is True
        assert payload["data"].get("source_limitations") in (None, [])


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
        "gsuid_cli.commands._shared.provider_for_region",
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
