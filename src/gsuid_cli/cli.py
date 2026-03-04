from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from collections.abc import Sequence
from typing import TextIO

from gsuid_cli import __version__
from gsuid_cli.commands import (
    account,
    auth,
    challenge,
    gacha,
    meta,
    panel,
    player,
    profile,
    progress,
    public_data,
    rank,
)
from gsuid_cli.core.envelope import error_envelope, success_envelope
from gsuid_cli.core.errors import (
    EXIT_INTERNAL_BUG,
    EXIT_INTERRUPTED,
    EXIT_INVALID_INPUT,
    CliError,
)
from gsuid_cli.core.models import CommandResult

GLOBAL_VALUE_OPTIONS = {
    "--profile",
    "--uid",
    "--region",
    "--format",
    "--render",
    "--output-dir",
    "--cache",
    "--timeout",
    "--request-id",
}
GLOBAL_FLAG_OPTIONS = {"--quiet", "--debug", "--help", "--version"}
OUTPUT_FORMATS = {"json", "text"}


class GsuidArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliError("INVALID_ARGUMENT", message, EXIT_INVALID_INPUT)


def build_parser() -> argparse.ArgumentParser:
    parser = GsuidArgumentParser(
        prog="gsuid",
        description="Agent-oriented Genshin Impact CLI.",
    )
    parser.add_argument("--profile", default=os.environ.get("GSUID_PROFILE", "default"))
    parser.add_argument("--uid")
    parser.add_argument(
        "--region",
        choices=("cn", "os"),
        default=os.environ.get("GSUID_REGION", "cn"),
    )
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default=os.environ.get("GSUID_FORMAT", "json"),
    )
    parser.add_argument("--render", choices=("data", "image", "both"), default="data")
    parser.add_argument("--output-dir", default=os.environ.get("GSUID_OUTPUT_DIR"))
    parser.add_argument("--cache", choices=("use", "refresh", "only", "off"), default="use")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--request-id")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    groups = parser.add_subparsers(dest="group", required=True, metavar="<group>")
    meta.register(groups)
    profile.register(groups)
    account.register(groups)
    auth.register(groups)
    public_data.register(groups)
    player.register(groups)
    challenge.register(groups)
    progress.register(groups)
    gacha.register(groups)
    panel.register(groups)
    rank.register(groups)
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    started = time.perf_counter()

    try:
        args = build_parser().parse_args(args_list)
        _validate_runtime_defaults(args)
        command = args.command_name
        request_id = args.request_id or str(uuid.uuid4())
        args.request_id = request_id
        args.stdout = stdout
        args.stderr = stderr
        result = args.handler(args)
        if not isinstance(result, CommandResult):
            result = CommandResult(data=result)
        payload = success_envelope(
            command=command,
            request_id=request_id,
            duration_ms=_duration_ms(started),
            data=result.data,
            region=args.region,
            warnings=result.warnings,
            artifacts=result.artifacts,
            source=result.source,
            pagination=result.pagination,
        )
        _write_payload(payload, args.format, stdout, stderr)
        return 0
    except SystemExit as exc:
        return _system_exit_code(exc)
    except CliError as exc:
        context = _context_from_args(args) if "args" in locals() else _error_context(args_list)
        payload = error_envelope(
            command=context["command"],
            request_id=context["request_id"],
            duration_ms=_duration_ms(started),
            error=exc,
            region=context["region"],
        )
        _write_payload(payload, context["format"], stdout, stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        context = _error_context(args_list)
        error = CliError("INTERRUPTED", "Interrupted.", EXIT_INTERRUPTED)
        payload = error_envelope(
            command=context["command"],
            request_id=context["request_id"],
            duration_ms=_duration_ms(started),
            error=error,
            region=context["region"],
        )
        _write_payload(payload, context["format"], stdout, stderr)
        return EXIT_INTERRUPTED
    except Exception as exc:  # pragma: no cover - defensive command boundary.
        context = _error_context(args_list)
        details = {}
        if context["debug"]:
            details = {"type": type(exc).__name__, "message": str(exc)}
        error = CliError("INTERNAL_ERROR", "Internal bug.", EXIT_INTERNAL_BUG, details)
        payload = error_envelope(
            command=context["command"],
            request_id=context["request_id"],
            duration_ms=_duration_ms(started),
            error=error,
            region=context["region"],
        )
        _write_payload(payload, context["format"], stdout, stderr)
        return EXIT_INTERNAL_BUG


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


def _validate_runtime_defaults(args: argparse.Namespace) -> None:
    if args.format not in OUTPUT_FORMATS:
        raise CliError(
            "INVALID_ARGUMENT",
            f"invalid output format: {args.format}",
            EXIT_INVALID_INPUT,
            {"format": args.format},
        )
    if args.timeout <= 0:
        raise CliError(
            "INVALID_ARGUMENT",
            "timeout must be greater than 0",
            EXIT_INVALID_INPUT,
            {"timeout": args.timeout},
        )


def _write_payload(
    payload: dict[str, object],
    output_format: str,
    stdout: TextIO,
    stderr: TextIO,
) -> None:
    if output_format == "json":
        stdout.write(json.dumps(payload, ensure_ascii=False))
        stdout.write("\n")
        return

    if payload["ok"]:
        stdout.write(json.dumps(payload["data"], ensure_ascii=False, indent=2))
        stdout.write("\n")
        return

    error = payload["error"]
    if isinstance(error, dict):
        stderr.write(f"{error['code']}: {error['message']}\n")


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _system_exit_code(exc: SystemExit) -> int:
    if isinstance(exc.code, int):
        return exc.code
    return EXIT_INVALID_INPUT


def _error_context(argv: Sequence[str]) -> dict[str, object]:
    return {
        "command": _guess_command(argv),
        "request_id": _option_value(argv, "--request-id") or str(uuid.uuid4()),
        "format": _global_option_value(argv, "--format")
        or _valid_env("GSUID_FORMAT", OUTPUT_FORMATS, "json"),
        "region": _global_option_value(argv, "--region")
        or _valid_env("GSUID_REGION", {"cn", "os"}, "cn"),
        "debug": "--debug" in argv,
    }


def _context_from_args(args: argparse.Namespace) -> dict[str, object]:
    return {
        "command": args.command_name,
        "request_id": args.request_id or str(uuid.uuid4()),
        "format": args.format,
        "region": args.region,
        "debug": args.debug,
    }


def _valid_env(name: str, allowed: set[str], default: str) -> str:
    value = os.environ.get(name)
    if value in allowed:
        return value
    return default


def _option_value(argv: Sequence[str], option: str) -> str | None:
    for index, token in enumerate(argv):
        if token == option and index + 1 < len(argv):
            return argv[index + 1]
    return None


def _global_option_value(argv: Sequence[str], option: str) -> str | None:
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == option and index + 1 < len(argv):
            return argv[index + 1]
        if token in GLOBAL_VALUE_OPTIONS:
            index += 2
            continue
        if token in GLOBAL_FLAG_OPTIONS:
            index += 1
            continue
        if not token.startswith("-"):
            return None
        index += 1
    return None


def _guess_command(argv: Sequence[str]) -> str:
    parts: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in GLOBAL_VALUE_OPTIONS:
            index += 2
            continue
        if token in GLOBAL_FLAG_OPTIONS:
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        parts.append(token)
        if len(parts) == 2:
            return ".".join(parts)
        index += 1
    return "unknown"
