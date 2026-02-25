from __future__ import annotations

import sqlite3

from gsuid_cli.core.errors import EXIT_INVALID_INPUT, CliError

CN_UID_PREFIXES = {"1", "2", "5"}
OS_UID_PREFIXES = {"6", "7", "8", "9"}


def infer_region(uid: str, requested_region: str | None = None) -> str:
    if requested_region:
        return requested_region
    if uid and uid[0] in OS_UID_PREFIXES:
        return "os"
    return "cn"


def ensure_supported_region(region: str) -> None:
    if region != "cn":
        raise CliError(
            "REGION_UNSUPPORTED",
            "Only CN provider support is implemented in the MVP.",
            EXIT_INVALID_INPUT,
            {"region": region},
        )


def resolve_profile_region(
    conn: sqlite3.Connection,
    *,
    profile_name: str,
    uid: str,
    requested_region: str | None,
) -> str:
    row = conn.execute("SELECT region FROM accounts WHERE uid = ?", (uid,)).fetchone()
    if row is not None:
        return str(row["region"])

    profile_row = conn.execute(
        "SELECT default_region FROM profiles WHERE name = ?",
        (profile_name,),
    ).fetchone()
    if profile_row is not None:
        return str(profile_row["default_region"])

    return infer_region(uid, requested_region)


def resolve_profile_uid(conn: sqlite3.Connection, profile_name: str) -> str | None:
    row = conn.execute(
        "SELECT default_uid FROM profiles WHERE name = ?",
        (profile_name,),
    ).fetchone()
    if row is None:
        return None
    return row["default_uid"]
