from __future__ import annotations

import json
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
from gsuid_cli.providers.mys.auth import _headers, _passport_headers, _ticket_from_url
from gsuid_cli.providers.mys.constants import (
    CHECK_QRCODE_PATH,
    CREATE_QRCODE_PATH,
    GET_COOKIE_TOKEN_BY_STOKEN_PATH,
    GET_STOKEN_BY_GAME_TOKEN_PATH,
    HK4_SDK_BASE_CN,
    PASSPORT_BASE_CN,
    PROVIDER,
)
from gsuid_cli.providers.mys.device import _random_device_id
from gsuid_cli.providers.mys.normalizers import _payload_data
from gsuid_cli.text import t as _t

_ACCOUNT_ID_KEYS = (
    "login_uid",
    "login_uid_v2",
    "account_id",
    "stuid",
    "stuid_v2",
    "ltuid",
    "ltuid_v2",
)
_STOKEN_KEYS = ("stoken", "stoken_v2")


class MysQrcodeMixin:
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
        cookie = f"account_id={account_id};cookie_token={cookie_token}"
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
        category: str = "auth.qrcode.cookie",
    ) -> tuple[dict[str, object], dict[str, object]]:
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
    mid = _first_cookie_value(parsed, ("mid",))
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


def _invalid_stoken_cookie() -> CliError:
    return CliError(
        "INVALID_ARGUMENT",
        _t("gsuid.providers.mys.qrcode.invalid_stoken_cookie"),
        EXIT_INVALID_INPUT,
        {"credential_type": "stoken"},
    )
