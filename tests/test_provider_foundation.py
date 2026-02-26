from __future__ import annotations

import json
import os

import httpx
import pytest

from gsuid_cli.core.cache import cache_key, sanitized_url
from gsuid_cli.core.errors import CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.providers.mys import MysProvider


def test_mys_cookie_validation_success() -> None:
    provider = MysProvider(_client(_json_response({"retcode": 0, "message": "OK", "data": {}})))

    result = provider.validate_cookie(
        uid="100000001",
        cookie="ltoken=secret-token",
        region="cn",
        credential_source="environment",
        storage_backend=None,
    )

    assert result.data["validity_status"] == "valid"
    assert result.data["provider_response"]["retcode"] == 0
    assert result.source["provider"] == "mys"


def test_mys_cookie_auth_failure_is_sanitized() -> None:
    provider = MysProvider(
        _client(_json_response({"retcode": -100, "message": "尚未登录", "data": None}))
    )

    with pytest.raises(CliError) as exc:
        provider.validate_cookie(
            uid="100000001",
            cookie="ltoken=secret-token",
            region="cn",
            credential_source="environment",
            storage_backend=None,
        )

    assert exc.value.code == "AUTH_EXPIRED"
    assert exc.value.exit_code == 2
    assert "secret-token" not in json.dumps(exc.value.details, ensure_ascii=False)
    assert exc.value.source["provider"] == "mys"


def test_non_json_provider_response_maps_to_upstream_error() -> None:
    client = _client(httpx.Response(200, text="<html>not json</html>"), debug=True)

    with pytest.raises(CliError) as exc:
        client.request_json(
            "GET",
            "https://example.test/path?authkey=secret",
            provider="mys",
            region="cn",
            category="test",
        )

    assert exc.value.code == "UPSTREAM_INVALID_RESPONSE"
    assert exc.value.exit_code == 3
    assert exc.value.details["url"] == "https://example.test/path"
    assert exc.value.details["body_preview"] == "<html>not json</html>"


def test_timeout_maps_to_network_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    client = HttpClient(
        timeout=1,
        cache_policy="off",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(CliError) as exc:
        client.request_json(
            "GET",
            "https://example.test/path",
            provider="mys",
            region="cn",
            category="test",
        )

    assert exc.value.code == "NETWORK_TIMEOUT"
    assert exc.value.exit_code == 4
    assert exc.value.retryable is True


def test_cache_key_excludes_secret_query_values() -> None:
    first = cache_key(
        "GET",
        "https://example.test/path?authkey=secret-a&role_id=100000001",
    )
    second = cache_key(
        "GET",
        "https://example.test/path?authkey=secret-b&role_id=100000001",
    )
    different_uid = cache_key(
        "GET",
        "https://example.test/path?authkey=secret-b&role_id=100000002",
    )

    assert first == second
    assert first != different_uid
    assert sanitized_url("https://example.test/path?authkey=secret&role_id=1").endswith("role_id=1")


def test_get_cache_policy_uses_cached_payload(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _json_response({"retcode": 0, "message": "OK", "data": {"calls": calls}})

    client = HttpClient(
        timeout=1,
        cache_policy="use",
        transport=httpx.MockTransport(handler),
    )
    kwargs = {
        "provider": "mys",
        "region": "cn",
        "category": "test",
        "params": {"role_id": "100000001"},
    }

    first = client.request_json("GET", "https://example.test/path", **kwargs)
    second = client.request_json("GET", "https://example.test/path", **kwargs)

    assert first.payload["data"]["calls"] == 1
    assert first.source["cached"] is False
    assert second.payload["data"]["calls"] == 1
    assert second.source["cached"] is True
    assert calls == 1


def test_qrcode_start_returns_session() -> None:
    provider = MysProvider(
        _client(
            _json_response(
                {
                    "retcode": 0,
                    "message": "OK",
                    "data": {"url": "https://example.test/login?ticket=ticket-1"},
                }
            )
        )
    )

    result = provider.create_qrcode_session(region="cn")

    assert result.data["app_id"] == "2"
    assert result.data["ticket"] == "ticket-1"
    assert result.data["url"] == "https://example.test/login?ticket=ticket-1"


def test_qrcode_poll_confirmed_does_not_return_game_token() -> None:
    provider = MysProvider(
        _client(
            _json_response(
                {
                    "retcode": 0,
                    "message": "OK",
                    "data": {
                        "stat": "Confirmed",
                        "payload": {"raw": json.dumps({"uid": "123456", "token": "game-secret"})},
                    },
                }
            )
        )
    )

    result = provider.poll_qrcode_session(
        app_id="2",
        ticket="ticket-1",
        device="device-1",
        region="cn",
    )

    assert result.data["status"] == "confirmed"
    assert result.data["account_id"] == "123456"
    assert "game-secret" not in json.dumps(result.data)


def test_qrcode_complete_exchanges_tokens() -> None:
    provider = MysProvider(
        _sequence_client(
            [
                _json_response(
                    {
                        "retcode": 0,
                        "message": "OK",
                        "data": {
                            "stat": "Confirmed",
                            "payload": {
                                "raw": json.dumps({"uid": "123456", "token": "game-secret"})
                            },
                        },
                    }
                ),
                _json_response(
                    {
                        "retcode": 0,
                        "message": "OK",
                        "data": {
                            "token": {"token": "stoken-secret"},
                            "user_info": {"aid": "123456", "mid": "mid-secret"},
                        },
                    }
                ),
                _json_response(
                    {
                        "retcode": 0,
                        "message": "OK",
                        "data": {"cookie_token": "cookie-secret"},
                    }
                ),
            ]
        )
    )

    result = provider.complete_qrcode_login(
        app_id="2",
        ticket="ticket-1",
        device="device-1",
        uid="100000001",
        region="cn",
    )

    assert result.data["uid"] == "100000001"
    assert result.data["account_id"] == "123456"
    assert result.data["cookie"] == "account_id=123456;cookie_token=cookie-secret"
    assert result.data["stoken"] == "stuid=123456;stoken=stoken-secret;mid=mid-secret"


def test_qrcode_complete_requires_confirmed_status() -> None:
    provider = MysProvider(
        _client(
            _json_response(
                {
                    "retcode": 0,
                    "message": "OK",
                    "data": {"stat": "Scanned", "payload": {"raw": ""}},
                }
            )
        )
    )

    with pytest.raises(CliError) as exc:
        provider.complete_qrcode_login(
            app_id="2",
            ticket="ticket-1",
            device="device-1",
            uid="100000001",
            region="cn",
        )

    assert exc.value.code == "QR_NOT_CONFIRMED"
    assert exc.value.exit_code == 6


@pytest.mark.skipif(
    os.environ.get("GSUID_LIVE_TESTS") != "1"
    or not os.environ.get("GSUID_COOKIE")
    or not os.environ.get("GSUID_TEST_UID"),
    reason="requires GSUID_LIVE_TESTS=1, GSUID_COOKIE, and GSUID_TEST_UID",
)
def test_live_cookie_validation_optional() -> None:
    uid = os.environ["GSUID_TEST_UID"]
    provider = MysProvider(HttpClient(timeout=20, cache_policy="off"))

    result = provider.validate_cookie(
        uid=uid,
        cookie=os.environ["GSUID_COOKIE"],
        region="cn",
        credential_source="environment",
        storage_backend=None,
    )

    assert result.data["validity_status"] == "valid"


def _client(response: httpx.Response, *, debug: bool = False) -> HttpClient:
    return HttpClient(
        timeout=1,
        cache_policy="off",
        debug=debug,
        transport=httpx.MockTransport(lambda _request: response),
    )


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
