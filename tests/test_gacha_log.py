from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from PIL import Image

from gsuid_cli.cli import run
from gsuid_cli.commands import gacha
from gsuid_cli.core.errors import EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.secrets import SecretStore
from gsuid_cli.core.state import state_db
from gsuid_cli.providers.mys import MysProvider
from gsuid_cli.renderers.gacha import (
    FALLBACK_CHARACTER_ICON_URL,
    gacha_summary_item_urls,
    gacha_summary_missing_icon_count,
)


def test_gacha_import_summary_export_round_trip(monkeypatch, tmp_path) -> None:
    first_home = tmp_path / "home-a"
    monkeypatch.setenv("GSUID_HOME", str(first_home))
    import_file = tmp_path / "uigf-v4.json"
    import_file.write_text(json.dumps(_uigf_v4()), encoding="utf-8")

    code, payload = _run_json(["gacha", "import", "--uid", "100000001", "--file", str(import_file)])

    assert code == 0
    assert payload["data"]["format"] == "uigf-v4"
    assert payload["data"]["inserted"] == 3
    assert payload["data"]["duplicates"] == 0

    code, payload = _run_json(["gacha", "import", "--uid", "100000001", "--file", str(import_file)])

    assert code == 0
    assert payload["data"]["inserted"] == 0
    assert payload["data"]["duplicates"] == 3

    code, payload = _run_json(["gacha", "summary", "--uid", "100000001", "--banner", "character"])

    assert code == 0
    assert payload["data"]["summary"]["total"] == 2
    assert payload["data"]["summary"]["by_rank"] == {"4": 1, "5": 1}

    export_file = tmp_path / "export.json"
    code, payload = _run_json(
        [
            "gacha",
            "export",
            "--uid",
            "100000001",
            "--format",
            "uigf-v4",
            "--output",
            str(export_file),
        ]
    )

    assert code == 0
    assert payload["artifacts"][0]["path"] == str(export_file.resolve())
    exported = json.loads(export_file.read_text(encoding="utf-8"))
    assert exported["info"]["export_app_version"]
    assert isinstance(exported["info"]["export_timestamp"], int)
    assert len(exported["hk4e"][0]["list"]) == 3

    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home-b"))
    code, payload = _run_json(["gacha", "import", "--uid", "100000001", "--file", str(export_file)])

    assert code == 0
    assert payload["data"]["inserted"] == 3


