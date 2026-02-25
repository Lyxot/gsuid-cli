from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from gsuid_cli.core.config import resolve_paths
from gsuid_cli.core.errors import EXIT_CACHE, CliError

SECRET_QUERY_KEYS = {
    "authkey",
    "cookie",
    "login_ticket",
    "stoken",
    "token",
}


@dataclass(frozen=True)
class CachedResponse:
    payload: dict[str, object]
    fetched_at: str
    status_code: int


class HttpCache:
    def __init__(self, output_dir: str | None = None) -> None:
        self.path = resolve_paths(output_dir).cache_http
        self.path.mkdir(mode=0o700, parents=True, exist_ok=True)

    def get(self, key: str) -> CachedResponse | None:
        file_path = self._path(key)
        if not file_path.exists():
            return None
        raw = json.loads(file_path.read_text(encoding="utf-8"))
        return CachedResponse(
            payload=raw["payload"],
            fetched_at=raw["fetched_at"],
            status_code=raw["status_code"],
        )

    def require(self, key: str) -> CachedResponse:
        cached = self.get(key)
        if cached is None:
            raise CliError(
                "CACHE_MISS",
                "No cached provider response is available for this request.",
                EXIT_CACHE,
            )
        return cached

    def set(
        self,
        key: str,
        *,
        payload: dict[str, object],
        fetched_at: str,
        status_code: int,
    ) -> None:
        file_path = self._path(key)
        file_path.write_text(
            json.dumps(
                {
                    "payload": payload,
                    "fetched_at": fetched_at,
                    "status_code": status_code,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _path(self, key: str) -> Path:
        return self.path / f"{key}.json"


def cache_key(
    method: str,
    url: str,
    *,
    params: dict[str, object] | None = None,
    body: dict[str, object] | None = None,
) -> str:
    identity = {
        "method": method.upper(),
        "url": sanitized_url(url, params=params),
        "body": body if method.upper() != "GET" else None,
    }
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sanitized_url(url: str, *, params: dict[str, object] | None = None) -> str:
    parts = urlsplit(url)
    query_items = parse_qsl(parts.query, keep_blank_values=True)
    if params:
        query_items.extend((key, str(value)) for key, value in params.items())
    safe_query = [
        (key, value) for key, value in query_items if key.lower() not in SECRET_QUERY_KEYS
    ]
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(sorted(safe_query)),
            "",
        )
    )
