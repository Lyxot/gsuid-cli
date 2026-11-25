from __future__ import annotations

import uuid
from http.cookies import CookieError, SimpleCookie

from gsuid_cli.core.errors import (
    EXIT_AUTH,
    EXIT_INVALID_INPUT,
    EXIT_NO_RESULT,
    EXIT_UPSTREAM,
    CliError,
)
from gsuid_cli.core.http import raise_for_retcode
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.core.secrets import redact_secret
from gsuid_cli.providers.mys.auth import _generate_seed, _headers, _passport_ds, _ticket_from_url
from gsuid_cli.providers.mys.constants import (
    APP_VERSION,
    CHECK_QRCODE_HYP_PATH,
    CREATE_QRCODE_HYP_PATH,
    EXCHANGE_TOKEN_PATH,
    GET_COOKIE_TOKEN_BY_STOKEN_PATH,
    PASSPORT_BASE_CN,
    PROVIDER,
)
from gsuid_cli.providers.mys.normalizers import _payload_data
from gsuid_cli.text import t as _t

_ACCOUNT_ID_KEYS = (
    "login_uid",
    "login_uid_v2",
    "account_id",
    "account_id_v2",
    "stuid",
    "stuid_v2",
    "ltuid",
    "ltuid_v2",
)
_STOKEN_KEYS = ("stoken", "stoken_v2")
_MID_KEYS = ("mid", "stmid_v2", "stmid", "account_mid_v2", "ltmid_v2")
_HYP_QRCODE_APP_ID = "2"
_HYP_QRCODE_RPC_APP_ID = "ddxf5dufpuyo"
_HYP_QRCODE_VERSION = "1.3.3.182"


