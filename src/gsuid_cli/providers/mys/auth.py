from __future__ import annotations

import hashlib
import json
import random
import string
import time
import uuid
from http.cookies import CookieError, SimpleCookie

from gsuid_cli.providers.mys.constants import (
    APP_VERSION,
    BBS_SALT,
    BBS_SIGN_SALT,
    PASSPORT_SALT,
    RECORD_SALT,
    SERVER_BY_UID_PREFIX,
    USER_AGENT,
    WEB_SALT,
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


def _sign_headers(cookie: str) -> dict[str, str]:
    return {
        **_headers(cookie),
        "DS": _web_ds(),
        "x-rpc-signgame": "hk4e",
        "x-rpc-device_id": uuid.uuid4().hex,
        "x-rpc-client_type": "5",
    }


def _hk4e_login_headers(cookie: str) -> dict[str, str]:
    return {
        **_headers(cookie),
        "Content-Type": "application/json;charset=UTF-8",
        "Referer": "https://webstatic.mihoyo.com/",
        "Origin": "https://webstatic.mihoyo.com",
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


def _bbs_headers(stoken: str, body: dict[str, object] | None = None) -> dict[str, str]:
    return {
        **_headers(stoken),
        "DS": _bbs_sign_ds(body) if body is not None else _bbs_ds(),
        "User-Agent": "okhttp/4.8.0",
        "x-rpc-client_type": "2",
        "x-rpc-sys_version": "6.0.1",
        "x-rpc-channel": "miyousheluodi",
        "x-rpc-device_id": _generate_seed(32).upper(),
        "x-rpc-device_name": _random_text(random.randint(1, 10)),
        "x-rpc-device_model": "Mi 10",
        "Referer": "https://app.mihoyo.com",
    }


def _web_ds() -> str:
    # Ported from gsuid_core.utils.api.mys.tools.get_web_ds_token.
    timestamp = str(int(time.time()))
    random_text = "".join(random.sample(string.ascii_lowercase + string.digits, 6))
    digest = hashlib.md5(f"salt={WEB_SALT}&t={timestamp}&r={random_text}".encode()).hexdigest()
    return f"{timestamp},{random_text},{digest}"


def _bbs_ds() -> str:
    timestamp = str(int(time.time()))
    random_text = "".join(random.sample(string.ascii_lowercase + string.digits, 6))
    digest = hashlib.md5(f"salt={BBS_SALT}&t={timestamp}&r={random_text}".encode()).hexdigest()
    return f"{timestamp},{random_text},{digest}"


def _bbs_sign_ds(body: dict[str, object] | None) -> str:
    timestamp = str(int(time.time()))
    random_number = str(random.randint(100000, 200000))
    body_text = _signed_body_text(body)
    digest = hashlib.md5(
        f"salt={BBS_SIGN_SALT}&t={timestamp}&r={random_number}&b={body_text}&q=".encode()
    ).hexdigest()
    return f"{timestamp},{random_number},{digest}"


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


def _fp_headers() -> dict[str, str]:
    headers = _headers("")
    del headers["Cookie"]
    return headers


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


def _generate_seed(length: int) -> str:
    return "".join(random.choices(string.digits + "abcdef", k=length))


def _random_text(length: int) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))
