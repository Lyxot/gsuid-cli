from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import ClassVar
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from filelock import FileLock

from gsuid_cli.core.config import resolve_paths
from gsuid_cli.core.errors import EXIT_CACHE, CliError

SECRET_QUERY_KEYS = {
    "authkey",
    "cookie",
    "login_ticket",
    "game_token",
    "stoken",
    "ticket",
    "token",
}


@dataclass(frozen=True)
class CachedResponse:
    payload: dict[str, object]
    fetched_at: str
    status_code: int


@dataclass(frozen=True)
class CachedAsset:
    content: bytes
    media_type: str
    path: Path
    metadata: dict[str, object]


class HttpCache:
    _items: ClassVar[dict[tuple[str, str], CachedResponse]] = {}
    _lock: ClassVar[threading.RLock] = threading.RLock()

    def __init__(self, output_dir: str | None = None) -> None:
        self._namespace = str(resolve_paths(output_dir).home)

    def get(self, key: str) -> CachedResponse | None:
        with self._lock:
            return self._items.get((self._namespace, key))

    def require(self, key: str) -> CachedResponse:
        cached = self.get(key)
        if cached is None:
            raise CliError(
                "CACHE_MISS",
                "No in-memory provider response is available for this request.",
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
        with self._lock:
            self._items[(self._namespace, key)] = CachedResponse(
                payload=payload,
                fetched_at=fetched_at,
                status_code=status_code,
            )


class AssetCache:
    def __init__(self, output_dir: str | None = None) -> None:
        self.path = resolve_paths(output_dir).cache_assets
        self.path.mkdir(mode=0o700, parents=True, exist_ok=True)

    @contextmanager
    def locked(self, key: str):
        lock = FileLock(str(self.path / f".{_short_hash(key)}.lock"))
        with lock:
            yield

    def get(self, key: str) -> CachedAsset | None:
        metadata = self.metadata(key)
        if metadata is None or metadata.get("status") != "ok":
            return None
        asset_path = self._safe_asset_path(metadata.get("path"))
        if asset_path is None or not asset_path.exists():
            return None
        media_type = str(metadata.get("media_type") or "application/octet-stream")
        return CachedAsset(
            content=asset_path.read_bytes(),
            media_type=media_type,
            path=asset_path,
            metadata=metadata,
        )

    def require(self, key: str, *, details: dict[str, object] | None = None) -> CachedAsset:
        cached = self.get(key)
        if cached is None:
            raise CliError(
                "CACHE_MISS",
                "No cached asset is available for this request.",
                EXIT_CACHE,
                details or {},
            )
        return cached

    def store_success(
        self,
        key: str,
        *,
        url: str,
        params: dict[str, object] | None,
        media_type: str,
        content: bytes,
        status_code: int,
        fetched_at: str,
    ) -> CachedAsset:
        previous = self.metadata(key) or {}
        asset_path = self.path / _asset_filename(url, key, media_type)
        metadata_path = self._metadata_path_for(asset_path, key)
        content_hash = hashlib.sha256(content).hexdigest()

        _atomic_write_bytes(asset_path, content)
        metadata: dict[str, object] = {
            "key": key,
            "url": sanitized_url(url, params=params),
            "original_filename": _original_filename(url),
            "path": str(asset_path),
            "media_type": media_type,
            "status_code": status_code,
            "status": "ok",
            "sha256": content_hash,
            "bytes": len(content),
            "fetched_at": fetched_at,
            "updated_at": fetched_at,
            "retry_count": int(previous.get("retry_count") or 0),
            "last_error": None,
        }
        _atomic_write_json(metadata_path, metadata)
        return CachedAsset(
            content=content, media_type=media_type, path=asset_path, metadata=metadata
        )

    def record_failure(
        self,
        key: str,
        *,
        url: str,
        params: dict[str, object] | None,
        error_code: str,
        message: str,
        attempted_at: str,
        status_code: int | None = None,
    ) -> None:
        previous = self.metadata(key) or {}
        retry_count = int(previous.get("retry_count") or 0) + 1
        last_error = {
            "code": error_code,
            "message": message,
            "status_code": status_code,
            "attempted_at": attempted_at,
        }
        previous_asset = self._safe_asset_path(previous.get("path"))
        if (
            previous.get("status") == "ok"
            and previous_asset is not None
            and previous_asset.exists()
        ):
            metadata = dict(previous)
            metadata["retry_count"] = retry_count
            metadata["last_error"] = last_error
            metadata["updated_at"] = attempted_at
            path = self._metadata_path_for(previous_asset, key)
        else:
            metadata = {
                "key": key,
                "url": sanitized_url(url, params=params),
                "original_filename": _original_filename(url),
                "path": None,
                "media_type": None,
                "status_code": status_code,
                "status": "failed",
                "sha256": None,
                "bytes": 0,
                "fetched_at": None,
                "updated_at": attempted_at,
                "retry_count": retry_count,
                "last_error": last_error,
            }
            path = (
                self.path
                / f"{_safe_stem(_original_filename(url))}.{_short_hash(key)}.metadata.json"
            )
        _atomic_write_json(path, metadata)

    def metadata(self, key: str) -> dict[str, object] | None:
        for metadata_path in self._metadata_paths(key):
            raw = _read_json_file(metadata_path)
            if isinstance(raw, dict) and raw.get("key") == key:
                return raw
        return None

    def clear(self) -> tuple[int, int]:
        removed_files = 0
        removed_dirs = 0
        removed_paths: set[Path] = set()
        for metadata_path in list(self.path.glob("*.metadata.json")):
            raw = _read_json_file(metadata_path)
            key = raw.get("key") if isinstance(raw, dict) else None
            if not isinstance(key, str):
                if self._unlink_untracked_cache_file(metadata_path):
                    removed_files += 1
                    removed_paths.add(metadata_path)
                continue
            with self.locked(key):
                metadata = self.metadata(key) or raw
                asset_path = self._safe_asset_path(metadata.get("path"))
                if asset_path is not None and _unlink_file(asset_path):
                    removed_files += 1
                    removed_paths.add(asset_path)
                for path in self._metadata_paths(key):
                    if _unlink_file(path):
                        removed_files += 1
                        removed_paths.add(path)

        for item in list(self.path.iterdir()):
            if item in removed_paths or item.name.startswith("."):
                continue
            if item.is_dir() and not item.is_symlink():
                removed_files += len([path for path in item.rglob("*") if path.is_file()])
                removed_dirs += len([path for path in item.rglob("*") if path.is_dir()]) + 1
                shutil.rmtree(item)
            elif self._unlink_untracked_cache_file(item):
                removed_files += 1
        return removed_files, removed_dirs

    def _metadata_paths(self, key: str) -> list[Path]:
        short = _short_hash(key)
        return [
            metadata_path
            for metadata_path in self.path.glob(f"*.{short}.metadata.json")
            if _metadata_key(metadata_path) == key
        ]

    def _metadata_path_for(self, asset_path: Path | None, key: str) -> Path:
        if asset_path is None:
            return self.path / f"asset.{_short_hash(key)}.metadata.json"
        return asset_path.with_name(f"{asset_path.stem}.metadata.json")

    def _safe_asset_path(self, value: object) -> Path | None:
        if not isinstance(value, str) or not value:
            return None
        path = Path(value)
        if not path.is_absolute():
            path = self.path / path.name
        if path.parent.resolve() != self.path.resolve():
            return None
        return path

    def _unlink_untracked_cache_file(self, path: Path) -> bool:
        short = _hash_from_cache_filename(path.name)
        if short:
            with FileLock(str(self.path / f".{short}.lock")):
                return _unlink_file(path)
        return _unlink_file(path)


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


def _read_json_file(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _metadata_key(path: Path) -> str | None:
    raw = _read_json_file(path)
    if isinstance(raw, dict) and isinstance(raw.get("key"), str):
        return str(raw["key"])
    return None


def _unlink_file(path: Path) -> bool:
    try:
        if path.exists() and (path.is_file() or path.is_symlink()):
            path.unlink()
            return True
    except FileNotFoundError:
        return False
    return False


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_bytes(content)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _asset_filename(url: str, key: str, media_type: str) -> str:
    original = _original_filename(url)
    suffix = _suffix(original) or _suffix_from_media_type(media_type)
    stem_source = Path(original).stem if _suffix(original) else original
    stem = _safe_stem(stem_source)
    return f"{stem}.{_short_hash(key)}{suffix}"


def _original_filename(url: str) -> str:
    name = PurePosixPath(unquote(urlsplit(url).path)).name
    return name or "asset"


def _safe_stem(value: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "_", value)
    safe = safe.strip("._-")
    return safe[:100] or "asset"


def _suffix(value: str) -> str:
    suffix = Path(value).suffix.lower()
    if re.fullmatch(r"\.[0-9a-z]{1,8}", suffix):
        return suffix
    return ""


def _suffix_from_media_type(media_type: str) -> str:
    if media_type == "image/jpeg":
        return ".jpg"
    if media_type == "image/png":
        return ".png"
    if media_type == "image/webp":
        return ".webp"
    if media_type == "image/gif":
        return ".gif"
    if media_type == "application/json":
        return ".json"
    return ".bin"


def _hash_from_cache_filename(name: str) -> str | None:
    parts = name.split(".")
    candidates = parts[:-2] if name.endswith(".metadata.json") else parts[:-1]
    if not candidates:
        return None
    value = candidates[-1]
    if re.fullmatch(r"[0-9a-f]{16}", value):
        return value
    return None


def _short_hash(key: str) -> str:
    return key[:16]
