from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from PIL import Image

from gsuid_cli.cli import run
from gsuid_cli.commands import public_data
from gsuid_cli.core.errors import CliError
from gsuid_cli.core.http import HttpClient, ProviderBytesResponse
from gsuid_cli.core.models import CommandResult
from gsuid_cli.providers import public as public_provider
from gsuid_cli.providers.public import PublicDataProvider, _parse_active_codes
from gsuid_cli.renderers import recommend as recommend_renderer


def test_public_wiki_command_returns_json(monkeypatch) -> None:
    monkeypatch.setattr("gsuid_cli.commands.public_data.PublicDataProvider", _fake_provider())

    code, payload = _run_json(["wiki", "character", "--name", "Amber"])

    assert code == 0
    assert payload["command"] == "wiki.character"
    assert payload["data"]["item"]["name"] == "Amber"
    assert payload["source"]["provider"] == "ambr"


def test_public_commands_reject_unsupported_region(monkeypatch) -> None:
    monkeypatch.setattr("gsuid_cli.commands.public_data.PublicDataProvider", _fake_provider())

    code, payload = _run_json(["--region", "os", "wiki", "character", "--name", "Amber"])

    assert code == 1
    assert payload["error"]["code"] == "REGION_UNSUPPORTED"


def test_daily_materials_rejects_conflicting_day_selectors() -> None:
    code, payload = _run_json(["daily", "materials", "--date", "2026-04-29", "--day", "monday"])

    assert code == 1
    assert payload["command"] == "daily.materials"
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_public_list_commands_return_json(monkeypatch) -> None:
    monkeypatch.setattr("gsuid_cli.commands.public_data.PublicDataProvider", _fake_provider())

    for argv, command, key in [
        (["events", "list"], "events.list", "events"),
        (["events", "banners"], "events.banners", "banners"),
        (["codes", "list"], "codes.list", "codes"),
        (["daily", "materials", "--date", "2026-04-29"], "daily.materials", "domains"),
    ]:
        code, payload = _run_json(argv)

        assert code == 0
        assert payload["command"] == command
        assert key in payload["data"]


def test_daily_materials_render_image_writes_card(monkeypatch, tmp_path) -> None:
    requested_urls: list[str] = []
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.public_data.PublicDataProvider", _fake_provider())
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")
    monkeypatch.setattr(public_data, "fetch_render_images", _fake_image_fetcher(requested_urls))

    code, payload = _run_json(
        [
            "--request-id",
            "daily-materials-img",
            "--output-dir",
            str(tmp_path / "artifacts"),
            "daily",
            "materials",
            "--date",
            "2026-04-29",
            "--render",
            "image",
        ]
    )

    assert code == 0
    assert payload["command"] == "daily.materials"
    assert payload["data"] == {
        "day": "wednesday",
        "render": "daily/materials",
        "artifact_sha256": payload["artifacts"][0]["sha256"],
    }
    artifact = payload["artifacts"][0]
    path = Path(artifact["path"])
    content = path.read_bytes()
    assert path.parent == tmp_path / "artifacts" / "2026-04-29" / "daily-materials-img"
    assert artifact["media_type"] == "image/png"
    assert artifact["sha256"] == hashlib.sha256(content).hexdigest()
    assert set(requested_urls) == {
        "https://gi.yatta.moe/assets/UI/UI_ItemIcon_104313.png",
        "https://gi.yatta.moe/assets/UI/UI_AvatarIcon_Ambor.png",
        "https://gi.yatta.moe/assets/UI/UI_AvatarIcon_Venti.png",
    }
    with Image.open(path) as image:
        assert image.size[0] == 950
        assert image.size[1] >= 820
        assert image.getbbox() is not None


def test_daily_materials_render_both_preserves_structured_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.public_data.PublicDataProvider", _fake_provider())
    monkeypatch.setattr(public_data, "fetch_render_images", _fake_image_fetcher([]))

    code, payload = _run_json(["daily", "materials", "--day", "monday", "--render", "both"])

    assert code == 0
    assert payload["data"]["domains"][0]["items"][0]["name"] == "安柏"
    assert payload["data"]["render"] == "daily/materials"
    assert payload["data"]["artifact_sha256"] == payload["artifacts"][0]["sha256"]


