from __future__ import annotations

import hashlib
import io
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from helpers import json_response as _json_response
from helpers import run_json as _run_json
from PIL import Image

from gsuid_cli.cli import run
from gsuid_cli.core.errors import CliError
from gsuid_cli.core.http import HttpClient, ProviderBytesResponse
from gsuid_cli.core.models import CommandResult
from gsuid_cli.providers import public as public_provider
from gsuid_cli.providers.public import PublicDataProvider, _parse_active_codes
from gsuid_cli.renderers import recommend as recommend_renderer


def test_public_wiki_command_returns_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )

    code, payload = _run_json(["wiki", "character", "--name", "Amber"])

    assert code == 0
    assert payload["command"] == "wiki.character"
    assert payload["data"]["item"]["name"] == "Amber"
    assert payload["sources"][0]["provider"] == "ambr"


def test_public_commands_reject_unsupported_region(monkeypatch) -> None:
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )

    code, payload = _run_json(["--region", "os", "wiki", "character", "--name", "Amber"])

    assert code == 1
    assert payload["error"]["code"] == "REGION_UNSUPPORTED"


def test_daily_materials_rejects_conflicting_day_selectors() -> None:
    code, payload = _run_json(["daily", "materials", "--date", "2026-04-29", "--day", "monday"])

    assert code == 1
    assert payload["command"] == "daily.materials"
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_public_list_commands_return_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )

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
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data.daily.fetch_render_images",
        _fake_image_fetcher(requested_urls),
    )

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
    assert len(requested_urls) == 3
    with Image.open(path) as image:
        assert image.size[0] == 950
        assert image.size[1] >= 820
        assert image.getbbox() is not None


def test_daily_materials_render_data_image_preserves_structured_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data.daily.fetch_render_images", _fake_image_fetcher([])
    )

    code, payload = _run_json(["daily", "materials", "--day", "monday", "--render", "data,image"])

    assert code == 0
    assert payload["data"]["domains"][0]["items"][0]["name"] == "安柏"
    assert payload["data"]["render"] == "daily/materials"
    assert payload["data"]["artifact_sha256"] == payload["artifacts"][0]["sha256"]


def test_daily_materials_render_text_writes_artifact(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )

    code, payload = _run_json(
        [
            "--request-id",
            "daily-materials-text",
            "--output-dir",
            str(tmp_path / "artifacts"),
            "daily",
            "materials",
            "--day",
            "monday",
            "--render",
            "text",
        ]
    )

    assert code == 0
    assert payload["command"] == "daily.materials"
    assert payload["data"]["render"] == "daily/materials-text"
    artifact = payload["artifacts"][0]
    path = Path(artifact["path"])
    assert artifact["kind"] == "text"
    assert artifact["media_type"] == "text/plain; charset=utf-8"
    assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("每日材料 - 周一\n")
    assert "璃月 深炎之底 - 精通秘境" in text
    assert "安柏 ★★★★☆" in text
    assert "温迪 ★★★★★" in text