class MysQrcodeMixin:
    def create_qrcode_session(self, *, region: str) -> CommandResult:
        ensure_supported_region(region)
        device = _random_hyp_device_id()
        response = self.http.request_json(
            "POST",
            f"{PASSPORT_BASE_CN}{CREATE_QRCODE_HYP_PATH}",
            provider=PROVIDER,
            region=region,
            category="auth.qrcode.start",
            json_body={},
            headers=_hyp_qrcode_headers(device),
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
        ticket = str(data.get("ticket") or _ticket_from_url(url))
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
                "app_id": _HYP_QRCODE_APP_ID,
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

        user_info = status["user_info"]
        tokens = status["tokens"]
        if not isinstance(user_info, dict) or not isinstance(tokens, list):
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "Provider confirmed QR login without usable credentials.",
                EXIT_UPSTREAM,
                {"provider": PROVIDER, "category": "auth.qrcode.complete"},
                source=status["source"],
            )
        stoken = _token_value(tokens)
        stuid = _account_id_from_user_info(user_info)
        mid = str(user_info.get("mid") or "")
        if not stoken or not stuid or not mid:
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "Provider returned incomplete stoken credentials.",
                EXIT_UPSTREAM,
                {"provider": PROVIDER, "category": "auth.qrcode.complete"},
                source=status["source"],
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
        cookie = _account_token_cookie(cookie_data, stuid)

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

    def refresh_cookie_from_stoken(
        self,
        *,
        uid: str,
        stoken_cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
    ) -> CommandResult:
        ensure_supported_region(region)
        account_id, stoken, full_cookie = _stoken_cookie_parts(stoken_cookie)
        try:
            cookie_data, cookie_source = self._cookie_token_by_stoken(
                stoken=stoken,
                account_id=account_id,
                full_cookie=full_cookie,
                region=region,
                category="auth.cookie.refresh",
            )
        except CliError as exc:
            if exc.code != "AUTH_EXPIRED":
                raise
            raise CliError(
                "AUTH_EXPIRED",
                _t("gsuid.providers.mys.qrcode.stoken_expired"),
                EXIT_AUTH,
                {
                    **exc.details,
                    "uid": uid,
                    "account_id": account_id,
                    "credential_type": "stoken",
                },
                source=exc.source,
            ) from exc
        cookie_token = str(cookie_data.get("cookie_token") or "")
        if not cookie_token:
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                _t("gsuid.providers.mys.qrcode.cookie_refresh_invalid"),
                EXIT_UPSTREAM,
                {"provider": PROVIDER, "category": "auth.cookie.refresh"},
                source=cookie_source,
            )
        cookie = _account_token_cookie(cookie_data, account_id)
        return CommandResult(
            data={
                "uid": uid,
                "account_id": account_id,
                "credential_type": "cookie",
                "validity_status": "refreshed",
                "source": credential_source,
                "storage_backend": storage_backend,
                "cookie": cookie,
                "redacted": redact_secret(cookie),
                "refreshed_from": "stoken",
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
            f"{PASSPORT_BASE_CN}{CHECK_QRCODE_HYP_PATH}",
            provider=PROVIDER,
            region=region,
            category=category,
            json_body={"ticket": ticket},
            headers=_hyp_qrcode_headers(device),
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
        raw_status = str(data.get("status") or data.get("stat") or "Created")
        status = {
            "Created": "created",
            "Scanned": "scanned",
            "Confirmed": "confirmed",
        }.get(raw_status, raw_status.lower())
        user_info = data.get("user_info")
        if not isinstance(user_info, dict):
            user_info = {}
        tokens = data.get("tokens")
        if not isinstance(tokens, list):
            tokens = []

        return {
            "status": status,
            "account_id": _account_id_from_user_info(user_info) or None,
            "tokens": tokens,
            "user_info": user_info,
            "source": response.source,
        }

    def _cookie_token_by_stoken(
        self,
        *,
        stoken: str,
        account_id: str,
        full_cookie: str,
        region: str,
        category: str = "auth.qrcode.cookie",
    ) -> tuple[dict[str, object], dict[str, object]]:
        mid = _cookie_value(full_cookie, "mid")
        if mid:
            return self._exchange_account_tokens(
                stoken=stoken, account_id=account_id, mid=mid, region=region, category=category
            )
        response = self.http.request_json(
            "GET",
            f"{PASSPORT_BASE_CN}{GET_COOKIE_TOKEN_BY_STOKEN_PATH}",
            provider=PROVIDER,
            region=region,
            category=category,
            params={"stoken": stoken, "uid": account_id},
            headers={**_headers(full_cookie), "Cookie": full_cookie},
        )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category=category,
            source=response.source,
            debug=self.http.debug,
        )
        return (
            _payload_data(response.payload, category, response.source),
            response.source,
        )

    def _exchange_account_tokens(
        self, *, stoken: str, account_id: str, mid: str, region: str, category: str
    ) -> tuple[dict[str, object], dict[str, object]]:
        device_id = _generate_seed(16)
        device_fp = _generate_seed(13)

        def exchange(token_type: int, token_mid: str):
            body = {
                "src_token": {"token": stoken, "token_type": 1},
                "mid": token_mid,
                "dst_token_type": token_type,
            }
            return self.http.request_json(
                "POST",
                f"{PASSPORT_BASE_CN}{EXCHANGE_TOKEN_PATH}",
                provider=PROVIDER,
                region=region,
                category=category,
                json_body=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "x-rpc-app_id": "bll8iq97cem8",
                    "x-rpc-client_type": "2",
                    "x-rpc-device_id": device_id,
                    "x-rpc-device_fp": device_fp,
                    "x-rpc-device_name": "OnePlus%20PHK110",
                    "x-rpc-device_model": "PHK110",
                    "x-rpc-sys_version": "16",
                    "x-rpc-game_biz": "bbs_cn",
                    "x-rpc-app_version": APP_VERSION,
                    "x-rpc-sdk_version": "2.44.0",
                    "x-rpc-lifecycle_id": str(uuid.uuid4()),
                    "x-rpc-account_version": "2.44.0",
                    "DS": _passport_ds(body=body),
                    "User-Agent": "okhttp/4.9.3",
                },
            )

        response = exchange(4, mid)
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category=category,
            source=response.source,
            debug=self.http.debug,
        )
        data = _payload_data(response.payload, category, response.source)
        token = data.get("token")
        cookie_token = token.get("token") if isinstance(token, dict) else None
        cookie_token = cookie_token if isinstance(cookie_token, str) else ""
        if not cookie_token:
            return {}, response.source
        user = data.get("user_info")
        if isinstance(user, dict):
            account_id = str(user.get("aid") or account_id)
            mid = str(user.get("mid") or mid)
        cookies = {"account_id": account_id, "cookie_token": cookie_token}
        if cookie_token.startswith("v2_"):
            cookies.update(
                account_id_v2=account_id, cookie_token_v2=cookie_token, account_mid_v2=mid
            )

        try:
            lt_payload = exchange(2, mid).payload
        except CliError:
            lt_payload = {}
        lt_data = lt_payload.get("data")
        lt_token = lt_data.get("token") if isinstance(lt_data, dict) else None
        ltoken = lt_token.get("token") if isinstance(lt_token, dict) else None
        if lt_payload.get("retcode") not in (0, "0") or not isinstance(ltoken, str):
            ltoken = ""
        if ltoken:
            cookies.update(ltuid=account_id, ltoken=ltoken)
            if ltoken.startswith("v2_"):
                cookies.update(ltuid_v2=account_id, ltoken_v2=ltoken, ltmid_v2=mid)
        return {"cookie_token": cookie_token, "cookies": cookies}, response.source


