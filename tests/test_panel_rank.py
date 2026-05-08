from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from argparse import Namespace
from pathlib import Path

import httpx
from helpers import run_json as _run_json
from PIL import Image

from gsuid_cli.cli import run
from gsuid_cli.commands import panel as panel_commands
from gsuid_cli.commands import rank as rank_commands
from gsuid_cli.commands.panel import _refresh_cache_policy
from gsuid_cli.commands.panel_cache import find_avatar, normalized_avatar
from gsuid_cli.core.errors import EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.secrets import SecretStore
from gsuid_cli.core.state import state_db
from gsuid_cli.providers.akasha import AkashaProvider
from gsuid_cli.providers.enka import EnkaProvider
from gsuid_cli.renderers.panel import render_panel_compare_text, render_panel_graduation
from gsuid_cli.renderers.panel.metrics import (
    _action_damage,
    _base_area,
    panel_reference_metrics,
)
from gsuid_cli.renderers.rank_text import render_rank_artifact_text


def test_panel_refresh_list_show_compare_and_save(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)

    code, payload = _run_json(["panel", "refresh", "--uid", "100000001"])

    assert code == 0
    assert payload["command"] == "panel.refresh"
    assert payload["data"]["character_count"] == 2
    assert payload["data"]["cache"]["backend"] == "sqlite"
    assert payload["data"]["failures"] == []
    assert payload["sources"][0]["provider"] == "enka"

    code, payload = _run_json(["panel", "list", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["count"] == 2
    assert payload["data"]["characters"][0]["name"] == "安柏"
    assert payload["sources"][0]["cached"] is True

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
    assert payload["data"]["panel"]["weapon"]["name"] == "西风猎弓"
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
    assert payload["data"]["baseline"]["panel"]["name"] == "安柏"
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
    assert saved["panel"]["name"] == "安柏"

    code, payload = _run_json(["panel", "artifacts", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["total_count"] == 3
    assert payload["data"]["artifacts"][0]["character"] == "温迪"

    code, payload = _run_json(["panel", "graduation", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["count"] == 2
    assert payload["data"]["characters"][0]["name"] == "安柏"
    assert payload["data"]["characters"][0]["graduation_score"] is not None
    assert payload["warnings"] == []


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
        "character": "安柏",
        "render": "panel/show",
        "artifact_sha256": payload["artifacts"][0]["sha256"],
    }
    assert captured_urls == [
        "genshinuid://resource/gacha_img/%E5%AE%89%E6%9F%8F.png",
        "genshinuid://resource/chars/10000021.png",
        "genshinuid://resource/weapon/%E8%A5%BF%E9%A3%8E%E7%8C%8E%E5%BC%93.png",
        "https://enka.network/ui/UI_RelicIcon_15002_4.png",
        "https://enka.network/ui/UI_RelicIcon_15002_2.png",
    ]
    artifact = payload["artifacts"][0]
    path = Path(artifact["path"])
    content = path.read_bytes()
    assert path.parent == tmp_path / "artifacts" / "2026-04-29" / "panel-img"
    assert artifact["media_type"] == "image/png"
    assert artifact["sha256"] == hashlib.sha256(content).hexdigest()
    with Image.open(path) as image:
        assert image.size == (950, 2250)
        assert image.getbbox() is not None


def test_panel_show_render_data_image_preserves_structured_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)
    monkeypatch.setattr(panel_commands, "fetch_render_images", _fake_image_fetcher([]))

    code, _payload = _run_json(["panel", "refresh", "--uid", "100000001"])
    assert code == 0

    code, payload = _run_json(
        ["panel", "show", "--uid", "100000001", "--character", "Amber", "--render", "data,image"]
    )

    assert code == 0
    assert payload["data"]["panel"]["name"] == "安柏"
    assert payload["data"]["render"] == "panel/show"
    assert payload["data"]["artifact_sha256"] == payload["artifacts"][0]["sha256"]


def test_panel_text_renders_for_group(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)

    code, payload = _run_json(["panel", "refresh", "--uid", "100000001", "--render", "text"])

    assert code == 0
    assert payload["data"]["render"] == "panel/refresh-text"
    assert "面板缓存刷新" in _text_artifact(payload)

    cases = [
        (
            ["panel", "list", "--uid", "100000001", "--render", "text"],
            "panel/list-text",
            "面板列表",
        ),
        (
            ["panel", "show", "--uid", "100000001", "--character", "Amber", "--render", "text"],
            "panel/show-text",
            "角色面板 - 安柏",
        ),
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
                "text",
            ],
            "panel/compare-text",
            "面板对比",
        ),
        (
            [
                "panel",
                "save",
                "--uid",
                "100000001",
                "--character",
                "Amber",
                "--name",
                "amber",
                "--render",
                "text",
            ],
            "panel/save-text",
            "面板保存",
        ),
        (
            ["panel", "artifacts", "--uid", "100000001", "--render", "text"],
            "panel/artifacts-text",
            "圣遗物仓库",
        ),
        (
            ["panel", "showcase", "--uid", "100000001", "--render", "text"],
            "panel/showcase-text",
            "角色展柜",
        ),
        (
            ["panel", "graduation", "--uid", "100000001", "--render", "text"],
            "panel/graduation-text",
            "练度统计",
        ),
    ]

    for argv, render, text in cases:
        code, payload = _run_json(argv)

        assert code == 0
        assert payload["data"]["render"] == render
        assert text in _text_artifact(payload)


def test_panel_show_render_text_plain_prints_text(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)

    code, _payload = _run_json(["panel", "refresh", "--uid", "100000001"])
    assert code == 0

    code, stdout, stderr = _run_plain(
        [
            "panel",
            "show",
            "--uid",
            "100000001",
            "--character",
            "Amber",
            "--render",
            "text",
            "--format",
            "plain",
        ]
    )

    assert code == 0
    assert stderr == ""
    assert "角色面板 - 安柏" in stdout
    assert "圣遗物评分: 25.6" in stdout
    assert "西风猎弓" in stdout
    assert "主词条: 血量 4780" in stdout
    assert "副词条:" in stdout
    assert "伤害参考:" in stdout


def test_panel_compare_text_includes_elemental_deltas() -> None:
    text = render_panel_compare_text(
        {
            "baseline": {
                "uid": "100000001",
                "character": "Amber",
                "panel": {"artifact_score": 25.6},
            },
            "builds": [],
            "deltas": [
                {
                    "character": "Venti",
                    "artifact_score": -5.6,
                    "fight_props": {
                        "pyro_bonus": 10,
                        "electro_bonus": -5,
                        "dendro_bonus": 2.5,
                    },
                }
            ],
        }
    )

    assert "火伤加成: +10" in text
    assert "雷伤加成: -5" in text
    assert "草伤加成: +2.5" in text


def test_panel_show_render_text_image_keeps_image_primary(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)
    monkeypatch.setattr(panel_commands, "fetch_render_images", _fake_image_fetcher([]))

    code, _payload = _run_json(["panel", "refresh", "--uid", "100000001"])
    assert code == 0

    code, payload = _run_json(
        [
            "panel",
            "show",
            "--uid",
            "100000001",
            "--character",
            "Amber",
            "--render",
            "image,text",
        ]
    )

    assert code == 0
    image_artifact = next(
        artifact for artifact in payload["artifacts"] if artifact["kind"] == "image"
    )
    text_artifact = next(
        artifact for artifact in payload["artifacts"] if artifact["kind"] == "text"
    )
    assert payload["data"]["render"] == "panel/show"
    assert payload["data"]["artifact_sha256"] == image_artifact["sha256"]
    assert payload["data"]["text_artifact_sha256"] == text_artifact["sha256"]
    assert "角色面板 - 安柏" in Path(str(text_artifact["path"])).read_text(encoding="utf-8")


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
            (1900, 2250),
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
        (
            ["panel", "graduation", "--uid", "100000001", "--render", "image"],
            "panel.graduation",
            "panel/graduation",
            (1600, 920),
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


def test_panel_showcase_render_data_image_preserves_structured_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)
    monkeypatch.setattr(panel_commands, "fetch_render_images", _fake_image_fetcher([]))

    code, _payload = _run_json(["panel", "refresh", "--uid", "100000001"])
    assert code == 0

    code, payload = _run_json(["panel", "showcase", "--uid", "100000001", "--render", "data,image"])

    assert code == 0
    assert payload["data"]["showcase"][0]["name"] == "安柏"
    assert payload["data"]["render"] == "panel/showcase"
    assert payload["data"]["artifact_sha256"] == payload["artifacts"][0]["sha256"]


def test_panel_graduation_render_handles_three_column_mode() -> None:
    avatar_list = [
        _avatar(
            avatar_id=10000021 + index,
            name=f"Amber{index}",
            level=80,
            weapon="Favonius Warbow",
            substats=[("FIGHT_PROP_CRITICAL", 3.9), ("FIGHT_PROP_CRITICAL_HURT", 7.8)],
            extra_artifact_score=0.0,
        )
        for index in range(87)
    ]
    panels = [normalized_avatar(avatar) for avatar in avatar_list]

    png = render_panel_graduation(
        uid="100000001",
        player={"nickname": "Traveler"},
        avatars=avatar_list,
        panels=panels,
    )

    with Image.open(io.BytesIO(png)) as image:
        assert image.size[0] == 2370
        assert image.getbbox() is not None


def test_panel_graduation_title_player_uses_mys_challenge_stats(monkeypatch, tmp_path) -> None:
    class FakeMysProvider:
        def player_summary(self, **kwargs) -> CommandResult:
            assert kwargs["uid"] == "100000001"
            assert kwargs["cookie"] == "cookie"
            return CommandResult(
                data={
                    "summary": {
                        "stats": {
                            "spiral_abyss": "12-3",
                            "role_combat": {
                                "difficulty_id": 5,
                                "max_round_id": 10,
                                "tarot_finished_cnt": 2,
                            },
                            "hard_challenge": {"difficulty": 6, "name": "鏖战"},
                        },
                    }
                },
                source={"provider": "mys", "region": "cn", "cached": False},
            )

    monkeypatch.setattr(
        panel_commands,
        "_credential",
        lambda _args, _uid: ("cookie", "environment", None),
    )
    monkeypatch.setattr(
        panel_commands, "provider_for_region", lambda _region, _http: FakeMysProvider()
    )
    args = Namespace(timeout=1, cache="off", output_dir=str(tmp_path), debug=False)
    cache = {
        "uid": "100000001",
        "player_info": {
            "nickname": "Traveler",
            "towerFloorIndex": 11,
            "towerLevelIndex": 2,
        },
        "avatars": [],
    }

    player, warnings = panel_commands._graduation_title_player(
        args,
        uid="100000001",
        region="cn",
        cache=cache,
    )

    assert warnings == []
    assert player["abyss_floor"] == 12
    assert player["abyss_chamber"] == 3
    assert player["theater"]["max_round_id"] == 10
    assert player["stygian_index"] == 6
    assert player["hard_name"] == "鏖战"


def test_panel_artifacts_render_data_image_uses_image_order(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)
    monkeypatch.setattr(panel_commands, "fetch_render_images", _fake_image_fetcher([]))

    code, _payload = _run_json(["panel", "refresh", "--uid", "100000001"])
    assert code == 0

    code, payload = _run_json(
        ["panel", "artifacts", "--uid", "100000001", "--render", "data,image"]
    )

    assert code == 0
    assert payload["data"]["artifacts"][0]["character"] == "温迪"
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


def test_panel_refresh_mys_source_requires_cookie(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    code, payload = _run_json(["panel", "refresh", "--uid", "100000001", "--source", "mys"])

    assert code == 2
    assert payload["error"]["code"] == "AUTH_REQUIRED"


def test_panel_refresh_auto_fetches_mys_but_keeps_current_enka(monkeypatch, tmp_path) -> None:
    mys_provider = FakeMysPanelProvider()
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)
    monkeypatch.setattr(panel_commands, "provider_for_region", lambda _region, _http: mys_provider)
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(["panel", "refresh", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["source"] == "enka"
    assert payload["data"]["requested_source"] == "auto"
    assert [source["provider"] for source in payload["sources"]] == ["mys", "enka"]
    assert mys_provider.summary_calls == 1
    assert mys_provider.details_calls == 1


def test_panel_refresh_auto_uses_mys_when_enka_is_outdated(monkeypatch, tmp_path) -> None:
    mys_provider = FakeMysPanelProvider()
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", StaleFakeEnkaProvider)
    monkeypatch.setattr(panel_commands, "provider_for_region", lambda _region, _http: mys_provider)
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(["panel", "refresh", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["source"] == "enka+mys"
    assert payload["sources"][-1]["provider"] == "enka+mys"
    assert "MYS 替换过期角色" in payload["warnings"][0]
    assert "安柏" in payload["warnings"][0]
    assert "等级不一致" in payload["warnings"][0]


def test_panel_refresh_auto_adds_mys_only_characters(monkeypatch, tmp_path) -> None:
    mys_provider = FakeMysPanelProvider(extra_avatar=_xiangling_avatar())
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)
    monkeypatch.setattr(panel_commands, "provider_for_region", lambda _region, _http: mys_provider)
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(["panel", "refresh", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["source"] == "enka+mys"
    assert payload["data"]["character_count"] == 3
    assert "MYS 补充角色: 香菱" in payload["warnings"]

    code, payload = _run_json(["panel", "list", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["count"] == 3
    assert payload["data"]["characters"][2]["name"] == "香菱"


def test_panel_refresh_mys_keeps_matching_enka_cache(monkeypatch, tmp_path) -> None:
    mys_provider = FakeMysPanelProvider()
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)
    monkeypatch.setattr(panel_commands, "provider_for_region", lambda _region, _http: mys_provider)

    code, payload = _run_json(["panel", "refresh", "--uid", "100000001", "--source", "enka"])
    assert code == 0
    assert payload["data"]["source"] == "enka"

    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")
    code, payload = _run_json(["panel", "refresh", "--uid", "100000001", "--source", "mys"])

    assert code == 0
    assert payload["data"]["source"] == "enka"
    assert payload["data"]["cache"]["status"] == "unchanged"
    assert payload["sources"][-1]["provider"] == "enka"
    assert "保留已有面板缓存" in payload["warnings"][0]


def test_panel_refresh_mys_supplements_existing_enka_cache(monkeypatch, tmp_path) -> None:
    mys_provider = FakeMysPanelProvider(extra_avatar=_xiangling_avatar())
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)
    monkeypatch.setattr(panel_commands, "provider_for_region", lambda _region, _http: mys_provider)

    code, payload = _run_json(["panel", "refresh", "--uid", "100000001", "--source", "enka"])
    assert code == 0
    assert payload["data"]["source"] == "enka"

    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")
    code, payload = _run_json(["panel", "refresh", "--uid", "100000001", "--source", "mys"])

    assert code == 0
    assert payload["data"]["source"] == "enka+mys"
    assert payload["data"]["character_count"] == 3
    assert payload["data"]["cache"]["status"] == "updated"
    assert "MYS 补充角色: 香菱" in payload["warnings"]

    code, payload = _run_json(["panel", "refresh", "--uid", "100000001", "--source", "mys"])

    assert code == 0
    assert payload["data"]["source"] == "enka+mys"
    assert payload["data"]["cache"]["status"] == "unchanged"


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


def test_rank_commands_use_akasha_provider(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.rank.AkashaProvider", FakeAkashaProvider)
    monkeypatch.setattr(rank_commands, "fetch_render_images", _fake_image_fetcher([]))

    code, payload = _run_json(["rank", "list", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["characters"][0]["avatar_id"] == "10000022"
    assert payload["sources"][0]["provider"] == "akasha"

    code, payload = _run_json(["rank", "list", "--uid", "100000001", "--render", "image"])

    assert code == 0
    assert payload["data"]["render"] == "rank/list"
    assert payload["artifacts"][0]["media_type"] == "image/png"

    code, payload = _run_json(["rank", "list", "--uid", "100000001", "--render", "text"])

    assert code == 0
    assert payload["data"]["render"] == "rank/list-text"
    list_text = _text_artifact(payload)
    assert "Akasha排行 - Traveler" in list_text
    assert "温迪 COMBO" in list_text
    assert "武器 绝弦 精5" in list_text

    def enriched_title_context(args, *, uid, region, player, characters):
        enriched = dict(player)
        enriched["title_stats"] = ["1/2", "3/4", "5/6", "7/8", "9/10", "11/12", 13, 14]
        return enriched, ["title enriched"]

    monkeypatch.setattr(rank_commands, "_rank_list_title_context", enriched_title_context)
    code, payload = _run_json(["rank", "list", "--uid", "100000001", "--render", "data,image"])

    assert code == 0
    assert payload["warnings"] == ["title enriched"]
    assert payload["data"]["render"] == "rank/list"
    assert payload["data"]["player"]["title_stats"][0] == "1/2"

    code, payload = _run_json(["rank", "character", "--character", "Venti"])

    assert code == 0
    assert payload["data"]["character"] == "温迪"
    assert payload["data"]["tag"] == "前20"
    assert payload["data"]["entries"][0]["uid"] == "200000001"

    code, payload = _run_json(
        [
            "rank",
            "character",
            "--character",
            "Venti",
            "--render",
            "image,text",
        ]
    )

    assert code == 0
    image_artifact = next(
        artifact for artifact in payload["artifacts"] if artifact["kind"] == "image"
    )
    text_artifact = next(
        artifact for artifact in payload["artifacts"] if artifact["kind"] == "text"
    )
    assert payload["data"]["render"] == "rank/character"
    assert payload["data"]["artifact_sha256"] == image_artifact["sha256"]
    assert payload["data"]["text_artifact_sha256"] == text_artifact["sha256"]
    assert "角色排行 - 温迪" in Path(str(text_artifact["path"])).read_text(encoding="utf-8")

    code, payload = _run_json(
        ["rank", "character", "--uid", "100000001", "--character", "温迪", "--nearby"]
    )

    assert code == 0
    assert payload["data"]["selected_uid"] == "100000001"
    assert payload["data"]["tag"] == "角色附近"

    code, payload = _run_json(["rank", "artifact", "--sort", "crit-rate"])

    assert code == 0
    assert payload["data"]["sort"] == "暴击率"
    assert payload["data"]["akasha_sort"] == "substats.Crit RATE"
    assert payload["data"]["artifacts"][0]["uid"] == "300000001"

    code, stdout, stderr = _run_plain(
        ["rank", "artifact", "--sort", "crit-rate", "--render", "text", "--format", "plain"]
    )

    assert code == 0
    assert stderr == ""
    assert "圣遗物排行 - 暴击率" in stdout
    assert "死之羽: 华馆之羽 +20 ★★★★★，双爆分 54.4" in stdout
    assert "暴击率: 23.3%" in stdout


def test_rank_artifact_text_uses_displayed_artifact_level() -> None:
    text = render_rank_artifact_text(
        {
            "sort": "双爆",
            "akasha_sort": "critValue",
            "count": 1,
            "artifacts": [{**_akasha_artifact(), "level": 1}],
        }
    )

    assert " +0 " in text


def test_rank_list_title_context_uses_chinese_warning(monkeypatch, tmp_path) -> None:
    def fail_credential(*_args, **_kwargs):
        raise CliError("UPSTREAM_REJECTED", "boom", EXIT_UPSTREAM)

    monkeypatch.setattr(rank_commands, "_credential", fail_credential)
    args = Namespace(timeout=1, output_dir=tmp_path, debug=False)

    player, warnings = rank_commands._rank_list_title_context(
        args,
        uid="100000001",
        region="cn",
        player={"nickname": "Traveler"},
        characters=[],
    )

    assert player == {"nickname": "Traveler"}
    assert warnings == ["排名列表米游社标题数据不可用，已使用 Akasha 标题数据"]


def test_rank_title_stats_use_mys_character_count_and_crown_stat() -> None:
    stats = rank_commands._title_stats_from_mys(
        {"role": {"nickname": "派蒙", "level": 60, "region": "cn_gf01"}},
        [
            {
                "rarity": 4,
                "actived_constellation_num": 6,
                "fetter": 10,
                "weapon": {"rarity": 4},
            },
            {
                "rarity": 5,
                "actived_constellation_num": 0,
                "fetter": 9,
                "weapon": {"rarity": 5},
            },
        ],
        [
            {"stats": {"critValue": 210}},
            {"stats": {"critValue": 180}},
        ],
        crown_stat="53/77",
    )

    assert stats[0] == "53/77"
    assert stats[1] == "1/2"
    assert stats[-2:] == [1, 2]


def test_rank_crown_cost_counts_crowned_combat_talents_only() -> None:
    assert (
        rank_commands._crown_cost_from_character_details(
            [
                {
                    "constellations": [
                        {
                            "pos": 3,
                            "is_actived": True,
                            "effect": "<color=#FFD780FF>Burst</color>的技能等级提高3级。",
                        }
                    ],
                    "skills": [
                        {"skill_type": 1, "level": 10},
                        {"skill_type": 1, "level": 9},
                        {"skill_type": 1, "name": "Burst", "level": 12},
                        {"skill_type": 2, "level": 10},
                    ],
                }
            ]
        )
        == 1
    )


def test_rank_crown_owned_reads_calculator_skill_material_bucket() -> None:
    assert (
        rank_commands._crown_owned_from_calculator_data(
            {
                "overall_material_consume": {
                    "avatar_skill_consume": [
                        {"id": 104319, "num": 10, "lack_num": 3},
                    ]
                }
            }
        )
        == 7
    )
    assert (
        rank_commands._crown_owned_from_calculator_data(
            {"overall_consume": [{"id": 104319, "num": 24, "lack_num": 0}]}
        )
        == 24
    )


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


def test_akasha_provider_uses_http_client_transport() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={"data": [_akasha_artifact()]})

    provider = AkashaProvider(
        HttpClient(timeout=1, cache_policy="off", transport=httpx.MockTransport(handler))
    )

    result = provider.artifact_leaderboard(sort_by="crit-rate", region="cn")

    assert result.data["sort"] == "暴击率"
    assert captured["request"].url.path == "/api/artifacts"
    assert captured["request"].headers["user-agent"] == "GsCore / GenshinUID / 6.2.0"


class FakeEnkaProvider:
    def __init__(self, _http_client) -> None:
        pass

    def profile(self, *, uid: str, region: str) -> CommandResult:
        assert uid == "100000001"
        assert region == "cn"
        return CommandResult(data=_enka_payload(), source=_source())


class StaleFakeEnkaProvider(FakeEnkaProvider):
    def profile(self, *, uid: str, region: str) -> CommandResult:
        result = super().profile(uid=uid, region=region)
        payload = json.loads(json.dumps(result.data))
        payload["avatarInfoList"][0]["level"] = 70
        return CommandResult(data=payload, source=result.source)


class FakeMysPanelProvider:
    def __init__(self, *, extra_avatar: dict[str, object] | None = None) -> None:
        self.summary_calls = 0
        self.details_calls = 0
        avatars = [*_enka_payload()["avatarInfoList"]]
        if extra_avatar is not None:
            avatars.append(extra_avatar)
        self.details = [_mys_detail_from_avatar(avatar) for avatar in avatars]

    def player_summary(self, **kwargs) -> CommandResult:
        assert kwargs["uid"] == "100000001"
        assert kwargs["cookie"] == "account_id=1;cookie_token=secret"
        self.summary_calls += 1
        return CommandResult(
            data={
                "summary": {
                    "role": {
                        "nickname": "Traveler",
                        "level": 60,
                        "region": "cn_gf01",
                    },
                    "stats": {
                        "world_level": 8,
                        "achievement_number": 900,
                    },
                    "avatars": [{"id": detail["base"]["id"]} for detail in self.details],
                }
            },
            source=_mys_source(),
        )

    def character_details(self, **kwargs) -> CommandResult:
        assert kwargs["uid"] == "100000001"
        assert kwargs["cookie"] == "account_id=1;cookie_token=secret"
        assert kwargs["character_ids"] == [detail["base"]["id"] for detail in self.details]
        assert kwargs["category"] == "panel.refresh.mys"
        self.details_calls += 1
        return CommandResult(data={"details": self.details}, source=_mys_source())


class FakeAkashaProvider:
    def __init__(self, _http_client) -> None:
        pass

    def user_rank(self, *, uid: str, region: str) -> CommandResult:
        assert uid == "100000001"
        assert region == "cn"
        return CommandResult(
            data={
                "uid": uid,
                "source": "akasha",
                "player": {"nickname": "Traveler"},
                "rank_data": {
                    "10000022": {
                        "calculations": {
                            "fit": {
                                "calculationId": "1000002200",
                                "short": "COMBO",
                                "result": 12345.6,
                                "ranking": 12,
                                "outOf": 1000,
                                "weapon": {
                                    "name": "The Stringless",
                                    "rarity": 4,
                                    "refinement": 5,
                                },
                                "stats": {
                                    "maxHP": 15000,
                                    "maxATK": 1800,
                                    "critRate": 0.7,
                                    "critDMG": 1.6,
                                    "critValue": 300,
                                },
                            }
                        },
                        "time": "2026-04-29T10:30:00Z",
                    }
                },
                "characters": [_akasha_character_summary()],
                "count": 1,
            },
            source=_akasha_source(),
        )

    def character_leaderboard(
        self,
        *,
        character_id: str,
        region: str,
        calculation_id: str | None = None,
        combo: float | None = None,
    ) -> CommandResult:
        assert character_id == "10000022"
        assert region == "cn"
        if calculation_id is not None:
            assert calculation_id == "1000002200"
            assert combo and combo > 12345
        return CommandResult(
            data={
                "source": "akasha",
                "character_id": character_id,
                "calculation_id": calculation_id or "1000002200",
                "total_count": 1000,
                "entries": [_akasha_leaderboard_entry()],
                "count": 1,
            },
            source=_akasha_source(),
        )

    def artifact_leaderboard(self, *, sort_by: str, region: str) -> CommandResult:
        assert sort_by == "crit-rate"
        assert region == "cn"
        return CommandResult(
            data={
                "source": "akasha",
                "sort": "暴击率",
                "sort_input": sort_by,
                "akasha_sort": "substats.Crit RATE",
                "artifacts": [_akasha_artifact()],
                "count": 1,
            },
            source=_akasha_source(),
        )


def _fake_image_fetcher(captured_urls: list[str]):
    def fetcher(args, urls, **_kwargs):
        unique_urls = list(dict.fromkeys(urls))
        captured_urls.extend(unique_urls)
        image = Image.new("RGBA", (512, 512), (220, 70, 50, 255))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return {url: buffer.getvalue() for url in unique_urls}, []

    return fetcher


def _run_plain(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    return code, stdout.getvalue(), stderr.getvalue()


def _text_artifact(payload: dict[str, object]) -> str:
    for artifact in payload["artifacts"]:
        if isinstance(artifact, dict) and artifact.get("kind") == "text":
            return Path(str(artifact["path"])).read_text(encoding="utf-8")
    raise AssertionError("text artifact not found")


def _source() -> dict[str, object]:
    return {
        "provider": "enka",
        "region": "cn",
        "cached": False,
        "fetched_at": "2026-04-29T10:30:00Z",
    }


def _mys_source() -> dict[str, object]:
    return {
        "provider": "mys",
        "region": "cn",
        "cached": False,
        "fetched_at": "2026-04-29T10:31:00Z",
    }


def _akasha_source() -> dict[str, object]:
    return {
        "provider": "akasha",
        "region": "cn",
        "cached": False,
        "fetched_at": "2026-04-29T10:30:00Z",
    }


def _akasha_character_summary() -> dict[str, object]:
    return {
        "avatar_id": "10000022",
        "name": "Venti",
        "calculation_id": "1000002200",
        "short": "COMBO",
        "result": 12345.6,
        "rank": 12,
        "out_of": 1000,
        "percent": 1.2,
        "constellation": 2,
        "weapon": {"name": "The Stringless", "rarity": 4, "refinement": 5},
        "stats": {
            "maxHP": 15000,
            "maxATK": 1800,
            "critRate": 0.7,
            "critDMG": 1.6,
            "critValue": 300,
        },
        "artifact_sets": {"Viridescent Venerer": {"icon": "UI_RelicIcon_15002_4", "count": 4}},
    }


def _akasha_leaderboard_entry() -> dict[str, object]:
    return {
        "uid": "200000001",
        "index": 1,
        "constellation": 2,
        "critValue": 300,
        "owner": {"region": "CN", "nickname": "Ranker"},
        "weapon": {"weaponInfo": {"refinementLevel": {"value": 4}}},
        "stats": {
            "maxHp": {"value": 15000},
            "atk": {"value": 1800},
            "critRate": {"value": 0.7},
            "critDamage": {"value": 1.6},
        },
        "artifactSets": {"Viridescent Venerer": {"icon": "UI_RelicIcon_15002_4", "count": 4}},
    }


def _akasha_artifact() -> dict[str, object]:
    return {
        "uid": "300000001",
        "critValue": 54.4,
        "equipType": "EQUIP_NECKLACE",
        "icon": "https://enka.network/ui/UI_RelicIcon_15021_2.png",
        "level": 21,
        "mainStatKey": "Flat ATK",
        "mainStatValue": 311,
        "name": "Plume of Luxury",
        "owner": {"region": "NA", "nickname": "Night"},
        "stars": 5,
        "substats": {"Crit RATE": 23.3, "Crit DMG": 7.8},
    }


def _mys_detail_from_avatar(avatar: dict[str, object]) -> dict[str, object]:
    panel = normalized_avatar(avatar)
    weapon = panel["weapon"]
    assert isinstance(weapon, dict)
    avatar_id = int(str(panel["avatar_id"]))
    weapon_id = int(str(weapon.get("item_id") or avatar_id))
    return {
        "base": {
            "id": avatar_id,
            "name": panel["name"],
            "level": panel["level"],
            "fetter": panel["friendship"],
        },
        "weapon": {
            "id": weapon_id,
            "name": weapon["name"],
            "level": weapon["level"],
            "affix_level": weapon["affix"],
            "rarity": weapon["rank"],
            "main_property": {"property_type": 4, "final": "454"},
            "sub_property": {"property_type": 23, "final": "61.3%"},
        },
        "constellations": [
            {"id": index + 1, "is_actived": True}
            for index in range(int(panel["constellation"] or 0))
        ],
        "skills": [],
        "base_properties": [],
        "extra_properties": [],
        "element_properties": [],
        "relics": [],
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


def _xiangling_avatar() -> dict[str, object]:
    return _avatar(
        avatar_id=10000023,
        name="Xiangling",
        level=90,
        weapon="The Catch",
        substats=[
            ("FIGHT_PROP_CRITICAL", 7.0),
            ("FIGHT_PROP_CRITICAL_HURT", 14.0),
        ],
        extra_artifact_score=0.0,
    )


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
            "reliquary": {"level": 21},
            "flat": {
                "name": f"{name} Flower",
                "itemType": "ITEM_RELIQUARY",
                "icon": "UI_RelicIcon_15002_4",
                "equipType": "EQUIP_BRACER",
                "rankLevel": 5,
                "reliquaryMainstat": {
                    "mainPropId": "FIGHT_PROP_HP",
                    "statValue": 4780,
                },
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
                "reliquary": {"level": 21},
                "flat": {
                    "name": f"{name} Plume",
                    "itemType": "ITEM_RELIQUARY",
                    "icon": "UI_RelicIcon_15002_2",
                    "equipType": "EQUIP_NECKLACE",
                    "rankLevel": 5,
                    "reliquaryMainstat": {
                        "mainPropId": "FIGHT_PROP_ATTACK",
                        "statValue": 311,
                    },
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
        "fightPropMap": {
            "20": 0.5,
            "22": 1.0,
            "23": 1.613,
            "28": 100,
            "44": 0.616,
            "2000": 18000,
            "2001": 1200,
            "2002": 900,
            "4": 800,
        },
        "equipList": [
            {
                "itemId": avatar_id,
                "weapon": {"level": 90, "affixMap": {"1": 0}},
                "flat": {
                    "name": weapon,
                    "itemType": "ITEM_WEAPON",
                    "rankLevel": 4,
                    "weaponStats": [
                        {"appendPropId": "FIGHT_PROP_BASE_ATTACK", "statValue": 454},
                        {"appendPropId": "FIGHT_PROP_CHARGE_EFFICIENCY", "statValue": 61.3},
                    ],
                },
            },
            *artifacts,
        ],
    }