def test_daily_materials_render_text_plain_prints_text(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(
        [
            "--output-dir",
            str(tmp_path / "artifacts"),
            "daily",
            "materials",
            "--day",
            "monday",
            "--render",
            "text",
            "--format",
            "plain",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert stderr.getvalue() == ""
    text = stdout.getvalue()
    assert text.startswith("每日材料 - 周一\n")
    assert "璃月 深炎之底 - 精通秘境" in text


def test_daily_materials_plain_prints_image_path_when_render_image(monkeypatch, tmp_path) -> None:
    requested_urls: list[str] = []
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data.daily.fetch_render_images",
        _fake_image_fetcher(requested_urls),
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(
        [
            "--output-dir",
            str(tmp_path / "artifacts"),
            "daily",
            "materials",
            "--day",
            "monday",
            "--render",
            "text,image",
            "--format",
            "plain",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert stderr.getvalue() == ""
    text = stdout.getvalue()
    assert text.startswith("每日材料 - 周一\n")
    assert "\n\n图片已保存至: " in text
    assert "daily-materials_monday_" in text
    assert ".png" in text
    assert requested_urls


def test_daily_materials_plain_prints_image_only_path_with_blank_line(
    monkeypatch, tmp_path
) -> None:
    requested_urls: list[str] = []
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data.daily.fetch_render_images",
        _fake_image_fetcher(requested_urls),
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(
        [
            "--output-dir",
            str(tmp_path / "artifacts"),
            "daily",
            "materials",
            "--day",
            "monday",
            "--render",
            "image",
            "--format",
            "plain",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert stderr.getvalue() == ""
    assert stdout.getvalue().startswith("\n图片已保存至: ")
    assert "daily-materials_monday_" in stdout.getvalue()
    assert requested_urls


def test_wiki_picwiki_renderers_write_cards(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data.wiki.fetch_render_images", _fake_image_fetcher([])
    )

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


def test_wiki_render_text_writes_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )

    commands = [
        (
            ["wiki", "character", "--name", "Amber"],
            "wiki.character",
            "wiki/character-text",
            "角色资料 - Amber",
        ),
        (
            ["wiki", "weapon", "--name", "Dull Blade"],
            "wiki.weapon",
            "wiki/weapon-text",
            "武器资料 - Dull Blade",
        ),
        (
            ["wiki", "artifact", "--name", "Gladiator"],
            "wiki.artifact",
            "wiki/artifact-text",
            "圣遗物资料 - Gladiator",
        ),
        (["wiki", "enemy", "--name", "Slime"], "wiki.enemy", "wiki/enemy-text", "原魔资料 - Slime"),
        (
            ["wiki", "food", "--name", "Sweet Madame"],
            "wiki.food",
            "wiki/food-text",
            "食物资料 - Sweet Madame",
        ),
        (
            ["wiki", "talent", "--character", "Amber", "--talent", "1"],
            "wiki.talent",
            "wiki/talent-text",
            "角色天赋 - Amber",
        ),
        (
            ["wiki", "constellation", "--character", "Amber", "--constellation", "1"],
            "wiki.constellation",
            "wiki/constellation-text",
            "角色命座 - Amber",
        ),
        (
            ["wiki", "character-materials", "--character", "Amber"],
            "wiki.character-materials",
            "wiki/character-materials-text",
            "角色材料 - Amber",
        ),
        (
            ["wiki", "weapon-materials", "--weapon", "Dull Blade"],
            "wiki.weapon-materials",
            "wiki/weapon-materials-text",
            "武器材料 - Dull Blade",
        ),
    ]

    for argv, command, render, title in commands:
        code, payload = _run_json([*argv, "--render", "text"])

        assert code == 0
        assert payload["command"] == command
        assert payload["data"]["render"] == render
        artifact = payload["artifacts"][0]
        path = Path(artifact["path"])
        assert artifact["kind"] == "text"
        assert artifact["media_type"] == "text/plain; charset=utf-8"
        assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        text = path.read_text(encoding="utf-8")
        assert text.startswith(f"{title}\n")
        if command in {"wiki.talent", "wiki.character-materials", "wiki.weapon-materials"}:
            assert "Small Lamp Grass x3" in text
        if command == "wiki.artifact":
            assert "2件: ATK +18%." in text
            assert "4件: Normal Attack DMG +35%." in text


def test_wiki_plain_text_image_prints_image_path(monkeypatch, tmp_path) -> None:
    requested_urls: list[str] = []
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data.wiki.fetch_render_images",
        _fake_image_fetcher(requested_urls),
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(
        [
            "--output-dir",
            str(tmp_path / "artifacts"),
            "wiki",
            "food",
            "--name",
            "Sweet Madame",
            "--render",
            "text,image",
            "--format",
            "plain",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert stderr.getvalue() == ""
    text = stdout.getvalue()
    assert text.startswith("食物资料 - Sweet Madame\n")
    assert "Flower x2" in text
    assert "\n\n图片已保存至: " in text
    assert "wiki-food_Sweet_Madame_" in text
    assert ".png" in text
    assert requested_urls


def test_wiki_render_text_image_preserves_image_primary_artifact(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data.wiki.fetch_render_images",
        _fake_image_fetcher([]),
    )

    code, payload = _run_json(["wiki", "food", "--name", "Sweet Madame", "--render", "text,image"])

    assert code == 0
    assert payload["command"] == "wiki.food"
    assert payload["data"]["render"] == "wiki/food"
    image_artifact, text_artifact = payload["artifacts"]
    assert image_artifact["kind"] == "image"
    assert text_artifact["kind"] == "text"
    assert payload["data"]["artifact_sha256"] == image_artifact["sha256"]
    assert payload["data"]["text_artifact_sha256"] == text_artifact["sha256"]


def test_guide_image_render_writes_resource_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )
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
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data.guide.fetch_render_images", _fake_image_fetcher([])
    )

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
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )
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


def test_rerun_and_primogems_render_images_write_artifacts(monkeypatch, tmp_path) -> None:
    requested_urls: list[str] = []
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data.guide.fetch_render_images",
        _fake_image_fetcher(requested_urls),
    )

    commands = [
        (["rerun", "list"], "rerun.list", "rerun/list"),
        (["misc", "primogems-plan"], "misc.primogems-plan", "misc/primogems-plan"),
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

    assert "https://example.test/amber.png" in requested_urls


def test_guide_recommend_rerun_render_text_writes_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )

    commands = [
        (
            ["guide", "abyss", "--version", "9.9", "--floor", "12"],
            "guide.abyss",
            "guide/abyss-text",
            "深渊攻略 - 第12层（9.9）",
            "草史莱姆 x2",
        ),
        (
            ["guide", "theater", "--version", "1"],
            "guide.theater",
            "guide/theater-text",
            "剧诗攻略 - 1",
            "特邀角色:\n  - 安柏",
        ),
        (
            ["recommend", "build", "--character", "Amber"],
            "recommend.build",
            "recommend/build-text",
            "养成推荐 - Amber",
            "5星: Bow",
        ),
        (
            ["recommend", "holder", "--item", "Bow"],
            "recommend.holder",
            "recommend/holder-text",
            "适用角色推荐 - Bow",
            "适用角色: Amber",
        ),
        (
            ["rerun", "list", "--limit", "1"],
            "rerun.list",
            "rerun/list-text",
            "未复刻列表 - 当前版本:9.9",
            "安柏: 120天未复刻",
        ),
    ]

    for argv, command, render, title, expected in commands:
        code, payload = _run_json([*argv, "--render", "text"])

        assert code == 0
        assert payload["command"] == command
        assert payload["data"]["render"] == render
        artifact = payload["artifacts"][0]
        path = Path(artifact["path"])
        assert artifact["kind"] == "text"
        assert artifact["media_type"] == "text/plain; charset=utf-8"
        assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        text = path.read_text(encoding="utf-8")
        assert text.startswith(f"{title}\n")
        assert expected in text


def test_recommend_render_text_image_preserves_image_primary_artifact(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )

    code, payload = _run_json(
        ["recommend", "build", "--character", "Amber", "--render", "text,image"]
    )

    assert code == 0
    assert payload["command"] == "recommend.build"
    assert payload["data"]["render"] == "recommend/build"
    image_artifact, text_artifact = payload["artifacts"]
    assert image_artifact["kind"] == "image"
    assert text_artifact["kind"] == "text"
    assert payload["data"]["artifact_sha256"] == image_artifact["sha256"]
    assert payload["data"]["text_artifact_sha256"] == text_artifact["sha256"]


def test_event_render_images_write_cards(monkeypatch, tmp_path) -> None:
    requested_urls: list[str] = []
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data.events.fetch_render_images",
        _fake_image_fetcher(requested_urls),
    )

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


def test_event_render_text_writes_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )

    commands = [
        (["events", "list"], "events.list", "events/list-text", "活动列表 - 进行中", "普通活动"),
        (
            ["events", "banners"],
            "events.banners",
            "events/banners-text",
            "活动祈愿 - 进行中",
            "角色活动祈愿",
        ),
    ]

    for argv, command, render, title, row_name in commands:
        code, payload = _run_json([*argv, "--render", "text"])

        assert code == 0
        assert payload["command"] == command
        assert payload["data"]["render"] == render
        artifact = payload["artifacts"][0]
        path = Path(artifact["path"])
        assert artifact["kind"] == "text"
        assert artifact["media_type"] == "text/plain; charset=utf-8"
        assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        text = path.read_text(encoding="utf-8")
        assert text.startswith(f"{title}\n")
        assert row_name in text
        assert "时间: 2026-04-01 10:00:00 至 2026-05-01 03:59:59" in text
        assert "图片: https://example.test/a.jpg" in text


def test_codes_render_text_writes_artifact(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )

    code, payload = _run_json(["codes", "list", "--render", "text"])

    assert code == 0
    assert payload["command"] == "codes.list"
    assert payload["data"]["render"] == "codes/list-text"
    artifact = payload["artifacts"][0]
    path = Path(artifact["path"])
    assert artifact["kind"] == "text"
    assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("兑换码\n")
    assert "可用兑换码\n  - GENSHINGIFT" in text
    assert "    服务器: 美服、欧服、亚服、港澳台服" in text
    assert "    奖励: 原石 x50、Jueyun Chili Chicken x5、Stir-Fried Fish Noodles x5" in text


def test_announcements_render_text_writes_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )

    commands = [
        (
            ["announcements", "list", "--limit", "3"],
            "announcements.list",
            "announcements/list-text",
            "公告列表",
            "公告\n",
            "公告ID: 1003",
        ),
        (
            ["announcements", "show", "--id", "1003"],
            "announcements.show",
            "announcements/show-text",
            "公告详情",
            "旅行者好。",
            None,
        ),
    ]

    for argv, command, render, title, expected, optional_expected in commands:
        code, payload = _run_json([*argv, "--render", "text"])

        assert code == 0
        assert payload["command"] == command
        assert payload["data"]["render"] == render
        artifact = payload["artifacts"][0]
        path = Path(artifact["path"])
        assert artifact["kind"] == "text"
        assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        text = path.read_text(encoding="utf-8")
        assert text.startswith(f"{title}\n")
        assert expected in text
        if optional_expected is not None:
            assert optional_expected in text


def test_announcements_plain_text_image_prints_image_path(monkeypatch, tmp_path) -> None:
    requested_urls: list[str] = []
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data.events.fetch_render_images",
        _fake_image_fetcher(requested_urls),
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(
        [
            "--output-dir",
            str(tmp_path / "artifacts"),
            "announcements",
            "show",
            "--id",
            "1003",
            "--render",
            "text,image",
            "--format",
            "plain",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert stderr.getvalue() == ""
    text = stdout.getvalue()
    assert text.startswith("公告详情\n")
    assert "旅行者好。" in text
    assert "\n\n图片已保存至: " in text
    assert "announcements-show_1003" in text
    assert requested_urls == [
        "https://example.test/banner.jpg",
        "https://example.test/detail.jpg",
    ]


def test_announcement_render_images_write_cards(monkeypatch, tmp_path) -> None:
    requested_urls: list[str] = []
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data.events.fetch_render_images",
        _fake_image_fetcher(requested_urls),
    )

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
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )

    code, payload = _run_json(["announcements", "show", "--latest"])

    assert code == 0
    assert payload["command"] == "announcements.show"
    assert payload["data"]["announcement"]["id"] == "1001"
    assert payload["data"]["selected_announcement"] == {
        "mode": "latest",
        "id": "1001",
        "start_at": "2026-05-01 10:00:00",
    }


def test_wiki_constellation_render_data_image_preserves_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", _fake_provider()
    )
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data.wiki.fetch_render_images", _fake_image_fetcher([])
    )

    code, payload = _run_json(
        [
            "wiki",
            "constellation",
            "--character",
            "Amber",
            "--constellation",
            "1",
            "--render",
            "data,image",
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
        "日常材料升级数据不可用；返回的秘境不包含物品匹配"
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
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    abyss_js = """
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
"""
    revision = "d7f257336b709273d5371a43da70cc6df2c35980"
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if str(request.url).startswith(public_provider.GENSHINUID_ABYSS_JS_COMMITS_URL):
            assert request.url.params["path"] == public_provider.GENSHINUID_ABYSS_JS_PATH
            assert request.url.params["per_page"] == "1"
            return httpx.Response(200, json=[{"sha": revision}])
        return httpx.Response(
            200,
            content=abyss_js.encode("utf-8"),
            headers={"content-type": "application/javascript"},
        )

    provider = PublicDataProvider(
        HttpClient(
            timeout=1,
            cache_policy="off",
            transport=httpx.MockTransport(handler),
        )
    )

    result = provider.guide_abyss(version="9.9", floor=12)

    assert requested_urls == [
        (
            f"{public_provider.GENSHINUID_ABYSS_JS_COMMITS_URL}"
            "?path=GenshinUID%2Fgenshinuid_guide%2Fabyss.js&per_page=1"
        ),
        public_provider._genshinuid_abyss_js_url(revision),
    ]
    assert result.data["available"] is True
    assert result.source["provider"] == "genshinuid"
    assert result.source["category"] == "guide.abyss.data"
    assert result.source["revision"] == revision
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


def test_rerun_list_uses_teyvat_return_list() -> None:
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(
                    {
                        "code": 200,
                        "version": "当前版本:9.9",
                        "result": [
                            [
                                {
                                    "role": "安柏",
                                    "avatar": "https://example.test/amber.png",
                                    "star": 5,
                                    "days": 100,
                                    "history": ["9.0上半"],
                                }
                            ],
                            [],
                            [],
                            [
                                {
                                    "role": "弓",
                                    "avatar": "https://example.test/bow.png",
                                    "star": 5,
                                    "days": 80,
                                    "history": ["9.1下半"],
                                }
                            ],
                        ],
                    }
                )
            ]
        )
    )

    result = provider.rerun_list(limit=2)

    assert result.source["provider"] == "teyvat"
    assert result.data["version"] == "当前版本:9.9"
    assert result.data["groups"][0]["items"][0]["entity"] == "安柏"
    assert result.data["groups"][3]["items"][0]["rarity"] == 4
    assert result.data["reruns"][1]["entity"] == "弓"


