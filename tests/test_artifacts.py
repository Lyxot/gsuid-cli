from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime
from pathlib import Path

from helpers import UUIDV7_RE

from gsuid_cli.core.artifacts import ArtifactManager, artifact_date, artifact_run_id


def test_artifact_manager_write_text(monkeypatch, tmp_path) -> None:
    artifact_run_id.cache_clear()
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")

    artifact = ArtifactManager("req-text", str(tmp_path)).write_text(
        name="daily/note",
        filename="daily-note.txt",
        content="hello\n",
        description="Daily note text render",
    )

    path = Path(artifact["path"])
    content = path.read_bytes()
    assert path.parent.parent == tmp_path / "2026-04-29"
    assert UUIDV7_RE.fullmatch(path.parent.name)
    assert path.name == "daily-note.txt"
    assert content == b"hello\n"
    assert artifact["kind"] == "text"
    assert artifact["media_type"] == "text/plain; charset=utf-8"
    assert artifact["sha256"] == hashlib.sha256(content).hexdigest()


def test_artifact_date_uses_local_machine_day(monkeypatch) -> None:
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-05-07T18:30:00Z")

    if not hasattr(time, "tzset"):
        expected = (
            datetime.fromisoformat("2026-05-07T18:30:00+00:00").astimezone().date().isoformat()
        )
        assert artifact_date() == expected
        return

    original_tz = os.environ.get("TZ")
    monkeypatch.setenv("TZ", "Asia/Singapore")
    time.tzset()
    try:
        assert artifact_date() == "2026-05-08"
    finally:
        if original_tz is None:
            monkeypatch.delenv("TZ", raising=False)
        else:
            monkeypatch.setenv("TZ", original_tz)
        time.tzset()


def test_artifact_run_directory_is_uuidv7_and_time_sortable(monkeypatch, tmp_path) -> None:
    artifact_run_id.cache_clear()
    current = {"now": "2026-04-29T10:30:00Z"}
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: current["now"])
    monkeypatch.setattr("gsuid_cli.core.artifacts.secrets.randbits", lambda _bits: 0)

    first = ArtifactManager("first", str(tmp_path)).write_text(
        name="first",
        filename="first.txt",
        content="first",
        description="First artifact",
    )
    current["now"] = "2026-04-29T10:30:01Z"
    second = ArtifactManager("second", str(tmp_path)).write_text(
        name="second",
        filename="second.txt",
        content="second",
        description="Second artifact",
    )

    first_dir = Path(str(first["path"])).parent.name
    second_dir = Path(str(second["path"])).parent.name
    assert UUIDV7_RE.fullmatch(first_dir)
    assert UUIDV7_RE.fullmatch(second_dir)
    assert first_dir < second_dir


def test_artifact_run_directory_is_stable_for_request(monkeypatch, tmp_path) -> None:
    artifact_run_id.cache_clear()
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")

    first = ArtifactManager("same-request", str(tmp_path)).write_text(
        name="first",
        filename="first.txt",
        content="first",
        description="First artifact",
    )
    second = ArtifactManager("same-request", str(tmp_path)).write_text(
        name="second",
        filename="second.txt",
        content="second",
        description="Second artifact",
    )

    assert Path(str(first["path"])).parent == Path(str(second["path"])).parent
