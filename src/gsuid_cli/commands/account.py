from __future__ import annotations

import argparse
import sqlite3

from gsuid_cli.commands import profile
from gsuid_cli.commands._text import command_subject_text_result, helps_from
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, EXIT_NO_RESULT, CliError
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import REGION_CHOICES, infer_region
from gsuid_cli.core.secrets import CREDENTIALS, SecretStore, credential_presence
from gsuid_cli.core.state import state_db
from gsuid_cli.core.time import utc_now
from gsuid_cli.renderers.local_auth import render_account_command_text
from gsuid_cli.text import t as _t

CAPABILITIES = [
    {
        "command": "account.add",
        "description": _t("gsuid.commands.account.19_23.d52dfaa1"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "account.list",
        "description": _t("gsuid.commands.account.26_23.de61fc2a"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "account.show",
        "description": _t("gsuid.commands.account.33_23.5acecf00"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "account.default",
        "description": _t("gsuid.commands.account.40_23.8faddb9e"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "account.remove",
        "description": _t("gsuid.commands.account.47_23.9a22d2a6"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
]

_HELPS = helps_from(CAPABILITIES)


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    account = groups.add_parser("account", help=_t("gsuid.commands.account.58_48.fa5f633d"))
    commands = account.add_subparsers(dest="account_command", required=True, metavar="<command>")

    add = commands.add_parser("add", help=_HELPS["account.add"])
    add.add_argument("--uid", dest="account_uid")
    add.add_argument("--region", choices=tuple(sorted(REGION_CHOICES)), dest="account_region")
    add.add_argument("--label")
    add.add_argument("--default", action="store_true")
    add.set_defaults(handler=add_command, command_name="account.add")

    list_parser = commands.add_parser("list", help=_HELPS["account.list"])
    list_parser.set_defaults(handler=list_command, command_name="account.list")

    show = commands.add_parser("show", help=_HELPS["account.show"])
    show.add_argument("--uid", dest="account_uid")
    show.set_defaults(handler=show_command, command_name="account.show")

    default = commands.add_parser("default", help=_HELPS["account.default"])
    default.add_argument("--uid", dest="account_uid")
    default.set_defaults(handler=default_command, command_name="account.default")

    remove = commands.add_parser("remove", help=_HELPS["account.remove"])
    remove.add_argument("--uid", dest="account_uid")
    remove.set_defaults(handler=remove_command, command_name="account.remove")


def add_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    uid = _required_uid(args)
    region = infer_region(uid, args.account_region or args.region)
    with state_db(args.output_dir) as conn:
        created = _upsert_account(conn, uid, region, args.label)
        if args.default:
            _set_default(conn, args.profile, uid, region)
        row = _get_account(conn, uid)
        data = {"account": _serialize_account(row), "created": created}
        return _account_text_result(args, data)


def list_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    with state_db(args.output_dir) as conn:
        rows = conn.execute("SELECT * FROM accounts ORDER BY uid").fetchall()
        data = {"accounts": [_serialize_account(row) for row in rows]}
        return _account_text_result(args, data)


def show_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    with state_db(args.output_dir) as conn:
        uid = _resolve_uid(conn, args)
        data = {"account": _serialize_account(_get_account(conn, uid))}
        return _account_text_result(args, data)


def default_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    uid = _required_uid(args)
    with state_db(args.output_dir) as conn:
        row = _get_account(conn, uid)
        _set_default(conn, args.profile, uid, row["region"])
        data = {"account": _serialize_account(_get_account(conn, uid))}
        return _account_text_result(args, data)


def remove_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    uid = _required_uid(args)
    with state_db(args.output_dir) as conn:
        row = _get_account(conn, uid)
        data = _serialize_account(row)
        conn.execute("DELETE FROM accounts WHERE uid = ?", (uid,))
        conn.execute("UPDATE profiles SET default_uid = NULL WHERE default_uid = ?", (uid,))

    store = SecretStore()
    for kind in CREDENTIALS:
        try:
            store.delete_secret(kind, uid)
        except CliError:
            pass
    return _account_text_result(args, {"account": data, "deleted": True})


def _upsert_account(
    conn: sqlite3.Connection,
    uid: str,
    region: str,
    label: str | None,
) -> bool:
    now = utc_now()
    existing = _find_account(conn, uid)
    if existing is None:
        conn.execute(
            """
            INSERT INTO accounts(uid, region, label, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            (uid, region, label, now, now),
        )
        return True

    conn.execute(
        "UPDATE accounts SET region = ?, label = ?, updated_at = ? WHERE uid = ?",
        (region, label, now, uid),
    )
    return False


def _set_default(conn: sqlite3.Connection, profile_name: str, uid: str, region: str) -> None:
    profile.ensure_profile(conn, profile_name, region)
    conn.execute("UPDATE accounts SET is_default = 0")
    conn.execute("UPDATE accounts SET is_default = 1 WHERE uid = ?", (uid,))
    profile.set_profile_default_uid(conn, profile_name, uid)


def _resolve_uid(conn: sqlite3.Connection, args: argparse.Namespace) -> str:
    command_uid = getattr(args, "account_uid", None)
    if command_uid:
        return _validate_uid(command_uid)
    if args.uid:
        return _validate_uid(args.uid)
    uid = profile.get_profile_default_uid(conn, args.profile)
    if uid:
        return uid
    raise CliError(
        "INVALID_ARGUMENT",
        "uid is required when the selected profile has no default account",
        EXIT_INVALID_INPUT,
        {"profile": args.profile},
    )


def _required_uid(args: argparse.Namespace) -> str:
    command_uid = getattr(args, "account_uid", None)
    uid = command_uid or args.uid
    if uid:
        return _validate_uid(uid)
    raise CliError("INVALID_ARGUMENT", "uid is required", EXIT_INVALID_INPUT)


def _validate_uid(uid: str) -> str:
    if not uid or not uid.isdigit():
        raise CliError(
            "INVALID_ARGUMENT",
            "uid must contain digits only",
            EXIT_INVALID_INPUT,
            {"uid": uid},
        )
    return uid


def _find_account(conn: sqlite3.Connection, uid: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM accounts WHERE uid = ?", (uid,)).fetchone()


def _get_account(conn: sqlite3.Connection, uid: str) -> sqlite3.Row:
    row = _find_account(conn, uid)
    if row is None:
        raise CliError(
            "NO_RESULT",
            _t("gsuid.commands.account.213_12.ed40a8f5", uid),
            EXIT_NO_RESULT,
            {"uid": uid},
        )
    return row


def _serialize_account(row: sqlite3.Row) -> dict[str, object]:
    credentials = credential_presence(row["uid"])
    return {
        "uid": row["uid"],
        "region": row["region"],
        "label": row["label"],
        "default": bool(row["is_default"]),
        "has_cookie": credentials["cookie"],
        "has_stoken": credentials["stoken"],
        "has_gacha_url": credentials["gacha_url"],
        "has_device": bool(row["device_id"] and row["device_fp"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _account_text_result(
    args: argparse.Namespace,
    data: dict[str, object],
) -> CommandResult | dict[str, object]:
    account_data = data.get("account")
    subject = str(account_data.get("uid") or "list") if isinstance(account_data, dict) else "list"
    return command_subject_text_result(
        args,
        data,
        subject=subject,
        render_fn=render_account_command_text,
        description=_t("gsuid.commands.account.247_20.f723a7a4"),
    )
