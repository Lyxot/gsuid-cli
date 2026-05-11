from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from gsuid_cli.core.config import resolve_paths
from gsuid_cli.core.time import utc_now


@dataclass(frozen=True)
class ArtifactManager:
    request_id: str
    output_dir: str | None = None
    artifact_id: str | None = None

    def write_bytes(
        self,
        *,
        name: str,
        filename: str,
        media_type: str,
        content: bytes,
        description: str,
        kind: str,
    ) -> dict[str, object]:
        path = self._request_dir() / filename
        path.write_bytes(content)
        return {
            "kind": kind,
            "name": name,
            "path": str(path),
            "media_type": media_type,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "description": description,
        }

    def write_text(
        self,
        *,
        name: str,
        filename: str,
        content: str,
        description: str,
        media_type: str = "text/plain; charset=utf-8",
        kind: str = "text",
    ) -> dict[str, object]:
        return self.write_bytes(
            name=name,
            filename=filename,
            media_type=media_type,
            content=content.encode("utf-8"),
            description=description,
            kind=kind,
        )

    def _request_dir(self) -> Path:
        today = utc_now()[:10]
        run_id = self.artifact_id or artifact_run_id(self.request_id)
        path = resolve_paths(self.output_dir).artifacts / today / run_id
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=4096)
def artifact_run_id(request_id: str) -> str:
    """Return the sortable artifact directory id for a CLI request."""
    return uuidv7()


def uuidv7() -> str:
    """Generate an RFC 9562 UUIDv7 string without requiring Python 3.14."""
    timestamp_ms = _current_unix_ms()
    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = (timestamp_ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= random_a << 64
    value |= 0b10 << 62
    value |= random_b
    return str(uuid.UUID(int=value))


def _current_unix_ms() -> int:
    now = datetime.fromisoformat(utc_now().replace("Z", "+00:00"))
    return int(now.timestamp() * 1000)