def test_wiki_picwiki_renderers_write_cards(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.public_data.PublicDataProvider", _fake_provider())
    monkeypatch.setattr(public_data, "fetch_render_images", _fake_image_fetcher([]))

    commands = [
        (["wiki", "food", "--name", "Sweet Madame"], "wiki.food", "wiki/food"),
        (["wiki", "artifact", "--name", "Gladiator"], "wiki.artifact", "wiki/artifact"),
        (["wiki", "weapon", "--name", "Dull Blade"], "wiki.weapon", "wiki/weapon"),
        (
            ["wiki", "constellation", "--character", "Amber", "--constellation", "1"],
            "wiki.constellation",
            "wiki/constellation",
        ),
        (
            ["wiki", "character-materials", "--character", "Amber"],
            "wiki.character-materials",
            "wiki/character-materials",
        ),
        (
            ["wiki", "weapon-materials", "--weapon", "Dull Blade"],
            "wiki.weapon-materials",
            "wiki/weapon-materials",
        ),
    ]

    for argv, command, render in commands:
        code, payload = _run_json([*argv, "--render", "image"])

        assert code == 0
        assert payload["command"] == command
        assert payload["data"]["render"] == render
        artifact = payload["artifacts"][0]
        path = Path(artifact["path"])
        assert artifact["media_type"] == "image/png"
        assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        with Image.open(path) as image:
            assert image.getbbox() is not None


def test_guide_image_render_writes_resource_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.public_data.PublicDataProvider", _fake_provider())
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")

    commands = [
        (
            ["guide", "character", "--name", "Amber"],
            "guide.character",
            "guide/character",
            "image/png",
        ),
        (
            ["guide", "reference-panel", "--character", "Amber"],
            "guide.reference-panel",
            "guide/reference-panel",
            "image/jpeg",
        ),
    ]

    for argv, command, render, media_type in commands:
        code, payload = _run_json(
            [
                "--request-id",
                "guide-img",
                "--output-dir",
                str(tmp_path / "artifacts"),
                *argv,
                "--render",
                "image",
            ]
        )

        assert code == 0
        assert payload["command"] == command
        assert payload["data"]["render"] == render
        artifact = payload["artifacts"][0]
        path = Path(artifact["path"])
        assert artifact["media_type"] == media_type
        assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_guide_layout_renderers_write_cards(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.public_data.PublicDataProvider", _fake_provider())
    monkeypatch.setattr(public_data, "fetch_render_images", _fake_image_fetcher([]))

    commands = [
        (["guide", "abyss", "--version", "9.9", "--floor", "12"], "guide.abyss", "guide/abyss"),
        (["guide", "theater", "--version", "1"], "guide.theater", "guide/theater"),
    ]

    for argv, command, render in commands:
        code, payload = _run_json([*argv, "--render", "image"])

        assert code == 0
        assert payload["command"] == command
        assert payload["data"]["render"] == render
        artifact = payload["artifacts"][0]
        path = Path(artifact["path"])
        assert artifact["media_type"] == "image/png"
        assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        with Image.open(path) as image:
            assert image.getbbox() is not None


def test_recommend_render_images_write_cards(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.public_data.PublicDataProvider", _fake_provider())
    assert recommend_renderer.FOOTER_TEXT == "Created by gsuid-cli & Data by GenshinUID"

    commands = [
        (["recommend", "build", "--character", "Amber"], "recommend.build", "recommend/build"),
        (["recommend", "holder", "--item", "Bow"], "recommend.holder", "recommend/holder"),
    ]

    for argv, command, render in commands:
        code, payload = _run_json([*argv, "--render", "image"])

        assert code == 0
        assert payload["command"] == command
        assert payload["data"]["render"] == render
        artifact = payload["artifacts"][0]
        path = Path(artifact["path"])
        assert artifact["media_type"] == "image/png"
        assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        with Image.open(path) as image:
            assert image.size[0] == 900
            assert image.getbbox() is not None


def test_event_render_images_write_cards(monkeypatch, tmp_path) -> None:
    requested_urls: list[str] = []
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.public_data.PublicDataProvider", _fake_provider())
    monkeypatch.setattr(public_data, "fetch_render_images", _fake_image_fetcher(requested_urls))

    commands = [
        (["events", "list"], "events.list", "events/list"),
        (["events", "banners"], "events.banners", "events/banners"),
    ]

    for argv, command, render in commands:
        code, payload = _run_json([*argv, "--render", "image"])

        assert code == 0
        assert payload["command"] == command
        assert payload["data"]["render"] == render
        artifact = payload["artifacts"][0]
        path = Path(artifact["path"])
        assert artifact["media_type"] == "image/png"
        assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        with Image.open(path) as image:
            assert image.size[0] == 950
            assert image.getbbox() is not None

    assert "https://example.test/a.jpg" in requested_urls


def test_announcement_render_images_write_cards(monkeypatch, tmp_path) -> None:
    requested_urls: list[str] = []
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.public_data.PublicDataProvider", _fake_provider())
    monkeypatch.setattr(public_data, "fetch_render_images", _fake_image_fetcher(requested_urls))

    commands = [
        (["announcements", "list", "--limit", "3"], "announcements.list", "announcements/list"),
        (
            ["announcements", "show", "--id", "1001"],
            "announcements.show",
            "announcements/show",
        ),
    ]

    for argv, command, render in commands:
        code, payload = _run_json([*argv, "--render", "image"])

        assert code == 0
        assert payload["command"] == command
        assert payload["data"]["render"] == render
        artifact = payload["artifacts"][0]
        path = Path(artifact["path"])
        assert artifact["media_type"] == "image/png"
        assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        with Image.open(path) as image:
            if command == "announcements.list":
                assert image.size[1] > 242
            assert image.getbbox() is not None

    assert "https://example.test/banner.jpg" in requested_urls
    assert "https://example.test/detail.jpg" in requested_urls


def test_announcement_show_latest_uses_newest_list_row(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.public_data.PublicDataProvider", _fake_provider())

    code, payload = _run_json(["announcements", "show", "--latest"])

    assert code == 0
    assert payload["command"] == "announcements.show"
    assert payload["data"]["announcement"]["id"] == "1001"
    assert payload["data"]["selected_announcement"] == {
        "mode": "latest",
        "id": "1001",
        "start_at": "2026-05-01 10:00:00",
    }


def test_wiki_constellation_render_both_preserves_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.public_data.PublicDataProvider", _fake_provider())
    monkeypatch.setattr(public_data, "fetch_render_images", _fake_image_fetcher([]))

    code, payload = _run_json(
        [
            "wiki",
            "constellation",
            "--character",
            "Amber",
            "--constellation",
            "1",
            "--render",
            "both",
        ]
    )

    assert code == 0
    assert payload["data"]["constellation"] == {"index": 1, "name": "One Arrow"}
    assert payload["data"]["requested_constellation"] == 1
    assert payload["data"]["render"] == "wiki/constellation"


def test_daily_materials_enriches_ambr_upgrade_icon_urls() -> None:
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(
                    {
                        "response": 200,
                        "data": {
                            "monday": {
                                "domain": {
                                    "id": 5257,
                                    "name": "精通秘境：炽炎祭场",
                                    "reward": [102, 104310],
                                    "city": 2,
                                }
                            }
                        },
                    }
                ),
                _json_response(
                    {
                        "response": 200,
                        "data": {
                            "avatar": {
                                "10000021": {
                                    "name": "安柏",
                                    "rank": 4,
                                    "icon": "UI_AvatarIcon_Ambor",
                                    "items": {"104310": 1},
                                }
                            },
                            "weapon": {},
                        },
                    }
                ),
            ]
        )
    )

    result = provider.daily_materials(day="monday")

    domain = result.data["domains"][0]
    assert domain["domain_icon_url"] == "https://gi.yatta.moe/assets/UI/UI_ItemIcon_104310.png"
    assert domain["items"] == [
        {
            "id": "10000021",
            "type": "avatar",
            "name": "安柏",
            "rank": 4,
            "icon": "UI_AvatarIcon_Ambor",
            "icon_url": "https://gi.yatta.moe/assets/UI/UI_AvatarIcon_Ambor.png",
        }
    ]


def test_daily_materials_keeps_base_data_when_upgrade_unavailable() -> None:
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(
                    {
                        "response": 200,
                        "data": {
                            "monday": {
                                "domain": {
                                    "id": 5257,
                                    "name": "精通秘境：炽炎祭场",
                                    "reward": [102, 104310],
                                    "city": 2,
                                }
                            }
                        },
                    }
                ),
                _json_response({"response": 500}),
            ]
        )
    )

    result = provider.daily_materials(day="monday")

    assert result.data["domains"][0]["items"] == []
    assert result.warnings == [
        "daily material upgrade data is unavailable; returned domains without item matches"
    ]


