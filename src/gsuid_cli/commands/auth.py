from __future__ import annotations

import argparse
import io
import json
import shlex
import sys
import time
from pathlib import Path

import qrcode
from qrcode.constants import ERROR_CORRECT_L

from gsuid_cli.commands._text import command_text_result, safe_filename_part
from gsuid_cli.commands.account import _validate_uid
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.errors import EXIT_AUTH, EXIT_INVALID_INPUT, EXIT_NO_RESULT, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import resolve_profile_region, resolve_profile_uid
from gsuid_cli.core.render import render_image_enabled, render_result_data, render_text_enabled
from gsuid_cli.core.secrets import CREDENTIALS, SecretStore, env_secret, redact_secret
from gsuid_cli.core.state import state_db
from gsuid_cli.core.time import utc_now
from gsuid_cli.providers import provider_for_region
from gsuid_cli.renderers.local_auth import render_auth_command_text

CAPABILITIES = [
    {
        "command": "auth.cookie.set",
        "description": "Store a cookie in the OS keyring.",
        "auth": "keyring",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "auth.cookie.test",
        "description": "Validate cookie availability against the CN provider.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "auth.cookie.delete",
        "description": "Delete a stored cookie from the OS keyring.",
        "auth": "keyring",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "auth.stoken.set",
        "description": "Store a stoken in the OS keyring.",
        "auth": "keyring",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "auth.stoken.test",
        "description": "Check local stoken availability without provider validation.",
        "auth": "stoken",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "auth.stoken.delete",
        "description": "Delete a stored stoken from the OS keyring.",
        "auth": "keyring",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "auth.gacha-url.set",
        "description": "Store a gacha authkey URL in the OS keyring.",
        "auth": "keyring",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "auth.gacha-url.test",
        "description": "Check local gacha URL availability without provider validation.",
        "auth": "gacha_url",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "auth.gacha-url.delete",
        "description": "Delete a stored gacha authkey URL from the OS keyring.",
        "auth": "keyring",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "auth.qrcode.start",
        "description": "Create a QR login session.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "auth.qrcode.poll",
        "description": "Poll a QR login session once.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "auth.qrcode.complete",
        "description": "Complete a confirmed QR login and store credentials.",
        "auth": "keyring",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "auth.qrcode.login",
        "description": "Run interactive QR login and store credentials.",
        "auth": "keyring",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "auth.device.set",
        "description": "Bind and store MYS device metadata for account requests.",
        "auth": "cookie",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "auth.device.test",
        "description": "Check local MYS device metadata availability.",
        "auth": "device",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "auth.device.delete",
        "description": "Delete local MYS device metadata.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
]


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    auth = groups.add_parser("auth", help="Manage local credentials.")
    credentials = auth.add_subparsers(dest="credential", required=True, metavar="<credential>")
    _register_credential(credentials, "cookie", "cookie")
    _register_credential(credentials, "stoken", "stoken")
    _register_credential(credentials, "gacha-url", "url")
    _register_qrcode(credentials)
    _register_device(credentials)


def set_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    uid = _uid(args)
    value = _read_value(args)
    store = SecretStore()
    store.set_secret(args.credential_kind, uid, value)
    data = _credential_data(
        uid=uid,
        kind=args.credential_kind,
        source="keyring",
        storage_backend=store.backend_name(),
        validity_status="stored",
        value=value,
    )
    return _auth_text_result(args, data)


def test_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
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
        result = provider.validate_cookie(
            uid=uid,
            cookie=value,
            region=region,
            credential_source=source,
            storage_backend=storage_backend,
        )
        return _auth_text_result(args, result)

    data = _credential_data(
        uid=uid,
        kind=args.credential_kind,
        source=source,
        storage_backend=storage_backend,
        validity_status="available",
        value=value,
    )
    return _auth_text_result(args, data)


def delete_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    uid = _uid(args)
    store = SecretStore()
    deleted = store.delete_secret(args.credential_kind, uid)
    data = {
        "uid": uid,
        "credential_type": args.credential_kind,
        "storage_backend": store.backend_name(),
        "validity_status": "deleted" if deleted else "missing",
        "deleted": deleted,
    }
    return _auth_text_result(args, data)


def qrcode_start_command(args: argparse.Namespace) -> CommandResult:
    provider = provider_for_region(args.region, _http_client(args))
    result = provider.create_qrcode_session(region=args.region)
    return _qrcode_render_result(args, result, url=str(result.data["url"]))


def qrcode_poll_command(args: argparse.Namespace) -> CommandResult:
    provider = provider_for_region(args.region, _http_client(args))
    return _auth_text_result(
        args,
        provider.poll_qrcode_session(
            app_id=args.app_id,
            ticket=args.ticket,
            device=args.device,
            region=args.region,
        ),
    )


def qrcode_complete_command(args: argparse.Namespace) -> CommandResult:
    uid = _uid(args)
    provider = provider_for_region(args.region, _http_client(args))
    result = provider.complete_qrcode_login(
        app_id=args.app_id,
        ticket=args.ticket,
        device=args.device,
        uid=uid,
        region=args.region,
    )
    return _auth_text_result(args, _store_qrcode_credentials(uid, result))


def qrcode_login_command(args: argparse.Namespace) -> CommandResult:
    uid = _uid(args)
    _validate_qrcode_login_timing(args)
    provider = provider_for_region(args.region, _http_client(args))
    session = provider.create_qrcode_session(region=args.region)
    app_id = str(session.data["app_id"])
    ticket = str(session.data["ticket"])
    device = str(session.data["device"])
    url = str(session.data["url"])
    image_artifact = None
    if render_image_enabled(args):
        image_artifact = _qrcode_image_artifact(
            args,
            command="auth.qrcode.login",
            url=url,
            subject=uid,
        )
        _write_interactive(args, f"二维码图片已保存至: {image_artifact['path']}", force=True)

    _write_interactive(args, "请使用米游社APP扫码登录")
    _write_interactive(args, _qrcode_terminal(url))
    _write_interactive(args, "Waiting for scan confirmation...")

    deadline = time.monotonic() + args.login_timeout
    last_status: str | None = None
    last_result = session

    while time.monotonic() < deadline:
        poll_result = provider.poll_qrcode_session(
            app_id=app_id,
            ticket=ticket,
            device=device,
            region=args.region,
        )
        last_result = poll_result
        status = str(poll_result.data["status"])
        if status != last_status:
            _write_interactive(args, f"QR login status: {status}")
            last_status = status
        if status == "confirmed":
            result = provider.complete_qrcode_login(
                app_id=app_id,
                ticket=ticket,
                device=device,
                uid=uid,
                region=args.region,
            )
            return _qrcode_render_result(
                args,
                _store_qrcode_credentials(uid, result),
                url=url,
                image_artifact=image_artifact,
            )
        time.sleep(args.poll_interval)

    raise CliError(
        "QR_LOGIN_TIMEOUT",
        "QR login timed out before confirmation.",
        EXIT_NO_RESULT,
        {"timeout_seconds": args.login_timeout},
        source=last_result.source,
    )


def device_set_command(args: argparse.Namespace) -> CommandResult:
    uid, region = _uid_and_region(args)
    cookie, credential_source, storage_backend = _credential(args, uid)
    provider = provider_for_region(region, _http_client(args))
    result = provider.device_login(
        uid=uid,
        cookie=cookie,
        region=region,
        credential_source=credential_source,
        storage_backend=storage_backend,
        device_payload=_read_device_payload(args),
    )
    return _auth_text_result(args, _store_device_binding(args, uid, region, result))


def device_test_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    uid, _region = _uid_and_region(args)
    with state_db(args.output_dir) as conn:
        row = conn.execute(
            """
            SELECT device_id, device_fp, device_info, device_updated_at
            FROM accounts
            WHERE uid = ?
            """,
            (uid,),
        ).fetchone()
    if row is None or not row["device_id"] or not row["device_fp"]:
        raise CliError(
            "AUTH_REQUIRED",
            "No MYS device metadata is available for this UID.",
            EXIT_AUTH,
            {"uid": uid, "credential_type": "device"},
        )
    device = {
        "device_id": str(row["device_id"]),
        "device_fp": str(row["device_fp"]),
        "device_info": str(row["device_info"] or "Unknown/Unknown/Unknown/Unknown"),
    }
    data = {
        **_device_result_data(uid=uid, status="available", device=device),
        "updated_at": row["device_updated_at"],
    }
    return _auth_text_result(args, data)


def device_delete_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    uid = _uid(args)
    with state_db(args.output_dir) as conn:
        row = conn.execute(
            "SELECT device_id, device_fp, device_info FROM accounts WHERE uid = ?",
            (uid,),
        ).fetchone()
        deleted = bool(row and row["device_id"] and row["device_fp"])
        conn.execute(
            """
            UPDATE accounts
            SET device_id = NULL,
                device_fp = NULL,
                device_info = NULL,
                device_updated_at = NULL,
                updated_at = ?
            WHERE uid = ?
            """,
            (utc_now(), uid),
        )
    data = {
        "uid": uid,
        "credential_type": "device",
        "validity_status": "deleted" if deleted else "missing",
        "deleted": deleted,
    }
    return _auth_text_result(args, data)


def _store_qrcode_credentials(uid: str, result: CommandResult) -> CommandResult:
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


def _store_device_binding(
    args: argparse.Namespace,
    uid: str,
    region: str,
    result: CommandResult,
) -> CommandResult:
    device_id = str(result.data.pop("device_id"))
    device_fp = str(result.data.pop("device_fp"))
    device_info = str(result.data.pop("device_info"))
    _store_device_metadata(
        output_dir=args.output_dir,
        uid=uid,
        region=region,
        device_id=device_id,
        device_fp=device_fp,
        device_info=device_info,
    )

    return CommandResult(
        data={
            **result.data,
            "uid": uid,
            "status": "stored",
            "stored": True,
            "storage": "state.sqlite",
        },
        source=result.source,
        warnings=result.warnings,
    )


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
    complete.add_argument("--uid", dest="command_uid")
    complete.set_defaults(handler=qrcode_complete_command, command_name="auth.qrcode.complete")

    login = actions.add_parser("login", help="Run interactive QR login.")
    login.add_argument("--uid", dest="command_uid")
    login.add_argument("--poll-interval", type=float, default=2.0)
    login.add_argument("--login-timeout", type=float, default=120.0)
    login.set_defaults(handler=qrcode_login_command, command_name="auth.qrcode.login")


def _register_device(
    credentials: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    device = credentials.add_parser("device", help="Manage MYS device binding.")
    actions = device.add_subparsers(dest="device_action", required=True, metavar="<action>")
    set_parser = actions.add_parser("set", help="Bind and store MYS device metadata.")
    set_parser.add_argument("--uid", dest="command_uid")
    _add_device_payload_args(set_parser)
    set_parser.set_defaults(
        handler=device_set_command,
        command_name="auth.device.set",
        credential_kind="cookie",
    )

    test = actions.add_parser("test", help="Check local MYS device metadata availability.")
    test.add_argument("--uid", dest="command_uid")
    test.set_defaults(handler=device_test_command, command_name="auth.device.test")

    delete = actions.add_parser("delete", help="Delete local MYS device metadata.")
    delete.add_argument("--uid", dest="command_uid")
    delete.set_defaults(handler=device_delete_command, command_name="auth.device.delete")


def _add_qrcode_session_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--app-id", default="2")
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--device", required=True)


def _add_device_payload_args(parser: argparse.ArgumentParser) -> None:
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--device-json")
    sources.add_argument("--device-file")
    sources.add_argument("--device-stdin", action="store_true")


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


def _read_device_payload(args: argparse.Namespace) -> dict[str, object]:
    if args.device_json is not None:
        raw = args.device_json
    elif args.device_file:
        raw = Path(args.device_file).read_text(encoding="utf-8")
    elif args.device_stdin:
        raw = sys.stdin.read()
    else:
        raise CliError("INVALID_ARGUMENT", "device payload is required", EXIT_INVALID_INPUT)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliError(
            "INVALID_ARGUMENT",
            "device payload must be valid JSON",
            EXIT_INVALID_INPUT,
        ) from exc
    if not isinstance(payload, dict):
        raise CliError(
            "INVALID_ARGUMENT",
            "device payload must be a JSON object",
            EXIT_INVALID_INPUT,
        )
    return payload


def _store_device_metadata(
    *,
    output_dir: str | None,
    uid: str,
    region: str,
    device_id: str,
    device_fp: str,
    device_info: str,
) -> None:
    now = utc_now()
    with state_db(output_dir) as conn:
        conn.execute(
            """
            INSERT INTO accounts(
                uid, region, label, is_default, created_at, updated_at,
                device_id, device_fp, device_info, device_updated_at
            )
            VALUES(?, ?, NULL, 0, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(uid) DO UPDATE SET
                region = excluded.region,
                updated_at = excluded.updated_at,
                device_id = excluded.device_id,
                device_fp = excluded.device_fp,
                device_info = excluded.device_info,
                device_updated_at = excluded.device_updated_at
            """,
            (uid, region, now, now, device_id, device_fp, device_info, now),
        )


def _device_result_data(
    *,
    uid: str,
    status: str,
    device: dict[str, str],
) -> dict[str, object]:
    return {
        "uid": uid,
        "credential_type": "device",
        "validity_status": status,
        "device": _device_summary(device["device_info"]),
        "redacted": {
            "device_id": redact_secret(device["device_id"]),
            "device_fp": redact_secret(device["device_fp"]),
        },
    }


def _device_summary(device_info: str) -> dict[str, object]:
    parts = [part.strip() for part in device_info.split("/") if part.strip()]
    return {
        "brand": parts[0] if parts else "Unknown",
        "model": parts[1] if len(parts) > 1 else (parts[0] if parts else "Unknown"),
        "has_device_info": bool(device_info.strip()),
    }


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
        "redacted": _redacted_credential(kind, value),
    }


def _redacted_credential(kind: str, value: str) -> str:
    if kind == "gacha_url":
        return "[REDACTED_URL]"
    return redact_secret(value)


def _http_client(args: argparse.Namespace) -> HttpClient:
    return HttpClient(
        timeout=args.timeout,
        cache_policy="off",
        output_dir=args.output_dir,
        debug=args.debug,
    )


def _qrcode_terminal(url: str) -> str:
    qr = qrcode.QRCode(
        version=1,
        error_correction=ERROR_CORRECT_L,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    buffer = io.StringIO()
    qr.print_ascii(out=buffer, invert=True)
    return buffer.getvalue().rstrip("\n")


def _qrcode_png(url: str) -> bytes:
    qr = qrcode.QRCode(
        version=1,
        error_correction=ERROR_CORRECT_L,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _validate_qrcode_login_timing(args: argparse.Namespace) -> None:
    if args.poll_interval <= 0:
        raise CliError(
            "INVALID_ARGUMENT",
            "poll interval must be greater than 0",
            EXIT_INVALID_INPUT,
            {"poll_interval": args.poll_interval},
        )
    if args.login_timeout <= 0:
        raise CliError(
            "INVALID_ARGUMENT",
            "login timeout must be greater than 0",
            EXIT_INVALID_INPUT,
            {"login_timeout": args.login_timeout},
        )


def _write_interactive(args: argparse.Namespace, message: str, *, force: bool = False) -> None:
    if args.quiet and not force:
        return
    args.stderr.write(f"{message}\n")


def _auth_text_result(
    args: argparse.Namespace,
    result: CommandResult | dict[str, object],
) -> CommandResult | dict[str, object]:
    command = str(args.command_name)
    data = result.data if isinstance(result, CommandResult) else result
    subject = data.get("uid") or data.get("account_id") or data.get("credential_type") or "session"
    return command_text_result(
        args,
        result,
        name=f"{command.replace('.', '/')}-text",
        filename=f"{command.replace('.', '-')}_{safe_filename_part(subject)}.txt",
        content=render_auth_command_text(command, data),
        description="Human-readable local authentication text",
    )


def _qrcode_render_result(
    args: argparse.Namespace,
    result: CommandResult,
    *,
    url: str,
    image_artifact: dict[str, object] | None = None,
) -> CommandResult:
    command = str(args.command_name)
    artifacts = list(result.artifacts)
    render_data: dict[str, object] = {}
    subject = result.data.get("uid") or result.data.get("account_id") or "session"
    image_enabled = render_image_enabled(args)
    if image_enabled:
        if image_artifact is None:
            image_artifact = _qrcode_image_artifact(
                args,
                command=command,
                url=url,
                subject=subject,
            )
        if image_artifact not in artifacts:
            artifacts.append(image_artifact)
        render_data.update(
            {
                "render": command.replace(".", "/"),
                "artifact_sha256": image_artifact["sha256"],
            }
        )
    text_enabled = render_text_enabled(args) or (
        command == "auth.qrcode.start" and str(getattr(args, "format", "")) == "plain"
    )
    if text_enabled:
        text_artifact = ArtifactManager(args.request_id, args.output_dir).write_text(
            name=f"{command.replace('.', '/')}-text",
            filename=f"{command.replace('.', '-')}_{safe_filename_part(subject)}.txt",
            content=_qrcode_text_content(command, result.data, url),
            description="Human-readable local authentication text",
            kind="text",
        )
        artifacts.append(text_artifact)
        if image_enabled:
            render_data["text_artifact_sha256"] = text_artifact["sha256"]
        else:
            render_data.update(
                {
                    "render": f"{command.replace('.', '/')}-text",
                    "artifact_sha256": text_artifact["sha256"],
                }
            )
    if not render_data:
        return result
    return CommandResult(
        data=render_result_data(args, result.data, render_data),
        artifacts=artifacts,
        source=result.source,
        warnings=result.warnings,
        pagination=result.pagination,
    )


def _qrcode_image_artifact(
    args: argparse.Namespace,
    *,
    command: str,
    url: str,
    subject: object,
) -> dict[str, object]:
    return ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name=command.replace(".", "/"),
        filename=f"{command.replace('.', '-')}_{safe_filename_part(subject)}.png",
        media_type="image/png",
        content=_qrcode_png(url),
        description="MiHoYo QR login image",
        kind="image",
    )


def _qrcode_text_content(
    command: str,
    data: dict[str, object],
    url: str,
) -> str:
    content = render_auth_command_text(command, data)
    if command != "auth.qrcode.start":
        return content
    lines = content.rstrip("\n").splitlines()
    if len(lines) < 2:
        return content
    return (
        "\n".join(
            [
                lines[0],
                lines[1],
                "",
                _qrcode_terminal(url),
                "",
                f"请在点击确认登录后立即执行: {_qrcode_poll_command(data)}",
                "",
                *lines[2:],
            ]
        ).rstrip()
        + "\n"
    )


def _qrcode_poll_command(data: dict[str, object]) -> str:
    app_id = shlex.quote(str(data.get("app_id") or "2"))
    ticket = shlex.quote(str(data.get("ticket") or ""))
    device = shlex.quote(str(data.get("device") or ""))
    return f"gsuid auth qrcode poll --app-id {app_id} --ticket {ticket} --device {device}"
