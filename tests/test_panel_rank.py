from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from argparse import Namespace
from pathlib import Path

import httpx
from PIL import Image

from gsuid_cli.cli import run
from gsuid_cli.commands import panel as panel_commands
from gsuid_cli.commands.panel import _refresh_cache_policy
from gsuid_cli.commands.panel_cache import find_avatar, normalized_avatar
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.state import state_db
from gsuid_cli.providers.enka import EnkaProvider
from gsuid_cli.renderers.panel_metrics import (
    _action_damage,
    _base_area,
    panel_reference_metrics,
)


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
    assert payload["data"]["panel"]["fight_props"]["anemo_bonus"] == 61.6
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
    assert payload["data"]["artifacts"][0]["character"] == "Venti"

    code, payload = _run_json(["panel", "graduation", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["count"] == 2
    assert payload["data"]["characters"][0]["name"] == "Amber"
    assert payload["data"]["characters"][0]["graduation_score"] is None
    assert payload["warnings"]


def test_panel_show_render_image_writes_card(monkeypatch, tmp_path) -> None:
    captured_urls: list[str] = []
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)
    monkeypatch.setattr(panel_commands, "fetch_render_images", _fake_image_fetcher(captured_urls))
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")

    code, _payload = _run_json(["panel", "refresh", "--uid", "100000001"])
    assert code == 0

    code, payload = _run_json(
        [
            "--request-id",
            "panel-img",
            "--output-dir",
            str(tmp_path / "artifacts"),
            "panel",
            "show",
            "--uid",
            "100000001",
            "--character",
            "Amber",
            "--render",
            "image",
        ]
    )

    assert code == 0
    assert payload["command"] == "panel.show"
    assert payload["data"] == {
        "uid": "100000001",
        "character": "Amber",
        "render": "panel/show",
        "artifact_sha256": payload["artifacts"][0]["sha256"],
    }
    assert captured_urls == [
        "https://example.test/GenshinUID/resource/gacha_img/Amber.png",
        "https://example.test/GenshinUID/resource/chars/10000021.png",
        "https://example.test/GenshinUID/resource/weapon/Favonius%20Warbow.png",
    ]
    artifact = payload["artifacts"][0]
    path = Path(artifact["path"])
    content = path.read_bytes()
    assert path.parent == tmp_path / "artifacts" / "2026-04-29" / "panel-img"
    assert artifact["media_type"] == "image/png"
    assert artifact["sha256"] == hashlib.sha256(content).hexdigest()
    with Image.open(path) as image:
        assert image.size == (950, 1850)
        assert image.getbbox() is not None


def test_panel_show_render_both_preserves_structured_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)
    monkeypatch.setattr(panel_commands, "fetch_render_images", _fake_image_fetcher([]))

    code, _payload = _run_json(["panel", "refresh", "--uid", "100000001"])
    assert code == 0

    code, payload = _run_json(
        ["panel", "show", "--uid", "100000001", "--character", "Amber", "--render", "both"]
    )

    assert code == 0
    assert payload["data"]["panel"]["name"] == "Amber"
    assert payload["data"]["render"] == "panel/show"
    assert payload["data"]["artifact_sha256"] == payload["artifacts"][0]["sha256"]


def test_panel_compare_artifacts_showcase_render_images(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)
    monkeypatch.setattr(panel_commands, "fetch_render_images", _fake_image_fetcher([]))

    code, _payload = _run_json(["panel", "refresh", "--uid", "100000001"])
    assert code == 0

    cases = [
        (
            [
                "panel",
                "compare",
                "--uid",
                "100000001",
                "--build",
                "Amber",
                "--build",
                "Venti",
                "--render",
                "image",
            ],
            "panel.compare",
            "panel/compare",
            (1900, 1850),
        ),
        (
            ["panel", "artifacts", "--uid", "100000001", "--render", "image"],
            "panel.artifacts",
            "panel/artifacts",
            (1300, 2450),
        ),
        (
            ["panel", "showcase", "--uid", "100000001", "--render", "image"],
            "panel.showcase",
            "panel/showcase",
            (1950, 1330),
        ),
    ]

    for argv, command, render, size in cases:
        code, payload = _run_json([*argv, "--output-dir", str(tmp_path / command)])

        assert code == 0
        assert payload["command"] == command
        assert payload["data"]["render"] == render
        assert payload["data"]["artifact_sha256"] == payload["artifacts"][0]["sha256"]
        with Image.open(payload["artifacts"][0]["path"]) as image:
            assert image.size == size
            assert image.getbbox() is not None


def test_panel_showcase_render_both_preserves_structured_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)
    monkeypatch.setattr(panel_commands, "fetch_render_images", _fake_image_fetcher([]))

    code, _payload = _run_json(["panel", "refresh", "--uid", "100000001"])
    assert code == 0

    code, payload = _run_json(["panel", "showcase", "--uid", "100000001", "--render", "both"])

    assert code == 0
    assert payload["data"]["showcase"][0]["name"] == "Amber"
    assert payload["data"]["render"] == "panel/showcase"
    assert payload["data"]["artifact_sha256"] == payload["artifacts"][0]["sha256"]


