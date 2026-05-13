from __future__ import annotations

import argparse
import sqlite3

from gsuid_cli.commands._text import command_subject_text_result, helps_from
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, EXIT_NO_RESULT, CliError
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import REGION_CHOICES
from gsuid_cli.core.state import get_setting, set_setting, state_db
from gsuid_cli.core.time import utc_now
from gsuid_cli.renderers.local_auth import render_profile_command_text
from gsuid_cli.text import t as _t

CAPABILITIES = [
    {
        "command": "profile.init",
        "description": _t("gsuid.commands.profile.17_23.363597de"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "profile.list",
        "description": _t("gsuid.commands.profile.24_23.d0d1c3c1"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "profile.show",
        "description": _t("gsuid.commands.profile.31_23.0f421177"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "profile.default",
        "description": _t("gsuid.commands.profile.38_23.27195bec"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "profile.delete",
        "description": _t("gsuid.commands.profile.45_23.664fb86e"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
]

_HELPS = helps_from(CAPABILITIES)


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    profile = groups.add_parser("profile", help=_t("gsuid.commands.profile.56_48.d897383e"))
    commands = profile.add_subparsers(dest="profile_command", required=True, metavar="<command>")

    init = commands.add_parser("init", help=_HELPS["profile.init"])
    init.add_argument("--name")
    init.add_argument("--region", choices=tuple(sorted(REGION_CHOICES)), dest="profile_region")
    init.set_defaults(handler=init_command, command_name="profile.init")

    list_parser = commands.add_parser("list", help=_HELPS["profile.list"])
    list_parser.set_defaults(handler=list_command, command_name="profile.list")

    show = commands.add_parser("show", help=_HELPS["profile.show"])
    show.add_argument("--name")
    show.set_defaults(handler=show_command, command_name="profile.show")

    default = commands.add_parser("default", help=_HELPS["profile.default"])
    default.add_argument("--name")
    default.set_defaults(handler=default_command, command_name="profile.default")

    delete = commands.add_parser("delete", help=_HELPS["profile.delete"])
    delete.add_argument("--name", required=True)
    delete.set_defaults(handler=delete_command, command_name="profile.delete")


def init_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    name = _profile_name(args)
    region = args.profile_region or args.region
    with state_db(args.output_dir) as conn:
        created = _upsert_profile(conn, name, region)
        if get_setting(conn, "default_profile") is None:
            set_setting(conn, "default_profile", name)
        row = _get_profile(conn, name)
        data = {"profile": _serialize_profile(conn, row), "created": created}
        return _profile_text_result(args, data)


def list_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    with state_db(args.output_dir) as conn:
        rows = conn.execute("SELECT * FROM profiles ORDER BY name").fetchall()
        data = {"profiles": [_serialize_profile(conn, row) for row in rows]}
        return _profile_text_result(args, data)


def show_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    name = _profile_name(args)
    with state_db(args.output_dir) as conn:
        row = _get_profile(conn, name)
        data = {"profile": _serialize_profile(conn, row)}
        return _profile_text_result(args, data)


def default_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    name = _profile_name(args)
    with state_db(args.output_dir) as conn:
        row = _get_profile(conn, name)
        set_setting(conn, "default_profile", name)
        data = {"profile": _serialize_profile(conn, row)}
        return _profile_text_result(args, data)


def delete_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    with state_db(args.output_dir) as conn:
        row = _get_profile(conn, args.name)
        conn.execute("DELETE FROM profiles WHERE name = ?", (args.name,))
        if get_setting(conn, "default_profile") == args.name:
            set_setting(conn, "default_profile", None)
        data = {"profile": _serialize_profile(conn, row), "deleted": True}
        return _profile_text_result(args, data)


def ensure_profile(conn: sqlite3.Connection, name: str, region: str) -> None:
    if _find_profile(conn, name) is None:
        _upsert_profile(conn, name, region)


def set_profile_default_uid(conn: sqlite3.Connection, name: str, uid: str | None) -> None:
    now = utc_now()
    conn.execute(
        "UPDATE profiles SET default_uid = ?, updated_at = ? WHERE name = ?",
        (uid, now, name),
    )


def get_profile_default_uid(conn: sqlite3.Connection, name: str) -> str | None:
    row = _find_profile(conn, name)
    if row is None:
        return None
    return row["default_uid"]


def _profile_name(args: argparse.Namespace) -> str:
    name = getattr(args, "name", None) or args.profile
    if not name:
        raise CliError(
            "INVALID_ARGUMENT", _t("gsuid.commands.profile.149_43.57758001"), EXIT_INVALID_INPUT
        )
    return name


def _upsert_profile(conn: sqlite3.Connection, name: str, region: str) -> bool:
    now = utc_now()
    existing = _find_profile(conn, name)
    if existing is None:
        conn.execute(
            """
            INSERT INTO profiles(name, default_region, created_at, updated_at)
            VALUES(?, ?, ?, ?)
            """,
            (name, region, now, now),
        )
        return True

    conn.execute(
        "UPDATE profiles SET default_region = ?, updated_at = ? WHERE name = ?",
        (region, now, name),
    )
    return False


def _find_profile(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM profiles WHERE name = ?", (name,)).fetchone()


def _get_profile(conn: sqlite3.Connection, name: str) -> sqlite3.Row:
    row = _find_profile(conn, name)
    if row is None:
        raise CliError(
            "NO_RESULT",
            _t("gsuid.commands.profile.182_12.adce1f5a", name),
            EXIT_NO_RESULT,
            {"profile": name},
        )
    return row


def _serialize_profile(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, object]:
    account_count = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    return {
        "name": row["name"],
        "default_uid": row["default_uid"],
        "default_region": row["default_region"],
        "account_count": account_count,
        "default": get_setting(conn, "default_profile") == row["name"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _profile_text_result(
    args: argparse.Namespace,
    data: dict[str, object],
) -> CommandResult | dict[str, object]:
    profile_data = data.get("profile")
    subject = str(profile_data.get("name") or "list") if isinstance(profile_data, dict) else "list"
    return command_subject_text_result(
        args,
        data,
        subject=subject,
        render_fn=render_profile_command_text,
        description=_t("gsuid.commands.profile.213_20.f682168c"),
    )
