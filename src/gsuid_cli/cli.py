from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path
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
)
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.config import CliDefaults, ConfigError, load_cli_defaults
from gsuid_cli.core.envelope import error_envelope, success_envelope
from gsuid_cli.core.errors import (
    EXIT_INTERNAL_BUG,
    EXIT_INTERRUPTED,
    EXIT_INVALID_INPUT,
    CliError,
)
from gsuid_cli.core.http import begin_source_capture, end_source_capture
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import REGION_CHOICES
from gsuid_cli.core.render import explicit_render_modes, normalize_render_modes, render_data_enabled
from gsuid_cli.core.secrets import redact_secret
from gsuid_cli.text import t as _t

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
GLOBAL_FLAG_OPTIONS = {"--quiet", "--no-quiet", "--debug", "--no-debug", "--help", "--version"}
HOISTED_GLOBAL_FLAG_OPTIONS = {"--quiet", "--no-quiet", "--debug", "--no-debug"}
OUTPUT_FORMATS = {"json", "pretty-json", "plain"}
CACHE_POLICIES = {"use", "refresh", "only", "off"}
ANSI_YELLOW = "\033[33m"
ANSI_RESET = "\033[0m"
SENSITIVE_KEY_PARTS = (
    "authkey",
    "cookie",
    "device_fp",
    "device_id",
    "gacha_url",
    "secret",
    "stoken",
    "token",
)
OPTION_HELP = {
    "--all": _t("gsuid.cli.72_13.80c7bc85"),
    "--app-id": _t("gsuid.cli.73_16.23b02302"),
    "--artifact-source-character": _t("gsuid.cli.74_35.12b00f08"),
    "--banner": _t("gsuid.cli.75_16.81e01ff3"),
    "--build": _t("gsuid.cli.76_15.63c90b76"),
    "--cache": _t("gsuid.cli.77_15.ab20db96"),
    "--character": _t("gsuid.cli.78_19.2552709c"),
    "--check": _t("gsuid.cli.79_15.02577482"),
    "--constellation": _t("gsuid.cli.80_23.83e36c26"),
    "--cookie": _t("gsuid.cli.81_16.36e9efc8"),
    "--cookie-file": _t("gsuid.cli.82_21.d7e94f77"),
    "--cookie-stdin": _t("gsuid.cli.83_22.c7c27395"),
    "--date": _t("gsuid.cli.84_14.d408a7e0"),
    "--day": _t("gsuid.cli.85_13.5aa9ec83"),
    "--debug": _t("gsuid.cli.86_15.4bbccfad"),
    "--deck-id": _t("gsuid.cli.87_17.d635dcac"),
    "--default": _t("gsuid.cli.88_17.e16f923b"),
    "--device": _t("gsuid.cli.89_16.2d0c91c8"),
    "--file": _t("gsuid.cli.90_14.28fabae0"),
    "--floor": _t("gsuid.cli.91_15.c11873fc"),
    "--force": _t("gsuid.cli.92_15.7eb1db5a"),
    "--full": _t("gsuid.cli.93_14.06219718"),
    "--id": _t("gsuid.cli.94_12.216b4ef5"),
    "--item": _t("gsuid.cli.95_14.2a8d2a8d"),
    "--label": _t("gsuid.cli.96_15.d0650369"),
    "--level": _t("gsuid.cli.97_15.b22a69fc"),
    "--limit": _t("gsuid.cli.98_15.7236070c"),
    "--login-timeout": _t("gsuid.cli.99_23.44a0e51e"),
    "--map": _t("gsuid.cli.100_13.5275a040"),
    "--material": _t("gsuid.cli.101_18.d1b51600"),
    "--max-artifact-files": _t("gsuid.cli.102_28.45377c79"),
    "--max-asset-cache-files": _t("gsuid.cli.103_31.034e32fb"),
    "--min-free-mb": _t("gsuid.cli.104_21.da010c5a"),
    "--name": _t("gsuid.cli.105_14.656a5932"),
    "--nearby": _t("gsuid.cli.106_16.eada310f"),
    "--output": _t("gsuid.cli.107_16.f12d2e5f"),
    "--output-dir": _t("gsuid.cli.108_20.12325143"),
    "--page": _t("gsuid.cli.109_14.468b936c"),
    "--poll-interval": _t("gsuid.cli.110_23.cbdff4b5"),
    "--profile": _t("gsuid.cli.111_17.76251a4a"),
    "--query": _t("gsuid.cli.112_15.5323cc71"),
    "--quiet": _t("gsuid.cli.113_15.b6e4e626"),
    "--region": _t("gsuid.cli.114_16.e2c46efe"),
    "--render": _t("gsuid.cli.115_16.74f75e5c"),
    "--request-id": _t("gsuid.cli.116_20.d006b223"),
    "--scope": _t("gsuid.cli.117_15.9212869b"),
    "--season": _t("gsuid.cli.118_16.11d49b1b"),
    "--sort": _t("gsuid.cli.119_14.306876c6"),
    "--source": _t("gsuid.cli.120_16.cf2d11d1"),
    "--stoken": _t("gsuid.cli.121_16.2d3c8b7e"),
    "--stoken-file": _t("gsuid.cli.122_21.40cc1625"),
    "--stoken-stdin": _t("gsuid.cli.123_22.23958c6d"),
    "--talent": _t("gsuid.cli.124_16.910aa1c6"),
    "--ticket": _t("gsuid.cli.125_16.6a5f4761"),
    "--timeout": _t("gsuid.cli.126_17.04b0fbc3"),
    "--uid": _t("gsuid.cli.127_13.4cad1c3f"),
    "--url": _t("gsuid.cli.128_13.e213125e"),
    "--url-file": _t("gsuid.cli.129_18.8ba35213"),
    "--url-stdin": _t("gsuid.cli.130_19.32077323"),
    "--version": _t("gsuid.cli.131_17.ec7b3c84"),
    "--weapon": _t("gsuid.cli.132_16.e7517378"),
}
DEST_HELP = {
    "account_region": _t("gsuid.cli.135_22.e1872fe3"),
    "account_uid": _t("gsuid.cli.136_19.f031ea26"),
    "command_uid": _t("gsuid.cli.127_13.4cad1c3f"),
    "export_format": _t("gsuid.cli.138_21.f42499ba"),
    "format": _t("gsuid.cli.139_14.bda6dd74"),
    "import_format": _t("gsuid.cli.140_21.5111b5f6"),
    "profile_region": _t("gsuid.cli.141_22.77c086e3"),
    "query": _t("gsuid.cli.142_13.655d0abb"),
}


class GsuidArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliError("INVALID_ARGUMENT", message, EXIT_INVALID_INPUT)


def build_parser(defaults: CliDefaults | None = None) -> argparse.ArgumentParser:
    defaults = defaults or effective_cli_defaults()
    parser = GsuidArgumentParser(
        prog="gsuid",
        description=_t("gsuid.cli.154_20.ea648adb"),
        add_help=False,
    )
    parser.set_defaults(cli_defaults=defaults)
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        default=argparse.SUPPRESS,
        help=_t("gsuid.cli.158_71.ca4abdda"),
    )
    parser.add_argument("--profile", default=defaults.profile)
    parser.add_argument("--uid")
    parser.add_argument(
        "--region",
        choices=tuple(sorted(REGION_CHOICES)),
        default=defaults.region,
    )
    parser.add_argument(
        "--format",
        choices=("json", "pretty-json", "plain"),
        default=defaults.format,
    )
    parser.add_argument("--render", action="append", metavar="data|image|text|all")
    parser.add_argument("--output-dir", default=defaults.output_dir)
    parser.add_argument("--cache", choices=tuple(sorted(CACHE_POLICIES)), default=defaults.cache)
    parser.add_argument("--timeout", type=float, default=defaults.timeout)
    parser.add_argument("--request-id")
    parser.add_argument("--quiet", action=argparse.BooleanOptionalAction, default=defaults.quiet)
    parser.add_argument("--debug", action=argparse.BooleanOptionalAction, default=defaults.debug)
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help=_t("gsuid.cli.180_79.9bdc68ac"),
    )

    groups = parser.add_subparsers(dest="group", required=True, metavar="<group>")
    meta.register(groups)
    profile.register(groups)
    account.register(groups)
    auth.register(groups)
    batch.register(groups)
    cache.register(groups)
    public_data.register(groups)
    monitor.register(groups)
    player.register(groups)
    challenge.register(groups)
    progress.register(groups)
    gacha.register(groups)
    panel.register(groups)
    rank.register(groups)
    _complete_help_information(parser)
    return parser


