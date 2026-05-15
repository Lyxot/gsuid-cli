from __future__ import annotations

import json
import os

import httpx
import pytest

from gsuid_cli.core.cache import cache_key, sanitized_url
from gsuid_cli.core.errors import CliError
from gsuid_cli.core.http import (
    HttpClient,
    begin_source_capture,
    end_source_capture,
    raise_for_retcode,
)
from gsuid_cli.providers.mys import MysProvider


def test_mys_cookie_validation_success() -> None:
    provider = MysProvider(_client(_account_card_response()))

    result = provider.validate_cookie(
        uid="100000001",
        cookie="account_id=1;cookie_token=secret-token",
        region="cn",
        credential_source="environment",
        storage_backend=None,
    )

    assert result.data["validity_status"] == "valid"
    assert result.data["provider_response"]["retcode"] == 0
    assert result.data["provider_response"]["role"]["game_role_id"] == "100000001"
    assert result.source["provider"] == "mys"


def test_http_client_source_capture_records_request_metadata() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"retcode": 0, "data": {}})

    token = begin_source_capture()
    try:
        response = HttpClient(
            timeout=1,
            cache_policy="off",
            transport=httpx.MockTransport(handler),
        ).request_json(
            "GET",
            "https://example.test/data",
            provider="test",
            region="cn",
            category="unit.capture",
        )
    finally:
        sources = end_source_capture(token)

    assert sources == [response.source]
    assert sources[0]["category"] == "unit.capture"
    assert sources[0]["status_code"] == 200
    assert sources[0]["retcode"] == 0


def test_http_client_cached_source_capture_keeps_retcode(tmp_path) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"retcode": 0, "data": {"ok": True}})

    client = HttpClient(
        timeout=1,
        cache_policy="use",
        output_dir=str(tmp_path),
        transport=httpx.MockTransport(handler),
    )
    kwargs = {
        "provider": "test",
        "region": "cn",
        "category": "unit.cached",
    }
    client.request_json("GET", "https://example.test/data", **kwargs)

    token = begin_source_capture()
    try:
        response = client.request_json("GET", "https://example.test/data", **kwargs)
    finally:
        sources = end_source_capture(token)

    assert calls == 1
    assert sources == [response.source]
    assert sources[0]["cached"] is True
    assert sources[0]["retcode"] == 0


def test_http_client_upstream_error_source_keeps_fetched_at() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    token = begin_source_capture()
    try:
        with pytest.raises(CliError):
            HttpClient(
                timeout=1,
                cache_policy="off",
                transport=httpx.MockTransport(handler),
            ).request_json(
                "GET",
                "https://example.test/data",
                provider="test",
                region="cn",
                category="unit.error",
            )
    finally:
        sources = end_source_capture(token)

    assert sources[0]["category"] == "unit.error"
    assert sources[0]["status_code"] == 503
    assert sources[0]["fetched_at"] is not None


def test_mys_cookie_validation_uses_record_headers() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return _account_card_response()

    provider = MysProvider(
        HttpClient(
            timeout=1,
            cache_policy="off",
            transport=httpx.MockTransport(handler),
        )
    )

    provider.validate_cookie(
        uid="100000001",
        cookie="account_id=1;cookie_token=secret-token",
        region="cn",
        credential_source="keyring",
        storage_backend="test",
    )

    request = captured["request"]
    assert str(request.url).endswith("/game_record/card/wapi/getGameRecordCard?uid=1")
    assert request.headers["x-rpc-app_version"] == "2.102.1"
    assert request.headers["x-rpc-client_type"] == "5"
    assert request.headers["x-requested-with"] == "com.mihoyo.hyperion"
    assert request.headers["ds"].count(",") == 2


def test_mys_cookie_validation_rejects_unlinked_uid() -> None:
    provider = MysProvider(_client(_account_card_response(game_role_id="100000002")))

    with pytest.raises(CliError) as exc:
        provider.validate_cookie(
            uid="100000001",
            cookie="account_id=1;cookie_token=secret-token",
            region="cn",
            credential_source="environment",
            storage_backend=None,
        )

    assert exc.value.code == "AUTH_UID_MISMATCH"
    assert exc.value.exit_code == 2
    assert exc.value.details["linked_game_uids"] == ["100000002"]


def test_mys_cookie_validation_falls_back_without_account_id() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return _json_response({"retcode": 0, "message": "OK", "data": {}})

    provider = MysProvider(
        HttpClient(
            timeout=1,
            cache_policy="off",
            transport=httpx.MockTransport(handler),
        )
    )

    result = provider.validate_cookie(
        uid="100000001",
        cookie="ltoken=secret-token",
        region="cn",
        credential_source="environment",
        storage_backend=None,
    )

    assert result.data["validity_status"] == "valid"
    assert str(captured["request"].url).endswith(
        "/game_record/app/genshin/api/index?role_id=100000001&server=cn_gf01"
    )


