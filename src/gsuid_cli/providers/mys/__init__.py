from __future__ import annotations

from gsuid_cli.core.errors import (
    EXIT_AUTH,
    CliError,
)
from gsuid_cli.core.http import HttpClient, raise_for_retcode
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.core.secrets import redact_secret
from gsuid_cli.providers.mys.auth import (
    _account_cookie,
    _account_id_from_cookie,
    _linked_role,
    _query_string,
    _record_headers,
    server_for_uid,
)
from gsuid_cli.providers.mys.bbs import MysBbsMixin
from gsuid_cli.providers.mys.challenge import MysChallengeMixin
from gsuid_cli.providers.mys.constants import CARD_PATH, INDEX_PATH, PROVIDER, RECORD_BASE_CN
from gsuid_cli.providers.mys.constants import (
    CN_TIMEZONE as CN_TIMEZONE,
)
from gsuid_cli.providers.mys.constants import (
    ELEMENT_ID_BY_NAME as ELEMENT_ID_BY_NAME,
)
from gsuid_cli.providers.mys.constants import (
    RECORD_SALT as RECORD_SALT,
)
from gsuid_cli.providers.mys.device import MysDeviceMixin
from gsuid_cli.providers.mys.gacha import MysGachaMixin
from gsuid_cli.providers.mys.normalizers import (
    _payload_data,
)
from gsuid_cli.providers.mys.player import MysPlayerMixin
from gsuid_cli.providers.mys.progress import MysProgressMixin
from gsuid_cli.providers.mys.qrcode import MysQrcodeMixin
from gsuid_cli.providers.mys.signin import MysSigninMixin


class MysProvider(
    MysBbsMixin,
    MysChallengeMixin,
    MysDeviceMixin,
    MysGachaMixin,
    MysPlayerMixin,
    MysProgressMixin,
    MysQrcodeMixin,
    MysSigninMixin,
):
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

    def _account_card_role(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
    ) -> dict[str, object] | None:
        account_id = _account_id_from_cookie(cookie)
        if not account_id:
            return None
        params = {"uid": account_id}
        response = self.http.request_json(
            "GET",
            f"{RECORD_BASE_CN}{CARD_PATH}",
            provider=PROVIDER,
            region=region,
            category="player.summary.role",
            params=params,
            headers=_record_headers(_account_cookie(cookie, account_id), _query_string(params)),
        )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category="player.summary.role",
            source=response.source,
            debug=self.http.debug,
        )
        data = response.payload.get("data")
        roles_value = data.get("list") if isinstance(data, dict) else []
        if not isinstance(roles_value, list):
            roles_value = []
        for role in roles_value:
            if not isinstance(role, dict):
                continue
            linked_role = _linked_role(role)
            if linked_role["game_id"] == "2" and linked_role["game_role_id"] == uid:
                return linked_role
        return None

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
