from __future__ import annotations

import argparse
import io
import json
import shlex
import sys
from pathlib import Path
from typing import Any

from gsuid_cli.core.envelope import error_envelope
from gsuid_cli.core.errors import EXIT_INTERNAL_BUG, EXIT_INVALID_INPUT, CliError
from gsuid_cli.core.models import CommandResult

CAPABILITIES = [
    {
        "command": "batch.run",
        "description": "Execute JSONL batch commands and return nested envelopes.",
        "auth": "mixed",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "mixed",
    },
    {
        "command": "batch.plan",
        "description": "Validate JSONL batch commands without executing them.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
]


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    batch = groups.add_parser("batch", help="Execute or validate command batches.")
    commands = batch.add_subparsers(dest="batch_command", required=True, metavar="<command>")

    run_parser = commands.add_parser("run", help="Execute a JSONL command batch.")
    run_parser.add_argument("--file", required=True)
    run_parser.set_defaults(handler=run_command, command_name="batch.run")

    plan = commands.add_parser("plan", help="Validate a JSONL command batch.")
    plan.add_argument("--file", required=True)
    plan.set_defaults(handler=plan_command, command_name="batch.plan")


def run_command(args: argparse.Namespace) -> CommandResult:
    rows = _read_rows(args.file)
    results = []
    ok_count = 0
    for index, row in enumerate(rows):
        request_id = _request_id(row, args.request_id, index)
        try:
            argv = _normalized_argv(_row_argv(row), request_id=request_id)
            exit_code, payload, stderr = _run_inner(argv)
            ok = bool(payload.get("ok")) if isinstance(payload, dict) else False
            if ok:
                ok_count += 1
            results.append(
                {
                    "index": index,
                    "id": row.get("id") if isinstance(row, dict) else None,
                    "argv": argv,
                    "exit_code": exit_code,
                    "stderr": stderr,
                    "payload": payload,
                }
            )
        except CliError as exc:
            payload = error_envelope(
                command=_guess_command(row),
                request_id=request_id,
                duration_ms=0,
                error=exc,
                region=args.region,
            )
            results.append(
                {
                    "index": index,
                    "id": row.get("id") if isinstance(row, dict) else None,
                    "argv": _error_argv(row),
                    "exit_code": exc.exit_code,
                    "stderr": "",
                    "payload": payload,
                }
            )
    return CommandResult(
        data={
            "mode": "run",
            "file": args.file,
            "count": len(results),
            "ok_count": ok_count,
            "error_count": len(results) - ok_count,
            "results": results,
        }
    )


def plan_command(args: argparse.Namespace) -> CommandResult:
    rows = _read_rows(args.file)
    steps = []
    for index, row in enumerate(rows):
        request_id = _request_id(row, args.request_id, index)
        try:
            argv = _normalized_argv(_row_argv(row), request_id=request_id)
            parsed = _parse_inner(argv)
            steps.append(
                {
                    "index": index,
                    "id": row.get("id") if isinstance(row, dict) else None,
                    "argv": argv,
                    "command": parsed.command_name,
                    "request_id": parsed.request_id,
                    "valid": True,
                    "error": None,
                }
            )
        except CliError as exc:
            steps.append(
                {
                    "index": index,
                    "id": row.get("id") if isinstance(row, dict) else None,
                    "argv": _error_argv(row),
                    "command": _guess_command(row),
                    "request_id": request_id,
                    "valid": False,
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                    },
                }
            )
    error_count = len([step for step in steps if not step["valid"]])
    return CommandResult(
        data={
            "mode": "plan",
            "file": args.file,
            "valid": error_count == 0,
            "count": len(steps),
            "error_count": error_count,
            "steps": steps,
        }
    )


def _read_rows(file: str) -> list[object]:
    try:
        text = sys.stdin.read() if file == "-" else Path(file).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CliError(
            "INVALID_ARGUMENT",
            "batch file is not readable",
            EXIT_INVALID_INPUT,
            {"file": file},
        ) from exc
    rows = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            rows.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise CliError(
                "INVALID_ARGUMENT",
                "batch file must contain one JSON object per line",
                EXIT_INVALID_INPUT,
                {"line": line_number},
            ) from exc
    return rows


def _row_argv(row: object) -> list[str]:
    if not isinstance(row, dict):
        raise CliError(
            "INVALID_ARGUMENT",
            "batch row must be a JSON object",
            EXIT_INVALID_INPUT,
        )
    raw = row.get("argv", row.get("command"))
    if isinstance(raw, str):
        return shlex.split(raw)
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        return list(raw)
    raise CliError(
        "INVALID_ARGUMENT",
        "batch row must include argv as a string array or command as a string",
        EXIT_INVALID_INPUT,
        {"id": row.get("id")},
    )


def _normalized_argv(argv: list[str], *, request_id: str) -> list[str]:
    from gsuid_cli.cli import _canonicalize_global_options, _global_option_value

    normalized = _without_global_output_format(_canonicalize_global_options(argv))
    if _global_option_value(normalized, "--request-id") is None:
        normalized = ["--request-id", request_id, *normalized]
    normalized = ["--format", "json", *normalized]
    if _argv_command(normalized).startswith("batch."):
        raise CliError(
            "INVALID_ARGUMENT",
            "batch commands cannot be nested",
            EXIT_INVALID_INPUT,
        )
    return normalized


def _without_global_output_format(argv: list[str]) -> list[str]:
    from gsuid_cli.cli import OUTPUT_FORMATS, _split_long_option

    result = []
    index = 0
    while index < len(argv):
        option, inline_value = _split_long_option(argv[index])
        if option == "--format":
            value = inline_value
            if value is None and index + 1 < len(argv):
                value = argv[index + 1]
            if value in OUTPUT_FORMATS:
                index += 1 if inline_value is not None else 2
                continue
        result.append(argv[index])
        index += 1
    return result


def _request_id(row: object, batch_request_id: str, index: int) -> str:
    if isinstance(row, dict) and isinstance(row.get("request_id"), str):
        return str(row["request_id"])
    return f"{batch_request_id}-{index}"


def _error_argv(row: object) -> list[str]:
    if not isinstance(row, dict):
        return []
    raw = row.get("argv", row.get("command"))
    if isinstance(raw, str):
        return shlex.split(raw)
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        return list(raw)
    return []


def _run_inner(argv: list[str]) -> tuple[int, dict[str, object], str]:
    from gsuid_cli.cli import run

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = run(argv, stdout=stdout, stderr=stderr)
    try:
        payload = json.loads(stdout.getvalue())
    except json.JSONDecodeError as exc:
        raise CliError(
            "INTERNAL_ERROR",
            "inner command did not produce a JSON envelope",
            EXIT_INTERNAL_BUG,
            {"argv": argv},
        ) from exc
    return exit_code, payload, stderr.getvalue()


def _parse_inner(argv: list[str]) -> Any:
    from gsuid_cli.cli import _validate_runtime_defaults, parse_argv

    parsed = parse_argv(argv)
    _validate_runtime_defaults(parsed)
    return parsed


def _guess_command(row: object) -> str:
    if not isinstance(row, dict):
        return "batch.item"
    try:
        argv = _row_argv(row)
    except CliError:
        return "batch.item"
    return _argv_command(argv)


def _argv_command(argv: list[str]) -> str:
    from gsuid_cli.cli import _guess_command as guess_command

    return guess_command(argv)