def parse_argv(argv: Sequence[str]) -> argparse.Namespace:
    defaults = effective_cli_defaults()
    args = build_parser(defaults).parse_args(_canonicalize_global_options(argv))
    _apply_post_parse_defaults(args, defaults)
    return args


def effective_cli_defaults() -> CliDefaults:
    try:
        defaults = load_cli_defaults()
    except ConfigError as exc:
        raise CliError(
            "INVALID_ARGUMENT",
            _t("gsuid.cli.config.invalid", exc),
            EXIT_INVALID_INPUT,
            {"config": str(exc.path)},
        ) from exc
    return CliDefaults(
        profile=os.environ.get("GSUID_PROFILE", defaults.profile),
        region=os.environ.get("GSUID_REGION", defaults.region),
        format=os.environ.get("GSUID_FORMAT", defaults.format),
        render=defaults.render,
        output_dir=os.environ.get("GSUID_OUTPUT_DIR") or defaults.output_dir,
        cache=defaults.cache,
        timeout=defaults.timeout,
        quiet=defaults.quiet,
        debug=defaults.debug,
        language=defaults.language,
    )


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
    captured_sources: list[dict[str, object]] = []

    try:
        defaults = effective_cli_defaults()
        parser = build_parser(defaults)
        if _write_explicit_help(parser, args_list, stdout):
            return 0
        if _write_incomplete_help(parser, args_list, stdout):
            return 0
        args = parser.parse_args(args_list)
        _apply_post_parse_defaults(args, defaults)
        _validate_runtime_defaults(args)
        command = args.command_name
        request_id = args.request_id or str(uuid.uuid4())
        args.request_id = request_id
        args.stdout = stdout
        args.stderr = stderr
        source_capture = begin_source_capture()
        try:
            result = args.handler(args)
        finally:
            captured_sources = end_source_capture(source_capture)
        if not isinstance(result, CommandResult):
            result = CommandResult(data=result)
        render_warnings = _unsupported_render_warnings(
            command,
            getattr(args, "explicit_render", []),
        )
        payload = success_envelope(
            command=command,
            request_id=request_id,
            duration_ms=_duration_ms(started),
            data=result.data,
            region=args.region,
            warnings=[*result.warnings, *render_warnings],
            artifacts=result.artifacts,
            sources=_result_sources(result, captured_sources),
            pagination=result.pagination,
        )
        _write_payload(
            payload,
            args.format,
            stdout,
            stderr,
            debug=args.debug,
            request_id=request_id,
            output_dir=args.output_dir,
            include_details=render_data_enabled(args),
        )
        return 0
    except SystemExit as exc:
        return _system_exit_code(exc)
    except CliError as exc:
        context = (
            _context_from_args(args)
            if "args" in locals()
            else _error_context(args_list, locals().get("defaults"))
        )
        payload = error_envelope(
            command=context["command"],
            request_id=context["request_id"],
            duration_ms=_duration_ms(started),
            error=exc,
            region=context["region"],
            sources=captured_sources,
        )
        _write_payload(
            payload,
            context["format"],
            stdout,
            stderr,
            debug=bool(context["debug"]),
            request_id=str(context["request_id"]),
            output_dir=_optional_str(context["output_dir"]),
            include_details=bool(context["include_details"]),
        )
        return exc.exit_code
    except KeyboardInterrupt:
        context = _error_context(args_list, locals().get("defaults"))
        error = CliError("INTERRUPTED", _t("gsuid.cli.289_40.d0ea587e"), EXIT_INTERRUPTED)
        payload = error_envelope(
            command=context["command"],
            request_id=context["request_id"],
            duration_ms=_duration_ms(started),
            error=error,
            region=context["region"],
            sources=captured_sources,
        )
        _write_payload(
            payload,
            context["format"],
            stdout,
            stderr,
            debug=bool(context["debug"]),
            request_id=str(context["request_id"]),
            output_dir=_optional_str(context["output_dir"]),
            include_details=bool(context["include_details"]),
        )
        return EXIT_INTERRUPTED
    except Exception as exc:  # pragma: no cover - defensive command boundary.
        context = _error_context(args_list, locals().get("defaults"))
        details = {}
        if context["debug"]:
            details = {"type": type(exc).__name__, "message": str(exc)}
        error = CliError(
            "INTERNAL_ERROR", _t("gsuid.cli.314_43.ba149deb"), EXIT_INTERNAL_BUG, details
        )
        payload = error_envelope(
            command=context["command"],
            request_id=context["request_id"],
            duration_ms=_duration_ms(started),
            error=error,
            region=context["region"],
            sources=captured_sources,
        )
        _write_payload(
            payload,
            context["format"],
            stdout,
            stderr,
            debug=bool(context["debug"]),
            request_id=str(context["request_id"]),
            output_dir=_optional_str(context["output_dir"]),
            include_details=bool(context["include_details"]),
        )
        return EXIT_INTERNAL_BUG


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


