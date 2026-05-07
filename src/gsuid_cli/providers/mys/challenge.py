from __future__ import annotations

from gsuid_cli.core.models import CommandResult
from gsuid_cli.providers.mys.auth import server_for_uid
from gsuid_cli.providers.mys.constants import ABYSS_PATH, HARD_CHALLENGE_PATH, ROLE_COMBAT_PATH
from gsuid_cli.providers.mys.normalizers import _abyss, _hard_challenge, _schedule_type, _theater


class MysChallengeMixin:
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
        server = server_for_uid(uid)
        data, source = self._record_get(
            path=HARD_CHALLENGE_PATH,
            uid=uid,
            cookie=cookie,
            region=region,
            category="challenge.hard",
            params={
                "role_id": uid,
                "server": server,
                "need_detail": "true",
            },
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