def test_panel_artifacts_render_both_uses_image_order(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)
    monkeypatch.setattr(panel_commands, "fetch_render_images", _fake_image_fetcher([]))

    code, _payload = _run_json(["panel", "refresh", "--uid", "100000001"])
    assert code == 0

    code, payload = _run_json(["panel", "artifacts", "--uid", "100000001", "--render", "both"])

    assert code == 0
    assert payload["data"]["artifacts"][0]["character"] == "Venti"
    assert payload["data"]["artifacts"][0]["score"] == 20.0
    assert payload["data"]["render"] == "panel/artifacts"
    assert payload["data"]["artifact_sha256"] == payload["artifacts"][0]["sha256"]


def test_panel_normalization_uses_genshinuid_text_maps() -> None:
    assert (
        find_avatar({"uid": "100000001", "avatars": [{"avatarId": 10000022}]}, "温迪")["avatarId"]
        == 10000022
    )

    panel = normalized_avatar(
        {
            "avatarId": 10000022,
            "equipList": [
                {
                    "itemId": 15416,
                    "weapon": {"level": 90},
                    "flat": {
                        "itemType": "ITEM_WEAPON",
                        "nameTextMapHash": "1860795787",
                        "rankLevel": 4,
                        "weaponStats": [],
                    },
                },
                {
                    "itemId": 76543,
                    "reliquary": {"level": 21},
                    "flat": {
                        "itemType": "ITEM_RELIQUARY",
                        "icon": "UI_RelicIcon_15002_4",
                        "equipType": "EQUIP_BRACER",
                        "rankLevel": 5,
                        "reliquaryMainstat": {},
                        "reliquarySubstats": [],
                    },
                },
            ],
        }
    )

    assert panel["name"] == "温迪"
    assert panel["weapon"]["name"] == "曚云之月"
    assert panel["artifacts"][0]["name"] == "野花记忆的绿野"
    assert panel["artifacts"][0]["set_name"] == "翠绿之影"


def test_panel_metrics_match_genshinuid_reference_counts() -> None:
    avatar = _venti_reference_avatar()
    panel = normalized_avatar(avatar)

    metrics = panel_reference_metrics(avatar, panel)
    rows = {str(row["action"]): row for row in metrics["damage_rows"]}

    assert metrics["effective_stat_count"] == 22.25
    assert metrics["sequence_label"] == "终末|翠绿|精精精"
    assert 12.0 < metrics["graduation_percent"] < 12.2
    assert round(rows["A一段伤害"]["normal"]) == 335
    assert round(rows["A一段伤害"]["avg"]) == 638
    assert round(rows["A一段伤害"]["crit"]) == 773
    assert round(rows["A扩散伤害"]["normal"]) == 786
    assert round(rows["Q持续伤害"]["normal"]) == 1343
    assert round(rows["Q持续伤害"]["avg"]) == 2558
    assert round(rows["Q持续伤害"]["crit"]) == 3100


def test_panel_metric_damage_primitives_follow_genshinuid() -> None:
    avatar: dict[str, object] = {"avatarId": 10000023}
    panel: dict[str, object] = {"name": "香菱"}
    real_prop = {
        "E_atk": 1000.0,
        "E_skill_level": 1,
        "E_powerPlus": 1.0,
        "E_baseArea": 1.5,
        "E_dmgBonus": 0.0,
        "E_d": 0.0,
        "E_ignoreDef": 0.0,
        "E_critRate": 0.0,
        "E_critDmg": 1.0,
        "E_elementalMastery": 100.0,
        "extraBonus": 0.2,
        "a": 0.4,
        "sp": [],
    }

    normal, avg, crit = _action_damage(
        "E伤害(蒸发)",
        {"type": "攻击", "plus": 1, "value": ["100%"]},
        avatar,
        panel,
        real_prop,
        {"PyroResist": 0.0},
    )

    reaction = 1.5 * (1 + (2.78 * 100) / (100 + 1400) + 0.4)
    expected = 1000 * (1 + 0.2) * (1.5 - 1) * reaction * 0.5
    assert normal == expected
    assert avg == expected
    assert crit == expected * 2


def test_panel_metric_sp_base_uses_atk_and_elemental_mastery() -> None:
    base = _base_area(
        "E灭净三业伤害",
        {"type": "攻击", "plus": 1, "value": ["100%+200%"]},
        {"avatarId": 10000073},
        {"name": "纳西妲"},
        "E",
        {
            "E_atk": 1000.0,
            "E_skill_level": 1,
            "E_powerPlus": 1.0,
            "E_elementalMastery": 200.0,
        },
        {"addDmg": 5.0, "attack": 0.0, "dmgBonus": 0.0},
    )

    assert base == 1405.0


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
    assert version == 4


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


def _fake_image_fetcher(captured_urls: list[str]):
    def fetcher(args, urls, **_kwargs):
        unique_urls = list(dict.fromkeys(urls))
        captured_urls.extend(unique_urls)
        image = Image.new("RGBA", (512, 512), (220, 70, 50, 255))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return {url: buffer.getvalue() for url in unique_urls}, []

    return fetcher


