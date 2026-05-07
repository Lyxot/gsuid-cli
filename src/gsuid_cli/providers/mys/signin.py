from __future__ import annotations

from gsuid_cli.core.http import raise_for_retcode
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.providers.mys.auth import _already_signed, _headers, _sign_headers, server_for_uid
from gsuid_cli.providers.mys.constants import (
    GS_BASE_CN,
    PROVIDER,
    SIGN_ACT_ID,
    SIGN_INFO_PATH,
    SIGN_PATH,
)
from gsuid_cli.providers.mys.normalizers import _payload_data


class MysSigninMixin:
    def daily_signin(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
    ) -> CommandResult:
        sign_info, source, info_message = self._sign_info(uid=uid, cookie=cookie, region=region)
        if sign_info.get("is_sign") is True:
            return CommandResult(
                data={
                    **_signin_data(
                        uid=uid,
                        credential_source=credential_source,
                        storage_backend=storage_backend,
                        already_signed=True,
                        signed=False,
                        sign_info=sign_info,
                        provider_message=info_message,
                    ),
                },
                source=source,
            )

        server = server_for_uid(uid)
        body = {
            "act_id": SIGN_ACT_ID,
            "lang": "zh-cn",
            "uid": uid,
            "region": server,
        }
        response = self.http.request_json(
            "POST",
            f"{GS_BASE_CN}{SIGN_PATH}",
            provider=PROVIDER,
            region=region,
            category="daily.signin",
            headers=_sign_headers(cookie),
            json_body=body,
        )
        if _already_signed(response.payload):
            return CommandResult(
                data={
                    **_signin_data(
                        uid=uid,
                        credential_source=credential_source,
                        storage_backend=storage_backend,
                        already_signed=True,
                        signed=False,
                        sign_info=sign_info,
                        provider_message=str(response.payload.get("message") or "Already signed"),
                    ),
                    "provider_response": {
                        "retcode": response.payload.get("retcode"),
                        "message": response.payload.get("message"),
                    },
                },
                source=response.source,
            )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category="daily.signin",
            source=response.source,
            debug=self.http.debug,
        )
        data = response.payload.get("data")
        if not isinstance(data, dict):
            data = {}
        return CommandResult(
            data={
                **_signin_data(
                    uid=uid,
                    credential_source=credential_source,
                    storage_backend=storage_backend,
                    already_signed=False,
                    signed=True,
                    sign_info=sign_info,
                    provider_message=str(response.payload.get("message") or "OK"),
                ),
                "provider_response": {
                    "retcode": response.payload.get("retcode"),
                    "message": response.payload.get("message"),
                    "data": data,
                },
            },
            source=response.source,
        )

    def daily_signin_status(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
    ) -> CommandResult:
        sign_info, source, info_message = self._sign_info(uid=uid, cookie=cookie, region=region)
        return CommandResult(
            data=_signin_data(
                uid=uid,
                credential_source=credential_source,
                storage_backend=storage_backend,
                already_signed=sign_info.get("is_sign") is True,
                signed=False,
                sign_info=sign_info,
                provider_message=info_message,
            ),
            source=source,
        )

    def _sign_info(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
    ) -> tuple[dict[str, object], dict[str, object], str]:
        ensure_supported_region(region)
        server = server_for_uid(uid)
        params = {
            "act_id": SIGN_ACT_ID,
            "lang": "zh-cn",
            "region": server,
            "uid": uid,
        }
        response = self.http.request_json(
            "GET",
            f"{GS_BASE_CN}{SIGN_INFO_PATH}",
            provider=PROVIDER,
            region=region,
            category="daily.signin.info",
            params=params,
            headers={**_headers(cookie), "x-rpc-signgame": "hk4e"},
        )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category="daily.signin.info",
            source=response.source,
            debug=self.http.debug,
        )
        return (
            _payload_data(response.payload, "daily.signin.info", response.source),
            response.source,
            str(response.payload.get("message") or "OK"),
        )


def _signin_data(
    *,
    uid: str,
    credential_source: str,
    storage_backend: str | None,
    already_signed: bool,
    signed: bool,
    sign_info: dict[str, object],
    provider_message: str,
) -> dict[str, object]:
    day_number = _signin_day_number(sign_info, signed=signed)
    return {
        "uid": uid,
        "credential_source": credential_source,
        "storage_backend": storage_backend,
        "already_signed": already_signed,
        "signed": signed,
        "day_number": day_number,
        "reward": _signin_reward(sign_info, day_number),
        "provider_message": provider_message,
        "sign_info": sign_info,
    }


def _signin_day_number(sign_info: dict[str, object], *, signed: bool) -> int | None:
    total = sign_info.get("total_sign_day")
    try:
        value = int(total)
    except (TypeError, ValueError):
        return None
    if signed:
        return value + 1
    return value


def _signin_reward(
    sign_info: dict[str, object], day_number: int | None
) -> dict[str, object] | None:
    awards = sign_info.get("awards")
    if day_number is None or not isinstance(awards, list):
        return None
    for award in awards:
        if isinstance(award, dict) and award.get("day") == day_number:
            return _signin_award(award)
    if 0 < day_number <= len(awards):
        award = awards[day_number - 1]
        if isinstance(award, dict):
            return _signin_award(award)
    return None


def _signin_award(award: dict[str, object]) -> dict[str, object]:
    return {
        "name": award.get("name"),
        "count": award.get("cnt"),
        "icon": award.get("icon"),
    }
