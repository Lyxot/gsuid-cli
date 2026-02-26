from __future__ import annotations

import hashlib
import json
import random
import string
import time
import uuid

from gsuid_cli.core.errors import EXIT_NO_RESULT, EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import HttpClient, raise_for_retcode
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.core.secrets import redact_secret

PROVIDER = "mys"
RECORD_BASE_CN = "https://api-takumi-record.mihoyo.com"
PASSPORT_BASE_CN = "https://passport-api.mihoyo.com"
HK4_SDK_BASE_CN = "https://hk4e-sdk.mihoyo.com"
INDEX_PATH = "/game_record/app/genshin/api/index"
CREATE_QRCODE_PATH = "/hk4e_cn/combo/panda/qrcode/fetch"
CHECK_QRCODE_PATH = "/hk4e_cn/combo/panda/qrcode/query"
GET_STOKEN_BY_GAME_TOKEN_PATH = "/account/ma-cn-session/app/getTokenByGameToken"
GET_COOKIE_TOKEN_BY_STOKEN_PATH = "/account/auth/api/getCookieAccountInfoBySToken"
APP_VERSION = "2.71.1"
PASSPORT_SALT = "JwYDpKvLj6MrMqqYU6jTKF17KNO2PXoS"

SERVER_BY_UID_PREFIX = {
    "1": "cn_gf01",
    "2": "cn_gf01",
    "5": "cn_qd01",
}


