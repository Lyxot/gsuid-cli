from __future__ import annotations

import os
import sqlite3
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from gsuid_cli.core.config import RuntimePaths, resolve_paths
from gsuid_cli.core.errors import EXIT_INTERNAL_BUG, CliError

SCHEMA_VERSION = 1


@contextmanager
def state_db(output_dir: str | None = None) -> Iterator[sqlite3.Connection]:
    paths = resolve_paths(output_dir)
    _ensure_storage(paths)
    conn = sqlite3.connect(paths.state)
    conn.row_factory = sqlite3.Row
    try:
        _migrate(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    return str(row["value"])


def set_setting(conn: sqlite3.Connection, key: str, value: str | None) -> None:
    if value is None:
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        return
    conn.execute(
        """
        INSERT INTO settings(key, value)
        VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def _ensure_storage(paths: RuntimePaths) -> None:
    for directory in (
        paths.home,
        paths.cache,
        paths.cache_http,
        paths.cache_resources,
        paths.artifacts,
        paths.logs,
    ):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        _chmod_if_supported(directory, 0o700)

    paths.state.touch(mode=0o600, exist_ok=True)
    _chmod_if_supported(paths.state, 0o600)


def _migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == SCHEMA_VERSION:
        return
    if version != 0:
        raise CliError(
            "STATE_SCHEMA_UNSUPPORTED",
            f"Unsupported state schema version: {version}",
            EXIT_INTERNAL_BUG,
            {"schema_version": version},
        )

    conn.executescript(
        """
        CREATE TABLE profiles (
            name TEXT PRIMARY KEY,
            default_uid TEXT,
            default_region TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE accounts (
            uid TEXT PRIMARY KEY,
            region TEXT NOT NULL,
            label TEXT,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        PRAGMA user_version = 1;
        """
    )


def _chmod_if_supported(path: Path, mode: int) -> None:
    if os.name == "nt":
        return
    current = stat.S_IMODE(path.stat().st_mode)
    if current != mode:
        path.chmod(mode)
