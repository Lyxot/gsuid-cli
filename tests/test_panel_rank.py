from __future__ import annotations

import io
import json
import sqlite3
from argparse import Namespace

import httpx

from gsuid_cli.cli import run
from gsuid_cli.commands.panel import _refresh_cache_policy
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.state import state_db
from gsuid_cli.providers.enka import EnkaProvider


def test_panel_refresh_list_show_compare_and_save(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)

    code, payload = _run_json(["panel", "refresh", "--uid", "100000001"])

    assert code == 0
    assert payload["command"] == "panel.refresh"
    assert payload["data"]["character_count"] == 2
    assert payload["data"]["cache"]["backend"] == "sqlite"
    assert payload["data"]["failures"] == []
    assert payload["source"]["provider"] == "enka"

    code, payload = _run_json(["panel", "list", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["count"] == 2
    assert payload["data"]["characters"][0]["name"] == "Amber"
    assert payload["source"]["cached"] is True

    code, payload = _run_json(
        [
            "panel",
            "show",
            "--uid",
            "100000001",
            "--character",
            "Amber",
            "--constellation",
            "4",
        ]
    )

    assert code == 0
    assert payload["warnings"] == ["typed panel overrides are recorded but not applied yet"]
    assert payload["data"]["panel"]["weapon"]["name"] == "Favonius Warbow"
    assert payload["data"]["panel"]["artifact_score"] == 25.6
    assert payload["data"]["panel"]["fight_props"]["crit_rate"] == 50.0
    assert payload["data"]["panel"]["fight_props"]["crit_damage"] == 100.0
    assert payload["data"]["panel"]["fight_props"]["base_atk"] == 800
    assert payload["data"]["requested_overrides"]["constellation"] == 4

    code, payload = _run_json(
        [
            "panel",
            "compare",
            "--uid",
            "100000001",
            "--build",
            "Amber",
            "--build",
            "Venti",
        ]
    )

    assert code == 0
    assert payload["data"]["baseline"]["panel"]["name"] == "Amber"
    assert payload["data"]["deltas"][0]["artifact_score"] == -5.6

    output = tmp_path / "amber-panel.json"
    code, payload = _run_json(
        [
            "--request-id",
            "panel-save",
            "panel",
            "save",
            "--uid",
            "100000001",
            "--character",
            "Amber",
            "--name",
            "amber",
            "--output",
            str(output),
        ]
    )

    assert code == 0
    assert payload["artifacts"][0]["path"] == str(output.resolve())
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["panel"]["name"] == "Amber"

    code, payload = _run_json(["panel", "artifacts", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["total_count"] == 3
    assert payload["data"]["artifacts"][0]["character"] == "Amber"

    code, payload = _run_json(["panel", "graduation", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["count"] == 2
    assert payload["data"]["characters"][0]["name"] == "Amber"
    assert payload["data"]["characters"][0]["graduation_score"] is None
    assert payload["warnings"]


def test_panel_missing_cache_returns_no_result(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    code, payload = _run_json(["panel", "list", "--uid", "100000001"])

    assert code == 6
    assert payload["command"] == "panel.list"
    assert payload["error"]["code"] == "NO_RESULT"


def test_panel_refresh_rejects_mys_source(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    code, payload = _run_json(["panel", "refresh", "--uid", "100000001", "--source", "mys"])

    assert code == 1
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_panel_compare_requires_two_builds(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    code, payload = _run_json(["panel", "compare", "--uid", "100000001", "--build", "Amber"])

    assert code == 1
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_panel_artifacts_rejects_invalid_page(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    code, payload = _run_json(["panel", "artifacts", "--uid", "100000001", "--page", "0"])

    assert code == 1
    assert payload["command"] == "panel.artifacts"
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_panel_refresh_fetches_fresh_by_default() -> None:
    assert _refresh_cache_policy(Namespace(force=False, cache="use")) == "refresh"
    assert _refresh_cache_policy(Namespace(force=True, cache="only")) == "only"
    assert _refresh_cache_policy(Namespace(force=True, cache="off")) == "off"
    assert _refresh_cache_policy(Namespace(force=False, cache="only")) == "only"
    assert _refresh_cache_policy(Namespace(force=False, cache="off")) == "off"


def test_rank_commands_use_local_panel_cache(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)

    code, _payload = _run_json(["panel", "refresh", "--uid", "100000001"])
    assert code == 0

    code, payload = _run_json(["rank", "summary", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["source"] == "local-panel-cache"
    assert payload["data"]["character_count"] == 2
    assert payload["data"]["max_artifact_score"] == 25.6

    code, payload = _run_json(["rank", "list", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["characters"][0]["name"] == "Amber"

    code, payload = _run_json(
        ["rank", "character", "--uid", "100000001", "--character", "Venti", "--nearby"]
    )

    assert code == 0
    assert payload["warnings"] == ["nearby rank lookup is not implemented for local cache rankings"]
    assert payload["data"]["rank"]["name"] == "Venti"
    assert payload["data"]["rank"]["percentile"] is None

    code, payload = _run_json(["rank", "artifact", "--uid", "100000001", "--character", "Amber"])

    assert code == 0
    assert payload["data"]["count"] == 2
    assert payload["data"]["artifacts"][0]["score"] == 15.6

    code, payload = _run_json(
        ["rank", "artifact", "--uid", "100000001", "--character", "Amber", "--sort", "crit-rate"]
    )

    assert code == 0
    assert payload["data"]["artifacts"][0]["name"] == "Amber Plume"


def test_state_v2_migrates_to_panel_cache(monkeypatch, tmp_path) -> None:
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
            uigf_gacha_type TEXT,
            item_id TEXT,
            count INTEGER NOT NULL DEFAULT 1,
            time TEXT NOT NULL,
            name TEXT NOT NULL,
            lang TEXT,
            item_type TEXT,
            rank_type TEXT,
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
        INSERT INTO profiles(name, default_uid, default_region, created_at, updated_at)
        VALUES('default', NULL, 'cn', 'now', 'now');
        PRAGMA user_version = 2;
        """
    )
    conn.close()
    monkeypatch.setenv("GSUID_HOME", str(home))

    with state_db(None) as migrated:
        panel_table = migrated.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='panel_cache'"
        ).fetchone()
        version = migrated.execute("PRAGMA user_version").fetchone()[0]

    assert panel_table["name"] == "panel_cache"
    assert version == 3


def test_enka_provider_uses_canonical_uid_endpoint() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=_enka_payload())

    provider = EnkaProvider(
        HttpClient(timeout=1, cache_policy="off", transport=httpx.MockTransport(handler))
    )

    result = provider.profile(uid="100000001", region="cn")

    assert result.data["playerInfo"]["nickname"] == "Traveler"
    assert captured["request"].url.path == "/api/uid/100000001"
    assert captured["request"].headers["user-agent"].startswith("gsuid-cli/")


class FakeEnkaProvider:
    def __init__(self, _http_client) -> None:
        pass

    def profile(self, *, uid: str, region: str) -> CommandResult:
        assert uid == "100000001"
        assert region == "cn"
        return CommandResult(data=_enka_payload(), source=_source())


def _run_json(argv: list[str]) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    assert stderr.getvalue() == ""
    return code, json.loads(stdout.getvalue())


def _source() -> dict[str, object]:
    return {
        "provider": "enka",
        "region": "cn",
        "cached": False,
        "fetched_at": "2026-04-29T10:30:00Z",
    }


def _enka_payload() -> dict[str, object]:
    return {
        "uid": "100000001",
        "ttl": 300,
        "playerInfo": {
            "nickname": "Traveler",
            "level": 60,
            "worldLevel": 8,
            "finishAchievementNum": 900,
        },
        "avatarInfoList": [
            _avatar(
                avatar_id=10000021,
                name="Amber",
                level=80,
                weapon="Favonius Warbow",
                substats=[
                    ("FIGHT_PROP_CRITICAL", 3.9),
                    ("FIGHT_PROP_CRITICAL_HURT", 7.8),
                ],
                extra_artifact_score=10.0,
            ),
            _avatar(
                avatar_id=10000022,
                name="Venti",
                level=90,
                weapon="Elegy for the End",
                substats=[
                    ("FIGHT_PROP_CRITICAL", 5.0),
                    ("FIGHT_PROP_CRITICAL_HURT", 10.0),
                ],
                extra_artifact_score=0.0,
            ),
        ],
    }


def _avatar(
    *,
    avatar_id: int,
    name: str,
    level: int,
    weapon: str,
    substats: list[tuple[str, float]],
    extra_artifact_score: float,
) -> dict[str, object]:
    artifacts = [
        {
            "itemId": avatar_id * 10,
            "reliquary": {"level": 20},
            "flat": {
                "name": f"{name} Flower",
                "itemType": "ITEM_RELIQUARY",
                "equipType": "EQUIP_BRACER",
                "rankLevel": 5,
                "reliquarySubstats": [
                    {"appendPropId": prop, "statValue": value} for prop, value in substats
                ],
            },
        }
    ]
    if extra_artifact_score:
        artifacts.append(
            {
                "itemId": avatar_id * 10 + 1,
                "reliquary": {"level": 20},
                "flat": {
                    "name": f"{name} Plume",
                    "itemType": "ITEM_RELIQUARY",
                    "equipType": "EQUIP_NECKLACE",
                    "rankLevel": 5,
                    "reliquarySubstats": [
                        {"appendPropId": "FIGHT_PROP_CRITICAL", "statValue": 5.0}
                    ],
                },
            }
        )
    return {
        "avatarId": avatar_id,
        "name": name,
        "level": level,
        "talentIdList": [1, 2],
        "fetterInfo": {"expLevel": 10},
        "fightPropMap": {"20": 0.5, "22": 1.0, "4": 800},
        "equipList": [
            {
                "itemId": avatar_id,
                "weapon": {"level": 90},
                "flat": {
                    "name": weapon,
                    "itemType": "ITEM_WEAPON",
                    "rankLevel": 4,
                    "weaponStats": [{"appendPropId": "FIGHT_PROP_ATTACK_PERCENT"}],
                },
            },
            *artifacts,
        ],
    }
