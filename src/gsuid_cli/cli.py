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
    batch,
    cache,
    challenge,
    gacha,
    meta,
    monitor,
    panel,
    player,
    profile,
    progress,
    public_data,
    rank,
    resources,
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
HOISTED_GLOBAL_FLAG_OPTIONS = {"--quiet", "--debug"}
OUTPUT_FORMATS = {"json", "pretty-json", "text"}


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
        choices=("json", "pretty-json", "text"),
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
    batch.register(groups)
    cache.register(groups)
    public_data.register(groups)
    resources.register(groups)
    monitor.register(groups)
    player.register(groups)
    challenge.register(groups)
    progress.register(groups)
    gacha.register(groups)
    panel.register(groups)
    rank.register(groups)
    return parser


def parse_argv(argv: Sequence[str]) -> argparse.Namespace:
    return build_parser().parse_args(_canonicalize_global_options(argv))


def run(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    args_list = _canonicalize_global_options(list(sys.argv[1:] if argv is None else argv))
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    started = time.perf_counter()

    try:
        parser = build_parser()
        if _write_incomplete_help(parser, args_list, stdout):
            return 0
        args = parser.parse_args(args_list)
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
    if output_format in {"json", "pretty-json"}:
        indent = 2 if output_format == "pretty-json" else None
        stdout.write(json.dumps(payload, ensure_ascii=False, indent=indent))
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
    argv = _canonicalize_global_options(argv)
    output_format = _global_option_value(argv, "--format")
    region = _global_option_value(argv, "--region")
    return {
        "command": _guess_command(argv),
        "request_id": _option_value(argv, "--request-id") or str(uuid.uuid4()),
        "format": output_format
        if output_format in OUTPUT_FORMATS
        else _valid_env("GSUID_FORMAT", OUTPUT_FORMATS, "json"),
        "region": region
        if region in {"cn", "os"}
        else _valid_env("GSUID_REGION", {"cn", "os"}, "cn"),
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
        if token.startswith(f"{option}="):
            return token.split("=", 1)[1]
        if token == option and index + 1 < len(argv):
            return argv[index + 1]
    return None


def _global_option_value(argv: Sequence[str], option: str) -> str | None:
    argv = _canonicalize_global_options(argv)
    index = 0
    while index < len(argv):
        token = argv[index]
        if token.startswith(f"{option}="):
            return token.split("=", 1)[1]
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


def _canonicalize_global_options(argv: Sequence[str]) -> list[str]:
    hoisted: list[str] = []
    remaining: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        option, value = _split_long_option(token)
        next_value = value
        if option in GLOBAL_VALUE_OPTIONS and value is None and index + 1 < len(argv):
            next_value = argv[index + 1]
        if option in GLOBAL_VALUE_OPTIONS and _should_hoist_global_option(option, next_value):
            if value is None and index + 1 < len(argv):
                hoisted.extend([token, argv[index + 1]])
                index += 2
                continue
            hoisted.append(token)
            index += 1
            continue
        if token in GLOBAL_VALUE_OPTIONS and index + 1 >= len(argv):
            hoisted.append(token)
            index += 1
            continue
        if token in HOISTED_GLOBAL_FLAG_OPTIONS:
            hoisted.append(token)
            index += 1
            continue
        remaining.append(token)
        index += 1
    return hoisted + remaining


def _split_long_option(token: str) -> tuple[str, str | None]:
    if not token.startswith("--") or "=" not in token:
        return token, None
    option, value = token.split("=", 1)
    return option, value


def _should_hoist_global_option(option: str, value: str | None) -> bool:
    if option != "--format":
        return True
    return value is None or value in OUTPUT_FORMATS


def _write_incomplete_help(
    parser: argparse.ArgumentParser,
    argv: Sequence[str],
    stdout: TextIO,
) -> bool:
    path = _incomplete_command_path(argv)
    if path is None:
        return False
    _validate_globals_for_help(argv)
    if not path:
        parser.print_help(stdout)
        return True

    group_parser = _subparser(parser, path[0])
    if group_parser is None:
        return False
    group_parser.print_help(stdout)
    return True


def _incomplete_command_path(argv: Sequence[str]) -> list[str] | None:
    if any(token in {"--help", "-h", "--version"} for token in argv):
        return None

    path: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        option, value = _split_long_option(token)
        next_value = value
        if option in GLOBAL_VALUE_OPTIONS and value is None and index + 1 < len(argv):
            next_value = argv[index + 1]
        if option in GLOBAL_VALUE_OPTIONS and _should_hoist_global_option(option, next_value):
            if value is None:
                if index + 1 >= len(argv):
                    return None
                index += 2
                continue
            index += 1
            continue
        if token in HOISTED_GLOBAL_FLAG_OPTIONS:
            index += 1
            continue
        if token.startswith("-"):
            return None

        path.append(token)
        if len(path) == 2:
            return None
        index += 1

    return path


def _subparser(parser: argparse.ArgumentParser, name: str) -> argparse.ArgumentParser | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices.get(name)
    return None


def _validate_globals_for_help(argv: Sequence[str]) -> None:
    index = 0
    while index < len(argv):
        token = argv[index]
        option, inline_value = _split_long_option(token)
        if option in GLOBAL_VALUE_OPTIONS:
            value, consumed = _global_value_for_validation(argv, index, inline_value)
            _validate_global_value(option, value)
            index += consumed
            continue
        if token in HOISTED_GLOBAL_FLAG_OPTIONS:
            index += 1
            continue
        if not token.startswith("-"):
            return
        return


def _global_value_for_validation(
    argv: Sequence[str],
    index: int,
    inline_value: str | None,
) -> tuple[str, int]:
    if inline_value is not None:
        return inline_value, 1
    if index + 1 >= len(argv):
        raise CliError(
            "INVALID_ARGUMENT",
            f"argument {argv[index]}: expected one argument",
            EXIT_INVALID_INPUT,
        )
    return argv[index + 1], 2


def _validate_global_value(option: str, value: str) -> None:
    choices = {
        "--region": {"cn", "os"},
        "--format": OUTPUT_FORMATS,
        "--render": {"data", "image", "both"},
        "--cache": {"use", "refresh", "only", "off"},
    }.get(option)
    if choices is not None and value not in choices:
        allowed = ", ".join(sorted(choices))
        raise CliError(
            "INVALID_ARGUMENT",
            f"argument {option}: invalid choice: {value!r} (choose from {allowed})",
            EXIT_INVALID_INPUT,
        )
    if option == "--timeout":
        try:
            timeout = float(value)
        except ValueError as exc:
            raise CliError(
                "INVALID_ARGUMENT",
                f"argument --timeout: invalid float value: {value!r}",
                EXIT_INVALID_INPUT,
            ) from exc
        if timeout <= 0:
            raise CliError(
                "INVALID_ARGUMENT",
                "timeout must be greater than 0",
                EXIT_INVALID_INPUT,
                {"timeout": timeout},
            )


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