def _source() -> dict[str, object]:
    return {
        "provider": "enka",
        "region": "cn",
        "cached": False,
        "fetched_at": "2026-04-29T10:30:00Z",
    }


def _venti_reference_avatar() -> dict[str, object]:
    return {
        "avatarId": 10000022,
        "propMap": {"4001": {"val": "90"}},
        "fetterInfo": {"expLevel": 10},
        "skillLevelMap": {"10221": 1, "10224": 9, "10225": 10},
        "talentIdList": [],
        "fightPropMap": {
            "1": 10531.4833984375,
            "4": 827.8800048828125,
            "7": 668.642333984375,
            "20": 0.6915,
            "22": 1.308,
            "23": 1.32,
            "26": 0,
            "28": 0,
            "30": 0,
            "44": 0.616,
            "2000": 17837.90625,
            "2001": 1824.848876953125,
            "2002": 855.5031127929688,
        },
        "equipList": [
            _venti_artifact(
                item_id=76543,
                icon="UI_RelicIcon_15002_4",
                slot="EQUIP_BRACER",
                main_prop="FIGHT_PROP_HP",
                main_value=4780,
                substats=[
                    ("FIGHT_PROP_ATTACK", 35),
                    ("FIGHT_PROP_DEFENSE", 23),
                    ("FIGHT_PROP_CRITICAL_HURT", 17.1),
                    ("FIGHT_PROP_CRITICAL", 5.8),
                ],
            ),
            _venti_artifact(
                item_id=76523,
                icon="UI_RelicIcon_15002_2",
                slot="EQUIP_NECKLACE",
                main_prop="FIGHT_PROP_ATTACK",
                main_value=311,
                substats=[
                    ("FIGHT_PROP_DEFENSE_PERCENT", 5.1),
                    ("FIGHT_PROP_CRITICAL", 10.1),
                    ("FIGHT_PROP_CRITICAL_HURT", 14.8),
                    ("FIGHT_PROP_HP_PERCENT", 11.1),
                ],
            ),
            _venti_artifact(
                item_id=76553,
                icon="UI_RelicIcon_15002_5",
                slot="EQUIP_SHOES",
                main_prop="FIGHT_PROP_ATTACK_PERCENT",
                main_value=46.6,
                substats=[
                    ("FIGHT_PROP_CRITICAL", 13.6),
                    ("FIGHT_PROP_ATTACK", 18),
                    ("FIGHT_PROP_CRITICAL_HURT", 7),
                    ("FIGHT_PROP_DEFENSE", 44),
                ],
            ),
            _venti_artifact(
                item_id=76513,
                icon="UI_RelicIcon_15002_1",
                slot="EQUIP_RING",
                main_prop="FIGHT_PROP_WIND_ADD_HURT",
                main_value=46.6,
                substats=[
                    ("FIGHT_PROP_DEFENSE", 53),
                    ("FIGHT_PROP_CRITICAL", 3.5),
                    ("FIGHT_PROP_CRITICAL_HURT", 20.2),
                    ("FIGHT_PROP_HP_PERCENT", 5.3),
                ],
            ),
            _venti_artifact(
                item_id=93534,
                icon="UI_RelicIcon_15019_3",
                slot="EQUIP_DRESS",
                main_prop="FIGHT_PROP_CRITICAL",
                main_value=31.1,
                substats=[
                    ("FIGHT_PROP_CRITICAL_HURT", 21.8),
                    ("FIGHT_PROP_DEFENSE", 32),
                    ("FIGHT_PROP_HP", 807),
                    ("FIGHT_PROP_ATTACK", 19),
                ],
            ),
            {
                "itemId": 15416,
                "weapon": {"level": 90, "affixMap": {"154161": 4}},
                "flat": {
                    "itemType": "ITEM_WEAPON",
                    "nameTextMapHash": "1860795787",
                    "rankLevel": 4,
                    "weaponStats": [
                        {"appendPropId": "FIGHT_PROP_BASE_ATTACK", "statValue": 565},
                        {"appendPropId": "FIGHT_PROP_ATTACK_PERCENT", "statValue": 27.6},
                    ],
                },
            },
        ],
    }


def _venti_artifact(
    *,
    item_id: int,
    icon: str,
    slot: str,
    main_prop: str,
    main_value: float,
    substats: list[tuple[str, float]],
) -> dict[str, object]:
    return {
        "itemId": item_id,
        "reliquary": {"level": 21},
        "flat": {
            "itemType": "ITEM_RELIQUARY",
            "icon": icon,
            "equipType": slot,
            "rankLevel": 5,
            "reliquaryMainstat": {"mainPropId": main_prop, "statValue": main_value},
            "reliquarySubstats": [
                {"appendPropId": prop, "statValue": value} for prop, value in substats
            ],
        },
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
        "fightPropMap": {"20": 0.5, "22": 1.0, "4": 800, "44": 0.616},
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
