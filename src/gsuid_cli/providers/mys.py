from __future__ import annotations

import hashlib
import json
import random
import re
import string
import time
import uuid
from datetime import UTC, datetime
from http.cookies import CookieError, SimpleCookie
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from gsuid_cli.core.errors import (
    EXIT_AUTH,
    EXIT_INVALID_INPUT,
    EXIT_NO_RESULT,
    EXIT_UPSTREAM,
    CliError,
)
from gsuid_cli.core.http import HttpClient, raise_for_retcode
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.core.secrets import redact_secret
from gsuid_cli.core.state import state_db

PROVIDER = "mys"
RECORD_BASE_CN = "https://api-takumi-record.mihoyo.com"
GS_BASE_CN = "https://api-takumi.mihoyo.com"
HK4_API_BASE_CN = "https://hk4e-api.mihoyo.com"
PASSPORT_BASE_CN = "https://passport-api.mihoyo.com"
HK4_SDK_BASE_CN = "https://hk4e-sdk.mihoyo.com"
NEW_BBS_BASE_CN = "https://bbs-api.miyoushe.com"
GET_FP_URL = "https://public-data-api.mihoyo.com/device-fp/api/getFp"
GACHA_LOG_URL = "https://public-operation-hk4e.mihoyo.com/gacha_info/api/getGachaLog"
INDEX_PATH = "/game_record/app/genshin/api/index"
CARD_PATH = "/game_record/card/wapi/getGameRecordCard"
DAILY_NOTE_PATH = "/game_record/app/genshin/api/dailyNote"
ABYSS_PATH = "/game_record/app/genshin/api/spiralAbyss"
ROLE_COMBAT_PATH = "/game_record/app/genshin/api/role_combat"
ACHIEVEMENT_PATH = "/game_record/app/genshin/api/achievement"
GCG_BASIC_PATH = "/game_record/app/genshin/api/gcg/basicInfo"
GCG_DECK_PATH = "/game_record/app/genshin/api/gcg/deckList"
CHARACTER_LIST_PATH = "/game_record/app/genshin/api/character/list"
MONTHLY_AWARD_PATH = "/event/ys_ledger/monthInfo"
SIGN_INFO_PATH = "/event/luna/info"
SIGN_PATH = "/event/luna/sign"
CREATE_QRCODE_PATH = "/hk4e_cn/combo/panda/qrcode/fetch"
CHECK_QRCODE_PATH = "/hk4e_cn/combo/panda/qrcode/query"
GET_STOKEN_BY_GAME_TOKEN_PATH = "/account/ma-cn-session/app/getTokenByGameToken"
GET_COOKIE_TOKEN_BY_STOKEN_PATH = "/account/auth/api/getCookieAccountInfoBySToken"
GET_AUTHKEY_PATH = "/binding/api/genAuthKey"
DEVICE_LOGIN_PATH = "/apihub/api/deviceLogin"
SAVE_DEVICE_PATH = "/apihub/api/saveDevice"
APP_VERSION = "2.102.1"
RECORD_SALT = "xV8v4Qu54lUKrEYFZkJhB8cuOh9Asafs"
WEB_SALT = "yBh10ikxtLPoIhgwgPZSv5dmfaOTSJ6a"
PASSPORT_SALT = "JwYDpKvLj6MrMqqYU6jTKF17KNO2PXoS"
SIGN_ACT_ID = "e202311201442471"
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
        self._device_headers_by_uid: dict[str, dict[str, str]] = {}

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

    def daily_note(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
    ) -> CommandResult:
        data, source = self._record_get(
            path=DAILY_NOTE_PATH,
            uid=uid,
            cookie=cookie,
            region=region,
            category="daily.note",
        )
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "note": _daily_note(data),
            },
            source=source,
        )

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

    def player_summary(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
    ) -> CommandResult:
        data, source = self._record_get(
            path=INDEX_PATH,
            uid=uid,
            cookie=cookie,
            region=region,
            category="player.summary",
        )
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "summary": _player_summary(data),
            },
            source=source,
        )

    def player_characters(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
    ) -> CommandResult:
        index_data, index_source = self._record_get(
            path=INDEX_PATH,
            uid=uid,
            cookie=cookie,
            region=region,
            category="player.characters.index",
        )
        avatars = index_data.get("avatars")
        character_ids = []
        if isinstance(avatars, list):
            character_ids = [
                int(avatar["id"])
                for avatar in avatars
                if isinstance(avatar, dict) and avatar.get("id")
            ]
        if not character_ids:
            return CommandResult(
                data={
                    "uid": uid,
                    "credential_source": credential_source,
                    "storage_backend": storage_backend,
                    "characters": [],
                    "count": 0,
                },
                source=index_source,
            )

        server = server_for_uid(uid)
        body = {"character_ids": character_ids, "role_id": uid, "server": server}
        response = self.http.request_json(
            "POST",
            f"{RECORD_BASE_CN}{CHARACTER_LIST_PATH}",
            provider=PROVIDER,
            region=region,
            category="player.characters",
            headers=self._record_headers_for_uid(uid, cookie, body=body),
            json_body=body,
        )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category="player.characters",
            source=response.source,
            debug=self.http.debug,
        )
        data = _payload_data(response.payload, "player.characters", response.source)
        characters_value = data.get("list")
        if not isinstance(characters_value, list):
            characters_value = []
        characters = [
            _character(character) for character in characters_value if isinstance(character, dict)
        ]
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "characters": characters,
                "count": len(characters),
            },
            source=response.source,
        )

    def player_diary(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
        month: str | None = None,
    ) -> CommandResult:
        server = server_for_uid(uid)
        params = {
            "act_id": "e202009291139501",
            "bind_region": server,
            "bind_uid": uid,
            "month": _diary_month(month),
            "bbs_presentation_style": "fullscreen",
            "bbs_auth_required": "true",
            "utm_source": "bbs",
            "utm_medium": "mys",
            "utm_campaign": "icon",
        }
        response = self.http.request_json(
            "GET",
            f"{HK4_API_BASE_CN}{MONTHLY_AWARD_PATH}",
            provider=PROVIDER,
            region=region,
            category="player.diary",
            params=params,
            headers={**_headers(cookie), "DS": _web_ds(), "x-rpc-device_id": uuid.uuid4().hex},
        )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category="player.diary",
            source=response.source,
            debug=self.http.debug,
        )
        data = _payload_data(response.payload, "player.diary", response.source)
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "requested_month": month,
                "diary": _diary(data),
            },
            source=response.source,
        )

    def challenge_abyss(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
        season: str,
        floor: int | None = None,
    ) -> CommandResult:
        server = server_for_uid(uid)
        schedule_type = _schedule_type(season)
        data, source = self._record_get(
            path=ABYSS_PATH,
            uid=uid,
            cookie=cookie,
            region=region,
            category="challenge.abyss",
            params={
                "role_id": uid,
                "schedule_type": schedule_type,
                "server": server,
            },
        )
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "season": season,
                "schedule_type": schedule_type,
                "floor": floor,
                "abyss": _abyss(data, floor),
            },
            source=source,
        )

    def challenge_theater(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
        season: str,
    ) -> CommandResult:
        warnings = []
        if season != "current":
            warnings.append("theater season selection is not exposed by the provider")
        server = server_for_uid(uid)
        data, source = self._record_get(
            path=ROLE_COMBAT_PATH,
            uid=uid,
            cookie=cookie,
            region=region,
            category="challenge.theater",
            params={
                "server": server,
                "role_id": uid,
                "need_detail": "true",
            },
        )
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "season": season,
                "effective_season": "current",
                "theater": _theater(data, season),
            },
            source=source,
            warnings=warnings,
        )

    def challenge_hard(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
        season: str,
    ) -> CommandResult:
        data, source = self._record_get(
            path=INDEX_PATH,
            uid=uid,
            cookie=cookie,
            region=region,
            category="challenge.hard",
        )
        warnings = []
        if season != "current":
            warnings.append("hard challenge season selection is not exposed by the provider")
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "season": season,
                "effective_season": "current",
                "hard": _hard_challenge(data),
            },
            source=source,
            warnings=warnings,
        )

    def progress_completion(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
    ) -> CommandResult:
        data, source = self._record_get(
            path=INDEX_PATH,
            uid=uid,
            cookie=cookie,
            region=region,
            category="progress.completion",
        )
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "completion": _completion(data),
            },
            source=source,
        )

    def progress_exploration(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
    ) -> CommandResult:
        data, source = self._record_get(
            path=INDEX_PATH,
            uid=uid,
            cookie=cookie,
            region=region,
            category="progress.exploration",
        )
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "exploration": _exploration(data),
            },
            source=source,
        )

    def progress_collection(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
    ) -> CommandResult:
        data, source = self._record_get(
            path=INDEX_PATH,
            uid=uid,
            cookie=cookie,
            region=region,
            category="progress.collection",
        )
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "collection": _collection(data),
            },
            source=source,
        )

    def progress_achievements(
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
        body = {"role_id": uid, "server": server}
        response = self.http.request_json(
            "POST",
            f"{RECORD_BASE_CN}{ACHIEVEMENT_PATH}",
            provider=PROVIDER,
            region=region,
            category="progress.achievements",
            headers=self._record_headers_for_uid(uid, cookie, body=body),
            json_body=body,
        )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category="progress.achievements",
            source=response.source,
            debug=self.http.debug,
        )
        data = _payload_data(response.payload, "progress.achievements", response.source)
        achievements = data.get("list")
        if not isinstance(achievements, list):
            achievements = []
        normalized = [item for item in achievements if isinstance(item, dict)]
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "achievements": normalized,
                "count": len(normalized),
            },
            source=response.source,
        )

    def progress_gcg(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
    ) -> CommandResult:
        basic, basic_source = self._record_get(
            path=GCG_BASIC_PATH,
            uid=uid,
            cookie=cookie,
            region=region,
            category="progress.gcg.basic",
        )
        decks, deck_source = self._record_get(
            path=GCG_DECK_PATH,
            uid=uid,
            cookie=cookie,
            region=region,
            category="progress.gcg.decks",
        )
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "gcg": _gcg(basic, decks),
            },
            source=deck_source or basic_source,
        )

    def progress_gcg_deck(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
        deck_id: int | None,
    ) -> CommandResult:
        decks, source = self._record_get(
            path=GCG_DECK_PATH,
            uid=uid,
            cookie=cookie,
            region=region,
            category="progress.gcg.deck",
        )
        deck_list = _gcg_decks(decks)
        if deck_id is not None:
            deck_list = [
                deck
                for deck in deck_list
                if str(deck.get("id") or deck.get("deck_id") or "") == str(deck_id)
            ]
            if not deck_list:
                raise CliError(
                    "NO_RESULT",
                    "No GCG deck matched the requested deck id.",
                    EXIT_NO_RESULT,
                    {"uid": uid, "deck_id": deck_id},
                    source=source,
                )
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "deck_id": deck_id,
                "decks": deck_list,
                "count": len(deck_list),
            },
            source=source,
        )

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

    def device_login(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
        device_payload: dict[str, object],
    ) -> CommandResult:
        ensure_supported_region(region)
        device = self._device_from_payload(device_payload)
        body = _device_login_body(device["device_id"], device["device_info"])
        headers = _device_login_headers(
            cookie=cookie,
            body=body,
            device_id=device["device_id"],
            device_fp=device["device_fp"],
            device_info=device["device_info"],
        )
        login = self.http.request_json(
            "POST",
            f"{NEW_BBS_BASE_CN}{DEVICE_LOGIN_PATH}",
            provider=PROVIDER,
            region=region,
            category="auth.device.set",
            json_body=body,
            headers=headers,
        )
        raise_for_retcode(
            login.payload,
            provider=PROVIDER,
            region=region,
            category="auth.device.set",
            source=login.source,
            debug=self.http.debug,
        )
        save = self.http.request_json(
            "POST",
            f"{NEW_BBS_BASE_CN}{SAVE_DEVICE_PATH}",
            provider=PROVIDER,
            region=region,
            category="auth.device.save",
            json_body=body,
            headers=headers,
        )
        raise_for_retcode(
            save.payload,
            provider=PROVIDER,
            region=region,
            category="auth.device.save",
            source=save.source,
            debug=self.http.debug,
        )
        return CommandResult(
            data={
                "uid": uid,
                "account_id": _account_id_from_cookie(cookie),
                "status": "bound",
                "credential_source": credential_source,
                "credential_storage_backend": storage_backend,
                "device_id": device["device_id"],
                "device_fp": device["device_fp"],
                "device_info": device["device_info"],
                "device": _device_info_summary(device["device_info"]),
                "generated_fp": device["generated_fp"],
                "redacted": {
                    "device_id": redact_secret(device["device_id"]),
                    "device_fp": redact_secret(device["device_fp"]),
                },
                "provider_response": {
                    "device_set": {
                        "retcode": login.payload.get("retcode"),
                        "message": login.payload.get("message"),
                    },
                    "save_device": {
                        "retcode": save.payload.get("retcode"),
                        "message": save.payload.get("message"),
                    },
                },
            },
            source=save.source,
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

    def _record_get(
        self,
        *,
        path: str,
        uid: str,
        cookie: str,
        region: str,
        category: str,
        params: dict[str, object] | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        ensure_supported_region(region)
        server = server_for_uid(uid)
        if params is None:
            params = {"role_id": uid, "server": server}
        response = self.http.request_json(
            "GET",
            f"{RECORD_BASE_CN}{path}",
            provider=PROVIDER,
            region=region,
            category=category,
            params=params,
            headers=self._record_headers_for_uid(uid, cookie, _query_string(params)),
        )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category=category,
            source=response.source,
            debug=self.http.debug,
        )
        return _payload_data(response.payload, category, response.source), response.source

    def _record_headers_for_uid(
        self,
        uid: str,
        cookie: str,
        query: str = "",
        body: dict[str, object] | None = None,
    ) -> dict[str, str]:
        return {
            **_record_headers(cookie, query, body),
            **self._device_headers(uid),
        }

    def _device_headers(self, uid: str) -> dict[str, str]:
        headers = self._device_headers_by_uid.get(uid)
        if headers is None:
            headers = _stored_device_headers(uid, self.http.output_dir)
            if headers is None:
                device_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"gsuid-cli:mys:{uid}")).lower()
                seed_id = str(uuid.uuid4()).lower()
                seed_time = str(int(time.time() * 1000))
                headers = {
                    "x-rpc-device_id": device_id,
                    "x-rpc-device_fp": self._generate_device_fp(device_id, seed_id, seed_time),
                }
            self._device_headers_by_uid[uid] = headers
        return dict(headers)

    def _generate_device_fp(self, device_id: str, seed_id: str, seed_time: str) -> str:
        response = self.http.request_json(
            "POST",
            GET_FP_URL,
            provider=PROVIDER,
            region="cn",
            category="device.fp",
            headers=_fp_headers(),
            json_body=_device_fp_body(device_id, seed_id, seed_time),
        )
        data = response.payload.get("data")
        if isinstance(data, dict) and data.get("device_fp"):
            return str(data["device_fp"])
        return _random_fp()

    def _device_from_payload(self, payload: dict[str, object]) -> dict[str, object]:
        device_id = _device_payload_value(payload, "device_id") or _device_payload_value(
            payload, "deviceId"
        )
        device_fp = _device_payload_value(payload, "fp")
        if device_id and device_fp:
            return {
                "device_id": device_id,
                "device_fp": device_fp,
                "device_info": _device_payload_value(payload, "device_info")
                or _device_payload_value(payload, "deviceInfo")
                or "Unknown/Unknown/Unknown/Unknown",
                "generated_fp": False,
            }

        device_id = str(uuid.uuid4()).lower()
        seed_id = str(uuid.uuid4()).lower()
        seed_time = str(int(time.time() * 1000))
        device_info = _required_device_payload(payload, "deviceFingerprint")
        device_fp = self._generate_device_fp_from_info(
            device_id,
            seed_id,
            seed_time,
            model_name=_required_device_payload(payload, "deviceModel"),
            device=_required_device_payload(payload, "deviceProduct"),
            device_type=_required_device_payload(payload, "deviceName"),
            board=_required_device_payload(payload, "deviceBoard"),
            oaid=_required_device_payload(payload, "oaid"),
            device_info=device_info,
        )
        return {
            "device_id": device_id,
            "device_fp": device_fp,
            "device_info": device_info,
            "generated_fp": True,
        }

    def _generate_device_fp_from_info(
        self,
        device_id: str,
        seed_id: str,
        seed_time: str,
        *,
        model_name: str,
        device: str,
        device_type: str,
        board: str,
        oaid: str,
        device_info: str,
    ) -> str:
        response = self.http.request_json(
            "POST",
            GET_FP_URL,
            provider=PROVIDER,
            region="cn",
            category="device.fp",
            headers=_fp_headers(),
            json_body=_device_fp_body(
                device_id,
                seed_id,
                seed_time,
                model_name=model_name,
                device=device,
                device_type=device_type,
                board=board,
                oaid=oaid,
                device_info=device_info,
            ),
        )
        data = response.payload.get("data")
        if isinstance(data, dict) and data.get("device_fp"):
            return str(data["device_fp"])
        return _random_fp()

    def _sign_info(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
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


def _record_headers(
    cookie: str,
    query: str = "",
    body: dict[str, object] | None = None,
) -> dict[str, str]:
    return {
        **_headers(cookie),
        "DS": _record_ds(query, body),
    }


def _record_ds(query: str = "", body: dict[str, object] | None = None) -> str:
    # Ported from gsuid_core.utils.api.mys.tools.get_ds_token.
    timestamp = str(int(time.time()))
    random_number = str(random.randint(100000, 200000))
    body_text = _signed_body_text(body)
    digest = hashlib.md5(
        f"salt={RECORD_SALT}&t={timestamp}&r={random_number}&b={body_text}&q={query}".encode()
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


def _daily_note(data: dict[str, object]) -> dict[str, object]:
    keys = (
        "current_resin",
        "max_resin",
        "resin_recovery_time",
        "finished_task_num",
        "total_task_num",
        "is_extra_task_reward_received",
        "remain_resin_discount_num",
        "resin_discount_num_limit",
        "current_expedition_num",
        "max_expedition_num",
        "expeditions",
        "current_home_coin",
        "max_home_coin",
        "home_coin_recovery_time",
        "transformer",
        "daily_task",
        "archon_quest_progress",
    )
    return {key: data.get(key) for key in keys}


def _player_summary(data: dict[str, object]) -> dict[str, object]:
    stats = data.get("stats")
    avatars = data.get("avatars")
    explorations = data.get("world_explorations")
    homes = data.get("homes")
    if not isinstance(stats, dict):
        stats = {}
    if not isinstance(avatars, list):
        avatars = []
    if not isinstance(explorations, list):
        explorations = []
    if not isinstance(homes, list):
        homes = []

    return {
        "role": {
            "nickname": data.get("nickname"),
            "level": data.get("level"),
            "region": data.get("region"),
            "region_name": data.get("region_name"),
            "avatar_icon": data.get("avatar_icon"),
        },
        "stats": stats,
        "avatars": [_avatar_summary(avatar) for avatar in avatars if isinstance(avatar, dict)],
        "avatar_count": len([avatar for avatar in avatars if isinstance(avatar, dict)]),
        "world_explorations": [
            exploration for exploration in explorations if isinstance(exploration, dict)
        ],
        "homes": [home for home in homes if isinstance(home, dict)],
    }


def _avatar_summary(avatar: dict[str, object]) -> dict[str, object]:
    return {
        "id": avatar.get("id"),
        "name": avatar.get("name"),
        "element": avatar.get("element"),
        "level": avatar.get("level"),
        "rarity": avatar.get("rarity"),
        "icon": avatar.get("icon"),
    }


def _character(character: dict[str, object]) -> dict[str, object]:
    weapon = character.get("weapon")
    reliquaries = character.get("reliquaries")
    constellations = character.get("constellations")
    costumes = character.get("costumes")
    if not isinstance(weapon, dict):
        weapon = {}
    if not isinstance(reliquaries, list):
        reliquaries = []
    if not isinstance(constellations, list):
        constellations = []
    if not isinstance(costumes, list):
        costumes = []

    return {
        "id": character.get("id"),
        "name": character.get("name"),
        "element": character.get("element"),
        "level": character.get("level"),
        "rarity": character.get("rarity"),
        "fetter": character.get("fetter"),
        "actived_constellation_num": character.get("actived_constellation_num"),
        "image": character.get("image"),
        "icon": character.get("icon"),
        "weapon": {
            "id": weapon.get("id"),
            "name": weapon.get("name"),
            "type": weapon.get("type"),
            "rarity": weapon.get("rarity"),
            "level": weapon.get("level"),
            "promote_level": weapon.get("promote_level"),
            "affix_level": weapon.get("affix_level"),
            "icon": weapon.get("icon"),
        },
        "reliquaries": [item for item in reliquaries if isinstance(item, dict)],
        "constellations": [item for item in constellations if isinstance(item, dict)],
        "costumes": [item for item in costumes if isinstance(item, dict)],
    }


def _diary(data: dict[str, object]) -> dict[str, object]:
    day_data = data.get("day_data")
    month_data = data.get("month_data")
    optional_month = data.get("optional_month")
    lantern = data.get("lantern")
    if not isinstance(day_data, dict):
        day_data = {}
    if not isinstance(month_data, dict):
        month_data = {}
    if not isinstance(optional_month, list):
        optional_month = []
    if not isinstance(lantern, dict):
        lantern = {}

    return {
        "uid": data.get("uid"),
        "region": data.get("region"),
        "account_id": data.get("account_id"),
        "nickname": data.get("nickname"),
        "date": data.get("date"),
        "month": data.get("month"),
        "data_month": data.get("data_month"),
        "data_last_month": data.get("data_last_month"),
        "day_data": day_data,
        "month_data": month_data,
        "optional_month": [item for item in optional_month if isinstance(item, dict)],
        "lantern": lantern,
    }


def _abyss(data: dict[str, object], floor: int | None) -> dict[str, object]:
    floors_value = data.get("floors")
    if not isinstance(floors_value, list):
        floors_value = []
    floors = [item for item in floors_value if isinstance(item, dict)]
    if floor is not None:
        floors = [item for item in floors if _floor_index(item) == floor]

    return {
        "schedule_id": data.get("schedule_id"),
        "start_time": data.get("start_time"),
        "end_time": data.get("end_time"),
        "total_battle_times": data.get("total_battle_times"),
        "total_win_times": data.get("total_win_times"),
        "max_floor": data.get("max_floor"),
        "total_star": data.get("total_star"),
        "is_unlock": data.get("is_unlock"),
        "rankings": _abyss_rankings(data),
        "floors": floors,
        "floor_count": len(floors),
    }


def _floor_index(floor: dict[str, object]) -> int | None:
    value = floor.get("index")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _abyss_rankings(data: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    rankings = {}
    for key in (
        "reveal_rank",
        "defeat_rank",
        "damage_rank",
        "take_damage_rank",
        "normal_skill_rank",
        "energy_skill_rank",
    ):
        value = data.get(key)
        rankings[key] = (
            [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
        )
    return rankings


def _theater(data: dict[str, object], _season: str) -> dict[str, object]:
    sessions_value = data.get("data")
    if not isinstance(sessions_value, list):
        sessions_value = []
    sessions = [item for item in sessions_value if isinstance(item, dict)]
    selected = sessions[0] if sessions else None
    links = data.get("links")
    if not isinstance(links, dict):
        links = {}
    return {
        "selected": selected,
        "sessions": sessions,
        "count": len(sessions),
        "links": links,
    }


def _hard_challenge(data: dict[str, object]) -> dict[str, object]:
    hard = data.get("hard_challenge")
    role_combat = data.get("role_combat")
    return {
        "hard_challenge": hard if isinstance(hard, dict) else {},
        "role_combat": role_combat if isinstance(role_combat, dict) else {},
    }


def _completion(data: dict[str, object]) -> dict[str, object]:
    stats = data.get("stats")
    explorations = data.get("world_explorations")
    if not isinstance(stats, dict):
        stats = {}
    if not isinstance(explorations, list):
        explorations = []
    return {
        "role": {
            "nickname": data.get("nickname"),
            "level": data.get("level"),
            "region": data.get("region"),
            "region_name": data.get("region_name"),
        },
        "stats": stats,
        "exploration_count": len([item for item in explorations if isinstance(item, dict)]),
        "world_explorations": [item for item in explorations if isinstance(item, dict)],
        "challenge": _hard_challenge(data),
    }


def _exploration(data: dict[str, object]) -> dict[str, object]:
    explorations = data.get("world_explorations")
    homes = data.get("homes")
    if not isinstance(explorations, list):
        explorations = []
    if not isinstance(homes, list):
        homes = []
    return {
        "world_explorations": [item for item in explorations if isinstance(item, dict)],
        "homes": [item for item in homes if isinstance(item, dict)],
    }


def _collection(data: dict[str, object]) -> dict[str, object]:
    stats = data.get("stats")
    if not isinstance(stats, dict):
        stats = {}
    return {
        "avatars": stats.get("avatar_number"),
        "achievements": stats.get("achievement_number"),
        "spiral_abyss": stats.get("spiral_abyss"),
        "oculi": {key: value for key, value in stats.items() if "oculus" in key},
        "chests": {key: value for key, value in stats.items() if key.endswith("_chest_number")},
        "waypoints": stats.get("way_point_number"),
        "domains": stats.get("domain_number"),
        "raw_stats": stats,
    }


def _gcg(basic: dict[str, object], decks: dict[str, object]) -> dict[str, object]:
    deck_list = _gcg_decks(decks)
    return {
        "basic": basic,
        "deck_data": decks,
        "decks": deck_list,
        "deck_count": len(deck_list),
    }


def _gcg_decks(decks: dict[str, object]) -> list[dict[str, object]]:
    deck_list = (
        decks.get("deck_list") or decks.get("card_list") or decks.get("list") or decks.get("decks")
    )
    if not isinstance(deck_list, list):
        return []
    return [item for item in deck_list if isinstance(item, dict)]


def _schedule_type(season: str) -> str:
    return "2" if season == "previous" else "1"


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


def _diary_month(month: str | None) -> str:
    if month is None:
        return "0"
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise CliError(
            "INVALID_ARGUMENT",
            "month must use YYYY-MM format",
            EXIT_INVALID_INPUT,
            {"month": month},
        )
    year = int(month.split("-", 1)[0])
    current_year = datetime.now(UTC).year
    if year != current_year:
        raise CliError(
            "INVALID_ARGUMENT",
            "month must be in the current ledger year",
            EXIT_INVALID_INPUT,
            {"month": month, "supported_year": current_year},
        )
    month_number = int(month.split("-", 1)[1])
    if month_number < 1 or month_number > 12:
        raise CliError(
            "INVALID_ARGUMENT",
            "month must use a month from 01 to 12",
            EXIT_INVALID_INPUT,
            {"month": month},
        )
    return str(month_number)


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


def _sign_headers(cookie: str) -> dict[str, str]:
    return {
        **_headers(cookie),
        "DS": _web_ds(),
        "x-rpc-signgame": "hk4e",
        "x-rpc-device_id": uuid.uuid4().hex,
        "x-rpc-client_type": "5",
    }


def _authkey_headers(stoken: str) -> dict[str, str]:
    # Ported from gsuid_core.utils.api.mys.account_request.get_authkey_by_cookie.
    return {
        **_headers(stoken),
        "DS": _web_ds(),
        "User-Agent": "okhttp/4.8.0",
        "x-rpc-app_version": APP_VERSION,
        "x-rpc-sys_version": "12",
        "x-rpc-client_type": "5",
        "x-rpc-channel": "mihoyo",
        "x-rpc-device_id": _generate_seed(32),
        "x-rpc-device_name": _random_text(random.randint(1, 10)),
        "x-rpc-device_model": "Mi 10",
        "Referer": "https://app.mihoyo.com",
        "Host": "api-takumi.mihoyo.com",
    }


def _web_ds() -> str:
    # Ported from gsuid_core.utils.api.mys.tools.get_web_ds_token.
    timestamp = str(int(time.time()))
    random_text = "".join(random.sample(string.ascii_lowercase + string.digits, 6))
    digest = hashlib.md5(f"salt={WEB_SALT}&t={timestamp}&r={random_text}".encode()).hexdigest()
    return f"{timestamp},{random_text},{digest}"


def _already_signed(payload: dict[str, object]) -> bool:
    return payload.get("retcode") in {-5003, "-5003"}


def _signed_body_text(body: dict[str, object] | None) -> str:
    if not body:
        return ""
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def _ticket_from_url(url: str) -> str:
    marker = "ticket="
    if marker not in url:
        return ""
    return url.split(marker, 1)[1].split("&", 1)[0]


def _random_device_id() -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=64))


def _fp_headers() -> dict[str, str]:
    headers = _headers("")
    del headers["Cookie"]
    return headers


def _stored_device_headers(uid: str, output_dir: str | None) -> dict[str, str] | None:
    with state_db(output_dir) as conn:
        row = conn.execute(
            "SELECT device_id, device_fp FROM accounts WHERE uid = ?",
            (uid,),
        ).fetchone()
    if row is None or not row["device_id"] or not row["device_fp"]:
        return None
    return {
        "x-rpc-device_id": str(row["device_id"]),
        "x-rpc-device_fp": str(row["device_fp"]),
    }


def _device_payload_value(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_device_payload(payload: dict[str, object], key: str) -> str:
    value = _device_payload_value(payload, key)
    if value is None:
        raise CliError(
            "INVALID_ARGUMENT",
            "device payload is missing a required field",
            EXIT_INVALID_INPUT,
            {"field": key},
        )
    return value


def _device_login_body(device_id: object, device_info: object) -> dict[str, object]:
    brand, model_name = _device_info_parts(str(device_info))
    return {
        "app_version": APP_VERSION,
        "device_id": str(device_id),
        "device_name": f"{brand}{model_name}",
        "os_version": "33",
        "platform": "Android",
        "registration_id": _generate_seed(19),
    }


def _device_login_headers(
    *,
    cookie: str,
    body: dict[str, object],
    device_id: object,
    device_fp: object,
    device_info: object,
) -> dict[str, str]:
    brand, model_name = _device_info_parts(str(device_info))
    return {
        **_headers(cookie),
        "x-rpc-device_id": str(device_id),
        "x-rpc-device_fp": str(device_fp),
        "x-rpc-device_name": f"{brand} {model_name}",
        "x-rpc-device_model": model_name,
        "x-rpc-csm_source": "myself",
        "Referer": "https://app.mihoyo.com",
        "Host": "bbs-api.miyoushe.com",
        "DS": _passport_ds(body=body),
    }


def _device_info_summary(device_info: object) -> dict[str, object]:
    brand, model_name = _device_info_parts(str(device_info))
    return {
        "brand": brand,
        "model": model_name,
        "has_device_info": bool(str(device_info).strip()),
    }


def _device_info_parts(device_info: str) -> tuple[str, str]:
    parts = [part.strip() for part in device_info.split("/") if part.strip()]
    brand = parts[0] if parts else "Unknown"
    model_name = parts[1] if len(parts) > 1 else brand
    return brand, model_name


def _device_fp_body(
    device_id: str,
    seed_id: str,
    seed_time: str,
    *,
    model_name: str = "PHK110",
    device: str = "PHK110",
    device_type: str = "OP5913L1",
    board: str = "taro",
    oaid: str = "1f1971b188c472f0",
    device_info: str = (
        "OnePlus/PHK110/OP5913L1:13/SKQ1.221119.001/T.1328291_b9_41:user/release-keys"
    ),
) -> dict[str, object]:
    # Ported from gsuid_core.utils.api.mys.base_request.generate_fake_fp.
    device_brand = device_info.split("/")[0]
    random_data = random.randint(400000, 600000)
    random_data2 = random.randint(150000, 300000)
    now_ms = int(time.time() * 1000)
    ext_fields = {
        "proxyStatus": 0,
        "isRoot": 1,
        "romCapacity": "512",
        "deviceName": "PrivatePhone",
        "productName": device,
        "romRemain": "491",
        "hostname": "dg02-pool06-kvm82",
        "screenSize": "1264x2640",
        "isTablet": 0,
        "aaid": _generate_id(),
        "model": model_name,
        "brand": device_brand,
        "hardware": "qcom",
        "deviceType": device_type,
        "devId": "REL",
        "serialNumber": "unknown",
        "sdCapacity": random_data,
        "buildTime": "1717740969000",
        "buildUser": "root",
        "simState": 5,
        "ramRemain": str(random_data2),
        "appUpdateTimeDiff": now_ms,
        "deviceInfo": device_info,
        "vaid": _generate_id(),
        "buildType": "user",
        "sdkVersion": "34",
        "ui_mode": "UI_MODE_TYPE_NORMAL",
        "isMockLocation": 0,
        "cpuType": "arm64-v8a",
        "isAirMode": 0,
        "ringMode": 1,
        "chargeStatus": 1,
        "manufacturer": device_brand,
        "emulatorStatus": 0,
        "appMemory": "512",
        "osVersion": "14",
        "vendor": "ChinaUnicom",
        "accelerometer": "-1.3004991x6.38764x7.19103",
        "sdRemain": random_data2,
        "buildTags": "release-keys",
        "packageName": "com.mihoyo.hyperion",
        "networkType": "WiFi",
        "oaid": oaid,
        "debugStatus": 1,
        "ramCapacity": str(random_data),
        "magnetometer": "27.1084x-48.5804x-24.8758",
        "display": f"{model_name}_14.0.0.810(CN01)",
        "appInstallTimeDiff": str(now_ms),
        "packageVersion": "2.20.2",
        "gyroscope": "-0.02543317x0.005725792x0.003195791",
        "batteryStatus": 50,
        "hasKeyboard": 0,
        "board": board,
    }
    return {
        "device_id": _generate_seed(16),
        "seed_id": seed_id,
        "platform": "2",
        "seed_time": seed_time,
        "ext_fields": json.dumps(ext_fields, separators=(",", ":")),
        "app_name": "bbs_cn",
        "bbs_device_id": device_id,
        "device_fp": _random_fp(),
    }


def _generate_id(length: int = 64) -> str:
    return "".join(random.choices(string.digits + string.ascii_uppercase, k=length))


def _generate_seed(length: int) -> str:
    return "".join(random.choices(string.digits + "abcdef", k=length))


def _random_text(length: int) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def _random_fp(length: int = 13) -> str:
    return _generate_seed(length)


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
    body_text = _signed_body_text(body)
    digest = hashlib.md5(
        f"salt={PASSPORT_SALT}&t={timestamp}&r={random_text}&b={body_text}&q={query}".encode()
    ).hexdigest()
    return f"{timestamp},{random_text},{digest}"
