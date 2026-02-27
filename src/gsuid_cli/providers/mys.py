from __future__ import annotations

import hashlib
import json
import random
import string
import time
import uuid
from http.cookies import CookieError, SimpleCookie

from gsuid_cli.core.errors import EXIT_AUTH, EXIT_NO_RESULT, EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import HttpClient, raise_for_retcode
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.core.secrets import redact_secret

PROVIDER = "mys"
RECORD_BASE_CN = "https://api-takumi-record.mihoyo.com"
PASSPORT_BASE_CN = "https://passport-api.mihoyo.com"
HK4_SDK_BASE_CN = "https://hk4e-sdk.mihoyo.com"
INDEX_PATH = "/game_record/app/genshin/api/index"
CARD_PATH = "/game_record/card/wapi/getGameRecordCard"
CREATE_QRCODE_PATH = "/hk4e_cn/combo/panda/qrcode/fetch"
CHECK_QRCODE_PATH = "/hk4e_cn/combo/panda/qrcode/query"
GET_STOKEN_BY_GAME_TOKEN_PATH = "/account/ma-cn-session/app/getTokenByGameToken"
GET_COOKIE_TOKEN_BY_STOKEN_PATH = "/account/auth/api/getCookieAccountInfoBySToken"
APP_VERSION = "2.102.1"
RECORD_SALT = "xV8v4Qu54lUKrEYFZkJhB8cuOh9Asafs"
PASSPORT_SALT = "JwYDpKvLj6MrMqqYU6jTKF17KNO2PXoS"
USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13; PHK110 Build/SKQ1.221119.001; wv)"
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/"
    f"126.0.6478.133 Mobile Safari/537.36 miHoYoBBS/{APP_VERSION}"
)

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
        account_id = _account_id_from_cookie(cookie)
        if account_id:
            return self._validate_account_cookie(
                uid=uid,
                account_id=account_id,
                cookie=_account_cookie(cookie, account_id),
                region=region,
                credential_source=credential_source,
                storage_backend=storage_backend,
                redacted_cookie=redact_secret(cookie),
            )

        return self._validate_role_cookie(
            uid=uid,
            cookie=cookie,
            region=region,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )

    def _validate_role_cookie(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
    ) -> CommandResult:
        server = server_for_uid(uid)
        params = {"role_id": uid, "server": server}
        response = self.http.request_json(
            "GET",
            f"{RECORD_BASE_CN}{INDEX_PATH}",
            provider=PROVIDER,
            region=region,
            category="auth.cookie.test",
            params=params,
            headers=_record_headers(cookie, _query_string(params)),
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

    def _validate_account_cookie(
        self,
        *,
        uid: str,
        account_id: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
        redacted_cookie: str,
    ) -> CommandResult:
        params = {"uid": account_id}
        response = self.http.request_json(
            "GET",
            f"{RECORD_BASE_CN}{CARD_PATH}",
            provider=PROVIDER,
            region=region,
            category="auth.cookie.test",
            params=params,
            headers=_record_headers(cookie, _query_string(params)),
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
        roles_value = data.get("list") if isinstance(data, dict) else []
        if not isinstance(roles_value, list):
            roles_value = []
        roles = [role for role in roles_value if isinstance(role, dict)]
        linked_roles = [_linked_role(role) for role in roles]
        role = next(
            (
                linked_role
                for linked_role in linked_roles
                if linked_role["game_id"] == "2" and linked_role["game_role_id"] == uid
            ),
            None,
        )
        if role is None:
            raise CliError(
                "AUTH_UID_MISMATCH",
                "The cookie is valid but is not linked to this UID.",
                EXIT_AUTH,
                {
                    "uid": uid,
                    "account_id": account_id,
                    "linked_game_uids": [
                        linked_role["game_role_id"]
                        for linked_role in linked_roles
                        if linked_role["game_role_id"]
                    ],
                },
                source=response.source,
            )

        return CommandResult(
            data={
                "uid": uid,
                "credential_type": "cookie",
                "source": credential_source,
                "storage_backend": storage_backend,
                "validity_status": "valid",
                "redacted": redacted_cookie,
                "provider_response": {
                    "retcode": response.payload.get("retcode"),
                    "message": response.payload.get("message"),
                    "account_id": account_id,
                    "role": role,
                    "linked_roles": linked_roles,
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


def _account_id_from_cookie(cookie: str) -> str | None:
    parsed = SimpleCookie()
    try:
        parsed.load(cookie)
    except CookieError:
        return None

    for key in ("account_id", "ltuid", "ltuid_v2", "stuid", "login_uid"):
        morsel = parsed.get(key)
        if morsel and morsel.value:
            return morsel.value
    return None


def _account_cookie(cookie: str, account_id: str) -> str:
    if "account_id=" in cookie:
        return cookie
    return f"{cookie};account_id={account_id}"


def _linked_role(role: dict[str, object]) -> dict[str, object]:
    return {
        "game_id": str(role.get("game_id") or ""),
        "game_role_id": str(role.get("game_role_id") or ""),
        "nickname": role.get("nickname"),
        "level": role.get("level"),
        "region": role.get("region"),
        "region_name": role.get("region_name"),
    }


def _headers(cookie: str) -> dict[str, str]:
    return {
        "Cookie": cookie,
        "User-Agent": USER_AGENT,
        "Referer": "https://webstatic.mihoyo.com/",
        "Origin": "https://webstatic.mihoyo.com/",
        "X-Requested-With": "com.mihoyo.hyperion",
        "x-rpc-app_version": APP_VERSION,
        "x-rpc-client_type": "5",
        "x-rpc-language": "zh-cn",
    }


def _record_headers(cookie: str, query: str) -> dict[str, str]:
    return {
        **_headers(cookie),
        "DS": _record_ds(query),
    }


def _record_ds(query: str) -> str:
    # Ported from gsuid_core.utils.api.mys.tools.get_ds_token.
    timestamp = str(int(time.time()))
    random_number = str(random.randint(100000, 200000))
    digest = hashlib.md5(
        f"salt={RECORD_SALT}&t={timestamp}&r={random_number}&b=&q={query}".encode()
    ).hexdigest()
    return f"{timestamp},{random_number},{digest}"


def _query_string(params: dict[str, object]) -> str:
    return "&".join(f"{key}={value}" for key, value in params.items())


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