def test_daily_materials_default_day_uses_four_oclock_reset(monkeypatch) -> None:
    class FixedDatetime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 4, 29, 3, 30, tzinfo=tz)

    monkeypatch.setattr(public_provider, "datetime", FixedDatetime)
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(
                    {
                        "response": 200,
                        "data": {
                            "tuesday": {
                                "domain": {
                                    "id": 1,
                                    "name": "精通秘境：深炎之底",
                                    "reward": [104313],
                                    "city": 2,
                                }
                            },
                            "wednesday": {
                                "domain": {
                                    "id": 2,
                                    "name": "精通秘境：焚尽之环",
                                    "reward": [104316],
                                    "city": 2,
                                }
                            },
                        },
                    }
                ),
                _json_response({"response": 200, "data": {"avatar": {}, "weapon": {}}}),
            ]
        )
    )

    result = provider.daily_materials(day=None)

    assert result.data["day"] == "tuesday"
    assert result.data["domains"][0]["id"] == "1"


def test_ambr_wiki_lookup_matches_route_alias() -> None:
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(
                    {
                        "response": 200,
                        "data": {
                            "items": {
                                "10000021": {
                                    "id": 10000021,
                                    "rank": 4,
                                    "name": "安柏",
                                    "element": "Fire",
                                    "weaponType": "WEAPON_BOW",
                                    "icon": "UI_AvatarIcon_Ambor",
                                    "route": "Amber",
                                }
                            }
                        },
                    }
                ),
                _json_response(
                    {
                        "response": 200,
                        "data": {
                            "id": 10000021,
                            "rank": 4,
                            "name": "安柏",
                            "element": "Fire",
                            "weaponType": "WEAPON_BOW",
                            "icon": "UI_AvatarIcon_Ambor",
                            "route": "Amber",
                            "fetter": {"title": "飞行冠军", "detail": "侦察骑士。"},
                        },
                    }
                ),
            ]
        )
    )

    result = provider.wiki_lookup(kind="character", query="amber")

    assert result.data["match"]["id"] == "10000021"
    assert result.data["item"]["title"] == "飞行冠军"