def _complete_help_information(parser: argparse.ArgumentParser) -> None:
    for current, description in _walk_parsers(parser, parser.description):
        if not current.description and description:
            current.description = description
        for action in current._actions:
            if isinstance(action, argparse._HelpAction):
                continue
            if isinstance(action, argparse._SubParsersAction):
                _complete_subparser_choice_help(action)
                continue
            if action.help in {None, ""}:
                action.help = _default_action_help(action)


def _walk_parsers(
    parser: argparse.ArgumentParser,
    description: str | None,
) -> list[tuple[argparse.ArgumentParser, str | None]]:
    parsers = [(parser, description)]
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        choice_help = {
            choice.dest: choice.help
            for choice in action._choices_actions
            if getattr(choice, "help", None)
        }
        for name, child in action.choices.items():
            parsers.extend(_walk_parsers(child, choice_help.get(name)))
    return parsers


def _complete_subparser_choice_help(action: argparse._SubParsersAction) -> None:
    for choice in action._choices_actions:
        if choice.help in {None, ""}:
            choice.help = _label_help(choice.dest)


def _default_action_help(action: argparse.Action) -> str:
    if action.dest in DEST_HELP:
        return DEST_HELP[action.dest]
    for option in action.option_strings:
        if option in OPTION_HELP:
            return OPTION_HELP[option]
    return _label_help(action.dest)


def _label_help(value: str) -> str:
    label = value.replace("_", " ").replace("-", " ").strip()
    if not label:
        return _t("gsuid.cli.390_15.c26f7543")
    return _t("gsuid.cli.391_11.d8d8b025", label.capitalize())


def _apply_post_parse_defaults(args: argparse.Namespace, defaults: CliDefaults) -> None:
    if args.render is None and defaults.render is not None:
        args.render = list(defaults.render)


