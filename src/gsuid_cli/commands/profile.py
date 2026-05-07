from __future__ import annotations

import argparse
import sqlite3

from gsuid_cli.commands._text import command_text_result, safe_filename_part
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, EXIT_NO_RESULT, CliError
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.state import get_setting, set_setting, state_db
from gsuid_cli.core.time import utc_now
from gsuid_cli.renderers.local_auth import render_profile_command_text

CAPABILITIES = [
    {
        "command": "profile.init",
        "description": "Create or update a local profile.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "profile.list",
        "description": "List local profiles.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "profile.show",
        "description": "Show one local profile.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "profile.default",
        "description": "Set the default local profile.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "profile.delete",
        "description": "Delete a local profile.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
]


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    profile = groups.add_parser("profile", help="Manage local profiles.")
    commands = profile.add_subparsers(dest="profile_command", required=True, metavar="<command>")

    init = commands.add_parser("init", help="Create or update a profile.")
    init.add_argument("--name")
    init.add_argument("--region", choices=("cn", "os"), dest="profile_region")
    init.set_defaults(handler=init_command, command_name="profile.init")

    list_parser = commands.add_parser("list", help="List profiles.")
    list_parser.set_defaults(handler=list_command, command_name="profile.list")

    show = commands.add_parser("show", help="Show a profile.")
    show.add_argument("--name")
    show.set_defaults(handler=show_command, command_name="profile.show")

    default = commands.add_parser("default", help="Set the default profile.")
    default.add_argument("--name")
    default.set_defaults(handler=default_command, command_name="profile.default")

    delete = commands.add_parser("delete", help="Delete a profile.")
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
        raise CliError("INVALID_ARGUMENT", "profile name is required", EXIT_INVALID_INPUT)
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
            f"Profile not found: {name}",
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
    command = str(args.command_name)
    action = command.rsplit(".", 1)[-1]
    profile_data = data.get("profile")
    subject = "list"
    if isinstance(profile_data, dict):
        subject = str(profile_data.get("name") or subject)
    return command_text_result(
        args,
        data,
        name=f"profile/{action}-text",
        filename=f"profile-{action}_{safe_filename_part(subject)}.txt",
        content=render_profile_command_text(command, data),
        description="Human-readable local profile text",
    )