def test_ambr_artifact_suit_icons_use_reliquary_asset_path() -> None:
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(
                    {
                        "response": 200,
                        "data": {
                            "items": {
                                "15001": {
                                    "id": 15001,
                                    "name": "角斗士的终幕礼",
                                    "route": "Gladiator's Finale",
                                }
                            }
                        },
                    }
                ),
                _json_response(
                    {
                        "response": 200,
                        "data": {
                            "id": 15001,
                            "name": "角斗士的终幕礼",
                            "icon": "UI_RelicIcon_15001_4",
                            "levelList": [4, 5],
                            "affixList": {"2": "攻击力提高18%。"},
                            "suit": {
                                "EQUIP_BRACER": {
                                    "name": "角斗士的留恋",
                                    "description": "小花。",
                                    "icon": "UI_RelicIcon_15001_4",
                                }
                            },
                        },
                    }
                ),
            ]
        )
    )

    result = provider.wiki_lookup(kind="artifact", query="Gladiator's Finale")

    assert result.data["item"]["icon_url"] == (
        "https://gi.yatta.moe/assets/UI/reliquary/UI_RelicIcon_15001_4.png"
    )
    assert result.data["item"]["suit"][0]["icon_url"] == (
        "https://gi.yatta.moe/assets/UI/reliquary/UI_RelicIcon_15001_4.png"
    )


def test_ambr_food_recipe_data_shape_stays_raw() -> None:
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(
                    {
                        "response": 200,
                        "data": {
                            "items": {
                                "1004": {
                                    "id": 1004,
                                    "name": "甜甜花酿鸡",
                                    "route": "Sweet Madame",
                                }
                            }
                        },
                    }
                ),
                _json_response(
                    {
                        "response": 200,
                        "data": {
                            "id": 1004,
                            "name": "甜甜花酿鸡",
                            "icon": "UI_ItemIcon_Recipe_1004",
                            "recipe": {
                                "effect": {"0": "恢复生命值。"},
                                "input": {
                                    "100012": {
                                        "name": "甜甜花",
                                        "icon": "UI_ItemIcon_100012",
                                        "count": 2,
                                    }
                                },
                                "effectIcon": "UI_Buff_Item_Recovery_HpAdd",
                            },
                        },
                    }
                ),
            ]
        )
    )

    result = provider.wiki_lookup(kind="food", query="Sweet Madame")

    recipe = result.data["item"]["recipe"]
    assert recipe["input"] == {
        "100012": {"name": "甜甜花", "icon": "UI_ItemIcon_100012", "count": 2}
    }
    assert recipe["effectIcon"] == "UI_Buff_Item_Recovery_HpAdd"


def test_recommend_build_uses_genshinuid_adv_data() -> None:
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(
                    {
                        "response": 200,
                        "data": {
                            "items": {
                                "10000021": {
                                    "id": 10000021,
                                    "name": "安柏",
                                    "route": "Amber",
                                }
                            }
                        },
                    }
                ),
                _json_response(
                    {
                        "response": 200,
                        "data": {
                            "id": 10000021,
                            "name": "安柏",
                            "route": "Amber",
                        },
                    }
                ),
                _json_response(
                    {
                        "安柏": {
                            "weapon": {"5": ["阿莫斯之弓"], "4": ["绝弦"], "3": []},
                            "artifact": [["昔日宗室之仪"], ["炽烈的炎之魔女", "角斗士的终幕礼"]],
                            "remark": ["侦察骑士。"],
                        }
                    }
                ),
            ]
        )
    )

    result = provider.recommend_build(character="Amber")

    assert result.data["character"] == "安柏"
    assert result.data["weapons"][0] == {"rarity": 5, "items": ["阿莫斯之弓"]}
    assert result.data["artifacts"][0] == {"sets": ["昔日宗室之仪"], "pieces": [4]}
    assert result.data["remarks"] == ["侦察骑士。"]


