from __future__ import annotations

import hashlib
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
from gsuid_cli.providers.mys.auth import record_path_for_uid


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
    assert request.headers["x-rpc-client_type"] == "5"
    assert "Chrome/111.0.5563.116" in request.headers["user-agent"]
    assert request.headers["ds"].count(",") == 2


@pytest.mark.parametrize(
    ("cn_path", "os_path"),
    [
        (
            "/game_record/app/genshin/api/role_combat",
            "/game_record/genshin/api/role_combat",
        ),
        (
            "/game_record/app/genshin/api/hard_challenge",
            "/game_record/genshin/api/hard_challenge",
        ),
        (
            "/game_record/app/genshin/api/achievement",
            "/game_record/genshin/api/achievement",
        ),
        (
            "/game_record/app/genshin/api/gcg/deckList",
            "/game_record/genshin/api/gcg/deckList",
        ),
        (
            "/game_record/app/genshin/api/character/list",
            "/game_record/genshin/api/character/list",
        ),
        (
            "/game_record/app/genshin/api/character/detail",
            "/game_record/genshin/api/character/detail",
        ),
    ],
)
def test_hoyolab_record_paths_match_current_os_endpoints(cn_path: str, os_path: str) -> None:
    assert record_path_for_uid("800000001", cn_path) == os_path


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
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _json_response(
            {
                "retcode": 0,
                "message": "OK",
                "data": {
                    "ticket": "ticket-1",
                    "url": "https://example.test/login?ticket=ticket-1",
                },
            }
        )

    provider = MysProvider(
        HttpClient(
            timeout=1,
            cache_policy="off",
            transport=httpx.MockTransport(handler),
        )
    )

    result = provider.create_qrcode_session(region="cn")

    assert result.data["app_id"] == "2"
    assert result.data["ticket"] == "ticket-1"
    assert result.data["url"] == "https://example.test/login?ticket=ticket-1"
    assert len(str(result.data["device"])) == 64
    assert requests[0].url.path == "/account/ma-cn-passport/app/createQRLogin"
    assert requests[0].headers["x-rpc-app_id"] == "ddxf5dufpuyo"
    assert requests[0].headers["user-agent"] == "HYPContainer/1.3.3.182"


def test_qrcode_poll_confirmed_does_not_return_game_token() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _json_response(
            {
                "retcode": 0,
                "message": "OK",
                "data": {
                    "status": "Confirmed",
                    "tokens": [{"name": "stoken", "token": "stoken-secret"}],
                    "user_info": {"aid": "123456", "mid": "mid-secret"},
                },
            }
        )

    provider = MysProvider(
        HttpClient(
            timeout=1,
            cache_policy="off",
            transport=httpx.MockTransport(handler),
        )
    )

    result = provider.poll_qrcode_session(
        app_id="legacy-app-id",
        ticket="ticket-1",
        device="device-1",
        region="cn",
    )

    assert result.data["status"] == "confirmed"
    assert result.data["account_id"] == "123456"
    assert "stoken-secret" not in json.dumps(result.data)
    assert requests[0].url.path == "/account/ma-cn-passport/app/queryQRLoginStatus"
    assert json.loads(requests[0].content.decode()) == {"ticket": "ticket-1"}
    assert requests[0].headers["x-rpc-device_id"] == "device-1"


