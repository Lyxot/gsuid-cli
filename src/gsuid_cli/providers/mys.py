from __future__ import annotations

from gsuid_cli.core.http import HttpClient, raise_for_retcode
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.core.secrets import redact_secret

PROVIDER = "mys"
RECORD_BASE_CN = "https://api-takumi-record.mihoyo.com"
INDEX_PATH = "/game_record/app/genshin/api/index"
APP_VERSION = "2.71.1"

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
