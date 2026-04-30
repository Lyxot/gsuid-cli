from __future__ import annotations

import os
import sqlite3
import stat

from helpers import run_json as _run_json

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
    assert payload["data"]["profile"]["default_region"] == "cn"

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