def test_qrcode_complete_exchanges_tokens() -> None:
    requests: list[httpx.Request] = []
    responses = [
        _json_response(
            {
                "retcode": 0,
                "message": "OK",
                "data": {
                    "status": "Confirmed",
                    "tokens": [{"name": "stoken", "token": "stoken-secret"}],
                    "user_info": {"aid": "123456", "mid": "mid-secret"},
                },
            }
        ),
        _json_response(
            {
                "retcode": 0,
                "message": "OK",
                "data": {"token": {"token": "cookie-secret"}},
            }
        ),
        _json_response({"retcode": -100, "message": "ltoken unavailable"}),
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

    result = provider.complete_qrcode_login(
        app_id="legacy-app-id",
        ticket="ticket-1",
        device="device-1",
        uid="100000001",
        region="cn",
    )

    assert result.data["uid"] == "100000001"
    assert result.data["account_id"] == "123456"
    assert result.data["cookie"] == "account_id=123456;cookie_token=cookie-secret"
    assert result.data["stoken"] == "stuid=123456;stoken=stoken-secret;mid=mid-secret"
    assert [request.url.path for request in requests] == [
        "/account/ma-cn-passport/app/queryQRLoginStatus",
        "/account/ma-cn-session/app/exchange",
        "/account/ma-cn-session/app/exchange",
    ]
    assert json.loads(requests[1].content)["mid"] == "mid-secret"
    assert json.loads(requests[2].content)["dst_token_type"] == 2


def test_cookie_refresh_exchanges_stoken_for_cookie() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        return _json_response(
            {
                "retcode": 0,
                "message": "OK",
                "data": {
                    "token": {
                        "token": "v2_fresh-cookie=.CAE="
                        if body["dst_token_type"] == 4
                        else "v2_fresh-ltoken=.CAE="
                    },
                    "user_info": {"aid": "123456", "mid": "resolved-mid"},
                },
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
    assert result.data["cookie"] == (
        "account_id=123456;cookie_token=v2_fresh-cookie=.CAE=;account_id_v2=123456;"
        "cookie_token_v2=v2_fresh-cookie=.CAE=;account_mid_v2=resolved-mid;ltuid=123456;"
        "ltoken=v2_fresh-ltoken=.CAE=;ltuid_v2=123456;ltoken_v2=v2_fresh-ltoken=.CAE=;"
        "ltmid_v2=resolved-mid"
    )
    assert result.data["redacted"] != result.data["cookie"]
    assert len(requests) == 2
    assert json.loads(requests[0].content) == {
        "src_token": {"token": "stoken-secret", "token_type": 1},
        "mid": "mid-secret",
        "dst_token_type": 4,
    }
    assert json.loads(requests[1].content)["mid"] == "resolved-mid"
    assert json.loads(requests[1].content)["dst_token_type"] == 2
    for request in requests:
        assert request.method == "POST"
        assert request.url.path == "/account/ma-cn-session/app/exchange"
        assert not request.url.query
        assert request.headers["x-rpc-app_id"] == "bll8iq97cem8"
        assert request.headers["x-rpc-client_type"] == "2"
        assert request.headers["user-agent"] == "okhttp/4.9.3"
        assert request.headers["ds"].count(",") == 2
    assert requests[0].headers["x-rpc-device_id"] == requests[1].headers["x-rpc-device_id"]
    assert requests[0].headers["x-rpc-device_fp"] == requests[1].headers["x-rpc-device_fp"]


@pytest.mark.parametrize("mid_key", ["stmid_v2", "stmid", "account_mid_v2", "ltmid_v2"])
def test_cookie_refresh_accepts_v2_identity_aliases(mid_key) -> None:
    requests = []

    def handler(request):
        requests.append(request)
        return _json_response({"retcode": 0, "data": {"token": {"token": "v2_fresh"}}})

    provider = MysProvider(
        HttpClient(timeout=1, cache_policy="off", transport=httpx.MockTransport(handler))
    )
    result = provider.refresh_cookie_from_stoken(
        uid="100000001",
        stoken_cookie=f"account_id_v2=123;stoken_v2=v2_secret;{mid_key}=mid",
        region="cn",
        credential_source="keyring",
        storage_backend="test",
    )
    assert "account_id_v2=123" in result.data["cookie"]
    assert json.loads(requests[0].content)["mid"] == "mid"


def test_cookie_refresh_legacy_without_mid_uses_get() -> None:
    requests = []

    def handler(request):
        requests.append(request)
        return _json_response({"retcode": 0, "data": {"cookie_token": "legacy-cookie"}})

    provider = MysProvider(
        HttpClient(timeout=1, cache_policy="off", transport=httpx.MockTransport(handler))
    )
    result = provider.refresh_cookie_from_stoken(
        uid="100000001",
        stoken_cookie="stuid=123;stoken=legacy",
        region="cn",
        credential_source="keyring",
        storage_backend="test",
    )
    assert result.data["cookie"] == "account_id=123;cookie_token=legacy-cookie"
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/account/auth/api/getCookieAccountInfoBySToken"
    assert dict(requests[0].url.params) == {"stoken": "legacy", "uid": "123"}


def test_cookie_refresh_keeps_cookie_when_optional_ltoken_times_out() -> None:
    def handler(request):
        if json.loads(request.content)["dst_token_type"] == 2:
            raise httpx.ReadTimeout("ltoken unavailable", request=request)
        return _json_response({"retcode": 0, "data": {"token": {"token": "v2_fresh"}}})

    provider = MysProvider(
        HttpClient(timeout=1, cache_policy="off", transport=httpx.MockTransport(handler))
    )
    result = provider.refresh_cookie_from_stoken(
        uid="100000001",
        stoken_cookie="stuid=123;stoken=v2_secret;mid=mid",
        region="cn",
        credential_source="keyring",
        storage_backend="test",
    )
    assert result.data["validity_status"] == "refreshed"
    assert result.data["cookie"] == (
        "account_id=123;cookie_token=v2_fresh;account_id_v2=123;"
        "cookie_token_v2=v2_fresh;account_mid_v2=mid"
    )


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"retcode": -100}, "AUTH_EXPIRED"),
        ({"retcode": 0, "data": {"token": {}}}, "UPSTREAM_INVALID_RESPONSE"),
        (
            {"retcode": 0, "data": {"token": {"token": {"bad": "value"}}}},
            "UPSTREAM_INVALID_RESPONSE",
        ),
    ],
)
def test_cookie_exchange_rejects_invalid_credentials(payload, code) -> None:
    provider = MysProvider(_client(_json_response(payload)))
    with pytest.raises(CliError) as exc:
        provider.refresh_cookie_from_stoken(
            uid="100000001",
            stoken_cookie="stuid=123;stoken=v2_secret;mid=mid",
            region="cn",
            credential_source="keyring",
            storage_backend="test",
        )
    assert exc.value.code == code


