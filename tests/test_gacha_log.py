from __future__ import annotations

import io
import json
import sqlite3

import httpx
import pytest

from gsuid_cli.cli import run
from gsuid_cli.core.errors import EXIT_AUTH, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.secrets import SecretStore
from gsuid_cli.core.state import state_db
from gsuid_cli.providers.mys import MysProvider


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


def test_gacha_refresh_expired_authkey_is_sanitized(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.gacha.provider_for_region", _expired_provider)
    SecretStore().set_secret(
        "gacha_url",
        "100000001",
        "https://example.test/getGachaLog?authkey=expired-secret",
    )

    code, payload = _run_json(["gacha", "refresh", "--uid", "100000001"])

    assert code == 2
    assert payload["error"]["code"] == "AUTH_EXPIRED"
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


def _capture_request(captured: dict[str, httpx.Request], request: httpx.Request) -> None:
    captured["request"] = request


def _run_json(argv: list[str]) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    assert stderr.getvalue() == ""
    return code, json.loads(stdout.getvalue())


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
                return CommandResult(data={"list": _items()[:2]}, source=_source())
            return CommandResult(data={"list": []}, source=_source())

    return FakeProvider()


def _expired_provider(_region: str, _http_client: HttpClient):
    class ExpiredProvider:
        def gacha_log_page(self, **_kwargs) -> CommandResult:
            raise CliError(
                "AUTH_EXPIRED",
                "The gacha authkey URL is expired or rejected by the provider.",
                EXIT_AUTH,
            )

    return ExpiredProvider()


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