def test_mys_cookie_validation_uses_hoyolab_record_endpoint_for_os_uid() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return _json_response({"retcode": 0, "message": "OK", "data": {}})

    provider = MysProvider(
        HttpClient(
            timeout=1,
            cache_policy="off",
            transport=httpx.MockTransport(handler),
        )
    )

    result = provider.validate_cookie(
        uid="800000001",
        cookie="ltoken=secret-token",
        region="os",
        credential_source="environment",
        storage_backend=None,
    )

    request = captured["request"]
    assert result.data["validity_status"] == "valid"
    assert request.url.host == "bbs-api-os.hoyolab.com"
    assert str(request.url).endswith(
        "/game_record/genshin/api/index?role_id=800000001&server=os_asia"
    )
    assert request.headers["x-rpc-app_version"] == "1.5.0"
    assert request.headers["x-rpc-client_type"] == "4"
    assert request.headers["ds"].count(",") == 2


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


def test_verification_retcode_uses_actionable_error() -> None:
    with pytest.raises(CliError) as exc:
        raise_for_retcode(
            {"retcode": 1034, "message": ""},
            provider="mys",
            region="cn",
            category="daily.note",
            source={
                "provider": "mys",
                "region": "cn",
                "cached": False,
                "fetched_at": "2026-04-29T10:30:00Z",
            },
        )

    assert exc.value.code == "UPSTREAM_VERIFICATION_REQUIRED"
    assert exc.value.exit_code == 3


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


def test_cookie_refresh_exchanges_stoken_for_cookie() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _json_response(
            {
                "retcode": 0,
                "message": "OK",
                "data": {"cookie_token": "fresh-cookie"},
            }
        )

    provider = MysProvider(
        HttpClient(
            timeout=1,
            cache_policy="off",
            transport=httpx.MockTransport(handler),
        )
    )

    result = provider.refresh_cookie_from_stoken(
        uid="100000001",
        stoken_cookie="stuid=123456;stoken=stoken-secret;mid=mid-secret",
        region="cn",
        credential_source="keyring",
        storage_backend="memory",
    )

    assert result.data["validity_status"] == "refreshed"
    assert result.data["cookie"] == "account_id=123456;cookie_token=fresh-cookie"
    assert result.data["redacted"] != result.data["cookie"]
    assert requests[0].url.params["stoken"] == "stoken-secret"
    assert requests[0].url.params["uid"] == "123456"
    assert requests[0].headers["cookie"] == "stuid=123456;stoken=stoken-secret;mid=mid-secret"


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


def test_device_set_uses_existing_fp_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _json_response({"retcode": 0, "message": "OK", "data": {}})

    provider = MysProvider(
        HttpClient(
            timeout=1,
            cache_policy="off",
            transport=httpx.MockTransport(handler),
        )
    )

    result = provider.device_login(
        uid="100000001",
        cookie="account_id=1;cookie_token=secret-token",
        region="cn",
        credential_source="keyring",
        storage_backend="test",
        device_payload={
            "fp": "fp-secret",
            "device_id": "device-secret",
            "device_info": "OnePlus/PHK110/OP5913L1",
        },
    )

    assert [request.url.path for request in requests] == [
        "/apihub/api/deviceLogin",
        "/apihub/api/saveDevice",
    ]
    assert requests[0].headers["x-rpc-device_id"] == "device-secret"
    assert requests[0].headers["x-rpc-device_fp"] == "fp-secret"
    assert requests[0].headers["host"] == "bbs-api.miyoushe.com"
    assert result.data["device_id"] == "device-secret"
    assert result.data["device_fp"] == "fp-secret"
    assert result.data["redacted"]["device_fp"] != "fp-secret"
    assert result.data["provider_response"]["device_set"]["retcode"] == 0


def test_device_set_generates_fp_from_app_payload() -> None:
    requests: list[httpx.Request] = []
    responses = [
        _json_response({"retcode": 0, "message": "OK", "data": {"device_fp": "generated-fp"}}),
        _json_response({"retcode": 0, "message": "OK", "data": {}}),
        _json_response({"retcode": 0, "message": "OK", "data": {}}),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return responses.pop(0)

    provider = MysProvider(
        HttpClient(
            timeout=1,
            cache_policy="off",
            transport=httpx.MockTransport(handler),
        )
    )

    result = provider.device_login(
        uid="100000001",
        cookie="account_id=1;cookie_token=secret-token",
        region="cn",
        credential_source="keyring",
        storage_backend="test",
        device_payload={
            "deviceModel": "PHK110",
            "deviceProduct": "PHK110",
            "deviceName": "OP5913L1",
            "deviceBoard": "taro",
            "oaid": "oaid-secret",
            "deviceFingerprint": "OnePlus/PHK110/OP5913L1:13/build",
        },
    )

    assert requests[0].url.host == "public-data-api.mihoyo.com"
    assert requests[1].url.path == "/apihub/api/deviceLogin"
    assert requests[1].headers["x-rpc-device_fp"] == "generated-fp"
    assert result.data["device_fp"] == "generated-fp"
    assert result.data["generated_fp"] is True


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


def _account_card_response(*, game_role_id: str = "100000001") -> httpx.Response:
    return _json_response(
        {
            "retcode": 0,
            "message": "OK",
            "data": {
                "list": [
                    {
                        "game_id": 2,
                        "game_role_id": game_role_id,
                        "nickname": "Traveler",
                        "level": 60,
                        "region": "cn_gf01",
                        "region_name": "天空岛",
                    }
                ]
            },
        }
    )
