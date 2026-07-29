from __future__ import annotations

from gsuid_cli.core.errors import EXIT_NO_RESULT, CliError
from gsuid_cli.core.http import raise_for_retcode
from gsuid_cli.core.models import CommandResult
from gsuid_cli.providers.mys.auth import record_base_for_uid, record_path_for_uid, server_for_uid
from gsuid_cli.providers.mys.constants import (
    ACHIEVEMENT_PATH,
    GCG_BASIC_PATH,
    GCG_DECK_PATH,
    INDEX_PATH,
    PROVIDER,
)
from gsuid_cli.providers.mys.normalizers import (
    _collection,
    _completion,
    _exploration,
    _gcg,
    _gcg_decks,
    _payload_data,
)


class MysProgressMixin:
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
        server = server_for_uid(uid)
        body = {"role_id": uid, "server": server}
        response = self.http.request_json(
            "POST",
            f"{record_base_for_uid(uid)}{record_path_for_uid(uid, ACHIEVEMENT_PATH)}",
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