def test_gacha_summary_counts_records_between_five_stars(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    import_file = tmp_path / "uigf-v4.json"
    payload = _uigf_v4()
    payload["hk4e"][0]["list"] = [
        _item("1", "301", "Noelle", "4"),
        _item("2", "301", "Venti", "5"),
        _item("3", "301", "Debate Club", "3", item_type="Weapon"),
        _item("4", "301", "Sucrose", "4"),
        _item("5", "301", "Diluc", "5"),
        _item("6", "302", "Skyward Harp", "5", item_type="Weapon"),
    ]
    import_file.write_text(json.dumps(payload), encoding="utf-8")

    code, _payload = _run_json(
        ["gacha", "import", "--uid", "100000001", "--file", str(import_file)]
    )
    assert code == 0

    code, payload = _run_json(["gacha", "summary", "--uid", "100000001"])

    assert code == 0
    intervals = payload["data"]["summary"]["five_star_intervals_by_gacha_type"]
    assert [item["records_since_previous_five_star"] for item in intervals["301"]] == [2, 3]
    assert [item["record_number_in_gacha_type"] for item in intervals["301"]] == [2, 5]
    assert intervals["301"][0]["item"]["name"] == "Venti"
    assert intervals["301"][1]["item"]["name"] == "Diluc"
    assert intervals["302"][0]["records_since_previous_five_star"] == 1


def test_gacha_summary_character_banner_keeps_gacha_type_intervals_separate(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    import_file = tmp_path / "uigf-v4.json"
    payload = _uigf_v4()
    payload["hk4e"][0]["list"] = [
        _item("1", "301", "Noelle", "4"),
        _item("2", "400", "Barbara", "4"),
        _item("3", "301", "Venti", "5"),
        _item("4", "400", "Diluc", "5"),
        _item("5", "302", "Skyward Harp", "5", item_type="Weapon"),
    ]
    import_file.write_text(json.dumps(payload), encoding="utf-8")

    code, _payload = _run_json(
        ["gacha", "import", "--uid", "100000001", "--file", str(import_file)]
    )
    assert code == 0

    code, payload = _run_json(["gacha", "summary", "--uid", "100000001", "--banner", "character"])

    assert code == 0
    intervals = payload["data"]["summary"]["five_star_intervals_by_gacha_type"]
    assert set(intervals) == {"301", "400"}
    assert intervals["301"][0]["records_since_previous_five_star"] == 2
    assert intervals["400"][0]["records_since_previous_five_star"] == 2


def test_gacha_summary_render_image_writes_card(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(gacha, "fetch_render_images", lambda *args, **kwargs: ({}, []))
    import_file = tmp_path / "uigf-v4.json"
    import_file.write_text(json.dumps(_uigf_v4()), encoding="utf-8")

    code, _payload = _run_json(
        ["gacha", "import", "--uid", "100000001", "--file", str(import_file)]
    )
    assert code == 0

    code, payload = _run_json(["gacha", "summary", "--uid", "100000001", "--render", "image"])

    assert code == 0
    assert payload["command"] == "gacha.summary"
    assert payload["data"]["render"] == "gacha/summary"
    artifact = payload["artifacts"][0]
    path = Path(artifact["path"])
    assert artifact["media_type"] == "image/png"
    with Image.open(path) as image:
        assert image.size[0] == 950
        assert image.getbbox() is not None


def test_gacha_summary_render_both_preserves_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(gacha, "fetch_render_images", lambda *args, **kwargs: ({}, []))
    import_file = tmp_path / "uigf-v4.json"
    import_file.write_text(json.dumps(_uigf_v4()), encoding="utf-8")

    code, _payload = _run_json(
        ["gacha", "import", "--uid", "100000001", "--file", str(import_file)]
    )
    assert code == 0

    code, payload = _run_json(["gacha", "summary", "--uid", "100000001", "--render", "both"])

    assert code == 0
    assert payload["data"]["summary"]["total"] == 3
    assert payload["data"]["render"] == "gacha/summary"
    assert payload["artifacts"][0]["kind"] == "image"


def test_gacha_summary_character_icon_urls_include_duplicate_name_candidates() -> None:
    fallback_item = {
        "rank_type": "5",
        "item_type": "角色",
        "item_id": "",
        "name": "哥伦",
    }
    exact_item = {
        "rank_type": "5",
        "item_type": "角色",
        "item_id": "",
        "name": "温迪",
    }
    duplicate_name_item = {
        "rank_type": "5",
        "item_type": "角色",
        "item_id": "",
        "name": "伊涅芙",
    }
    duplicate_name_with_id = {
        "rank_type": "5",
        "item_type": "角色",
        "item_id": "10000903",
        "name": "伊涅芙",
    }
    weapon_item = {
        "rank_type": "5",
        "item_type": "武器",
        "item_id": "",
        "name": "missing-weapon",
    }

    assert gacha_summary_item_urls([fallback_item]) == [FALLBACK_CHARACTER_ICON_URL]
    assert gacha_summary_item_urls([exact_item]) == [
        "https://example.test/GenshinUID/resource/chars/10000022.png",
        FALLBACK_CHARACTER_ICON_URL,
    ]
    assert gacha_summary_item_urls([duplicate_name_item]) == [
        "https://example.test/GenshinUID/resource/chars/10000116.png",
        "https://example.test/GenshinUID/resource/chars/10000903.png",
        FALLBACK_CHARACTER_ICON_URL,
    ]
    assert gacha_summary_item_urls([duplicate_name_with_id]) == [
        "https://example.test/GenshinUID/resource/chars/10000903.png",
        "https://example.test/GenshinUID/resource/chars/10000116.png",
        FALLBACK_CHARACTER_ICON_URL,
    ]
    assert (
        gacha_summary_missing_icon_count(
            [duplicate_name_item],
            {"https://example.test/GenshinUID/resource/chars/10000116.png": b"x"},
        )
        == 0
    )
    assert gacha_summary_missing_icon_count([weapon_item], {FALLBACK_CHARACTER_ICON_URL: b"x"}) == 1


def test_gacha_import_supports_uigf_v2(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    import_file = tmp_path / "uigf-v2.json"
    import_file.write_text(
        json.dumps({"info": {"uid": "100000001", "uigf_version": "v2.4"}, "list": _items()}),
        encoding="utf-8",
    )

    code, payload = _run_json(
        ["gacha", "import", "--uid", "100000001", "--file", str(import_file), "--format", "auto"]
    )

    assert code == 0
    assert payload["data"]["format"] == "uigf-v2"
    assert payload["data"]["inserted"] == 3


def test_gacha_import_rejects_invalid_uigf(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    import_file = tmp_path / "bad.json"
    import_file.write_text('{"info": {"version": "v1"}}', encoding="utf-8")

    code, payload = _run_json(["gacha", "import", "--uid", "100000001", "--file", str(import_file)])

    assert code == 1
    assert payload["command"] == "gacha.import"
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_gacha_import_rejects_shaped_file_with_missing_item_fields(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    import_file = tmp_path / "bad-shaped.json"
    import_file.write_text(
        json.dumps(
            {"info": {"version": "v4.0"}, "hk4e": [{"uid": "100000001", "list": [{"id": "1"}]}]}
        ),
        encoding="utf-8",
    )

    code, payload = _run_json(["gacha", "import", "--uid", "100000001", "--file", str(import_file)])

    assert code == 1
    assert payload["error"]["code"] == "INVALID_ARGUMENT"
    assert payload["error"]["details"]["missing"] == [
        "count",
        "gacha_type",
        "item_id",
        "item_type",
        "name",
        "rank_type",
        "time",
    ]


def test_gacha_import_rejects_empty_item_id(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    import_file = tmp_path / "uigf-v4.json"
    payload = _uigf_v4()
    payload["hk4e"][0]["list"][0]["item_id"] = ""
    import_file.write_text(json.dumps(payload), encoding="utf-8")

    code, payload = _run_json(["gacha", "import", "--uid", "100000001", "--file", str(import_file)])

    assert code == 1
    assert payload["error"]["code"] == "INVALID_ARGUMENT"
    assert payload["error"]["details"]["missing"] == ["item_id"]


def test_gacha_import_rejects_conflicting_duplicate(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps(_uigf_v4()), encoding="utf-8")
    changed = _uigf_v4()
    changed["hk4e"][0]["list"][0]["name"] = "Different"
    second.write_text(json.dumps(changed), encoding="utf-8")

    code, _payload = _run_json(["gacha", "import", "--uid", "100000001", "--file", str(first)])
    assert code == 0

    code, payload = _run_json(["gacha", "import", "--uid", "100000001", "--file", str(second)])

    assert code == 1
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_gacha_import_backfills_empty_item_id_duplicate(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    first = _items()
    first[0].pop("item_id")
    with state_db(None) as conn:
        stats = gacha._insert_items(conn, "100000001", first, require_item_id=False)
        backfill = gacha._insert_items(conn, "100000001", _items())
        row = conn.execute(
            "SELECT item_id FROM gacha_items WHERE uid = ? AND id = ?",
            ("100000001", "1"),
        ).fetchone()

    assert stats == {"inserted": 3, "duplicates": 0}
    assert backfill == {"inserted": 0, "duplicates": 3}
    assert row["item_id"] == "1"


def test_gacha_refresh_duplicate_allows_incoming_missing_item_id(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    incoming = _items()
    incoming[0].pop("item_id")
    with state_db(None) as conn:
        stats = gacha._insert_items(conn, "100000001", _items())
        duplicate = gacha._insert_items(
            conn,
            "100000001",
            incoming,
            require_item_id=False,
        )
        row = conn.execute(
            "SELECT item_id FROM gacha_items WHERE uid = ? AND id = ?",
            ("100000001", "1"),
        ).fetchone()

    assert stats == {"inserted": 3, "duplicates": 0}
    assert duplicate == {"inserted": 0, "duplicates": 3}
    assert row["item_id"] == "1"


def test_gacha_import_uses_global_uid(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    import_file = tmp_path / "uigf-v4.json"
    import_file.write_text(json.dumps(_uigf_v4()), encoding="utf-8")

    code, payload = _run_json(["--uid", "100000001", "gacha", "import", "--file", str(import_file)])

    assert code == 0
    assert payload["data"]["inserted"] == 3


def test_gacha_export_command_format_parse_error_stays_json(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    code, payload = _run_json(
        ["gacha", "export", "--uid", "100000001", "--format", "uigf-v4", "--bad"]
    )

    assert code == 1
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_gacha_type_400_exports_as_uigf_301(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    import_file = tmp_path / "uigf-v4.json"
    payload = _uigf_v4()
    payload["hk4e"][0]["list"] = [
        {
            "uid": "100000001",
            "gacha_type": "400",
            "uigf_gacha_type": "400",
            "item_id": "4",
            "count": "1",
            "time": "2026-04-29 12:00:04",
            "name": "Character",
            "lang": "zh-cn",
            "item_type": "Character",
            "rank_type": "5",
            "id": "4",
        }
    ]
    import_file.write_text(json.dumps(payload), encoding="utf-8")
    export_file = tmp_path / "export.json"

    code, _payload = _run_json(
        ["gacha", "import", "--uid", "100000001", "--file", str(import_file)]
    )
    assert code == 0
    code, _payload = _run_json(
        ["gacha", "export", "--uid", "100000001", "--output", str(export_file)]
    )

    assert code == 0
    exported = json.loads(export_file.read_text(encoding="utf-8"))
    assert exported["hk4e"][0]["list"][0]["gacha_type"] == "400"
    assert exported["hk4e"][0]["list"][0]["uigf_gacha_type"] == "301"


def test_gacha_authkey_command_fully_redacts_url(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    SecretStore().set_secret(
        "gacha_url",
        "100000001",
        "https://example.test/getGachaLog?authkey=expired-secret",
    )

    code, payload = _run_json(["gacha", "authkey", "--uid", "100000001"])

    assert code == 0
    raw = json.dumps(payload, ensure_ascii=False)
    assert payload["data"]["redacted"] == "[REDACTED_URL]"
    assert "expired-secret" not in raw
    assert "cret" not in raw

    code, status_payload = _run_json(["gacha", "authkey", "status", "--uid", "100000001"])

    assert code == 0
    assert status_payload["command"] == "gacha.authkey"
    assert status_payload["data"]["available"] is True


def test_gacha_authkey_help_lists_status_and_refresh(capsys: pytest.CaptureFixture[str]) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(["gacha", "authkey", "--help"], stdout=stdout, stderr=stderr)

    assert code == 0
    assert stderr.getvalue() == ""
    help_text = stdout.getvalue() or capsys.readouterr().out
    assert "status" in help_text
    assert "refresh" in help_text
    assert "With no action, status is returned." in help_text


def test_gacha_authkey_refresh_stores_generated_url_without_printing_it(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.gacha.provider_for_region", _authkey_provider)
    store = SecretStore()
    store.set_secret("cookie", "100000001", "account_id=1;cookie_token=cookie-secret")
    store.set_secret("stoken", "100000001", "stuid=1;stoken=stoken-secret")

    code, payload = _run_json(["gacha", "authkey", "refresh", "--uid", "100000001"])

    raw = json.dumps(payload, ensure_ascii=False)
    stored_url = store.get_secret("gacha_url", "100000001")
    assert code == 0
    assert payload["command"] == "gacha.authkey.refresh"
    assert payload["data"]["stored"] is True
    assert payload["data"]["available"] is True
    assert payload["data"]["credential_sources"] == {"cookie": "keyring", "stoken": "keyring"}
    assert stored_url is not None
    assert "secret-authkey" in stored_url
    assert "secret-authkey" not in raw
    assert "stoken-secret" not in raw
    assert "cookie-secret" not in raw

    code, status = _run_json(["gacha", "authkey", "--uid", "100000001"])

    assert code == 0
    assert status["data"]["available"] is True


def test_state_v1_migrates_to_gacha_tables(monkeypatch, tmp_path) -> None:
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
        INSERT INTO profiles(name, default_uid, default_region, created_at, updated_at)
        VALUES('default', NULL, 'cn', 'now', 'now');
        PRAGMA user_version = 1;
        """
    )
    conn.close()
    monkeypatch.setenv("GSUID_HOME", str(home))

    with state_db(None) as migrated:
        profile = migrated.execute("SELECT name FROM profiles").fetchone()
        gacha_table = migrated.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='gacha_items'"
        ).fetchone()

    assert profile["name"] == "default"
    assert gacha_table["name"] == "gacha_items"


def test_gacha_refresh_uses_stored_authkey_without_printing_it(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.gacha.provider_for_region", _refresh_provider)
    _disable_gacha_refresh_sleep(monkeypatch)
    secret_url = "https://example.test/getGachaLog?authkey=secret-authkey&authkey_ver=1"
    SecretStore().set_secret("gacha_url", "100000001", secret_url)

    code, payload = _run_json(["gacha", "refresh", "--uid", "100000001"])

    raw = json.dumps(payload, ensure_ascii=False)
    assert code == 0
    assert payload["data"]["inserted"] == 2
    assert payload["data"]["duplicates"] == 0
    assert "secret-authkey" not in raw
    assert "hkey" not in raw

    code, payload = _run_json(["gacha", "refresh", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["inserted"] == 0
    assert payload["data"]["duplicates"] == 2


def test_gacha_refresh_continues_past_mixed_duplicate_page(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.gacha.provider_for_region", _gap_refresh_provider)
    _disable_gacha_refresh_sleep(monkeypatch)
    SecretStore().set_secret(
        "gacha_url",
        "100000001",
        "https://example.test/getGachaLog?authkey=secret-authkey&authkey_ver=1",
    )
    with state_db(None) as conn:
        gacha._insert_items(conn, "100000001", [_item("3", "301", "Existing", "4")])

    code, payload = _run_json(["gacha", "refresh", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["inserted"] == 2
    assert payload["data"]["duplicates"] == 1
    with state_db(None) as conn:
        ids = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM gacha_items WHERE uid = ? ORDER BY CAST(id AS INTEGER)",
                ("100000001",),
            )
        ]
    assert ids == ["1", "2", "3"]


def test_gacha_refresh_delays_after_terminal_pages(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.gacha.provider_for_region", _empty_refresh_provider)
    sleeps: list[float] = []
    monkeypatch.setattr(gacha.time, "sleep", sleeps.append)
    SecretStore().set_secret(
        "gacha_url",
        "100000001",
        "https://example.test/getGachaLog?authkey=secret-authkey&authkey_ver=1",
    )

    code, payload = _run_json(["gacha", "refresh", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["fetched"] == 0
    assert sleeps == [gacha.GACHA_REFRESH_REQUEST_DELAY_SECONDS] * len(gacha.GACHA_TYPES)


def test_gacha_refresh_auto_refreshes_expired_authkey(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    provider = _auto_refresh_authkey_provider()
    monkeypatch.setattr(
        "gsuid_cli.commands.gacha.provider_for_region",
        lambda _region, _http_client: provider,
    )
    _disable_gacha_refresh_sleep(monkeypatch)
    store = SecretStore()
    store.set_secret(
        "gacha_url",
        "100000001",
        "https://example.test/getGachaLog?authkey=expired-secret",
    )
    store.set_secret("cookie", "100000001", "account_id=1;cookie_token=cookie-secret")
    store.set_secret("stoken", "100000001", "stuid=1;stoken=stoken-secret")

    code, payload = _run_json(["gacha", "refresh", "--uid", "100000001"])

    raw = json.dumps(payload, ensure_ascii=False)
    assert code == 0
    assert payload["data"]["inserted"] == 2
    assert payload["data"]["credential_source"] == "keyring"
    assert payload["warnings"] == ["gacha authkey expired; refreshed automatically"]
    assert provider.generated == 1
    assert any("expired-secret" in url for url in provider.gacha_urls)
    assert any("fresh-authkey" in url for url in provider.gacha_urls)
    assert "fresh-authkey" in (store.get_secret("gacha_url", "100000001") or "")
    assert "expired-secret" not in raw
    assert "fresh-authkey" not in raw
    assert "cookie-secret" not in raw
    assert "stoken-secret" not in raw


def test_gacha_refresh_expired_authkey_requires_recovery_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.gacha.provider_for_region", _expired_provider)
    SecretStore().set_secret(
        "gacha_url",
        "100000001",
        "https://example.test/getGachaLog?authkey=expired-secret",
    )

    code, payload = _run_json(["gacha", "refresh", "--uid", "100000001"])

    assert code == 2
    assert payload["error"]["code"] == "AUTH_REQUIRED"
    assert payload["error"]["details"]["credential_type"] == "cookie"
    raw = json.dumps(payload, ensure_ascii=False)
    assert "expired-secret" not in raw
    assert "cret" not in raw


def test_mys_gacha_log_page_uses_api_endpoint_for_webstatic_authkey_url() -> None:
    captured: dict[str, httpx.Request] = {}
    provider = MysProvider(
        _mock_client(
            lambda request: (
                _capture_request(captured, request),
                httpx.Response(
                    200,
                    json={"retcode": -100, "message": "authkey timeout", "data": None},
                ),
            )[1]
        )
    )

    with pytest.raises(CliError) as exc:
        provider.gacha_log_page(
            uid="100000001",
            authkey_url=(
                "https://webstatic.mihoyo.com/hk4e/event/e20190909gacha-v3/index.html"
                "?authkey=secret-authkey&authkey_ver=1"
            ),
            region="cn",
            gacha_type="301",
            page=1,
            end_id="0",
        )

    assert exc.value.code == "AUTH_EXPIRED"
    assert captured["request"].url.path == "/gacha_info/api/getGachaLog"
    assert "secret-authkey" not in json.dumps(exc.value.details, ensure_ascii=False)


def test_mys_gacha_log_page_sanitizes_expired_authkey() -> None:
    provider = MysProvider(
        _mock_client(
            lambda _request: httpx.Response(
                200,
                json={"retcode": -100, "message": "authkey timeout", "data": None},
            )
        )
    )

    with pytest.raises(CliError) as exc:
        provider.gacha_log_page(
            uid="100000001",
            authkey_url="https://example.test/getGachaLog?authkey=secret-authkey&authkey_ver=1",
            region="cn",
            gacha_type="301",
            page=1,
            end_id="0",
        )

    assert exc.value.code == "AUTH_EXPIRED"
    assert "secret-authkey" not in json.dumps(exc.value.details, ensure_ascii=False)


def test_mys_gacha_authkey_generation_uses_stoken_endpoint() -> None:
    captured: dict[str, httpx.Request] = {}
    provider = MysProvider(
        _mock_client(
            lambda request: (
                _capture_request(captured, request),
                httpx.Response(
                    200,
                    json={
                        "retcode": 0,
                        "message": "OK",
                        "data": {"authkey": "secret auth/key=="},
                    },
                ),
            )[1]
        )
    )

    result = provider.generate_gacha_authkey_url(
        uid="100000001",
        cookie="account_id=1;cookie_token=cookie-secret",
        stoken="stuid=1;stoken=stoken-secret",
        region="cn",
    )

    request = captured["request"]
    body = json.loads(request.content)
    query = parse_qs(urlsplit(str(result.data["gacha_url"])).query)
    assert request.method == "POST"
    assert request.url.path == "/binding/api/genAuthKey"
    assert body == {
        "auth_appid": "webview_gacha",
        "game_biz": "hk4e_cn",
        "game_uid": "100000001",
        "region": "cn_gf01",
    }
    assert request.headers["cookie"] == "stuid=1;stoken=stoken-secret"
    assert request.headers["x-rpc-client_type"] == "5"
    assert request.headers["x-rpc-device_model"] == "Mi 10"
    assert query["authkey"] == ["secret auth/key=="]
    assert query["region"] == ["cn_gf01"]
    assert query["auth_appid"] == ["webview_gacha"]


def _capture_request(captured: dict[str, httpx.Request], request: httpx.Request) -> None:
    captured["request"] = request


def _run_json(argv: list[str]) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    assert stderr.getvalue() == ""
    return code, json.loads(stdout.getvalue())


def _disable_gacha_refresh_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gacha, "GACHA_REFRESH_REQUEST_DELAY_SECONDS", 0)
    monkeypatch.setattr(gacha, "GACHA_REFRESH_CONTINUE_DELAY_SECONDS", 0)


def _refresh_provider(_region: str, _http_client: HttpClient):
    class FakeProvider:
        def gacha_log_page(
            self,
            *,
            uid: str,
            authkey_url: str,
            region: str,
            gacha_type: str,
            page: int,
            end_id: str,
        ) -> CommandResult:
            assert uid == "100000001"
            assert "secret-authkey" in authkey_url
            assert region == "cn"
            if gacha_type == "301" and page == 1:
                assert end_id == "0"
                items = _items()[:2]
                del items[0]["item_id"]
                return CommandResult(data={"list": items}, source=_source())
            return CommandResult(data={"list": []}, source=_source())

    return FakeProvider()


def _empty_refresh_provider(_region: str, _http_client: HttpClient):
    class FakeProvider:
        def gacha_log_page(
            self,
            *,
            uid: str,
            authkey_url: str,
            region: str,
            gacha_type: str,
            page: int,
            end_id: str,
        ) -> CommandResult:
            assert uid == "100000001"
            assert "secret-authkey" in authkey_url
            assert region == "cn"
            assert gacha_type in gacha.GACHA_TYPES
            assert page == 1
            assert end_id == "0"
            return CommandResult(data={"list": []}, source=_source())

    return FakeProvider()


def _gap_refresh_provider(_region: str, _http_client: HttpClient):
    class FakeProvider:
        def gacha_log_page(
            self,
            *,
            uid: str,
            authkey_url: str,
            region: str,
            gacha_type: str,
            page: int,
            end_id: str,
        ) -> CommandResult:
            assert uid == "100000001"
            assert "secret-authkey" in authkey_url
            assert region == "cn"
            if gacha_type == "301" and page == 1:
                assert end_id == "0"
                return CommandResult(
                    data={
                        "list": [
                            _item("3", "301", "Existing", "4"),
                            _item("2", "301", "Venti", "5"),
                        ]
                    },
                    source=_source(),
                )
            if gacha_type == "301" and page == 2:
                assert end_id == "2"
                return CommandResult(
                    data={"list": [_item("1", "301", "Noelle", "4")]},
                    source=_source(),
                )
            return CommandResult(data={"list": []}, source=_source())

    return FakeProvider()


def _expired_provider(_region: str, _http_client: HttpClient):
    class ExpiredProvider:
        def gacha_log_page(self, **_kwargs) -> CommandResult:
            raise CliError(
                "UPSTREAM_REJECTED",
                "Provider rejected the request.",
                EXIT_UPSTREAM,
                {
                    "provider": "mys",
                    "region": "cn",
                    "category": "gacha.refresh",
                    "retcode": -101,
                    "message": "authkey timeout",
                },
                retryable=False,
                source=_source(),
            )

    return ExpiredProvider()


def _auto_refresh_authkey_provider():
    class AutoRefreshAuthkeyProvider:
        def __init__(self) -> None:
            self.generated = 0
            self.gacha_urls: list[str] = []

        def generate_gacha_authkey_url(
            self,
            *,
            uid: str,
            cookie: str,
            stoken: str,
            region: str,
        ) -> CommandResult:
            assert uid == "100000001"
            assert cookie == "account_id=1;cookie_token=cookie-secret"
            assert stoken == "stuid=1;stoken=stoken-secret"
            assert region == "cn"
            self.generated += 1
            return CommandResult(
                data={
                    "uid": uid,
                    "server": "cn_gf01",
                    "game_biz": "hk4e_cn",
                    "auth_appid": "webview_gacha",
                    "account_id": "1",
                    "gacha_url": (
                        "https://public-operation-hk4e.mihoyo.com/gacha_info/api/getGachaLog"
                        "?authkey=fresh-authkey"
                    ),
                    "redacted": "[REDACTED_URL]",
                },
                source=_source(),
            )

        def gacha_log_page(
            self,
            *,
            uid: str,
            authkey_url: str,
            region: str,
            gacha_type: str,
            page: int,
            end_id: str,
        ) -> CommandResult:
            assert uid == "100000001"
            assert region == "cn"
            self.gacha_urls.append(authkey_url)
            if "expired-secret" in authkey_url:
                raise CliError(
                    "UPSTREAM_REJECTED",
                    "Provider rejected the request.",
                    EXIT_UPSTREAM,
                    {
                        "provider": "mys",
                        "region": "cn",
                        "category": "gacha.refresh",
                        "retcode": -101,
                        "message": "authkey timeout",
                    },
                    retryable=False,
                    source=_source(),
                )
            assert "fresh-authkey" in authkey_url
            if gacha_type == "301" and page == 1:
                assert end_id == "0"
                items = _items()[:2]
                del items[0]["item_id"]
                return CommandResult(data={"list": items}, source=_source())
            return CommandResult(data={"list": []}, source=_source())

    return AutoRefreshAuthkeyProvider()


def _authkey_provider(_region: str, _http_client: HttpClient):
    class FakeAuthkeyProvider:
        def generate_gacha_authkey_url(
            self,
            *,
            uid: str,
            cookie: str,
            stoken: str,
            region: str,
        ) -> CommandResult:
            assert uid == "100000001"
            assert cookie == "account_id=1;cookie_token=cookie-secret"
            assert stoken == "stuid=1;stoken=stoken-secret"
            assert region == "cn"
            return CommandResult(
                data={
                    "uid": uid,
                    "server": "cn_gf01",
                    "game_biz": "hk4e_cn",
                    "auth_appid": "webview_gacha",
                    "account_id": "1",
                    "gacha_url": (
                        "https://public-operation-hk4e.mihoyo.com/gacha_info/api/getGachaLog"
                        "?authkey=secret-authkey"
                    ),
                    "redacted": "[REDACTED_URL]",
                },
                source=_source(),
            )

    return FakeAuthkeyProvider()


def _source() -> dict[str, object]:
    return {
        "provider": "mys",
        "region": "cn",
        "cached": False,
        "fetched_at": "2026-04-29T10:30:00Z",
    }


def _mock_client(handler) -> HttpClient:
    return HttpClient(timeout=1, cache_policy="off", transport=httpx.MockTransport(handler))


def _uigf_v4() -> dict[str, object]:
    return {
        "info": {"version": "v4.0", "export_app": "test", "region_time_zone": 8},
        "hk4e": [{"uid": "100000001", "timezone": 8, "list": _items()}],
    }


def _items() -> list[dict[str, object]]:
    return [
        _item("1", "301", "Noelle", "4"),
        _item("2", "301", "Venti", "5"),
        _item("3", "302", "Skyward Harp", "5", item_type="Weapon"),
    ]


def _item(
    item_id: str,
    gacha_type: str,
    name: str,
    rank_type: str,
    *,
    item_type: str = "Character",
) -> dict[str, object]:
    return {
        "uid": "100000001",
        "gacha_type": gacha_type,
        "uigf_gacha_type": gacha_type,
        "item_id": item_id,
        "count": "1",
        "time": f"2026-04-29 12:00:0{item_id}",
        "name": name,
        "lang": "zh-cn",
        "item_type": item_type,
        "rank_type": rank_type,
        "id": item_id,
    }
