from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import qrcode
from qrcode.constants import ERROR_CORRECT_L

from gsuid_cli.commands.account import _validate_uid
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.errors import EXIT_AUTH, EXIT_INVALID_INPUT, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import resolve_profile_region, resolve_profile_uid
from gsuid_cli.core.secrets import CREDENTIALS, SecretStore, env_secret, redact_secret
from gsuid_cli.core.state import state_db
from gsuid_cli.providers import provider_for_region

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
        "description": "Validate cookie availability against the CN provider.",
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
    {
        "command": "auth.qrcode.start",
        "description": "Create a QR login session.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "both"],
        "cache": "off",
    },
    {
        "command": "auth.qrcode.poll",
        "description": "Poll a QR login session once.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "auth.qrcode.complete",
        "description": "Complete a confirmed QR login and store credentials.",
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
    _register_qrcode(credentials)


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
    uid, region = _uid_and_region(args)
    value, source, storage_backend = _credential(args, uid)
    if args.credential_kind == "cookie":
        http_client = HttpClient(
            timeout=args.timeout,
            cache_policy="off",
            output_dir=args.output_dir,
            debug=args.debug,
        )
        provider = provider_for_region(region, http_client)
        return provider.validate_cookie(
            uid=uid,
            cookie=value,
            region=region,
            credential_source=source,
            storage_backend=storage_backend,
        )

    return _credential_data(
        uid=uid,
        kind=args.credential_kind,
        source=source,
        storage_backend=storage_backend,
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


def qrcode_start_command(args: argparse.Namespace) -> CommandResult:
    provider = provider_for_region(args.region, _http_client(args))
    result = provider.create_qrcode_session(region=args.region)
    if args.render in {"image", "both"}:
        artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
            name="qrcode_login",
            filename="qrcode_login.png",
            media_type="image/png",
            content=_qrcode_png(str(result.data["url"])),
            description="QR login code for the MiHoYo app",
            kind="image",
        )
        return CommandResult(
            data=result.data,
            source=result.source,
            artifacts=[artifact],
            warnings=result.warnings,
        )
    return result


def qrcode_poll_command(args: argparse.Namespace) -> CommandResult:
    provider = provider_for_region(args.region, _http_client(args))
    return provider.poll_qrcode_session(
        app_id=args.app_id,
        ticket=args.ticket,
        device=args.device,
        region=args.region,
    )


def qrcode_complete_command(args: argparse.Namespace) -> CommandResult:
    uid = _validate_uid(args.command_uid)
    provider = provider_for_region(args.region, _http_client(args))
    result = provider.complete_qrcode_login(
        app_id=args.app_id,
        ticket=args.ticket,
        device=args.device,
        uid=uid,
        region=args.region,
    )
    cookie = str(result.data.pop("cookie"))
    stoken = str(result.data.pop("stoken"))

    store = SecretStore()
    store.set_secret("cookie", uid, cookie)
    store.set_secret("stoken", uid, stoken)

    data = {
        **result.data,
        "storage_backend": store.backend_name(),
        "stored": True,
    }
    return CommandResult(data=data, source=result.source, warnings=result.warnings)


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


def _register_qrcode(
    credentials: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    qrcode_parser = credentials.add_parser("qrcode", help="Manage QR login sessions.")
    actions = qrcode_parser.add_subparsers(
        dest="qrcode_action",
        required=True,
        metavar="<action>",
    )

    start = actions.add_parser("start", help="Create a QR login session.")
    start.set_defaults(handler=qrcode_start_command, command_name="auth.qrcode.start")

    poll = actions.add_parser("poll", help="Poll a QR login session once.")
    _add_qrcode_session_args(poll)
    poll.set_defaults(handler=qrcode_poll_command, command_name="auth.qrcode.poll")

    complete = actions.add_parser("complete", help="Complete a confirmed QR login.")
    _add_qrcode_session_args(complete)
    complete.add_argument("--uid", required=True, dest="command_uid")
    complete.set_defaults(handler=qrcode_complete_command, command_name="auth.qrcode.complete")


def _add_qrcode_session_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--app-id", default="2")
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--device", required=True)


def _uid(args: argparse.Namespace) -> str:
    uid, _region = _uid_and_region(args)
    return uid


def _uid_and_region(args: argparse.Namespace) -> tuple[str, str]:
    command_uid = getattr(args, "command_uid", None)
    if command_uid:
        uid = _validate_uid(command_uid)
    elif args.uid:
        uid = _validate_uid(args.uid)
    else:
        with state_db(args.output_dir) as conn:
            uid = resolve_profile_uid(conn, args.profile)
            if uid is None:
                raise CliError(
                    "INVALID_ARGUMENT",
                    "uid is required when the selected profile has no default account",
                    EXIT_INVALID_INPUT,
                    {"profile": args.profile},
                )
            region = resolve_profile_region(
                conn,
                profile_name=args.profile,
                uid=uid,
                requested_region=args.region,
            )
            return uid, region

    with state_db(args.output_dir) as conn:
        region = resolve_profile_region(
            conn,
            profile_name=args.profile,
            uid=uid,
            requested_region=args.region,
        )
    return uid, region


def _credential(args: argparse.Namespace, uid: str) -> tuple[str, str, str | None]:
    env_value = env_secret(args.credential_kind)
    if env_value:
        return env_value, "environment", None

    store = SecretStore()
    value = store.get_secret(args.credential_kind, uid)
    if value is None:
        raise CliError(
            "AUTH_REQUIRED",
            f"No {CREDENTIALS[args.credential_kind].label} is available for this UID.",
            EXIT_AUTH,
            {"uid": uid, "credential_type": args.credential_kind},
        )
    return value, "keyring", store.backend_name()


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


def _http_client(args: argparse.Namespace) -> HttpClient:
    return HttpClient(
        timeout=args.timeout,
        cache_policy="off",
        output_dir=args.output_dir,
        debug=args.debug,
    )


def _qrcode_png(url: str) -> bytes:
    qr = qrcode.QRCode(
        version=1,
        error_correction=ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color=(255, 134, 36), back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
