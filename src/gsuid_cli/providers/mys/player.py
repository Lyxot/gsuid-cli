from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from gsuid_cli.core.errors import EXIT_INVALID_INPUT, EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import ProviderResponse, raise_for_retcode
from gsuid_cli.core.models import CommandResult
from gsuid_cli.providers.mys.auth import (
    _headers,
    _hk4e_login_headers,
    _query_string,
    _record_headers,
    _web_ds,
    server_for_uid,
)
from gsuid_cli.providers.mys.constants import (
    ACT_CALENDAR_PATH,
    CALCULATOR_BATCH_COMPUTE_PATH,
    CHARACTER_DETAIL_PATH,
    CHARACTER_LIST_PATH,
    DAILY_NOTE_PATH,
    GS_BASE_CN,
    HK4_API_BASE_CN,
    HK4E_LOGIN_PATH,
    INDEX_PATH,
    MONTHLY_AWARD_PATH,
    PROVIDER,
    RECORD_BASE_CN,
    REGISTER_TIME_PATH,
)
from gsuid_cli.providers.mys.normalizers import (
    _calendar,
    _character,
    _daily_note,
    _diary,
    _dict_list,
    _inventory,
    _inventory_compute_item,
    _inventory_compute_item_summary,
    _is_calculator_payload_rejection,
    _is_calculator_row_rejection,
    _merge_role_identity,
    _payload_data,
    _player_summary,
    _register_time,
    _retcode_ok,
    _role_needs_identity,
)


