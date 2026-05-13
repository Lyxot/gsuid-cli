from __future__ import annotations

import io
import os
import sqlite3
import stat
from pathlib import Path

from helpers import run_json as _run_json

from gsuid_cli.cli import run
from gsuid_cli.core.state import state_db


def test_profile_init_show_and_default(monkeypatch, tmp_path) -> None:
    home = tmp_path / "gsuid-home"
    monkeypatch.setenv("GSUID_HOME", str(home))

    code, payload = _run_json(["--request-id", "req-profile", "profile", "init", "--name", "main"])

    assert code == 0
    assert payload["command"] == "profile.init"
    assert payload["data"]["created"] is True
    assert payload["data"]["profile"]["name"] == "main"
    assert payload["data"]["profile"]["default"] is True

    code, payload = _run_json(["profile", "show", "--name", "main"])

    assert code == 0
    assert payload["data"]["profile"]["default_region"] == "auto"

    code, payload = _run_json(["profile", "default", "--name", "main"])

    assert code == 0
    assert payload["data"]["profile"]["default"] is True

    if os.name != "nt":
        mode = stat.S_IMODE((home / "state.sqlite").stat().st_mode)
        assert mode == 0o600


def test_account_crud_and_profile_default(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    code, payload = _run_json(
        [
            "--profile",
            "main",
            "account",
            "add",
            "--uid",
            "100000001",
            "--label",
            "Traveler",
            "--default",
        ]
    )

    assert code == 0
    assert payload["data"]["created"] is True
    assert payload["data"]["account"]["uid"] == "100000001"
    assert payload["data"]["account"]["default"] is True
    assert payload["data"]["account"]["has_cookie"] is False

    code, payload = _run_json(["--profile", "main", "account", "show"])

    assert code == 0
    assert payload["data"]["account"]["uid"] == "100000001"

    code, payload = _run_json(["account", "list"])

    assert code == 0
    assert [account["uid"] for account in payload["data"]["accounts"]] == ["100000001"]

    code, payload = _run_json(["account", "remove", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["deleted"] is True


def test_account_add_auto_region_infers_from_uid(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    code, payload = _run_json(["account", "add", "--uid", "800000001"])

    assert code == 0
    assert payload["data"]["account"]["region"] == "os"


def test_profile_and_account_render_text_plain(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    code, stdout, stderr = _run_plain(
        ["profile", "init", "--name", "main", "--render", "text", "--format", "plain"]
    )

    assert code == 0
    assert stderr == ""
    assert "本地档案 - main" in stdout
    assert "状态: 已创建" in stdout
    assert "默认地区: 自动" in stdout

    code, stdout, stderr = _run_plain(
        [
            "--profile",
            "main",
            "account",
            "add",
            "--uid",
            "100000001",
            "--label",
            "Traveler",
            "--default",
            "--render",
            "text",
            "--format",
            "plain",
        ]
    )

    assert code == 0
    assert stderr == ""
    assert "本地账号 - 100000001 - Traveler" in stdout
    assert "状态: 已创建" in stdout
    assert "凭据: Cookie 未保存，Stoken 未保存，祈愿链接 未保存，设备 未保存" in stdout

    code, stdout, stderr = _run_plain(["account", "list", "--render", "text", "--format", "plain"])

    assert code == 0
    assert stderr == ""
    assert "本地账号列表" in stdout
    assert "- 100000001 - Traveler（默认）" in stdout


def test_profile_text_artifact_metadata(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    code, payload = _run_json(["profile", "init", "--name", "main", "--render", "text"])

    assert code == 0
    assert payload["data"]["render"] == "profile/init-text"
    assert payload["artifacts"][0]["name"] == "profile/init-text"
    assert payload["artifacts"][0]["media_type"] == "text/plain; charset=utf-8"
    assert "本地档案 - main" in _artifact_text(payload)


def test_profile_text_artifact_filename_is_bounded(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    name = "p" * 300

    code, payload = _run_json(["profile", "init", "--name", name, "--render", "text"])

    assert code == 0
    artifact = payload["artifacts"][0]
    assert isinstance(artifact, dict)
    assert len(Path(str(artifact["path"])).name) < 120


def test_profile_and_account_render_text_escape_multiline_values(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    name = "main\n状态: 已删除"
    label = "Traveler\n状态: 已删除"

    code, stdout, stderr = _run_plain(
        ["profile", "init", "--name", name, "--render", "text", "--format", "plain"]
    )

    assert code == 0
    assert stderr == ""
    assert "本地档案 - main 状态: 已删除" in stdout
    assert "状态: 已删除" not in stdout.splitlines()

    code, stdout, stderr = _run_plain(
        [
            "--profile",
            name,
            "account",
            "add",
            "--uid",
            "100000001",
            "--label",
            label,
            "--render",
            "text",
            "--format",
            "plain",
        ]
    )

    assert code == 0
    assert stderr == ""
    assert "Traveler 状态: 已删除" in stdout
    assert "状态: 已删除" not in stdout.splitlines()


def test_missing_account_returns_no_result(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    code, payload = _run_json(["account", "show", "--uid", "100000001"])

    assert code == 6
    assert payload["error"]["code"] == "NO_RESULT"


def test_state_v3_migrates_to_account_device_columns(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    db = home / "state.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE profiles (
            name TEXT PRIMARY KEY,
            default_uid TEXT,
            default_region TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE accounts (
            uid TEXT PRIMARY KEY,
            region TEXT NOT NULL,
            label TEXT,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE gacha_items (
            uid TEXT NOT NULL,
            id TEXT NOT NULL,
            gacha_type TEXT NOT NULL,
            time TEXT NOT NULL,
            name TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            PRIMARY KEY(uid, id)
        );
        CREATE TABLE gacha_sync (
            uid TEXT NOT NULL,
            gacha_type TEXT NOT NULL,
            last_id TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(uid, gacha_type)
        );
        CREATE TABLE panel_cache (
            uid TEXT PRIMARY KEY,
            source_provider TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            ttl INTEGER,
            player_info_json TEXT NOT NULL,
            avatar_info_json TEXT NOT NULL,
            raw_json TEXT NOT NULL
        );
        PRAGMA user_version = 3;
        """
    )
    conn.close()
    monkeypatch.setenv("GSUID_HOME", str(home))

    with state_db(None) as migrated:
        columns = {
            str(row["name"]) for row in migrated.execute("PRAGMA table_info(accounts)").fetchall()
        }

    assert {"device_id", "device_fp", "device_info", "device_updated_at"}.issubset(columns)


def _run_plain(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    return code, stdout.getvalue(), stderr.getvalue()


def _artifact_text(payload: dict[str, object]) -> str:
    artifact = payload["artifacts"][0]
    assert isinstance(artifact, dict)
    return open(str(artifact["path"]), encoding="utf-8").read()
