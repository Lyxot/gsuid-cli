from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import parse_qsl

import httpx
import pytest
from PIL import Image

from gsuid_cli.cli import run
from gsuid_cli.commands import challenge as challenge_commands
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.secrets import SecretStore, redact_secret
from gsuid_cli.providers.mys import RECORD_SALT, MysProvider
from gsuid_cli.renderers.challenge.abyss import _overview_floor_slots


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
    monkeypatch.setattr("gsuid_cli.commands.challenge.provider_for_region", _fake_provider)
    monkeypatch.setattr("gsuid_cli.commands.progress.provider_for_region", _fake_provider)
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
    monkeypatch.setattr("gsuid_cli.commands.challenge.provider_for_region", _fake_provider)
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

    assert "https://upload.example.test/avatar.png" in captured_urls
    assert "https://upload.example.test/amber.png" in captured_urls


def test_challenge_abyss_render_both_preserves_structured_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.challenge.provider_for_region", _fake_provider)
    monkeypatch.setattr(challenge_commands, "fetch_render_images", _fake_image_fetcher([]))
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(["challenge", "abyss", "--uid", "100000001", "--render", "both"])

    assert code == 0
    assert payload["data"]["abyss"]["floor_count"] == 1
    assert payload["data"]["artifact_sha256"] == payload["artifacts"][0]["sha256"]


def test_challenge_abyss_render_image_requires_floor_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.challenge.provider_for_region", _empty_abyss_provider)
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(["challenge", "abyss", "--uid", "100000001", "--render", "image"])

    assert code == 6
    assert payload["command"] == "challenge.abyss"
    assert payload["error"]["code"] == "NO_RESULT"
    assert payload["artifacts"] == []


def test_challenge_abyss_overview_marks_missing_lower_floors_as_skipped() -> None:
    slots = _overview_floor_slots(
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


def _run_json(argv: list[str]) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    assert stderr.getvalue() == ""
    return code, json.loads(stdout.getvalue())


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
                    "stats": {},
                },
            )

        def progress_completion(self, **kwargs) -> CommandResult:
            return _result(kwargs, "completion", {"stats": {}})

        def progress_exploration(self, **kwargs) -> CommandResult:
            return _result(kwargs, "exploration", {"world_explorations": []})

        def progress_collection(self, **kwargs) -> CommandResult:
            return _result(kwargs, "collection", {"raw_stats": {}})

        def progress_achievements(self, **kwargs) -> CommandResult:
            return _result(kwargs, "achievements", [])

        def progress_gcg(self, **kwargs) -> CommandResult:
            return _result(kwargs, "gcg", {"basic": {}, "decks": []})

    return FakeProvider()


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


def _png_bytes() -> bytes:
    image = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _mock_client(handler) -> HttpClient:
    return HttpClient(
        timeout=1,
        cache_policy="off",
        transport=httpx.MockTransport(handler),
    )


def _sequence_client(responses: list[httpx.Response]) -> HttpClient:
    remaining = list(responses)

    def handler(_request: httpx.Request) -> httpx.Response:
        return remaining.pop(0)

    return _mock_client(handler)


def _json_response(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, json=payload)


def _device_fp_response() -> httpx.Response:
    return _json_response(
        {
            "retcode": 0,
            "message": "OK",
            "data": {"device_fp": "device-fp-1", "code": 200, "msg": "ok"},
        }
    )
