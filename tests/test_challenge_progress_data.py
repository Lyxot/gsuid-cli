from __future__ import annotations

import hashlib
import io
import json
from urllib.parse import parse_qsl

import httpx
import pytest

from gsuid_cli.cli import run
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.secrets import SecretStore, redact_secret
from gsuid_cli.providers.mys import RECORD_SALT, MysProvider


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
    provider = MysProvider(
        _sequence_client(
            [
                _device_fp_response(),
                _json_response(
                    {
                        "retcode": 0,
                        "message": "OK",
                        "data": {"hard_challenge": {"schedule_id": 1}},
                    }
                ),
            ]
        )
    )

    result = provider.challenge_hard(
        uid="100000001",
        cookie="account_id=1;cookie_token=secret",
        region="cn",
        credential_source="keyring",
        storage_backend="tests.MemoryKeyring",
        season="previous",
    )

    assert result.data["season"] == "previous"
    assert result.data["effective_season"] == "current"
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


def _run_json(argv: list[str]) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    assert stderr.getvalue() == ""
    return code, json.loads(stdout.getvalue())


def _fake_provider(_region: str, _http_client: HttpClient):
    class FakeProvider:
        def challenge_abyss(self, **kwargs) -> CommandResult:
            return _result(kwargs, "abyss", {"floor_count": 0})

        def challenge_theater(self, **kwargs) -> CommandResult:
            return _result(kwargs, "theater", {"count": 0})

        def challenge_hard(self, **kwargs) -> CommandResult:
            return _result(kwargs, "hard", {"hard_challenge": {}})

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
