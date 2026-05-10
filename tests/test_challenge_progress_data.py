from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import parse_qsl

import httpx
import pytest
from helpers import (
    json_response as _json_response,
    mock_client as _mock_client,
    run_json as _run_json,
)
from PIL import Image

from gsuid_cli.cli import run
from gsuid_cli.commands import challenge as challenge_commands, progress as progress_commands
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.secrets import SecretStore, redact_secret
from gsuid_cli.providers.mys import RECORD_SALT, MysProvider
from gsuid_cli.renderers.challenge import abyss as abyss_renderer
from gsuid_cli.renderers.common import crop_center


def test_challenge_abyss_requires_cookie(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    code, payload = _run_json(["challenge", "abyss", "--uid", "100000001"])

    assert code == 2
    assert payload["command"] == "challenge.abyss"
    assert payload["error"]["code"] == "AUTH_REQUIRED"


def test_challenge_abyss_validates_floor_before_cookie_lookup(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    code, payload = _run_json(["challenge", "abyss", "--uid", "100000001", "--floor", "8"])

    assert code == 1
    assert payload["command"] == "challenge.abyss"
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_challenge_and_progress_commands_use_stored_cookie(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands._shared.provider_for_region", _fake_provider)
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    commands = [
        (["challenge", "abyss", "--uid", "100000001"], "challenge.abyss", "abyss"),
        (["challenge", "theater", "--uid", "100000001"], "challenge.theater", "theater"),
        (["challenge", "hard", "--uid", "100000001"], "challenge.hard", "hard"),
        (["progress", "completion", "--uid", "100000001"], "progress.completion", "completion"),
        (["progress", "exploration", "--uid", "100000001"], "progress.exploration", "exploration"),
        (["progress", "collection", "--uid", "100000001"], "progress.collection", "collection"),
        (
            ["progress", "achievements", "--uid", "100000001"],
            "progress.achievements",
            "achievements",
        ),
        (["progress", "gcg", "--uid", "100000001"], "progress.gcg", "gcg"),
    ]

    for argv, command, key in commands:
        code, payload = _run_json(argv)

        assert code == 0
        assert payload["command"] == command
        assert payload["data"]["credential_source"] == "keyring"
        assert key in payload["data"]


def test_challenge_render_images(monkeypatch, tmp_path) -> None:
    captured_urls: list[str] = []
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands._shared.provider_for_region", _fake_provider)
    monkeypatch.setattr(
        challenge_commands,
        "fetch_render_images",
        _fake_image_fetcher(captured_urls),
    )
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    cases = [
        (
            ["challenge", "abyss", "--uid", "100000001", "--render", "image"],
            "challenge.abyss",
            "challenge/abyss",
            (950, 2000),
        ),
        (
            ["challenge", "theater", "--uid", "100000001", "--render", "image"],
            "challenge.theater",
            "challenge/theater",
            (1200, 1120),
        ),
        (
            ["challenge", "hard", "--uid", "100000001", "--render", "image"],
            "challenge.hard",
            "challenge/hard",
            (900, 1900),
        ),
    ]

    for argv, command, render, size in cases:
        code, payload = _run_json(
            [
                *argv,
                "--request-id",
                command,
                "--output-dir",
                str(tmp_path / "artifacts"),
            ]
        )

        assert code == 0
        assert payload["command"] == command
        assert payload["data"]["render"] == render
        artifact = payload["artifacts"][0]
        path = Path(artifact["path"])
        assert path.parent == tmp_path / "artifacts" / "2026-04-29" / command
        assert artifact["media_type"] == "image/png"
        assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        with Image.open(path) as image:
            assert image.size == size
            assert image.getbbox() is not None
            if command == "challenge.abyss":
                background = crop_center(
                    Image.open(abyss_renderer.TEXTURE / "bg.jpg").convert("RGBA"),
                    *size,
                ).convert("RGB")
                image_rgb = image.convert("RGB")
                assert image_rgb.getpixel((250, 575)) == background.getpixel((250, 575))
                assert (
                    "paste_footer"
                    not in abyss_renderer.render_challenge_abyss_card.__code__.co_names
                )

    assert "https://upload.example.test/avatar.png" in captured_urls
    assert "https://upload.example.test/amber.png" in captured_urls


def test_challenge_abyss_render_data_image_preserves_structured_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands._shared.provider_for_region", _fake_provider)
    monkeypatch.setattr(challenge_commands, "fetch_render_images", _fake_image_fetcher([]))
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(
        ["challenge", "abyss", "--uid", "100000001", "--render", "data,image"]
    )

    assert code == 0
    assert payload["data"]["abyss"]["floor_count"] == 1
    assert payload["data"]["artifact_sha256"] == payload["artifacts"][0]["sha256"]


def test_challenge_commands_render_text_write_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands._shared.provider_for_region", _fake_provider)
    monkeypatch.setattr(challenge_commands, "AkashaProvider", FakeHardRankProvider)
    monkeypatch.setattr(challenge_commands, "fetch_render_images", _fail_image_fetcher)
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    cases = [
        (
            ["challenge", "abyss", "--uid", "100000001"],
            "challenge.abyss",
            "challenge/abyss-text",
            "深境螺旋 - 派蒙",
            "第12层",
        ),
        (
            ["challenge", "theater", "--uid", "100000001"],
            "challenge.theater",
            "challenge/theater-text",
            "幻想真境剧诗 - 派蒙",
            "第1幕",
        ),
        (
            ["challenge", "hard", "--uid", "100000001"],
            "challenge.hard",
            "challenge/hard-text",
            "幽境危战 - 派蒙",
            "试炼",
        ),
        (
            ["challenge", "hard-rank"],
            "challenge.hard-rank",
            "challenge/hard-rank-text",
            "幽境危战排行",
            "数量: 1",
        ),
    ]

    for index, (argv, command, render_name, expected_title, expected_detail) in enumerate(cases):
        code, payload = _run_json(
            [
                *argv,
                "--render",
                "text",
                "--request-id",
                f"challenge-text-{index}",
                "--output-dir",
                str(tmp_path / "artifacts"),
            ]
        )

        assert code == 0
        assert payload["command"] == command
        assert payload["data"]["render"] == render_name
        artifact = payload["artifacts"][0]
        path = Path(artifact["path"])
        assert path.parent == tmp_path / "artifacts" / "2026-04-29" / f"challenge-text-{index}"
        assert artifact["kind"] == "text"
        assert artifact["media_type"] == "text/plain; charset=utf-8"
        assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        text = path.read_text(encoding="utf-8")
        assert expected_title in text
        assert expected_detail in text
        if command != "challenge.hard-rank":
            assert "Amber" in text


def test_challenge_plain_text_image_prints_image_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands._shared.provider_for_region", _fake_provider)
    monkeypatch.setattr(challenge_commands, "fetch_render_images", _fake_image_fetcher([]))
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(
        [
            "challenge",
            "abyss",
            "--uid",
            "100000001",
            "--render",
            "text,image",
            "--format",
            "plain",
            "--request-id",
            "challenge-plain-text-image",
            "--output-dir",
            str(tmp_path / "artifacts"),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert stderr.getvalue() == ""
    text = stdout.getvalue()
    assert text.startswith("深境螺旋 - 派蒙\nUID: 100000001\n")
    assert "\n\n图片已保存至: " in text
    assert "challenge-abyss_100000001.png" in text


def test_challenge_abyss_render_text_image_preserves_image_primary_artifact(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands._shared.provider_for_region", _fake_provider)
    monkeypatch.setattr(challenge_commands, "fetch_render_images", _fake_image_fetcher([]))
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(
        ["challenge", "abyss", "--uid", "100000001", "--render", "text,image"]
    )

    assert code == 0
    image_artifact, text_artifact = payload["artifacts"]
    assert image_artifact["kind"] == "image"
    assert text_artifact["kind"] == "text"
    assert payload["data"]["render"] == "challenge/abyss"
    assert payload["data"]["artifact_sha256"] == image_artifact["sha256"]
    assert payload["data"]["text_artifact_sha256"] == text_artifact["sha256"]


def test_challenge_hard_rank_plain_text_prints_warning(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(challenge_commands, "AkashaProvider", FakeHardRankProvider)
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(
        ["challenge", "hard-rank", "--render", "text", "--format", "plain"],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert stdout.getvalue().startswith("幽境危战排行\n")
    assert "数量: 1" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_progress_render_images(monkeypatch, tmp_path) -> None:
    captured_urls: list[str] = []
    fetcher = _fake_image_fetcher(captured_urls)
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands._shared.provider_for_region", _fake_provider)
    monkeypatch.setattr(progress_commands, "fetch_render_images", fetcher)
    monkeypatch.setattr("gsuid_cli.commands.player.impl.fetch_render_images", fetcher)
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    cases = [
        (
            ["progress", "completion", "--uid", "100000001", "--render", "image"],
            "progress.completion",
            "progress/completion",
            (1680, 1510),
        ),
        (
            ["progress", "exploration", "--uid", "100000001", "--render", "image"],
            "progress.exploration",
            "progress/exploration",
            (750, 945),
        ),
        (
            ["progress", "collection", "--uid", "100000001", "--render", "image"],
            "progress.collection",
            "progress/collection",
            (750, 1520),
        ),
        (
            ["progress", "achievements", "--uid", "100000001", "--render", "image"],
            "progress.achievements",
            "progress/achievements",
            (1950, 1110),
        ),
        (
            ["progress", "gcg", "--uid", "100000001", "--render", "image"],
            "progress.gcg",
            "progress/gcg",
            (900, 500),
        ),
        (
            ["progress", "gcg-deck", "--uid", "100000001", "--render", "image"],
            "progress.gcg-deck",
            "progress/gcg-deck",
            (950, 2300),
        ),
    ]

    for argv, command, render, size in cases:
        code, payload = _run_json(
            [
                *argv,
                "--request-id",
                command,
                "--output-dir",
                str(tmp_path / "artifacts"),
            ]
        )

        assert code == 0
        assert payload["command"] == command
        assert payload["data"]["render"] == render
        if command == "progress.gcg-deck":
            assert payload["data"]["deck_id"] == 1
            assert payload["data"]["deck_name"] == "Deck"
        artifact = payload["artifacts"][0]
        path = Path(artifact["path"])
        assert path.parent == tmp_path / "artifacts" / "2026-04-29" / command
        assert artifact["media_type"] == "image/png"
        assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        with Image.open(path) as image:
            assert image.size == size
            assert image.getbbox() is not None

    assert "https://upload.example.test/world.png" in captured_urls
    assert "https://upload.example.test/achievement.png" in captured_urls
    assert "https://upload.example.test/gcg-card.png" in captured_urls


def test_progress_commands_render_text_write_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands._shared.provider_for_region", _fake_provider)
    monkeypatch.setattr(progress_commands, "_public_provider", lambda _args: FakeGuideProvider())
    monkeypatch.setattr(progress_commands, "fetch_render_images", _fail_image_fetcher)
    monkeypatch.setattr("gsuid_cli.commands.player.impl.fetch_render_images", _fail_image_fetcher)
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    cases = [
        (
            ["progress", "completion", "--uid", "100000001"],
            "progress.completion",
            "progress/completion-text",
            "完成进度",
            "蒙德",
        ),
        (
            ["progress", "exploration", "--uid", "100000001"],
            "progress.exploration",
            "progress/exploration-text",
            "探索进度",
            "蒙德",
        ),
        (
            ["progress", "collection", "--uid", "100000001"],
            "progress.collection",
            "progress/collection-text",
            "收集进度",
            "普通宝箱",
        ),
        (
            ["progress", "achievements", "--uid", "100000001"],
            "progress.achievements",
            "progress/achievements-text",
            "成就进度",
            "天地万象",
        ),
        (
            ["progress", "achievement-guide", "--query", "commission"],
            "progress.achievement-guide",
            "progress/achievement-guide-text",
            "成就攻略查询",
            "分类: 天地万象",
        ),
        (
            ["progress", "commission-guide", "--query", "anna"],
            "progress.commission-guide",
            "progress/commission-guide-text",
            "委托攻略查询",
            "关联成就: Yo dala？",
        ),
        (
            ["progress", "gcg", "--uid", "100000001"],
            "progress.gcg",
            "progress/gcg-text",
            "七圣召唤 - TCG",
            "凯亚",
        ),
        (
            ["progress", "gcg-deck", "--uid", "100000001"],
            "progress.gcg-deck",
            "progress/gcg-deck-text",
            "七圣召唤卡组 - Deck",
            "Avatar",
        ),
    ]

    for index, (argv, command, render_name, expected_title, expected_detail) in enumerate(cases):
        code, payload = _run_json(
            [
                *argv,
                "--render",
                "text",
                "--request-id",
                f"progress-text-{index}",
                "--output-dir",
                str(tmp_path / "artifacts"),
            ]
        )

        assert code == 0
        assert payload["command"] == command
        assert payload["data"]["render"] == render_name
        artifact = payload["artifacts"][0]
        path = Path(artifact["path"])
        assert path.parent == tmp_path / "artifacts" / "2026-04-29" / f"progress-text-{index}"
        assert artifact["kind"] == "text"
        assert artifact["media_type"] == "text/plain; charset=utf-8"
        assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        text = path.read_text(encoding="utf-8")
        assert expected_title in text
        assert expected_detail in text


def test_progress_plain_text_image_prints_image_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands._shared.provider_for_region", _fake_provider)
    monkeypatch.setattr(progress_commands, "fetch_render_images", _fake_image_fetcher([]))
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(
        [
            "progress",
            "completion",
            "--uid",
            "100000001",
            "--render",
            "text,image",
            "--format",
            "plain",
            "--request-id",
            "progress-plain-text-image",
            "--output-dir",
            str(tmp_path / "artifacts"),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert stderr.getvalue() == ""
    text = stdout.getvalue()
    assert text.startswith("完成进度\nUID: 100000001\n")
    assert "\n\n图片已保存至: " in text
    assert "progress-completion_100000001.png" in text


def test_progress_render_text_image_preserves_image_primary_artifact(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands._shared.provider_for_region", _fake_provider)
    monkeypatch.setattr(progress_commands, "fetch_render_images", _fake_image_fetcher([]))
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(
        ["progress", "completion", "--uid", "100000001", "--render", "text,image"]
    )

    assert code == 0
    image_artifact, text_artifact = payload["artifacts"]
    assert image_artifact["kind"] == "image"
    assert text_artifact["kind"] == "text"
    assert payload["data"]["render"] == "progress/completion"
    assert payload["data"]["artifact_sha256"] == image_artifact["sha256"]
    assert payload["data"]["text_artifact_sha256"] == text_artifact["sha256"]


def test_progress_guide_plain_text_prints_warning(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        progress_commands,
        "_public_provider",
        lambda _args: FakeNoMatchGuideProvider(),
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(
        [
            "progress",
            "achievement-guide",
            "--query",
            "commission",
            "--render",
            "text",
            "--format",
            "plain",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert stdout.getvalue().startswith("成就攻略查询\n")
    assert "\033[33m警告: 暂无匹配成就攻略: commission" in stderr.getvalue()
    assert stderr.getvalue().endswith("\033[0m\n")


def test_challenge_abyss_render_image_requires_floor_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands._shared.provider_for_region", _empty_abyss_provider)
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(["challenge", "abyss", "--uid", "100000001", "--render", "image"])

    assert code == 6
    assert payload["command"] == "challenge.abyss"
    assert payload["error"]["code"] == "NO_RESULT"
    assert payload["artifacts"] == []


def test_challenge_abyss_render_text_allows_empty_floor_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands._shared.provider_for_region", _empty_abyss_provider)
    monkeypatch.setattr(challenge_commands, "fetch_render_images", _fail_image_fetcher)
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(["challenge", "abyss", "--uid", "100000001", "--render", "text"])

    assert code == 0
    assert payload["command"] == "challenge.abyss"
    assert payload["data"]["render"] == "challenge/abyss-text"
    assert payload["artifacts"][0]["kind"] == "text"
    text = Path(payload["artifacts"][0]["path"]).read_text(encoding="utf-8")
    assert "暂无深境螺旋楼层记录" in text


def test_challenge_abyss_overview_marks_missing_lower_floors_as_skipped() -> None:
    slots = abyss_renderer._overview_floor_slots(
        [
            {
                "index": 12,
                "star": 3,
                "max_star": 9,
                "settle_time": "2026-04-29 10:30:00",
            }
        ]
    )

    assert [slot["index"] for slot in slots] == [9, 10, 11, 12]
    assert [slot.get("settle_time") for slot in slots[:3]] == [
        "0000-00-00 00:00:00",
        "0000-00-00 00:00:00",
        "0000-00-00 00:00:00",
    ]


def test_challenge_abyss_image_time_text_uses_hyphen_dates() -> None:
    text = abyss_renderer._level_time_text({"battles": [{"timestamp": 1777132890}]})

    assert text.split(" ")[0].count("-") == 2
    assert "." not in text.split(" ")[0]


def test_challenge_abyss_image_rank_enrichment_preserves_source_data() -> None:
    provider = _fake_provider("cn", HttpClient(timeout=1, cache_policy="off"))
    result = provider.challenge_abyss(
        uid="100000001",
        cookie="account_id=1;cookie_token=secret",
        region="cn",
        credential_source="keyring",
        storage_backend="tests.MemoryKeyring",
    )
    abyss = result.data["abyss"]

    enriched, warnings = challenge_commands._abyss_with_character_ranks(
        provider,
        abyss,
        uid="100000001",
        region="cn",
        cookie="account_id=1;cookie_token=secret",
        credential_source="keyring",
        storage_backend="tests.MemoryKeyring",
    )

    original_avatar = abyss["floors"][0]["levels"][0]["battles"][0]["avatars"][0]
    enriched_avatar = enriched["floors"][0]["levels"][0]["battles"][0]["avatars"][0]
    assert warnings == []
    assert "rank" not in original_avatar
    assert enriched_avatar["rank"] == 2


def test_mys_challenge_abyss_filters_floor_and_uses_previous_schedule() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return _device_fp_response()
        return _json_response(
            {
                "retcode": 0,
                "message": "OK",
                "data": {
                    "total_star": 6,
                    "floors": [
                        {"index": 11, "star": 3},
                        {"index": 12, "star": 3},
                    ],
                },
            }
        )

    provider = MysProvider(_mock_client(handler))

    result = provider.challenge_abyss(
        uid="100000001",
        cookie="account_id=1;cookie_token=secret",
        region="cn",
        credential_source="keyring",
        storage_backend="tests.MemoryKeyring",
        season="previous",
        floor=12,
    )

    assert requests[1].url.path.endswith("/spiralAbyss")
    assert "schedule_type=2" in str(requests[1].url)
    assert result.data["abyss"]["floor_count"] == 1
    assert result.data["abyss"]["floors"][0]["index"] == 12


def test_mys_challenge_theater_signs_sent_query_and_marks_effective_season() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return _device_fp_response()
        return _json_response(
            {
                "retcode": 0,
                "message": "OK",
                "data": {"data": [{"stat": {"medal_num": 10}}]},
            }
        )

    provider = MysProvider(_mock_client(handler))

    result = provider.challenge_theater(
        uid="100000001",
        cookie="account_id=1;cookie_token=secret",
        region="cn",
        credential_source="keyring",
        storage_backend="tests.MemoryKeyring",
        season="previous",
    )

    query = dict(parse_qsl(requests[1].url.query.decode()))
    timestamp, random_value, digest = requests[1].headers["ds"].split(",")
    signed_query = "&".join(f"{key}={value}" for key, value in query.items())
    expected_digest = hashlib.md5(
        f"salt={RECORD_SALT}&t={timestamp}&r={random_value}&b=&q={signed_query}".encode()
    ).hexdigest()
    assert query == {"server": "cn_gf01", "role_id": "100000001", "need_detail": "true"}
    assert digest == expected_digest
    assert result.data["season"] == "previous"
    assert result.data["effective_season"] == "current"
    assert result.warnings == ["theater season selection is not exposed by the provider"]


def test_mys_challenge_hard_marks_effective_season_when_previous_requested() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return _device_fp_response()
        return _json_response(
            {
                "retcode": 0,
                "message": "OK",
                "data": {
                    "data": [
                        {
                            "schedule": {"start_time": "1777130000"},
                            "single": {"best": {"difficulty": 4}, "challenge": []},
                        }
                    ]
                },
            }
        )

    provider = MysProvider(_mock_client(handler))

    result = provider.challenge_hard(
        uid="100000001",
        cookie="account_id=1;cookie_token=secret",
        region="cn",
        credential_source="keyring",
        storage_backend="tests.MemoryKeyring",
        season="previous",
    )

    query = dict(parse_qsl(requests[1].url.query.decode()))
    assert requests[1].url.path.endswith("/hard_challenge")
    assert query == {"role_id": "100000001", "server": "cn_gf01", "need_detail": "true"}
    assert result.data["season"] == "previous"
    assert result.data["effective_season"] == "current"
    assert result.data["hard"]["count"] == 1
    assert result.data["hard"]["data"][0]["single"]["best"]["difficulty"] == 4
    assert result.warnings == ["hard challenge season selection is not exposed by the provider"]


def test_mys_challenge_errors_do_not_leak_cookie() -> None:
    provider = MysProvider(
        _sequence_client(
            [
                _device_fp_response(),
                _json_response({"retcode": 1034, "message": "", "data": None}),
            ]
        )
    )
    cookie = "account_id=1;cookie_token=secret"

    with pytest.raises(Exception) as exc:
        provider.challenge_abyss(
            uid="100000001",
            cookie=cookie,
            region="cn",
            credential_source="keyring",
            storage_backend="tests.MemoryKeyring",
            season="current",
        )

    assert "secret" not in json.dumps(exc.value.details, ensure_ascii=False)
    assert redact_secret(cookie) not in json.dumps(exc.value.details, ensure_ascii=False)


def test_mys_progress_achievements_posts_signed_body() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return _device_fp_response()
        return _json_response(
            {
                "retcode": 0,
                "message": "OK",
                "data": {"list": [{"id": 1, "name": "天地万象", "finish_num": 10}]},
            }
        )

    provider = MysProvider(_mock_client(handler))

    result = provider.progress_achievements(
        uid="100000001",
        cookie="account_id=1;cookie_token=secret",
        region="cn",
        credential_source="keyring",
        storage_backend="tests.MemoryKeyring",
    )

    body_text = requests[1].content.decode()
    timestamp, random_value, digest = requests[1].headers["ds"].split(",")
    expected_digest = hashlib.md5(
        f"salt={RECORD_SALT}&t={timestamp}&r={random_value}&b={body_text}&q=".encode()
    ).hexdigest()
    assert requests[1].url.path.endswith("/achievement")
    assert body_text == '{"role_id":"100000001","server":"cn_gf01"}'
    assert digest == expected_digest
    assert result.data["count"] == 1


def test_mys_progress_gcg_fetches_basic_and_decks() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return _device_fp_response()
        if len(requests) == 2:
            return _json_response(
                {"retcode": 0, "message": "OK", "data": {"level": 10, "nickname": "TCG"}}
            )
        return _json_response(
            {
                "retcode": 0,
                "message": "OK",
                "data": {"deck_list": [{"id": 1, "name": "Deck"}]},
            }
        )

    provider = MysProvider(_mock_client(handler))

    result = provider.progress_gcg(
        uid="100000001",
        cookie="account_id=1;cookie_token=secret",
        region="cn",
        credential_source="keyring",
        storage_backend="tests.MemoryKeyring",
    )

    assert requests[1].url.path.endswith("/gcg/basicInfo")
    assert requests[2].url.path.endswith("/gcg/deckList")
    assert result.data["gcg"]["basic"]["level"] == 10
    assert result.data["gcg"]["deck_count"] == 1


def test_mys_progress_gcg_deck_filters_deck_list_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return _device_fp_response()
        return _json_response(
            {
                "retcode": 0,
                "message": "OK",
                "data": {
                    "deck_list": [
                        {"id": 1, "name": "First"},
                        {"id": 2, "name": "Second"},
                    ]
                },
            }
        )

    provider = MysProvider(_mock_client(handler))

    result = provider.progress_gcg_deck(
        uid="100000001",
        cookie="account_id=1;cookie_token=secret",
        region="cn",
        credential_source="keyring",
        storage_backend="tests.MemoryKeyring",
        deck_id=2,
    )

    assert requests[1].url.path.endswith("/gcg/deckList")
    assert result.data["count"] == 1
    assert result.data["decks"][0]["name"] == "Second"


def test_challenge_title_context_uses_player_profile_picture_when_role_avatar_missing(
    monkeypatch,
) -> None:
    class Provider:
        def player_summary(self, **kwargs) -> CommandResult:
            return _result(kwargs, "summary", {"role": {"nickname": "派蒙"}, "stats": {}})

    monkeypatch.setattr(
        challenge_commands,
        "_player_profile_title_avatar_url",
        lambda _args, _uid, _region: ("https://enka.example.test/profile.png", ["profile"]),
    )
    monkeypatch.setattr(
        challenge_commands,
        "_player_profile_image_assets",
        lambda _args, url, _region: ({url: _png_bytes()}, ["profile image"]),
    )

    summary, images, avatar_url, warnings = challenge_commands._challenge_title_context(
        argparse.Namespace(),
        Provider(),
        uid="100000001",
        region="cn",
        cookie="account_id=1;cookie_token=secret",
        credential_source="keyring",
        storage_backend="tests.MemoryKeyring",
    )

    assert summary["role"]["nickname"] == "派蒙"
    assert avatar_url == "https://enka.example.test/profile.png"
    assert avatar_url in images
    assert warnings == ["profile", "profile image"]


def _fake_provider(_region: str, _http_client: HttpClient):
    class FakeProvider:
        def challenge_abyss(self, **kwargs) -> CommandResult:
            return _result(
                kwargs,
                "abyss",
                {
                    "total_battle_times": 2,
                    "floor_count": 1,
                    "rankings": {
                        "damage_rank": [
                            {
                                "avatar_id": 10000021,
                                "avatar_icon": "https://upload.example.test/amber-side.png",
                                "value": 12345,
                            }
                        ],
                        "defeat_rank": [],
                        "take_damage_rank": [],
                        "energy_skill_rank": [],
                    },
                    "floors": [
                        {
                            "index": 12,
                            "star": 3,
                            "max_star": 9,
                            "settle_time": "2026-04-29 10:30:00",
                            "levels": [
                                {
                                    "star": 3,
                                    "battles": [
                                        {
                                            "timestamp": 1777132890,
                                            "avatars": [
                                                {
                                                    "id": 10000021,
                                                    "name": "Amber",
                                                    "level": 80,
                                                    "rarity": 4,
                                                    "icon": "https://upload.example.test/amber.png",
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                },
            )

        def challenge_theater(self, **kwargs) -> CommandResult:
            return _result(
                kwargs,
                "theater",
                {
                    "count": 1,
                    "selected": {
                        "schedule": {"start_time": "1777130000", "end_time": "1779730000"},
                        "stat": {
                            "difficulty_id": 3,
                            "max_round_id": 1,
                            "medal_num": 1,
                            "coin_num": 10,
                            "avatar_bonus_num": 2,
                            "rent_cnt": 0,
                            "tarot_finished_cnt": 0,
                        },
                        "detail": {
                            "fight_statisic": {
                                "total_use_time": 90,
                                "max_damage_avatar": {
                                    "avatar_id": 10000021,
                                    "avatar_icon": "https://upload.example.test/amber-side.png",
                                    "value": 12345,
                                },
                            },
                            "rounds_data": [
                                {
                                    "is_get_medal": True,
                                    "round_id": 1,
                                    "is_tarot": False,
                                    "tarot_serial_no": -1,
                                    "splendour_buff": {
                                        "buffs": [
                                            {
                                                "name": "祝福",
                                                "icon": "https://upload.example.test/buff.png",
                                                "level": 1,
                                            }
                                        ]
                                    },
                                    "enemies": [
                                        {
                                            "name": "史莱姆",
                                            "icon": "https://upload.example.test/enemy.png",
                                        }
                                    ],
                                    "avatars": [
                                        {
                                            "avatar_id": 10000021,
                                            "avatar_type": 1,
                                            "name": "Amber",
                                            "level": 80,
                                            "rarity": 4,
                                            "image": "https://upload.example.test/amber.png",
                                        }
                                    ],
                                }
                            ],
                        },
                    },
                },
            )

        def challenge_hard(self, **kwargs) -> CommandResult:
            return _result(
                kwargs,
                "hard",
                {
                    "data": [
                        {
                            "schedule": {"start_time": "1777130000", "end_time": "1779730000"},
                            "single": {
                                "best": {"difficulty": 3, "second": 90},
                                "challenge": [
                                    {
                                        "name": "试炼",
                                        "second": 90,
                                        "monster": {
                                            "name": "史莱姆",
                                            "level": 90,
                                            "icon": "https://upload.example.test/enemy.png",
                                        },
                                        "teams": [
                                            {
                                                "avatar_id": 10000021,
                                                "name": "Amber",
                                                "level": 80,
                                                "rarity": 4,
                                                "image": "https://upload.example.test/amber.png",
                                                "rank": 2,
                                            }
                                        ],
                                        "best_avatar": [
                                            {
                                                "avatar_id": 10000021,
                                                "side_icon": "https://upload.example.test/amber-side.png",
                                                "dps": "12345",
                                            },
                                            {
                                                "avatar_id": 10000021,
                                                "side_icon": "https://upload.example.test/amber-side.png",
                                                "dps": "67890",
                                            },
                                        ],
                                    }
                                ],
                            },
                        }
                    ],
                    "count": 1,
                },
            )

        def player_summary(self, **kwargs) -> CommandResult:
            return _result(
                kwargs,
                "summary",
                {
                    "role": {
                        "nickname": "派蒙",
                        "level": 60,
                        "avatar_icon": "https://upload.example.test/avatar.png",
                    },
                    "stats": _fake_stats(),
                    "avatars": [
                        {
                            "id": 10000021,
                            "name": "Amber",
                            "level": 80,
                            "rarity": 4,
                        }
                    ],
                    "world_explorations": _fake_worlds(),
                },
            )

        def player_characters(self, **kwargs) -> CommandResult:
            return _result(
                kwargs,
                "characters",
                [
                    {
                        "id": 10000021,
                        "name": "Amber",
                        "actived_constellation_num": 2,
                    }
                ],
            )

        def progress_completion(self, **kwargs) -> CommandResult:
            return _result(
                kwargs,
                "completion",
                {
                    "stats": _fake_stats(),
                    "world_explorations": _fake_worlds(),
                    "exploration_count": 1,
                },
            )

        def progress_exploration(self, **kwargs) -> CommandResult:
            return _result(kwargs, "exploration", {"world_explorations": _fake_worlds()})

        def progress_collection(self, **kwargs) -> CommandResult:
            return _result(kwargs, "collection", {"raw_stats": _fake_stats()})

        def progress_achievements(self, **kwargs) -> CommandResult:
            return _result(
                kwargs,
                "achievements",
                [
                    {
                        "name": "天地万象",
                        "id": 1,
                        "percentage": -1,
                        "finish_num": 10,
                        "icon": "https://upload.example.test/achievement.png",
                    }
                ],
            )

        def progress_gcg(self, **kwargs) -> CommandResult:
            return _result(
                kwargs,
                "gcg",
                {
                    "basic": {
                        "level": 10,
                        "nickname": "TCG",
                        "avatar_card_num_gained": 10,
                        "avatar_card_num_total": 20,
                        "action_card_num_gained": 30,
                        "action_card_num_total": 40,
                        "covers": [
                            {
                                "id": 1103,
                                "image": "https://upload.example.test/gcg-card.png",
                            }
                        ],
                    },
                    "decks": [_fake_gcg_deck()],
                    "deck_count": 1,
                },
            )

        def progress_gcg_deck(self, **kwargs) -> CommandResult:
            deck_id = kwargs.get("deck_id")
            decks = [_fake_gcg_deck()] if deck_id in (None, 1) else []
            return CommandResult(
                data={
                    "uid": kwargs["uid"],
                    "credential_source": kwargs["credential_source"],
                    "storage_backend": kwargs["storage_backend"],
                    "deck_id": deck_id,
                    "decks": decks,
                    "count": len(decks),
                },
                source=_source(str(kwargs["region"])),
            )

    return FakeProvider()


class FakeHardRankProvider:
    def __init__(self, _http_client: HttpClient) -> None:
        pass

    def stygian_rank(self, *, region: str) -> CommandResult:
        assert region == "cn"
        return CommandResult(
            data={
                "available": True,
                "source": "akasha",
                "entries": [
                    {
                        "uid": "100000001",
                        "nickname": "派蒙",
                        "level": 60,
                        "stygian_index": 6,
                        "stygian_seconds": 90,
                        "stygian_time": "01:30",
                        "achievement_count": 900,
                    }
                ],
                "count": 1,
                "total_count": 1,
            },
            source=_source(region),
        )


class FakeGuideProvider:
    def achievement_guide(self, *, query: str) -> CommandResult:
        return CommandResult(
            data={
                "query": query,
                "kind": "achievement",
                "available": True,
                "matches": [
                    {
                        "name": "昨日重现",
                        "book": "天地万象",
                        "description": "激活60首旋律。",
                        "guide": "日常购买",
                        "link": "",
                    }
                ],
                "count": 1,
            },
            source=_source("cn"),
        )

    def commission_guide(self, *, query: str) -> CommandResult:
        return CommandResult(
            data={
                "query": query,
                "kind": "commission",
                "available": True,
                "matches": [
                    {
                        "name": "诗歌交流",
                        "achievement": "Yo dala？",
                        "description": "与丘丘人交流成功。",
                        "guide": "选择正确选项",
                        "link": "",
                    }
                ],
                "count": 1,
            },
            source=_source("cn"),
        )


class FakeNoMatchGuideProvider:
    def achievement_guide(self, *, query: str) -> CommandResult:
        return CommandResult(
            data={
                "query": query,
                "kind": "achievement",
                "available": True,
                "matches": [],
                "count": 0,
            },
            warnings=[f"暂无匹配成就攻略: {query}"],
            source=_source("cn"),
        )


def _fake_stats() -> dict[str, object]:
    return {
        "active_day_number": 100,
        "achievement_number": 10,
        "anemoculus_number": 66,
        "avatar_number": 1,
        "way_point_number": 10,
        "domain_number": 2,
        "spiral_abyss": "12-3",
        "common_chest_number": 20,
        "exquisite_chest_number": 15,
        "precious_chest_number": 10,
        "luxurious_chest_number": 5,
        "magic_chest_number": 3,
    }


def _fake_worlds() -> list[dict[str, object]]:
    return [
        {
            "id": 1,
            "name": "蒙德",
            "level": 10,
            "exploration_percentage": 800,
            "icon": "https://upload.example.test/world.png",
            "offerings": [
                {
                    "name": "忍冬之树",
                    "level": 8,
                    "icon": "https://upload.example.test/offering.png",
                }
            ],
        }
    ]


def _fake_gcg_deck() -> dict[str, object]:
    return {
        "id": 1,
        "name": "Deck",
        "avatar_cards": [
            {
                "id": 1,
                "name": "Avatar",
                "image": "https://upload.example.test/gcg-card.png",
            }
        ],
        "action_cards": [
            {
                "id": 2,
                "name": "Action",
                "image": "https://upload.example.test/gcg-action.png",
                "num": 2,
                "action_cost": [{"cost_type": "CostTypeSame", "cost_value": 1}],
            }
        ],
    }


def _empty_abyss_provider(_region: str, _http_client: HttpClient):
    class EmptyAbyssProvider:
        def challenge_abyss(self, **kwargs) -> CommandResult:
            return _result(
                kwargs,
                "abyss",
                {
                    "total_battle_times": 0,
                    "floor_count": 0,
                    "rankings": {},
                    "floors": [],
                },
            )

    return EmptyAbyssProvider()


def _result(kwargs: dict[str, object], key: str, value: object) -> CommandResult:
    return CommandResult(
        data={
            "uid": kwargs["uid"],
            "credential_source": kwargs["credential_source"],
            "storage_backend": kwargs["storage_backend"],
            key: value,
        },
        source=_source(str(kwargs["region"])),
    )


def _source(region: str) -> dict[str, object]:
    return {
        "provider": "mys",
        "region": region,
        "cached": False,
        "fetched_at": "2026-04-29T10:30:00Z",
    }


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
        url_list = list(urls)
        requested_urls.extend(url_list)
        return {url: _png_bytes() for url in url_list}, []

    return fetcher


def _fail_image_fetcher(*args, **kwargs):
    del args, kwargs
    raise AssertionError("text-only challenge renders must not fetch image assets")


def _png_bytes() -> bytes:
    image = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _sequence_client(responses: list[httpx.Response]) -> HttpClient:
    remaining = list(responses)

    def handler(_request: httpx.Request) -> httpx.Response:
        return remaining.pop(0)

    return _mock_client(handler)


def _device_fp_response() -> httpx.Response:
    return _json_response(
        {
            "retcode": 0,
            "message": "OK",
            "data": {"device_fp": "device-fp-1", "code": 200, "msg": "ok"},
        }
    )