def _validate_runtime_defaults(args: argparse.Namespace) -> None:
    if args.format not in OUTPUT_FORMATS:
        raise CliError(
            "INVALID_ARGUMENT",
            f"invalid output format: {args.format}",
            EXIT_INVALID_INPUT,
            {"format": args.format},
        )
    if args.region not in REGION_CHOICES:
        raise CliError(
            "INVALID_ARGUMENT",
            f"invalid region: {args.region}",
            EXIT_INVALID_INPUT,
            {"region": args.region},
        )
    if args.cache not in CACHE_POLICIES:
        raise CliError(
            "INVALID_ARGUMENT",
            f"invalid cache policy: {args.cache}",
            EXIT_INVALID_INPUT,
            {"cache": args.cache},
        )
    args.explicit_render = explicit_render_modes(args.render)
    args.render = normalize_render_modes(args.render)
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
    *,
    debug: bool = False,
    request_id: str | None = None,
    output_dir: str | None = None,
    include_details: bool = False,
) -> None:
    if debug:
        payload = _payload_with_debug_artifact(
            payload,
            request_id=request_id,
            output_dir=output_dir,
        )
    if output_format in {"json", "pretty-json"}:
        payload = _json_payload_for_output(
            payload,
            debug=debug,
            include_details=include_details,
        )
        indent = 2 if output_format == "pretty-json" else None
        stdout.write(json.dumps(payload, ensure_ascii=False, indent=indent))
        stdout.write("\n")
        return

    if payload["ok"]:
        _write_plain_warnings(payload, stderr)
        text = _plain_render_text_artifact_content(payload)
        image_paths = _plain_artifact_paths(payload, kind="image")
        if text is not None:
            stdout.write(text)
            if not text.endswith("\n"):
                stdout.write("\n")
            _write_plain_artifact_paths(
                stdout,
                image_paths,
                label=_t("gsuid.cli.452_22.54f0b9a2"),
                leading_blank=True,
            )
            return
        if image_paths:
            if include_details and "data" in payload:
                stdout.write(json.dumps(payload["data"], ensure_ascii=False, indent=2))
                stdout.write("\n")
            _write_plain_artifact_paths(
                stdout,
                image_paths,
                label=_t("gsuid.cli.452_22.54f0b9a2"),
            )
            return
        stdout.write(json.dumps(payload["data"], ensure_ascii=False, indent=2))
        stdout.write("\n")
        return

    error = payload["error"]
    if isinstance(error, dict):
        stderr.write(f"{error['code']}: {error['message']}\n")


def _unsupported_render_warnings(command: str, requested: object) -> list[str]:
    requested_modes = requested if isinstance(requested, list) else explicit_render_modes(requested)
    if not requested_modes:
        return []
    supported = _command_supported_renders(command)
    if not supported:
        return []
    unsupported = [
        str(mode) for mode in requested_modes if mode != "all" and str(mode) not in supported
    ]
    if not unsupported:
        return []
    return [_t("gsuid.cli.487_12.1556201d", command, ", ".join(unsupported))]


def _command_supported_renders(command: str) -> set[str]:
    for capability in meta._capabilities():
        if capability.get("command") != command:
            continue
        renders = capability.get("render")
        if isinstance(renders, list):
            return {str(render) for render in renders}
        return set()
    return set()


def _json_payload_for_output(
    payload: dict[str, object],
    *,
    debug: bool,
    include_details: bool,
) -> dict[str, object]:
    result = dict(payload)
    result["artifacts"] = list(_artifact_list(payload))
    if not (debug or include_details):
        result.pop("data", None)
        result.pop("sources", None)
    return result


def _plain_render_text_artifact_content(payload: dict[str, object]) -> str | None:
    for artifact in _artifact_list(payload):
        if artifact.get("kind") != "text":
            continue
        name = artifact.get("name")
        if not isinstance(name, str) or not name.endswith("-text"):
            continue
        path = artifact.get("path")
        if not isinstance(path, str) or not path:
            continue
        try:
            return Path(path).read_text(encoding="utf-8")
        except OSError:
            return None
    return None


def _plain_artifact_paths(payload: dict[str, object], *, kind: str) -> list[str]:
    paths: list[str] = []
    for artifact in _artifact_list(payload):
        if artifact.get("kind") != kind:
            continue
        path = artifact.get("path")
        if isinstance(path, str) and path:
            paths.append(path)
    return paths


def _write_plain_artifact_paths(
    stdout: TextIO,
    paths: Sequence[str],
    *,
    label: str,
    leading_blank: bool = False,
) -> None:
    if paths and leading_blank:
        stdout.write("\n")
    for path in paths:
        stdout.write(f"{label}: {path}\n")