def test_guide_abyss_uses_genshinuid_abyss_js_data(monkeypatch, tmp_path) -> None:
    abyss_js = tmp_path / "abyss.js"
    abyss_js.write_text(
        """
var _SpiralAbyssSchedule = [
  {"Name": "9.9", "Show": "9.9", "OpenTime": "2026/01/01 - 2026/12/31", "Floors": [1, 2, 3, 4]}
]
var _Monsters = {
  "100": {"Name": "草史莱姆", "Icon": ["UI_MonsterIcon_Slime_Grass_02"]},
  "60513": {"Name": "西尼阿斯", "Icon": ["pbv"]}
}
var _SpiralAbyssFloorConfig = {
  "4": {
    "Disorder": "<b>上半</b> 草元素伤害提升。",
    "Chambers": [
      {
        "Name": "12-1",
        "Level": 95,
        "Upper": [{"WaveDesc": 1, "Monsters": [{"ID": 100, "Num": 2}, {"ID": 60513, "Num": 1}]}],
        "Lower": [{"WaveDesc": 0, "Monsters": [{"ID": 100, "Num": 1}]}]
      }
    ]
  }
}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(public_provider, "GENSHINUID_ABYSS_JS_PATH", abyss_js)
    provider = PublicDataProvider(_sequence_client([]))

    result = provider.guide_abyss(version="9.9", floor=12)

    assert result.data["available"] is True
    assert result.source["path"] == "package:assets/guide/abyss/data/abyss.js"
    assert result.data["version"] == "9.9"
    abyss = result.data["abyss"]
    assert abyss["disorder"] == "上半 草元素伤害提升。"
    monster = abyss["chambers"][0]["upper"][0]["monsters"][0]
    assert monster["name"] == "草史莱姆"
    assert monster["icon_url"] == (
        "https://gi.yatta.moe/assets/UI/monster/UI_MonsterIcon_Slime_Grass_02.png"
    )
    local_legend = abyss["chambers"][0]["upper"][0]["monsters"][1]
    assert local_legend["name"] == "西尼阿斯"
    assert local_legend["icon"] == "pbv"
    assert local_legend["icon_url"] is None


def test_guide_theater_uses_hakush_rolecombat_data() -> None:
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(
                    {
                        "1": {
                            "begin": "2026-01-01 00:00:00",
                            "end": "2026-12-31 23:59:59",
                        }
                    }
                ),
                _json_response(
                    {
                        "BeginTime": "2026-01-01 00:00:00",
                        "EndTime": "2026-12-31 23:59:59",
                        "AvatarConfig": {
                            "BuffAvatarList": [{"Id": 10000021, "Desc": "<b>火元素强化</b>"}],
                            "InviteAvatarList": [10000022],
                        },
                        "DifficultyConfig": {
                            "3": {
                                "Room": {
                                    "1": {"MonsterLevel": 90},
                                    "2": {
                                        "Title": "首领",
                                        "Desc": "<b>击败敌人</b>",
                                        "MonsterPreviewList": [
                                            {
                                                "Id": 1,
                                                "Name": "草史莱姆",
                                                "Icon": "pbv",
                                                "Hp": 12345,
                                            }
                                        ],
                                    },
                                }
                            }
                        },
                    }
                ),
                _json_response(
                    {
                        "response": 200,
                        "data": {
                            "items": {
                                "10000021": {"id": 10000021, "name": "安柏"},
                                "10000022": {"id": 10000022, "name": "温迪"},
                            }
                        },
                    }
                ),
            ]
        )
    )

    result = provider.guide_theater(version=None)

    assert result.data["available"] is True
    theater = result.data["theater"]
    assert theater["event_id"] == "1"
    assert theater["buff_avatars"][0]["name"] == "安柏"
    assert theater["invite_avatars"][0]["name"] == "温迪"
    monster = theater["rooms"][1]["monsters"][0]
    assert monster["hp"] == 12345
    assert monster["icon_url"] is None
    assert monster["icon_urls"] == ["https://api.hakush.in/gi/UI/pbv.webp"]


def test_ambr_wiki_lookup_no_result() -> None:
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(
                    {
                        "response": 200,
                        "data": {"items": {"1": {"id": 1, "name": "Amber", "route": "Amber"}}},
                    }
                )
            ]
        )
    )

    with pytest.raises(CliError) as exc:
        provider.wiki_lookup(kind="character", query="Missing")

    assert exc.value.code == "NO_RESULT"
    assert exc.value.exit_code == 6
    assert exc.value.source["provider"] == "ambr"


def test_events_banners_filters_wish_rows() -> None:
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(
                    {
                        "1": {
                            "id": 1,
                            "name": {"CHS": "普通活动"},
                            "nameFull": {"CHS": "普通活动说明"},
                            "startAt": "2026-04-01 00:00:00",
                            "endAt": "2026-05-01 00:00:00",
                            "banner": {"CHS": "https://example.test/event.jpg"},
                        },
                        "2": {
                            "id": 2,
                            "name": {"CHS": "「苍林月祷」祈愿"},
                            "nameFull": {"CHS": "角色活动祈愿"},
                            "startAt": "2026-04-01 00:00:00",
                            "endAt": "2026-05-01 00:00:00",
                            "banner": {"CHS": "https://example.test/wish.jpg"},
                        },
                    }
                )
            ]
        )
    )

    result = provider.event_banners(include_all=True, limit=10)

    assert result.data["count"] == 1
    assert result.data["banners"][0]["id"] == "2"


def test_announcements_list_uses_mihoyo_announcement_api() -> None:
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(
                    {
                        "retcode": 0,
                        "message": "OK",
                        "data": {
                            "list": [
                                {
                                    "type_id": 2,
                                    "type_label": "活动公告",
                                    "list": [
                                        {
                                            "ann_id": 1001,
                                            "title": "标题",
                                            "subtitle": "版本活动",
                                            "banner": "https://example.test/banner.jpg",
                                            "tag_label": "活动",
                                            "start_time": "2026-04-01 10:00:00",
                                            "end_time": "2026-05-01 03:59:59",
                                        },
                                        {"ann_id": 762, "subtitle": "GenshinUID隐藏公告"},
                                    ],
                                }
                            ]
                        },
                    }
                )
            ]
        )
    )

    result = provider.announcements_list(limit=20)

    assert result.source["provider"] == "mihoyo-announcement"
    assert result.data["count"] == 1
    assert result.data["total"] == 1
    row = result.data["announcements"][0]
    assert row["id"] == "1001"
    assert row["type_label"] == "活动公告"
    assert result.data["sections"][0]["items"][0]["subtitle"] == "版本活动"


def test_announcement_show_normalizes_content_html() -> None:
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(
                    {
                        "retcode": 0,
                        "message": "OK",
                        "data": {
                            "list": [
                                {
                                    "ann_id": 1001,
                                    "title": "标题",
                                    "subtitle": "版本活动",
                                    "banner": "https://example.test/banner.jpg",
                                    "content": (
                                        "<p>旅行者好</p>"
                                        '<p><img src="https://example.test/detail.jpg" /></p>'
                                    ),
                                }
                            ]
                        },
                    }
                ),
                _json_response(
                    {
                        "retcode": 0,
                        "message": "OK",
                        "data": {
                            "list": [
                                {
                                    "type_id": 2,
                                    "type_label": "活动公告",
                                    "list": [
                                        {
                                            "ann_id": 1001,
                                            "title": "标题",
                                            "subtitle": "版本活动",
                                            "start_time": "2026-04-01 10:00:00",
                                            "end_time": "2026-05-01 03:59:59",
                                        }
                                    ],
                                }
                            ]
                        },
                    }
                ),
            ]
        )
    )

    result = provider.announcement_show(announcement_id="1001")

    announcement = result.data["announcement"]
    assert announcement["id"] == "1001"
    assert announcement["start_at"] == "2026-04-01 10:00:00"
    assert announcement["end_at"] == "2026-05-01 03:59:59"
    assert announcement["text"] == "旅行者好"
    assert announcement["image_urls"] == ["https://example.test/detail.jpg"]


def test_codes_parser_extracts_active_rows() -> None:
    codes = _parse_active_codes(
        """
==Active Codes==
{{Code Row/Header}}
{{Code Row|GENSHINGIFT|G|Primogem*50;Hero's Wit*3|2020-11-10|indef|Permanent row}}
{{Code Row|YuanShen|CN|Primogem*50|2020-11-10|unknown}}
{{Code Row/Footer}}
==References==
"""
    )

    assert codes[0]["codes"] == ["GENSHINGIFT"]
    assert codes[0]["servers"] == ["America", "Europe", "Asia", "TW/HK/Macao"]
    assert codes[0]["rewards"][0] == {"name": "Primogem", "count": 50}
    assert codes[1]["servers"] == ["China"]


def _run_json(argv: list[str]) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    assert stderr.getvalue() == ""
    return code, json.loads(stdout.getvalue())


def _fake_provider():
    class FakeProvider:
        def __init__(self, _http_client: HttpClient) -> None:
            pass

        def wiki_lookup(self, *, kind: str, query: str) -> CommandResult:
            return CommandResult(
                data={
                    "kind": kind,
                    "query": query,
                    "match": {"id": "1", "name": "Amber"},
                    "item": _fake_wiki_item(kind, query),
                },
                source=_source("ambr"),
            )

        def character_constellation(
            self,
            *,
            character: str,
            constellation: int | None,
        ) -> CommandResult:
            return CommandResult(
                data={
                    "character": character,
                    "constellation": {"index": constellation, "name": "One Arrow"},
                },
                source=_source("ambr"),
            )

        def character_materials(self, *, character: str) -> CommandResult:
            return CommandResult(
                data={"character": character, "ascension": {"1001": 3}},
                source=_source("ambr"),
            )

        def weapon_materials(self, *, weapon: str) -> CommandResult:
            return CommandResult(
                data={"weapon": weapon, "ascension": {"1001": 3}},
                source=_source("ambr"),
            )

        def guide_character(self, *, character: str) -> CommandResult:
            return CommandResult(
                data={
                    "character": "安柏",
                    "overview": {},
                    "guide_image_url": "https://example.test/guide.png",
                },
                source=_source("ambr"),
            )

        def reference_panel(self, *, character: str) -> CommandResult:
            return CommandResult(
                data={
                    "character": "安柏",
                    "available": True,
                    "reference_panel": {"format": "image"},
                },
                source=_source("ambr"),
            )

        def recommend_build(self, *, character: str) -> CommandResult:
            return CommandResult(
                data={
                    "character": character,
                    "weapons": [{"rarity": 5, "items": ["Bow"]}],
                    "artifacts": [{"sets": ["Set"], "pieces": [4]}],
                    "remarks": ["Remark"],
                    "recommendations": [],
                },
                source=_source("genshinuid"),
            )

        def recommend_holder(self, *, item: str) -> CommandResult:
            return CommandResult(
                data={
                    "item": item,
                    "matches": [{"kind": "weapon", "match": item, "holders": ["Amber"]}],
                    "count": 1,
                },
                source=_source("genshinuid"),
            )

        def guide_image(self, *, kind: str, character: str) -> ProviderBytesResponse:
            if kind == "reference-panel":
                return ProviderBytesResponse(
                    content=b"\xff\xd8fake-jpeg",
                    media_type="image/jpeg",
                    source=_source("genshinuid-resource"),
                    status_code=200,
                )
            return ProviderBytesResponse(
                content=_png_bytes(character),
                media_type="image/png",
                source=_source("genshinuid-resource"),
                status_code=200,
            )

        def guide_abyss(self, *, version: str | None, floor: int | None) -> CommandResult:
            floor_number = floor or 12
            return CommandResult(
                data={
                    "version": version or "9.9",
                    "requested_version": version,
                    "floor": floor_number,
                    "available": True,
                    "schedule": {"name": version or "9.9", "show": version or "9.9"},
                    "abyss": {
                        "floor": floor_number,
                        "disorder": "上半 草元素伤害提升。",
                        "chambers": [
                            {
                                "name": "12-1",
                                "level": 95,
                                "upper": [
                                    {
                                        "index": 1,
                                        "monsters": [
                                            {
                                                "name": "草史莱姆",
                                                "count": 2,
                                                "icon_url": "https://example.test/monster.png",
                                            }
                                        ],
                                    }
                                ],
                                "lower": [
                                    {
                                        "index": 1,
                                        "monsters": [
                                            {
                                                "name": "草史莱姆",
                                                "count": 1,
                                                "icon_url": "https://example.test/monster.png",
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    },
                },
                source=_source("genshinuid"),
            )

        def guide_theater(self, *, version: str | None) -> CommandResult:
            return CommandResult(
                data={
                    "version": version or "1",
                    "requested_version": version,
                    "available": True,
                    "theater": {
                        "event_id": version or "1",
                        "begin_time": "2026-01-01 00:00:00",
                        "end_time": "2026-12-31 23:59:59",
                        "buff_description": "火元素强化",
                        "buff_avatars": [
                            {
                                "id": "10000021",
                                "name": "安柏",
                                "image_url": "https://example.test/amber.png",
                            }
                        ],
                        "invite_avatars": [
                            {
                                "id": "10000022",
                                "name": "温迪",
                                "image_url": "https://example.test/venti.png",
                            }
                        ],
                        "rooms": [
                            {"id": "1", "monster_level": 90, "monsters": []},
                            {
                                "id": "2",
                                "title": "首领",
                                "description": "击败敌人",
                                "monster_level": 95,
                                "monsters": [
                                    {
                                        "name": "草史莱姆",
                                        "hp": 12345,
                                        "icon_urls": ["https://example.test/monster.png"],
                                    }
                                ],
                            },
                        ],
                    },
                },
                source=_source("hakush"),
            )

        def events_list(self, *, include_all: bool, limit: int) -> CommandResult:
            return CommandResult(
                data={
                    "events": [
                        {
                            "id": "1",
                            "name": "Event",
                            "name_full": "普通活动",
                            "start_at": "2026-04-01 10:00:00",
                            "end_at": "2026-05-01 03:59:59",
                            "banner_url": "https://example.test/a.jpg",
                        }
                    ],
                    "count": min(1, limit),
                    "filter": "all" if include_all else "active",
                },
                source=_source("ambr"),
            )

        def event_banners(self, *, include_all: bool, limit: int) -> CommandResult:
            return CommandResult(
                data={
                    "banners": [
                        {
                            "id": "1",
                            "name": "Wish",
                            "name_full": "角色活动祈愿",
                            "start_at": "2026-04-01 10:00:00",
                            "end_at": "2026-05-01 03:59:59",
                            "banner_url": "https://example.test/a.jpg",
                        }
                    ],
                    "count": min(1, limit),
                    "filter": "all" if include_all else "active",
                },
                source=_source("ambr"),
            )

        def announcements_list(self, *, limit: int) -> CommandResult:
            row1 = {
                "id": "1003",
                "ann_id": "1003",
                "title": "公告",
                "subtitle": "版本更新说明",
                "type_id": 2,
                "type_label": "活动公告",
                "start_at": "2026-04-01 10:00:00",
            }
            row2 = {
                "id": "1001",
                "ann_id": "1001",
                "title": "活动",
                "subtitle": "活动公告",
                "type_id": 1,
                "type_label": "活动公告",
                "start_at": "2026-05-01 10:00:00",
            }
            row3 = {
                "id": "1002",
                "ann_id": "1002",
                "title": "千星奇域",
                "subtitle": "奇域公告",
                "type_id": 26,
                "type_label": "千星奇域",
                "start_at": "2026-04-15 10:00:00",
            }
            rows = [row1, row2, row3][:limit]
            sections = [
                {"type_id": row["type_id"], "type_label": row["type_label"], "items": [row]}
                for row in rows
            ]
            return CommandResult(
                data={
                    "announcements": rows,
                    "sections": sections,
                    "count": len(rows),
                },
                source=_source("mihoyo-announcement"),
            )

        def announcement_show(self, *, announcement_id: str) -> CommandResult:
            return CommandResult(
                data={
                    "announcement": {
                        "id": announcement_id,
                        "title": "公告",
                        "subtitle": "版本更新说明",
                        "banner_url": "https://example.test/banner.jpg",
                        "content_html": (
                            '<p>旅行者好。</p><p><img src="https://example.test/detail.jpg" /></p>'
                        ),
                        "image_urls": ["https://example.test/detail.jpg"],
                    }
                },
                source=_source("mihoyo-announcement"),
            )

        def codes_list(self) -> CommandResult:
            return CommandResult(
                data={"codes": [{"codes": ["GENSHINGIFT"]}], "count": 1},
                source=_source("fandom"),
            )

        def daily_materials(
            self,
            *,
            day: str | None,
            date: str | None = None,
            require_upgrade: bool = False,
        ) -> CommandResult:
            return CommandResult(
                data={
                    "date": date,
                    "day": day or "wednesday",
                    "domains": [
                        {
                            "id": "1",
                            "name": "精通秘境：深炎之底",
                            "city": 2,
                            "reward_item_ids": [104313],
                            "domain_icon_url": (
                                "https://gi.yatta.moe/assets/UI/UI_ItemIcon_104313.png"
                            ),
                            "items": [
                                {
                                    "id": "10000021",
                                    "type": "avatar",
                                    "name": "安柏",
                                    "rank": 4,
                                    "icon": "UI_AvatarIcon_Ambor",
                                    "icon_url": (
                                        "https://gi.yatta.moe/assets/UI/UI_AvatarIcon_Ambor.png"
                                    ),
                                },
                                {
                                    "id": "10000022",
                                    "type": "avatar",
                                    "name": "温迪",
                                    "rank": 5,
                                    "icon": "UI_AvatarIcon_Venti",
                                    "icon_url": (
                                        "https://gi.yatta.moe/assets/UI/UI_AvatarIcon_Venti.png"
                                    ),
                                },
                            ],
                        }
                    ],
                    "count": 1,
                },
                source=_source("ambr"),
            )

    return FakeProvider


def _fake_wiki_item(kind: str, query: str) -> dict[str, object]:
    if kind == "food":
        return {
            "id": "1004",
            "name": query,
            "rank": 2,
            "icon_url": "https://example.test/food.png",
            "description": "Tasty food.",
            "recipe": {
                "effect": {"0": "Restores HP."},
                "effect_icon": "UI_Buff_Item_Recovery_HpAdd",
                "effect_icon_url": "https://example.test/effect.png",
                "input": [
                    {
                        "id": "1001",
                        "name": "Flower",
                        "icon_url": "https://example.test/flower.png",
                        "count": 2,
                    }
                ],
            },
        }
    if kind == "artifact":
        return {
            "id": "15001",
            "name": query,
            "level_list": [4, 5],
            "bonuses": {"2": "ATK +18%.", "4": "Normal Attack DMG +35%."},
            "suit": [
                {
                    "slot": "flower",
                    "name": "Flower",
                    "description": "A flower.",
                    "icon_url": "https://example.test/artifact.png",
                }
            ],
        }
    if kind == "weapon":
        return {
            "id": "11101",
            "name": query,
            "rank": 1,
            "icon_url": "https://example.test/weapon.png",
            "weapon_type": "单手剑",
            "description": "A sword.",
            "special_prop": None,
            "affixes": [],
            "ascension": {"1001": 3},
            "upgrade": {
                "prop": [
                    {"propType": "FIGHT_PROP_BASE_ATTACK", "initValue": 23},
                ]
            },
        }
    return {
        "id": "10000021",
        "name": query,
        "rank": 4,
        "icon_url": "https://example.test/amber.png",
        "element": "Fire",
        "title": "Champion",
        "description": "Scout Knight.",
        "ascension": {"1001": 3},
        "talent": {
            "0": {
                "promote": {
                    "2": {"costItems": {"1002": 3}},
                    "3": {"costItems": {"1003": 2}},
                }
            }
        },
        "constellation": {
            "0": {
                "name": "One Arrow",
                "description": "Shoots one more arrow.",
                "icon": "UI_Talent_S_Ambor_01",
            }
        },
    }


def _source(provider: str) -> dict[str, object]:
    return {
        "provider": provider,
        "region": "cn",
        "cached": False,
        "fetched_at": "2026-04-29T10:30:00Z",
    }


def _sequence_client(responses: list[httpx.Response]) -> HttpClient:
    remaining = list(responses)

    def handler(_request: httpx.Request) -> httpx.Response:
        return remaining.pop(0)

    return HttpClient(
        timeout=1,
        cache_policy="off",
        transport=httpx.MockTransport(handler),
    )


def _json_response(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, json=payload)


def _fake_image_fetcher(requested_urls: list[str]):
    def fetcher(
        _args,
        urls,
        *,
        provider: str,
        region: str,
        category: str,
        unavailable_warning: str,
        max_workers: int = 8,
    ) -> tuple[dict[str, bytes], list[str]]:
        del provider, region, category, unavailable_warning, max_workers
        requested_urls.extend(urls)
        return {url: _png_bytes(url) for url in urls}, []

    return fetcher


def _png_bytes(seed: str) -> bytes:
    digest = hashlib.sha1(seed.encode("utf-8")).digest()
    image = Image.new("RGBA", (16, 16), (digest[0], digest[1], digest[2], 255))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
