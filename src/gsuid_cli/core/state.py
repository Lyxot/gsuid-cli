from __future__ import annotations

import os
import sqlite3
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from gsuid_cli.core.config import RuntimePaths, resolve_paths
from gsuid_cli.core.errors import EXIT_INTERNAL_BUG, CliError

SCHEMA_VERSION = 3


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
    if version not in {0, 1, 2}:
        raise CliError(
            "STATE_SCHEMA_UNSUPPORTED",
            f"Unsupported state schema version: {version}",
            EXIT_INTERNAL_BUG,
            {"schema_version": version},
        )

    if version == 0:
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
            """
        )

    if version < 2:
        _migrate_gacha(conn)
    if version < 3:
        _migrate_panels(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _migrate_gacha(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS gacha_items (
            uid TEXT NOT NULL,
            id TEXT NOT NULL,
            gacha_type TEXT NOT NULL,
            uigf_gacha_type TEXT,
            item_id TEXT,
            count INTEGER NOT NULL DEFAULT 1,
            time TEXT NOT NULL,
            name TEXT NOT NULL,
            lang TEXT,
            item_type TEXT,
            rank_type TEXT,
            imported_at TEXT NOT NULL,
            PRIMARY KEY(uid, id)
        );

        CREATE INDEX IF NOT EXISTS idx_gacha_items_uid_time
        ON gacha_items(uid, time);

        CREATE INDEX IF NOT EXISTS idx_gacha_items_uid_gacha_type
        ON gacha_items(uid, gacha_type);

        CREATE TABLE IF NOT EXISTS gacha_sync (
            uid TEXT NOT NULL,
            gacha_type TEXT NOT NULL,
            last_id TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(uid, gacha_type)
        );
        """
    )


def _migrate_panels(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS panel_cache (
            uid TEXT PRIMARY KEY,
            source_provider TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            ttl INTEGER,
            player_info_json TEXT NOT NULL,
            avatar_info_json TEXT NOT NULL,
            raw_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_panel_cache_fetched_at
        ON panel_cache(fetched_at);
        """
    )


def _chmod_if_supported(path: Path, mode: int) -> None:
    if os.name == "nt":
        return
    current = stat.S_IMODE(path.stat().st_mode)
    if current != mode:
        path.chmod(mode)