class MysPlayerMixin:
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
        summary = _player_summary(data)
        warnings: list[str] = []
        if _role_needs_identity(summary.get("role")):
            try:
                role = self._account_card_role(uid=uid, cookie=cookie, region=region)
            except CliError:
                role = None
            else:
                if role is not None:
                    _merge_role_identity(summary, role)
            if _role_needs_identity(summary.get("role")):
                warnings.append(
                    "player role identity is unavailable; nickname and level may be empty"
                )
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "summary": summary,
            },
            source=source,
            warnings=warnings,
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

    def character_details(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        character_ids: list[int],
        category: str,
    ) -> CommandResult:
        server = server_for_uid(uid)
        body = {"character_ids": character_ids, "role_id": uid, "server": server}
        response = self.http.request_json(
            "POST",
            f"{RECORD_BASE_CN}{CHARACTER_DETAIL_PATH}",
            provider=PROVIDER,
            region=region,
            category=category,
            headers=self._record_headers_for_uid(uid, cookie, body=body),
            json_body=body,
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
        details_value = data.get("list")
        details = (
            [item for item in details_value if isinstance(item, dict)]
            if isinstance(details_value, list)
            else []
        )
        return CommandResult(data={"details": details}, source=response.source)

    def player_inventory(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
    ) -> CommandResult:
        characters_result = self.player_characters(
            uid=uid,
            cookie=cookie,
            region=region,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )
        character_rows = characters_result.data.get("characters")
        characters = _dict_list(character_rows)
        items = [_inventory_compute_item(character) for character in characters]
        items = [item for item in items if item is not None]
        server = server_for_uid(uid)
        body = {
            "items": items,
            "region": server,
            "uid": uid,
        }
        response = self._inventory_compute_response(
            cookie=cookie,
            region=region,
            body=body,
        )
        warnings = list(characters_result.warnings)
        skipped_items: list[dict[str, object]] = []
        try:
            raise_for_retcode(
                response.payload,
                provider=PROVIDER,
                region=region,
                category="player.inventory",
                source=response.source,
                debug=self.http.debug,
            )
        except CliError as exc:
            if not _is_calculator_row_rejection(exc) or len(items) <= 1:
                raise
            invalid_indexes = self._invalid_inventory_indexes(
                uid=uid,
                cookie=cookie,
                region=region,
                items=items,
            )
            invalid_index_set = set(invalid_indexes)
            skipped_items = [
                _inventory_compute_item_summary(items[index]) for index in invalid_indexes
            ]
            body["items"] = [
                item for index, item in enumerate(items) if index not in invalid_index_set
            ]
            response = self._inventory_compute_response(
                cookie=cookie,
                region=region,
                body=body,
            )
            raise_for_retcode(
                response.payload,
                provider=PROVIDER,
                region=region,
                category="player.inventory",
                source=response.source,
                debug=self.http.debug,
            )
            warnings.append(
                "skipped MYS calculator rows rejected by the provider: "
                + ", ".join(
                    str(item.get("name") or item.get("avatar_id")) for item in skipped_items
                )
            )
        data = _payload_data(response.payload, "player.inventory", response.source)
        inventory = _inventory(data)
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "coverage": "owned_character_ascension_and_equipped_weapon_materials",
                "compute_item_count": len(body["items"]),
                "skipped_compute_item_count": len(skipped_items),
                "skipped_compute_items": skipped_items,
                "character_count": len(characters),
                "inventory": inventory,
            },
            source=response.source,
            warnings=warnings,
        )

    def player_calendar(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
    ) -> CommandResult:
        server = server_for_uid(uid)
        body = {"role_id": uid, "server": server}
        response = self.http.request_json(
            "POST",
            f"{RECORD_BASE_CN}{ACT_CALENDAR_PATH}",
            provider=PROVIDER,
            region=region,
            category="player.calendar",
            headers=_headers(cookie),
            json_body=body,
        )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category="player.calendar",
            source=response.source,
            debug=self.http.debug,
        )
        data = _payload_data(response.payload, "player.calendar", response.source)
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "calendar": _calendar(data),
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

    def player_register_time(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
    ) -> CommandResult:
        hk4e_token, _login_source = self._hk4e_token(uid=uid, cookie=cookie, region=region)
        params = {
            "game_biz": "hk4e_cn",
            "lang": "zh-cn",
            "badge_uid": uid,
            "badge_region": server_for_uid(uid),
        }
        response = self.http.request_json(
            "GET",
            f"{HK4_API_BASE_CN}{REGISTER_TIME_PATH}",
            provider=PROVIDER,
            region=region,
            category="player.register-time",
            params=params,
            headers=_record_headers(f"{hk4e_token};{cookie}", _query_string(params)),
        )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category="player.register-time",
            source=response.source,
            debug=self.http.debug,
        )
        data = _payload_data(response.payload, "player.register-time", response.source)
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "register_time": _register_time(uid, data, response.source),
            },
            source=response.source,
        )

    def _hk4e_token(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
    ) -> tuple[str, dict[str, object]]:
        body = {
            "game_biz": "hk4e_cn",
            "lang": "zh-cn",
            "uid": uid,
            "region": server_for_uid(uid),
        }
        response = self.http.request_json(
            "POST",
            f"{GS_BASE_CN}{HK4E_LOGIN_PATH}",
            provider=PROVIDER,
            region=region,
            category="player.register-time.hk4e-token",
            headers=_hk4e_login_headers(cookie),
            json_body=body,
        )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category="player.register-time.hk4e-token",
            source=response.source,
            debug=self.http.debug,
        )
        token = response.cookies.get("e_hk4e_token")
        if not token:
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "Provider did not return an e_hk4e_token cookie.",
                EXIT_UPSTREAM,
                {"provider": PROVIDER, "category": "player.register-time.hk4e-token"},
                source=response.source,
            )
        return f"e_hk4e_token={token}", response.source

    def _inventory_compute_response(
        self,
        *,
        cookie: str,
        region: str,
        body: dict[str, object],
    ) -> ProviderResponse:
        return self.http.request_json(
            "POST",
            f"{GS_BASE_CN}{CALCULATOR_BATCH_COMPUTE_PATH}",
            provider=PROVIDER,
            region=region,
            category="player.inventory",
            headers=_headers(cookie),
            json_body=body,
        )

    def _invalid_inventory_indexes(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        items: list[dict[str, object]],
    ) -> list[int]:
        indexed = list(enumerate(items))
        midpoint = len(indexed) // 2
        return [
            *self._invalid_inventory_indexes_in_batch(
                uid=uid,
                cookie=cookie,
                region=region,
                indexed_items=indexed[:midpoint],
            ),
            *self._invalid_inventory_indexes_in_batch(
                uid=uid,
                cookie=cookie,
                region=region,
                indexed_items=indexed[midpoint:],
            ),
        ]

    def _invalid_inventory_indexes_in_batch(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        indexed_items: list[tuple[int, dict[str, object]]],
    ) -> list[int]:
        body = {
            "items": [item for _index, item in indexed_items],
            "region": server_for_uid(uid),
            "uid": uid,
        }
        response = self._inventory_compute_response(cookie=cookie, region=region, body=body)
        if _retcode_ok(response.payload):
            return []
        if not _is_calculator_payload_rejection(response.payload):
            raise_for_retcode(
                response.payload,
                provider=PROVIDER,
                region=region,
                category="player.inventory",
                source=response.source,
                debug=self.http.debug,
            )
        if len(indexed_items) == 1:
            return [indexed_items[0][0]]
        midpoint = len(indexed_items) // 2
        return [
            *self._invalid_inventory_indexes_in_batch(
                uid=uid,
                cookie=cookie,
                region=region,
                indexed_items=indexed_items[:midpoint],
            ),
            *self._invalid_inventory_indexes_in_batch(
                uid=uid,
                cookie=cookie,
                region=region,
                indexed_items=indexed_items[midpoint:],
            ),
        ]


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
