from __future__ import annotations

import multiprocessing
import queue
from collections.abc import Sequence
from time import monotonic
from typing import Any

PNG_MEDIA_TYPE = "image/png"
PNG_LARGE_IMAGE_THRESHOLD_BYTES = 1024 * 1024
PNG_COMPRESSION_TIMEOUT_SECONDS = 0.9
_SMALL_PNG_LEVELS = (0, 1, 2)
_LARGE_PNG_LEVELS = (0,)
_PROCESS_JOIN_TIMEOUT_SECONDS = 0.05


def optimize_png_artifact(
    content: bytes,
    *,
    media_type: str,
    enabled: bool = True,
) -> bytes:
    if not enabled or _base_media_type(media_type) != PNG_MEDIA_TYPE:
        return content

    results = _optimize_png_levels(
        content,
        _compression_levels(len(content)),
        PNG_COMPRESSION_TIMEOUT_SECONDS,
    )
    optimized = _best_completed_optimization(content, results)
    if optimized is None:
        return content
    return optimized


def _compression_levels(content_size: int) -> tuple[int, ...]:
    if content_size >= PNG_LARGE_IMAGE_THRESHOLD_BYTES:
        return _LARGE_PNG_LEVELS
    return _SMALL_PNG_LEVELS


def _best_completed_optimization(
    original: bytes,
    results: dict[int, bytes | None],
) -> bytes | None:
    for level in sorted(results, reverse=True):
        content = results[level]
        if content is not None and len(content) < len(original):
            return content
    return None


def _optimize_png_levels(
    content: bytes,
    levels: Sequence[int],
    timeout_seconds: float,
) -> dict[int, bytes | None]:
    if not levels or timeout_seconds <= 0:
        return {}

    context = _multiprocessing_context()
    result_queue = context.Queue()
    processes: dict[int, Any] = {}
    for level in levels:
        process = context.Process(
            target=_optimize_png_level_worker,
            args=(content, level, result_queue),
        )
        process.daemon = True
        try:
            process.start()
        except Exception:
            continue
        processes[level] = process
    if not processes:
        result_queue.close()
        result_queue.join_thread()
        return {}

    deadline = monotonic() + timeout_seconds
    results: dict[int, bytes | None] = {}
    try:
        while processes:
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            try:
                level, optimized = result_queue.get(timeout=remaining)
            except queue.Empty:
                break
            results[int(level)] = optimized
            process = processes.pop(int(level), None)
            if process is not None:
                _stop_process(process)
        _finish_after_budget(content, results, processes, result_queue)
    finally:
        for process in processes.values():
            _stop_process(process)
        result_queue.close()
        result_queue.join_thread()

    return results


def _finish_after_budget(
    content: bytes,
    results: dict[int, bytes | None],
    processes: dict[int, Any],
    result_queue: Any,
) -> None:
    _drain_ready_results(results, processes, result_queue)
    if _best_completed_optimization(content, results) is not None or 0 not in processes:
        return

    level_zero_process = processes.pop(0)
    for level, process in list(processes.items()):
        _stop_process(process)
        del processes[level]
    results[0] = _wait_for_process_result(
        0,
        level_zero_process,
        result_queue,
        _PROCESS_JOIN_TIMEOUT_SECONDS,
    )


def _drain_ready_results(
    results: dict[int, bytes | None],
    processes: dict[int, Any],
    result_queue: Any,
) -> None:
    while True:
        try:
            level, optimized = result_queue.get_nowait()
        except queue.Empty:
            return
        results[int(level)] = optimized
        process = processes.pop(int(level), None)
        if process is not None:
            _stop_process(process)


def _wait_for_process_result(
    level: int,
    process: Any,
    result_queue: Any,
    timeout_seconds: float,
) -> bytes | None:
    process.join(timeout=timeout_seconds)
    if process.is_alive():
        _stop_process(process)
        return None
    while True:
        try:
            result_level, optimized = result_queue.get(timeout=_PROCESS_JOIN_TIMEOUT_SECONDS)
        except queue.Empty:
            return None
        if int(result_level) == level:
            return optimized


def _optimize_png_level_worker(content: bytes, level: int, result_queue: Any) -> None:
    try:
        optimized = _optimize_png_level(content, level)
    except Exception:
        optimized = None
    result_queue.put((level, optimized))


def _optimize_png_level(content: bytes, level: int) -> bytes:
    import oxipng

    return oxipng.optimize_from_memory(
        content,
        level=level,
        strip=oxipng.StripChunks.safe(),
    )


def _stop_process(process: Any) -> None:
    if process.is_alive():
        process.terminate()
    process.join(timeout=_PROCESS_JOIN_TIMEOUT_SECONDS)
    if process.is_alive() and hasattr(process, "kill"):
        process.kill()
        process.join(timeout=_PROCESS_JOIN_TIMEOUT_SECONDS)


def _multiprocessing_context() -> Any:
    if "fork" in multiprocessing.get_all_start_methods():
        return multiprocessing.get_context("fork")
    return multiprocessing.get_context()


def _base_media_type(media_type: str) -> str:
    return media_type.split(";", 1)[0].strip().lower()