def _write_plain_warnings(payload: dict[str, object], stderr: TextIO) -> None:
    warnings = payload.get("warnings")
    if not isinstance(warnings, list):
        return
    for warning in warnings:
        if isinstance(warning, str) and warning:
            stderr.write(
                _t(
                    "gsuid.cli.562_25.edb1c72b",
                    ANSI_YELLOW,
                    _plain_warning_text(warning),
                    ANSI_RESET,
                )
            )


def _plain_warning_text(warning: str) -> str:
    return warning


def _payload_with_debug_artifact(
    payload: dict[str, object],
    *,
    request_id: str | None,
    output_dir: str | None,
) -> dict[str, object]:
    result = dict(payload)
    result["artifacts"] = list(_artifact_list(payload))
    if not request_id:
        return result
    debug_payload = _redacted_debug_payload(result)
    content = json.dumps(debug_payload, ensure_ascii=False, indent=2)
    try:
        artifact = ArtifactManager(request_id, output_dir).write_text(
            name="debug-envelope",
            filename="debug-envelope.json",
            content=content,
            description=_t("gsuid.cli.586_24.94d7b91b"),
            media_type="application/json; charset=utf-8",
            kind="debug",
        )
    except OSError as exc:
        warnings = result.setdefault("warnings", [])
        if isinstance(warnings, list):
            warnings.append(_t("gsuid.cli.593_28.d00773a0", type(exc).__name__))
        return result
    result["artifacts"] = [*_artifact_list(result), artifact]
    return result


def _redacted_debug_payload(payload: dict[str, object]) -> dict[str, object]:
    return _redact_value(deepcopy(payload))


def _redact_value(value: object) -> object:
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, item in value.items():
            key_text = str(key)
            result[key_text] = (
                _redacted_secret_value(item) if _sensitive_key(key_text) else _redact_value(item)
            )
        return result
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def _sensitive_key(key: str) -> bool:
    folded = key.casefold()
    return any(part in folded for part in SENSITIVE_KEY_PARTS)


def _redacted_secret_value(value: object) -> object:
    if isinstance(value, str):
        if "authkey=" in value or value.startswith(("http://", "https://")):
            return "[REDACTED_URL]"
        return redact_secret(value)
    if isinstance(value, list):
        return [_redacted_secret_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redacted_secret_value(item) for key, item in value.items()}
    if value is None:
        return None
    return "[REDACTED]"


