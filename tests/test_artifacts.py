from __future__ import annotations

import hashlib
from pathlib import Path

from gsuid_cli.core.artifacts import ArtifactManager


def test_artifact_manager_write_text(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")

    artifact = ArtifactManager("req-text", str(tmp_path)).write_text(
        name="daily/note",
        filename="daily-note.txt",
        content="hello\n",
        description="Daily note text render",
    )

    path = Path(artifact["path"])
    content = path.read_bytes()
    assert path == tmp_path / "2026-04-29" / "req-text" / "daily-note.txt"
    assert content == b"hello\n"
    assert artifact["kind"] == "text"
    assert artifact["media_type"] == "text/plain; charset=utf-8"
    assert artifact["sha256"] == hashlib.sha256(content).hexdigest()