def _random_hyp_device_id() -> str:
    return f"{uuid.uuid4().hex}{uuid.uuid4().hex}"


def _hyp_qrcode_headers(device_id: str) -> dict[str, str]:
    return {
        "x-rpc-device_id": device_id,
        "User-Agent": f"HYPContainer/{_HYP_QRCODE_VERSION}",
        "x-rpc-app_id": _HYP_QRCODE_RPC_APP_ID,
        "x-rpc-client_type": "3",
    }


def _account_id_from_user_info(user_info: dict[str, object]) -> str:
    for key in ("aid", "uid", "account_id"):
        value = str(user_info.get(key) or "")
        if value:
            return value
    return ""


def _token_value(tokens: list[object]) -> str:
    fallback = ""
    for token in tokens:
        if not isinstance(token, dict):
            continue
        value = str(token.get("token") or "")
        if not value:
            continue
        if not fallback:
            fallback = value
        if token.get("name") in _STOKEN_KEYS:
            return value
    return fallback


def _cookie_value(cookie: str, key: str) -> str:
    parsed = SimpleCookie()
    try:
        parsed.load(cookie)
    except CookieError:
        return ""
    morsel = parsed.get(key)
    return morsel.value if morsel and morsel.value else ""


def _stoken_cookie_parts(stoken_cookie: str) -> tuple[str, str, str]:
    parsed = SimpleCookie()
    try:
        parsed.load(stoken_cookie)
    except CookieError as exc:
        raise _invalid_stoken_cookie() from exc
    account_id = _first_cookie_value(parsed, _ACCOUNT_ID_KEYS)
    stoken = _first_cookie_value(parsed, _STOKEN_KEYS)
    if not account_id or not stoken:
        raise _invalid_stoken_cookie()
    mid = _first_cookie_value(parsed, _MID_KEYS)
    if stoken.startswith("v2_") and not mid:
        raise CliError(
            "INVALID_ARGUMENT",
            _t("gsuid.providers.mys.qrcode.stoken_v2_requires_mid"),
            EXIT_INVALID_INPUT,
            {"credential_type": "stoken"},
        )
    full_cookie = f"stuid={account_id};stoken={stoken}"
    if mid:
        full_cookie = f"{full_cookie};mid={mid}"
    return account_id, stoken, full_cookie


def _first_cookie_value(parsed: SimpleCookie, keys: tuple[str, ...]) -> str:
    for key in keys:
        morsel = parsed.get(key)
        if morsel and morsel.value:
            return morsel.value
    return ""


def _account_token_cookie(data: dict[str, object], account_id: str) -> str:
    cookies = data.get("cookies")
    if isinstance(cookies, dict):
        return ";".join(f"{key}={value}" for key, value in cookies.items() if value)
    return f"account_id={account_id};cookie_token={data['cookie_token']}"


def _invalid_stoken_cookie() -> CliError:
    return CliError(
        "INVALID_ARGUMENT",
        _t("gsuid.providers.mys.qrcode.invalid_stoken_cookie"),
        EXIT_INVALID_INPUT,
        {"credential_type": "stoken"},
    )