class MysProvider:
    def __init__(self, http_client: HttpClient) -> None:
        self.http = http_client

    def validate_cookie(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
    ) -> CommandResult:
        ensure_supported_region(region)
        server = server_for_uid(uid)
        response = self.http.request_json(
            "GET",
            f"{RECORD_BASE_CN}{INDEX_PATH}",
            provider=PROVIDER,
            region=region,
            category="auth.cookie.test",
            params={"server": server, "role_id": uid},
            headers=_headers(cookie),
        )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category="auth.cookie.test",
            source=response.source,
            debug=self.http.debug,
        )
        data = response.payload.get("data")
        if not isinstance(data, dict):
            data = {}

        role = {
            "nickname": data.get("nickname"),
            "level": data.get("level"),
            "region": data.get("region") or server,
        }
        return CommandResult(
            data={
                "uid": uid,
                "credential_type": "cookie",
                "source": credential_source,
                "storage_backend": storage_backend,
                "validity_status": "valid",
                "redacted": redact_secret(cookie),
                "provider_response": {
                    "retcode": response.payload.get("retcode"),
                    "message": response.payload.get("message"),
                    "role": role,
                },
            },
            source=response.source,
        )

    def create_qrcode_session(self, *, region: str) -> CommandResult:
        ensure_supported_region(region)
        device = _random_device_id()
        app_id = "2"
        response = self.http.request_json(
            "POST",
            f"{HK4_SDK_BASE_CN}{CREATE_QRCODE_PATH}",
            provider=PROVIDER,
            region=region,
            category="auth.qrcode.start",
            json_body={"app_id": app_id, "device": device},
        )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category="auth.qrcode.start",
            source=response.source,
            debug=self.http.debug,
        )
        data = _payload_data(response.payload, "auth.qrcode.start", response.source)
        url = str(data.get("url") or "")
        ticket = _ticket_from_url(url)
        if not url or not ticket:
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "Provider returned an invalid QR login session.",
                EXIT_UPSTREAM,
                {"provider": PROVIDER, "category": "auth.qrcode.start"},
                source=response.source,
            )
        return CommandResult(
            data={
                "app_id": app_id,
                "ticket": ticket,
                "device": device,
                "url": url,
                "status": "created",
            },
            source=response.source,
        )

    def poll_qrcode_session(
        self,
        *,
        app_id: str,
        ticket: str,
        device: str,
        region: str,
    ) -> CommandResult:
        status = self._qrcode_status(
            app_id=app_id,
            ticket=ticket,
            device=device,
            region=region,
            category="auth.qrcode.poll",
        )
        return CommandResult(
            data={
                "app_id": app_id,
                "ticket": ticket,
                "device": device,
                "status": status["status"],
                "account_id": status["account_id"],
                "confirmed": status["status"] == "confirmed",
            },
            source=status["source"],
        )

    def complete_qrcode_login(
        self,
        *,
        app_id: str,
        ticket: str,
        device: str,
        uid: str,
        region: str,
    ) -> CommandResult:
        status = self._qrcode_status(
            app_id=app_id,
            ticket=ticket,
            device=device,
            region=region,
            category="auth.qrcode.complete",
        )
        if status["status"] != "confirmed":
            raise CliError(
                "QR_NOT_CONFIRMED",
                "QR login has not been confirmed.",
                EXIT_NO_RESULT,
                {"status": status["status"], "ticket": "[REDACTED]"},
                source=status["source"],
            )

        game_token = status["game_token"]
        account_id = status["account_id"]
        if not isinstance(game_token, str) or not isinstance(account_id, str):
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "Provider confirmed QR login without a usable game token.",
                EXIT_UPSTREAM,
                {"provider": PROVIDER, "category": "auth.qrcode.complete"},
                source=status["source"],
            )

        stoken_data, stoken_source = self._stoken_by_game_token(
            account_id=account_id,
            game_token=game_token,
            region=region,
        )
        token_data = stoken_data.get("token")
        user_info = stoken_data.get("user_info")
        if not isinstance(token_data, dict) or not isinstance(user_info, dict):
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "Provider returned an invalid stoken response.",
                EXIT_UPSTREAM,
                {"provider": PROVIDER, "category": "auth.qrcode.complete"},
                source=stoken_source,
            )
        stoken = str(token_data.get("token") or "")
        stuid = str(user_info.get("aid") or account_id)
        mid = str(user_info.get("mid") or "")
        if not stoken or not mid:
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "Provider returned incomplete stoken credentials.",
                EXIT_UPSTREAM,
                {"provider": PROVIDER, "category": "auth.qrcode.complete"},
                source=stoken_source,
            )

        stoken_cookie = f"stuid={stuid};stoken={stoken};mid={mid}"
        cookie_data, cookie_source = self._cookie_token_by_stoken(
            stoken=stoken,
            account_id=stuid,
            full_cookie=stoken_cookie,
            region=region,
        )
        cookie_token = str(cookie_data.get("cookie_token") or "")
        if not cookie_token:
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "Provider returned an invalid cookie token response.",
                EXIT_UPSTREAM,
                {"provider": PROVIDER, "category": "auth.qrcode.complete"},
                source=cookie_source,
            )
        cookie = f"account_id={stuid};cookie_token={cookie_token}"

        return CommandResult(
            data={
                "uid": uid,
                "account_id": stuid,
                "status": "stored",
                "credential_types": ["cookie", "stoken"],
                "cookie": cookie,
                "stoken": stoken_cookie,
                "redacted": {
                    "cookie": redact_secret(cookie),
                    "stoken": redact_secret(stoken_cookie),
                },
            },
            source=cookie_source,
        )

    def _qrcode_status(
        self,
        *,
        app_id: str,
        ticket: str,
        device: str,
        region: str,
        category: str,
    ) -> dict[str, object]:
        ensure_supported_region(region)
        response = self.http.request_json(
            "POST",
            f"{HK4_SDK_BASE_CN}{CHECK_QRCODE_PATH}",
            provider=PROVIDER,
            region=region,
            category=category,
            json_body={"app_id": app_id, "ticket": ticket, "device": device},
        )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category=category,
            source=response.source,
            debug=self.http.debug,
        )
        data = _payload_data(response.payload, category, response.source)
        raw_status = str(data.get("stat") or "Init")
        status = {
            "Init": "init",
            "Scanned": "scanned",
            "Confirmed": "confirmed",
        }.get(raw_status, raw_status.lower())

        account_id = None
        game_token = None
        payload = data.get("payload")
        if isinstance(payload, dict) and payload.get("raw"):
            try:
                raw = json.loads(str(payload["raw"]))
            except json.JSONDecodeError as exc:
                raise CliError(
                    "UPSTREAM_INVALID_RESPONSE",
                    "Provider returned invalid QR login payload.",
                    EXIT_UPSTREAM,
                    {"provider": PROVIDER, "category": category},
                    source=response.source,
                ) from exc
            account_id = str(raw.get("uid") or "") or None
            game_token = str(raw.get("token") or "") or None

        return {
            "status": status,
            "account_id": account_id,
            "game_token": game_token,
            "source": response.source,
        }

    def _stoken_by_game_token(
        self,
        *,
        account_id: str,
        game_token: str,
        region: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        body = {"account_id": int(account_id), "game_token": game_token}
        response = self.http.request_json(
            "POST",
            f"{PASSPORT_BASE_CN}{GET_STOKEN_BY_GAME_TOKEN_PATH}",
            provider=PROVIDER,
            region=region,
            category="auth.qrcode.stoken",
            json_body=body,
            headers=_passport_headers(body),
        )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category="auth.qrcode.stoken",
            source=response.source,
            debug=self.http.debug,
        )
        return (
            _payload_data(response.payload, "auth.qrcode.stoken", response.source),
            response.source,
        )

    def _cookie_token_by_stoken(
        self,
        *,
        stoken: str,
        account_id: str,
        full_cookie: str,
        region: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        response = self.http.request_json(
            "GET",
            f"{PASSPORT_BASE_CN}{GET_COOKIE_TOKEN_BY_STOKEN_PATH}",
            provider=PROVIDER,
            region=region,
            category="auth.qrcode.cookie",
            params={"stoken": stoken, "uid": account_id},
            headers={**_headers(full_cookie), "Cookie": full_cookie},
        )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category="auth.qrcode.cookie",
            source=response.source,
            debug=self.http.debug,
        )
        return (
            _payload_data(response.payload, "auth.qrcode.cookie", response.source),
            response.source,
        )


