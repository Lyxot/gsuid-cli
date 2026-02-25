from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gsuid_cli.commands.account import _validate_uid
from gsuid_cli.core.errors import EXIT_AUTH, EXIT_INVALID_INPUT, CliError
from gsuid_cli.core.secrets import CREDENTIALS, SecretStore, env_secret, redact_secret

CAPABILITIES = [
    {
        "command": "auth.cookie.set",
        "description": "Store a cookie in the OS keyring.",
        "auth": "keyring",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "auth.cookie.test",
        "description": "Check local cookie availability without provider validation.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "auth.cookie.delete",
        "description": "Delete a stored cookie from the OS keyring.",
        "auth": "keyring",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "auth.stoken.set",
        "description": "Store a stoken in the OS keyring.",
        "auth": "keyring",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "auth.stoken.test",
        "description": "Check local stoken availability without provider validation.",
        "auth": "stoken",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "auth.stoken.delete",
        "description": "Delete a stored stoken from the OS keyring.",
        "auth": "keyring",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "auth.gacha-url.set",
        "description": "Store a gacha authkey URL in the OS keyring.",
        "auth": "keyring",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "auth.gacha-url.test",
        "description": "Check local gacha URL availability without provider validation.",
        "auth": "gacha_url",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "auth.gacha-url.delete",
        "description": "Delete a stored gacha authkey URL from the OS keyring.",
        "auth": "keyring",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
]


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    auth = groups.add_parser("auth", help="Manage local credentials.")
    credentials = auth.add_subparsers(dest="credential", required=True, metavar="<credential>")
    _register_credential(credentials, "cookie", "cookie")
    _register_credential(credentials, "stoken", "stoken")
    _register_credential(credentials, "gacha-url", "url")


def set_command(args: argparse.Namespace) -> dict[str, object]:
    uid = _uid(args)
    value = _read_value(args)
    store = SecretStore()
    store.set_secret(args.credential_kind, uid, value)
    return _credential_data(
        uid=uid,
        kind=args.credential_kind,
        source="keyring",
        storage_backend=store.backend_name(),
        validity_status="stored",
        value=value,
    )


def test_command(args: argparse.Namespace) -> dict[str, object]:
    uid = _uid(args)
    env_value = env_secret(args.credential_kind)
    if env_value:
        return _credential_data(
            uid=uid,
            kind=args.credential_kind,
            source="environment",
            storage_backend=None,
            validity_status="available",
            value=env_value,
        )

    store = SecretStore()
    value = store.get_secret(args.credential_kind, uid)
    if value is None:
        raise CliError(
            "AUTH_REQUIRED",
            f"No {CREDENTIALS[args.credential_kind].label} is available for this UID.",
            EXIT_AUTH,
            {"uid": uid, "credential_type": args.credential_kind},
        )
    return _credential_data(
        uid=uid,
        kind=args.credential_kind,
        source="keyring",
        storage_backend=store.backend_name(),
        validity_status="available",
        value=value,
    )


def delete_command(args: argparse.Namespace) -> dict[str, object]:
    uid = _uid(args)
    store = SecretStore()
    deleted = store.delete_secret(args.credential_kind, uid)
    return {
        "uid": uid,
        "credential_type": args.credential_kind,
        "storage_backend": store.backend_name(),
        "validity_status": "deleted" if deleted else "missing",
        "deleted": deleted,
    }


def _register_credential(
    credentials: argparse._SubParsersAction[argparse.ArgumentParser],
    cli_name: str,
    value_name: str,
) -> None:
    kind = cli_name.replace("-", "_")
    credential = credentials.add_parser(cli_name, help=f"Manage {cli_name} credentials.")
    actions = credential.add_subparsers(dest="credential_action", required=True, metavar="<action>")

    set_parser = actions.add_parser("set", help=f"Store a {cli_name} in the OS keyring.")
    set_parser.add_argument("--uid", dest="command_uid")
    sources = set_parser.add_mutually_exclusive_group(required=True)
    sources.add_argument(f"--{value_name}-stdin", action="store_true")
    sources.add_argument(f"--{value_name}-file")
    sources.add_argument(f"--{value_name}")
    set_parser.set_defaults(
        handler=set_command,
        command_name=f"auth.{cli_name}.set",
        credential_kind=kind,
        value_name=value_name,
    )

    test_parser = actions.add_parser("test", help=f"Check local {cli_name} availability.")
    test_parser.add_argument("--uid", dest="command_uid")
    test_parser.set_defaults(
        handler=test_command,
        command_name=f"auth.{cli_name}.test",
        credential_kind=kind,
    )

    delete_parser = actions.add_parser("delete", help=f"Delete a stored {cli_name}.")
    delete_parser.add_argument("--uid", dest="command_uid")
    delete_parser.set_defaults(
        handler=delete_command,
        command_name=f"auth.{cli_name}.delete",
        credential_kind=kind,
    )


def _uid(args: argparse.Namespace) -> str:
    command_uid = getattr(args, "command_uid", None)
    if command_uid:
        return _validate_uid(command_uid)
    if args.uid:
        return _validate_uid(args.uid)
    raise CliError("INVALID_ARGUMENT", "uid is required", EXIT_INVALID_INPUT)


def _read_value(args: argparse.Namespace) -> str:
    value_name = args.value_name
    inline_value = getattr(args, value_name)
    file_path = getattr(args, f"{value_name}_file")
    stdin_requested = getattr(args, f"{value_name}_stdin")

    if inline_value is not None:
        value = inline_value
    elif file_path:
        value = Path(file_path).read_text(encoding="utf-8")
    elif stdin_requested:
        value = sys.stdin.read()
    else:
        raise CliError("INVALID_ARGUMENT", "credential value is required", EXIT_INVALID_INPUT)

    value = value.rstrip("\r\n")
    if not value:
        raise CliError("INVALID_ARGUMENT", "credential value is empty", EXIT_INVALID_INPUT)
    return value


def _credential_data(
    *,
    uid: str,
    kind: str,
    source: str,
    storage_backend: str | None,
    validity_status: str,
    value: str,
) -> dict[str, object]:
    return {
        "uid": uid,
        "credential_type": kind,
        "source": source,
        "storage_backend": storage_backend,
        "validity_status": validity_status,
        "redacted": redact_secret(value),
    }