def _artifact_list(payload: dict[str, object]) -> list[dict[str, object]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    return [artifact for artifact in artifacts if isinstance(artifact, dict)]


def _result_sources(
    result: CommandResult,
    captured_sources: list[dict[str, object]],
) -> list[dict[str, object]]:
    sources = [*captured_sources, *result.sources]
    if result.source is not None:
        sources.append(result.source)
    return sources


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _system_exit_code(exc: SystemExit) -> int:
    if isinstance(exc.code, int):
        return exc.code
    return EXIT_INVALID_INPUT


def _error_context(
    argv: Sequence[str],
    defaults: CliDefaults | None = None,
) -> dict[str, object]:
    defaults = defaults or CliDefaults(
        profile=os.environ.get("GSUID_PROFILE", "default"),
        region=_valid_env("GSUID_REGION", REGION_CHOICES, "auto"),
        format=_valid_env("GSUID_FORMAT", OUTPUT_FORMATS, "json"),
        output_dir=os.environ.get("GSUID_OUTPUT_DIR"),
    )
    argv = _canonicalize_global_options(argv)
    output_format = _global_option_value(argv, "--format")
    region = _global_option_value(argv, "--region")
    return {
        "command": _guess_command(argv),
        "request_id": _option_value(argv, "--request-id") or str(uuid.uuid4()),
        "format": output_format
        if output_format in OUTPUT_FORMATS
        else _safe_output_format(defaults.format),
        "region": region if region in REGION_CHOICES else defaults.region,
        "debug": _context_flag_value(argv, "--debug", "--no-debug", defaults.debug),
        "output_dir": _global_option_value(argv, "--output-dir") or defaults.output_dir,
        "include_details": _context_render_data_enabled(argv, defaults),
    }


def _context_from_args(args: argparse.Namespace) -> dict[str, object]:
    return {
        "command": args.command_name,
        "request_id": args.request_id or str(uuid.uuid4()),
        "format": _safe_output_format(args.format),
        "region": args.region,
        "debug": args.debug,
        "output_dir": args.output_dir,
        "include_details": _safe_render_data_enabled(args),
    }


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _safe_output_format(value: object) -> str:
    return value if isinstance(value, str) and value in OUTPUT_FORMATS else "json"


def _context_flag_value(
    argv: Sequence[str],
    positive: str,
    negative: str,
    default: bool,
) -> bool:
    value = default
    for token in _canonicalize_global_options(argv):
        if token == positive:
            value = True
        elif token == negative:
            value = False
    return value


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
    path = _incomplete_command_path(parser, argv)
    if path is None:
        return False
    _validate_globals_for_help(argv)
    if not path:
        parser.print_help(stdout)
        return True

    path_parser = _parser_for_path(parser, path)
    if path_parser is None:
        return False
    path_parser.print_help(stdout)
    return True


def _write_explicit_help(
    parser: argparse.ArgumentParser,
    argv: Sequence[str],
    stdout: TextIO,
) -> bool:
    if not any(token in {"--help", "-h"} for token in argv):
        return False
    _validate_globals_for_help(argv)
    current = parser
    index = 0
    while index < len(argv):
        token = argv[index]
        option, inline_value = _split_long_option(token)
        if token in {"--help", "-h"}:
            current.print_help(stdout)
            return True
        if option in GLOBAL_VALUE_OPTIONS and _should_hoist_global_option(option, inline_value):
            index += 1 if inline_value is not None else 2
            continue
        if token in HOISTED_GLOBAL_FLAG_OPTIONS:
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        child = _subparser(current, token)
        if child is None:
            if _subparser_action(current) is not None:
                return False
            index += 1
            continue
        current = child
        index += 1
    return False


def _incomplete_command_path(
    parser: argparse.ArgumentParser,
    argv: Sequence[str],
) -> list[str] | None:
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
        index += 1

    if not path:
        return path
    path_parser = _parser_for_path(parser, path)
    if path_parser is None:
        return None
    if path_parser.get_default("handler") is not None:
        return None
    return path if _subparser_action(path_parser) is not None else None


def _parser_for_path(
    parser: argparse.ArgumentParser,
    path: Sequence[str],
) -> argparse.ArgumentParser | None:
    current = parser
    for token in path:
        child = _subparser(current, token)
        if child is None:
            return None
        current = child
    return current


def _subparser(parser: argparse.ArgumentParser, name: str) -> argparse.ArgumentParser | None:
    action = _subparser_action(parser)
    if action is None:
        return None
    return action.choices.get(name)


def _subparser_action(
    parser: argparse.ArgumentParser,
) -> argparse._SubParsersAction | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
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
        "--region": REGION_CHOICES,
        "--format": OUTPUT_FORMATS,
        "--cache": CACHE_POLICIES,
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
    if option == "--render":
        normalize_render_modes(value)


def _context_render_data_enabled(
    argv: Sequence[str],
    defaults: CliDefaults | None = None,
) -> bool:
    values = _global_option_values(argv, "--render")
    if not values:
        if defaults is not None and defaults.render is not None:
            return _safe_render_data_enabled(defaults.render)
        return True
    return _safe_render_data_enabled(values)


def _safe_render_data_enabled(value: object) -> bool:
    try:
        if hasattr(value, "render"):
            return render_data_enabled(value)
        return "data" in normalize_render_modes(value)
    except CliError:
        return False


def _global_option_values(argv: Sequence[str], option: str) -> list[str]:
    argv = _canonicalize_global_options(argv)
    values: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token.startswith(f"{option}="):
            values.append(token.split("=", 1)[1])
            index += 1
            continue
        if token == option and index + 1 < len(argv):
            values.append(argv[index + 1])
            index += 2
            continue
        if token in GLOBAL_VALUE_OPTIONS:
            index += 2
            continue
        if token in GLOBAL_FLAG_OPTIONS:
            index += 1
            continue
        if not token.startswith("-"):
            return values
        index += 1
    return values


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
