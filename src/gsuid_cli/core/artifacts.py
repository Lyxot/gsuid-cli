from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from gsuid_cli.core.config import resolve_paths
from gsuid_cli.core.time import utc_now


@dataclass(frozen=True)
class ArtifactManager:
    request_id: str
    output_dir: str | None = None

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
        path = resolve_paths(self.output_dir).artifacts / today / self.request_id
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        return path