def test_qrcode_complete_requires_confirmed_status() -> None:
    provider = MysProvider(
        _client(
            _json_response(
                {
                    "retcode": 0,
                    "message": "OK",
                    "data": {"status": "Scanned"},
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


@pytest.mark.parametrize(
    "android,sdk",
    [
        ("16", "36"),
        ("15", "35"),
        ("14", "34"),
        ("13", "33"),
        ("12L", "32"),
        ("12", "31"),
        ("11", "30"),
        ("10", "29"),
        ("99", "34"),
    ],
)
def test_device_set_matches_android_version_and_signature(android, sdk) -> None:
    requests = []

    def handler(request):
        requests.append(request)
        data = {"device_fp": "generated-fp"} if len(requests) == 1 else {}
        return _json_response({"retcode": 0, "data": data})

    provider = MysProvider(
        HttpClient(timeout=1, cache_policy="off", transport=httpx.MockTransport(handler))
    )
    provider.device_login(
        uid="100000001",
        cookie="stuid=123;stoken=v2_secret;mid=mid",
        region="cn",
        credential_source="keyring",
        storage_backend="test",
        device_payload={
            "device_id": "preserved-id",
            "deviceModel": "TestModel",
            "deviceProduct": "product",
            "deviceName": "device",
            "deviceBoard": "board",
            "oaid": "oaid",
            "deviceFingerprint": f"TestBrand/TestModel/TestDev:{android}/build",
        },
    )
    fp_body = json.loads(requests[0].content)
    ext = json.loads(fp_body["ext_fields"])
    assert fp_body["bbs_device_id"] == "preserved-id"
    assert ext["osVersion"] == android
    assert ext["sdkVersion"] == sdk
    assert ext["display"] == f"TestModel_{android}.0.0.810(CN01)"
    assert len(requests) == 3
    for request in requests[1:]:
        assert json.loads(request.content)["os_version"] == sdk
        assert request.headers["cookie"] == "stuid=123;stoken=v2_secret;mid=mid"
        assert request.headers["x-rpc-device_id"] == "preserved-id"
        assert request.headers["x-rpc-device_fp"] == "generated-fp"
        assert request.headers["x-rpc-client_type"] == "2"
        assert request.headers["x-rpc-sys_version"] == android
        assert request.headers["user-agent"] == "okhttp/4.9.3"
        timestamp, nonce, digest = request.headers["ds"].split(",")
        assert (
            digest
            == hashlib.md5(
                f"salt=lX8m5VO5at5JG7hR8hzqFwzyL5aB1tYo&t={timestamp}&r={nonce}".encode()
            ).hexdigest()
        )


def test_device_set_accepts_aliases_and_uses_default_device() -> None:
    requests = []

    def handler(request):
        requests.append(request)
        return _json_response({"retcode": 0, "data": {}})

    provider = MysProvider(
        HttpClient(timeout=1, cache_policy="off", transport=httpx.MockTransport(handler))
    )
    result = provider.device_login(
        uid="100000001",
        cookie="stuid=1;stoken=secret",
        region="cn",
        credential_source="keyring",
        storage_backend="test",
        device_payload={"fp": " ", "device_fp": "alias-fp", "device_id": " ", "deviceId": "id"},
    )
    assert result.data["device_fp"] == "alias-fp"
    assert result.data["generated_fp"] is False
    assert requests[0].headers["x-rpc-device_name"] == "OnePlus PHK110"
    assert json.loads(requests[0].content)["os_version"] == "34"


def test_device_set_stops_before_save_on_login_failure() -> None:
    requests = []

    def handler(request):
        requests.append(request)
        return _json_response({"retcode": -100})

    provider = MysProvider(
        HttpClient(timeout=1, cache_policy="off", transport=httpx.MockTransport(handler))
    )
    with pytest.raises(CliError) as exc:
        provider.device_login(
            uid="100000001",
            cookie="stuid=1;stoken=secret",
            region="cn",
            credential_source="keyring",
            storage_backend="test",
            device_payload={"fp": "fp", "device_id": "id"},
        )
    assert exc.value.code == "AUTH_EXPIRED"
    assert len(requests) == 1


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
