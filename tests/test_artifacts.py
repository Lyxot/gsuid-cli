from __future__ import annotations

import argparse
import hashlib
import io
import os
import time
from datetime import datetime
from pathlib import Path

from helpers import UUIDV7_RE
from PIL import Image

from gsuid_cli.commands._text import write_image_artifact
from gsuid_cli.core import image_compression
from gsuid_cli.core.artifacts import ArtifactManager, artifact_date, artifact_run_id
from gsuid_cli.renderers.common import png_bytes as renderer_png_bytes


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


def test_write_image_artifact_compresses_valid_png(monkeypatch, tmp_path) -> None:
    artifact_run_id.cache_clear()
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")
    raw = _png_bytes(compress_level=0)
    args = argparse.Namespace(
        request_id="image-compressed",
        output_dir=str(tmp_path),
        image_compression=True,
    )

    artifact = write_image_artifact(
        args,
        name="test/image",
        filename="image.png",
        content=raw,
        description="Image artifact",
    )

    content = Path(str(artifact["path"])).read_bytes()
    assert len(content) < len(raw)
    assert _rgba_bytes(content) == _rgba_bytes(raw)
    assert artifact["sha256"] == hashlib.sha256(content).hexdigest()


def test_write_image_artifact_can_disable_compression(monkeypatch, tmp_path) -> None:
    artifact_run_id.cache_clear()
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")
    raw = _png_bytes(compress_level=0)
    args = argparse.Namespace(
        request_id="image-uncompressed",
        output_dir=str(tmp_path),
        image_compression=False,
    )

    artifact = write_image_artifact(
        args,
        name="test/image",
        filename="image.png",
        content=raw,
        description="Image artifact",
    )

    content = Path(str(artifact["path"])).read_bytes()
    assert content == raw
    assert artifact["sha256"] == hashlib.sha256(raw).hexdigest()


def test_write_image_artifact_keeps_invalid_png_bytes(monkeypatch, tmp_path) -> None:
    artifact_run_id.cache_clear()
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")
    raw = b"png"
    args = argparse.Namespace(
        request_id="image-invalid",
        output_dir=str(tmp_path),
        image_compression=True,
    )

    artifact = write_image_artifact(
        args,
        name="test/image",
        filename="image.png",
        content=raw,
        description="Image artifact",
    )

    content = Path(str(artifact["path"])).read_bytes()
    assert content == raw
    assert artifact["sha256"] == hashlib.sha256(raw).hexdigest()


def test_renderer_png_bytes_saves_without_pillow_compression() -> None:
    image = Image.new("RGBA", (64, 64), (214, 83, 63, 255))
    uncompressed = renderer_png_bytes(image)
    compressed = _png_bytes(compress_level=9)

    assert len(uncompressed) > len(compressed)
    assert _rgba_bytes(uncompressed) == _rgba_bytes(compressed)


def test_png_optimizer_races_small_images_and_uses_highest_finished_level(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_optimize_levels(
        content: bytes,
        levels: tuple[int, ...],
        timeout_seconds: float,
    ) -> dict[int, bytes | None]:
        captured["content"] = content
        captured["levels"] = levels
        captured["timeout_seconds"] = timeout_seconds
        return {0: b"level-zero", 1: b"level-one"}

    monkeypatch.setattr(image_compression, "_optimize_png_levels", fake_optimize_levels)
    monkeypatch.setattr(image_compression, "PNG_LARGE_IMAGE_THRESHOLD_BYTES", 20)

    optimized = image_compression.optimize_png_artifact(
        b"original-content",
        media_type="image/png",
    )

    assert optimized == b"level-one"
    assert captured == {
        "content": b"original-content",
        "levels": (0, 1, 2),
        "timeout_seconds": image_compression.PNG_COMPRESSION_TIMEOUT_SECONDS,
    }


def test_png_optimizer_uses_level_zero_for_large_images(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_optimize_levels(
        content: bytes,
        levels: tuple[int, ...],
        timeout_seconds: float,
    ) -> dict[int, bytes | None]:
        captured["levels"] = levels
        captured["timeout_seconds"] = timeout_seconds
        return {0: b"smaller"}

    monkeypatch.setattr(image_compression, "_optimize_png_levels", fake_optimize_levels)
    monkeypatch.setattr(image_compression, "PNG_LARGE_IMAGE_THRESHOLD_BYTES", 8)

    optimized = image_compression.optimize_png_artifact(
        b"large-image",
        media_type="image/png",
    )

    assert optimized == b"smaller"
    assert captured == {
        "levels": (0,),
        "timeout_seconds": image_compression.PNG_COMPRESSION_TIMEOUT_SECONDS,
    }


def test_png_optimizer_waits_briefly_for_level_zero_when_budget_has_no_success(
    monkeypatch,
) -> None:
    stopped: list[int] = []
    level_zero = _FakeCompressionProcess(0)
    processes = {
        0: level_zero,
        1: _FakeCompressionProcess(1),
        2: _FakeCompressionProcess(2),
    }

    def fake_stop_process(process: _FakeCompressionProcess) -> None:
        stopped.append(process.level)

    monkeypatch.setattr(image_compression, "_stop_process", fake_stop_process)
    results: dict[int, bytes | None] = {}

    image_compression._finish_after_budget(
        b"original-content",
        results,
        processes,
        _FakeCompressionQueue(waited=[(0, b"level0")]),
    )

    assert results == {0: b"level0"}
    assert stopped == [1, 2]
    assert level_zero.joined is True
    assert level_zero.join_timeouts == [image_compression._PROCESS_JOIN_TIMEOUT_SECONDS]
    assert processes == {}


def test_png_optimizer_stops_level_zero_when_budget_wait_expires(monkeypatch) -> None:
    stopped: list[int] = []
    level_zero = _FakeCompressionProcess(0, alive=True)
    processes = {0: level_zero}

    def fake_stop_process(process: _FakeCompressionProcess) -> None:
        stopped.append(process.level)
        process.alive = False

    monkeypatch.setattr(image_compression, "_stop_process", fake_stop_process)
    results: dict[int, bytes | None] = {}

    image_compression._finish_after_budget(
        b"original-content",
        results,
        processes,
        _FakeCompressionQueue(waited=[(0, b"level0")]),
    )

    assert results == {0: None}
    assert stopped == [0]
    assert level_zero.joined is True
    assert level_zero.join_timeouts == [image_compression._PROCESS_JOIN_TIMEOUT_SECONDS]
    assert processes == {}


def _png_bytes(*, compress_level: int) -> bytes:
    image = Image.new("RGBA", (64, 64), (214, 83, 63, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=compress_level)
    return buffer.getvalue()


def _rgba_bytes(content: bytes) -> bytes:
    with Image.open(io.BytesIO(content)) as image:
        return image.convert("RGBA").tobytes()


class _FakeCompressionProcess:
    def __init__(self, level: int, *, alive: bool = False) -> None:
        self.level = level
        self.alive = alive
        self.joined = False
        self.join_timeouts: list[float | None] = []

    def join(self, timeout: float | None = None) -> None:
        self.joined = True
        self.join_timeouts.append(timeout)

    def is_alive(self) -> bool:
        return self.alive


class _FakeCompressionQueue:
    def __init__(self, *, waited: list[tuple[int, bytes | None]]) -> None:
        self.waited = waited

    def get_nowait(self) -> tuple[int, bytes | None]:
        raise image_compression.queue.Empty

    def get(self, timeout: float | None = None) -> tuple[int, bytes | None]:
        if self.waited:
            return self.waited.pop(0)
        raise image_compression.queue.Empty