def server_for_uid(uid: str) -> str:
    return SERVER_BY_UID_PREFIX.get(uid[0], "cn_gf01")


def _headers(cookie: str) -> dict[str, str]:
    return {
        "Cookie": cookie,
        "User-Agent": f"Mozilla/5.0 miHoYoBBS/{APP_VERSION}",
        "Referer": "https://webstatic.mihoyo.com/",
        "x-rpc-app_version": APP_VERSION,
        "x-rpc-client_type": "5",
        "x-rpc-language": "zh-cn",
    }


def _payload_data(
    payload: dict[str, object],
    category: str,
    source: dict[str, object],
) -> dict[str, object]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise CliError(
            "UPSTREAM_INVALID_RESPONSE",
            "Provider returned an unexpected response shape.",
            EXIT_UPSTREAM,
            {"provider": PROVIDER, "category": category},
            source=source,
        )
    return data


def _ticket_from_url(url: str) -> str:
    marker = "ticket="
    if marker not in url:
        return ""
    return url.split(marker, 1)[1].split("&", 1)[0]


def _random_device_id() -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=64))


def _passport_headers(body: dict[str, object]) -> dict[str, str]:
    # Ported from gsuid_core.utils.api.mys.account_request.get_stoken_by_game_token.
    return {
        "x-rpc-app_version": "2.41.0",
        "DS": _passport_ds(body=body),
        "x-rpc-aigis": "",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-rpc-game_biz": "bbs_cn",
        "x-rpc-sys_version": "11",
        "x-rpc-device_id": uuid.uuid4().hex,
        "x-rpc-device_fp": "".join(random.choices(string.ascii_letters + string.digits, k=13)),
        "x-rpc-device_name": "GenshinUid_login_device_lulu",
        "x-rpc-device_model": "GenshinUid_login_device_lulu",
        "x-rpc-app_id": "bll8iq97cem8",
        "x-rpc-client_type": "2",
        "User-Agent": "okhttp/4.8.0",
    }


def _passport_ds(
    *,
    query: str = "",
    body: dict[str, object] | None = None,
) -> str:
    timestamp = str(int(time.time()))
    random_text = "".join(random.sample(string.ascii_letters, 6))
    body_text = json.dumps(body) if body else ""
    digest = hashlib.md5(
        f"salt={PASSPORT_SALT}&t={timestamp}&r={random_text}&b={body_text}&q={query}".encode()
    ).hexdigest()
    return f"{timestamp},{random_text},{digest}"
