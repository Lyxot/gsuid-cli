from __future__ import annotations

import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from gsuid_cli.core.errors import EXIT_INVALID_INPUT, EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import raise_for_retcode
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.providers.mys.auth import _account_id_from_cookie, _authkey_headers, server_for_uid
from gsuid_cli.providers.mys.constants import (
    GACHA_LOG_URL,
    GET_AUTHKEY_PATH,
    GS_BASE_CN,
    PROVIDER,
)
from gsuid_cli.providers.mys.normalizers import _payload_data


class MysGachaMixin:
    def gacha_log_page(
        self,
        *,
        uid: str,
        authkey_url: str,
        region: str,
        gacha_type: str,
        page: int,
        end_id: str,
    ) -> CommandResult:
        ensure_supported_region(region)
        base_url, params = _gacha_request(authkey_url)
        server = server_for_uid(uid)
        params.update(
            {
                "init_type": gacha_type,
                "gacha_type": gacha_type,
                "page": page,
                "size": "20",
                "end_id": end_id,
                "timestamp": str(int(time.time())),
                "lang": params.get("lang") or "zh-cn",
                "region": params.get("region") or server,
                "game_biz": params.get("game_biz") or "hk4e_cn",
                "auth_appid": params.get("auth_appid") or "webview_gacha",
                "authkey_ver": params.get("authkey_ver") or "1",
                "sign_type": params.get("sign_type") or "2",
            }
        )
        response = self.http.request_json(
            "GET",
            base_url,
            provider=PROVIDER,
            region=region,
            category="gacha.refresh",
            params=params,
        )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category="gacha.refresh",
            source=response.source,
            debug=self.http.debug,
        )
        data = _payload_data(response.payload, "gacha.refresh", response.source)
        return CommandResult(data=data, source=response.source)

    def generate_gacha_authkey_url(
        self,
        *,
        uid: str,
        cookie: str,
        stoken: str,
        region: str,
    ) -> CommandResult:
        ensure_supported_region(region)
        server = server_for_uid(uid)
        body = {
            "auth_appid": "webview_gacha",
            "game_biz": "hk4e_cn",
            "game_uid": uid,
            "region": server,
        }
        response = self.http.request_json(
            "POST",
            f"{GS_BASE_CN}{GET_AUTHKEY_PATH}",
            provider=PROVIDER,
            region=region,
            category="gacha.authkey.refresh",
            json_body=body,
            headers=_authkey_headers(stoken),
        )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category="gacha.authkey.refresh",
            source=response.source,
            debug=self.http.debug,
        )
        data = _payload_data(response.payload, "gacha.authkey.refresh", response.source)
        authkey = str(data.get("authkey") or "")
        if not authkey:
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "Provider returned an empty gacha authkey.",
                EXIT_UPSTREAM,
                {"provider": PROVIDER, "category": "gacha.authkey.refresh"},
                source=response.source,
            )
        return CommandResult(
            data={
                "uid": uid,
                "server": server,
                "game_biz": "hk4e_cn",
                "auth_appid": "webview_gacha",
                "account_id": _account_id_from_cookie(cookie) or _account_id_from_cookie(stoken),
                "gacha_url": _gacha_authkey_url(authkey, server),
                "redacted": "[REDACTED_URL]",
            },
            source=response.source,
        )


def _gacha_request(authkey_url: str) -> tuple[str, dict[str, object]]:
    parsed = urlsplit(authkey_url)
    if not parsed.scheme or not parsed.netloc:
        raise CliError(
            "INVALID_ARGUMENT",
            "gacha authkey URL is invalid",
            EXIT_INVALID_INPUT,
            {"credential_type": "gacha_url"},
        )
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if not params.get("authkey"):
        raise CliError(
            "INVALID_ARGUMENT",
            "gacha authkey URL is missing authkey",
            EXIT_INVALID_INPUT,
            {"credential_type": "gacha_url"},
        )
    api = urlsplit(GACHA_LOG_URL)
    base_url = urlunsplit((api.scheme, api.netloc, api.path, "", ""))
    return base_url, params


def _gacha_authkey_url(authkey: str, server: str) -> str:
    params = {
        "authkey_ver": "1",
        "sign_type": "2",
        "auth_appid": "webview_gacha",
        "init_type": "301",
        "gacha_id": "fecafa7b6560db5f3182222395d88aaa6aaac1bc",
        "timestamp": str(int(time.time())),
        "lang": "zh-cn",
        "device_type": "mobile",
        "plat_type": "ios",
        "region": server,
        "authkey": authkey,
        "game_biz": "hk4e_cn",
        "gacha_type": "301",
        "page": "1",
        "size": "5",
        "end_id": "0",
    }
    return f"{GACHA_LOG_URL}?{urlencode(params)}"