def test_primogems_plan_reports_bundled_versions(monkeypatch, tmp_path) -> None:
    image_dir = tmp_path / "primogems"
    image_dir.mkdir()
    (image_dir / "5.0.png").write_bytes(b"png")
    (image_dir / "4.8.png").write_bytes(b"png")
    monkeypatch.setattr(public_provider, "PRIMOGEMS_PLAN_ASSET_DIR", image_dir)
    provider = PublicDataProvider(_sequence_client([]))

    result = provider.primogems_plan(version=None)

    assert result.data["available_versions"] == ["4.8", "5.0"]
    assert result.data["selected_version"] == "5.0"
    assert result.source["path"] == "package:assets/misc/primogems"


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

        def material_names_by_id(self) -> dict[str, str]:
            return {"1001": "Small Lamp Grass"}

        def character_talent(self, *, character: str, talent: int) -> CommandResult:
            return CommandResult(
                data={
                    "character": character,
                    "talent": {
                        "index": talent,
                        "name": "Sharpshooter",
                        "type": "普通攻击",
                        "description": "Fires arrows.",
                        "promote": {"2": {"costItems": {"1001": 3}}},
                    },
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

        def rerun_list(self, *, limit: int) -> CommandResult:
            row = {
                "entity": "安柏",
                "kind": "character",
                "rarity": 4,
                "icon_url": "https://example.test/amber.png",
                "days_since_last_banner": 120,
                "last_banner_version": "9.1上半",
            }
            return CommandResult(
                data={
                    "version": "当前版本:9.9",
                    "groups": [
                        {"kind": "character", "rarity": 5, "label": "五星角色", "items": []},
                        {"kind": "character", "rarity": 4, "label": "四星角色", "items": [row]},
                        {"kind": "weapon", "rarity": 5, "label": "五星武器", "items": []},
                        {"kind": "weapon", "rarity": 4, "label": "四星武器", "items": []},
                    ],
                    "reruns": [row][:limit],
                    "count": min(1, limit),
                    "total_count": 1,
                },
                source=_source("teyvat"),
            )

        def primogems_plan(self, *, version: str | None) -> CommandResult:
            available_versions = ["4.8", "5.0", "6.0"]
            selected_version = version if version in available_versions else "6.0"
            return CommandResult(
                data={
                    "version": version,
                    "selected_version": selected_version,
                    "available_versions": available_versions,
                    "estimate_available": True,
                    "estimate": None,
                    "source_limitations": [
                        "GenshinUID provides this command as a static version-plan image"
                    ],
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
                        "text": "旅行者好。",
                        "image_urls": ["https://example.test/detail.jpg"],
                    }
                },
                source=_source("mihoyo-announcement"),
            )

        def codes_list(self) -> CommandResult:
            return CommandResult(
                data={
                    "codes": [
                        {
                            "codes": ["GENSHINGIFT"],
                            "servers": ["America", "Europe", "Asia", "TW/HK/Macao"],
                            "rewards": [
                                {"name": "Primogem", "count": 50},
                                {"name": "Jueyun Chili Chicken", "count": 5},
                                {"name": "Stir-Fried Fish Noodles", "count": 5},
                            ],
                        }
                    ],
                    "count": 1,
                },
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
                            "domain_icon_url": "https://example.test/domain-icon.png",
                            "items": [
                                {
                                    "id": "10000021",
                                    "type": "avatar",
                                    "name": "安柏",
                                    "rank": 4,
                                    "icon": "UI_AvatarIcon_Ambor",
                                    "icon_url": "https://example.test/ambor.png",
                                },
                                {
                                    "id": "10000022",
                                    "type": "avatar",
                                    "name": "温迪",
                                    "rank": 5,
                                    "icon": "UI_AvatarIcon_Venti",
                                    "icon_url": "https://example.test/venti.png",
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
            "bonuses": {"2150010": "ATK +18%.", "2150011": "Normal Attack DMG +35%."},
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
            "special_prop": "None",
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
