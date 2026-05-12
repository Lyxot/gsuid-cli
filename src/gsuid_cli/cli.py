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
from gsuid_cli.core.envelope import error_envelope, success_envelope
from gsuid_cli.core.errors import (
    EXIT_INTERNAL_BUG,
    EXIT_INTERRUPTED,
    EXIT_INVALID_INPUT,
    CliError,
)
from gsuid_cli.core.http import begin_source_capture, end_source_capture
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.render import normalize_render_modes, render_data_enabled
from gsuid_cli.core.secrets import redact_secret

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
OUTPUT_FORMATS = {"json", "pretty-json", "plain"}
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
    "--all": "包含通常省略的行。",
    "--app-id": "来自 auth.qrcode.start 的二维码登录 app id。",
    "--artifact-source-character": "要复用其圣遗物进行对比的角色。",
    "--banner": "要汇总的祈愿卡池分类。",
    "--build": "要对比的已保存或已缓存的配置名称。",
    "--cache": "处理 JSON 和静态资源的缓存策略。",
    "--character": "角色名称或 ID。",
    "--check": "要运行的诊断检查分类。",
    "--constellation": "命之座名称、序号或等级。",
    "--cookie": "用于此次凭据写入的 Cookie 值。",
    "--cookie-file": "从文件读取 Cookie 值。",
    "--cookie-stdin": "从标准输入读取 Cookie 值。",
    "--date": "请求数据的日历日期。",
    "--day": "工作日名称或数字。",
    "--debug": "在错误详情中包含调试诊断信息。",
    "--deck-id": "七圣召唤牌组 ID。",
    "--default": "将创建或选择的记录标记为默认。",
    "--device": "来自 auth.qrcode.start 的二维码登录设备 ID。",
    "--file": "输入文件路径。",
    "--floor": "挑战层数。",
    "--force": "在支持的情况下绕过本地时效性或防重复快捷策略。",
    "--full": "使用较大的完全刷新分页限制。",
    "--id": "请求行的数据源 ID。",
    "--item": "物品名称或 ID。",
    "--label": "本地账号标签。",
    "--level": "派生 wiki 数据的目标等级。",
    "--limit": "返回的最大行数。",
    "--login-timeout": "二维码登录最大等待时间（秒）。",
    "--map": "地图来源或地图 ID。",
    "--material": "材料名称或 ID。",
    "--max-artifact-files": "当产物文件超过此数量时发出警告。",
    "--max-asset-cache-files": "当静态资源缓存文件超过此数量时发出警告。",
    "--min-free-mb": "当可用磁盘空间低于此 MB 数时发出警告。",
    "--name": "此命令的名称值。",
    "--nearby": "要包含的附近排名行数。",
    "--output": "输出文件路径。",
    "--output-dir": "产物输出目录。",
    "--page": "结果页码。",
    "--poll-interval": "二维码登录轮询间隔（秒）。",
    "--profile": "本地配置文件名称。",
    "--query": "搜索查询。",
    "--quiet": "抑制非结果的 stderr 日志。",
    "--region": "目标 API 区服。",
    "--render": "逗号分隔的渲染模式。重复使用以选择多个模式。",
    "--request-id": "调用者提供的请求 ID。",
    "--scope": "操作范围。",
    "--season": "挑战赛季选择器。",
    "--sort": "排序字段。",
    "--source": "数据源提供者。",
    "--stoken": "用于此次凭据写入的 Stoken 值。",
    "--stoken-file": "从文件读取 Stoken 值。",
    "--stoken-stdin": "从标准输入读取 Stoken 值。",
    "--talent": "天赋名称或 ID。",
    "--ticket": "来自 auth.qrcode.start 的二维码登录 ticket。",
    "--timeout": "HTTP 超时时间（秒）。",
    "--uid": "目标原神 UID。覆盖配置文件默认值。",
    "--url": "用于此次凭据写入的安全 URL 值。",
    "--url-file": "从文件读取安全 URL 值。",
    "--url-stdin": "从标准输入读取安全 URL 值。",
    "--version": "游戏或指南版本选择器。",
    "--weapon": "武器名称或 ID。",
}
DEST_HELP = {
    "account_region": "账号 API 区服。",
    "account_uid": "账号原神 UID。",
    "command_uid": "目标原神 UID。覆盖配置文件默认值。",
    "export_format": "祈愿记录导出格式。",
    "format": "标准输出格式。",
    "import_format": "祈愿记录导入格式。",
    "profile_region": "配置文件默认 API 区服。",
    "query": "搜索查询或查找名称。",
}


class GsuidArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliError("INVALID_ARGUMENT", message, EXIT_INVALID_INPUT)


def build_parser() -> argparse.ArgumentParser:
    parser = GsuidArgumentParser(
        prog="gsuid",
        description="面向 Agent 的原神命令行工具。",
        add_help=False,
    )
    parser.add_argument(
        "-h", "--help", action="help", default=argparse.SUPPRESS, help="显示此帮助信息并退出。"
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
        choices=("json", "pretty-json", "plain"),
        default=os.environ.get("GSUID_FORMAT", "json"),
    )
    parser.add_argument("--render", action="append", metavar="data|image|text|all")
    parser.add_argument("--output-dir", default=os.environ.get("GSUID_OUTPUT_DIR"))
    parser.add_argument("--cache", choices=("use", "refresh", "only", "off"), default="use")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--request-id")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}", help="显示版本号并退出。"
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
    captured_sources: list[dict[str, object]] = []

    try:
        parser = build_parser()
        if _write_explicit_help(parser, args_list, stdout):
            return 0
        if _write_incomplete_help(parser, args_list, stdout):
            return 0
        args = parser.parse_args(args_list)
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
        payload = success_envelope(
            command=command,
            request_id=request_id,
            duration_ms=_duration_ms(started),
            data=result.data,
            region=args.region,
            warnings=result.warnings,
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
        context = _context_from_args(args) if "args" in locals() else _error_context(args_list)
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
        context = _error_context(args_list)
        error = CliError("INTERRUPTED", "已中断。", EXIT_INTERRUPTED)
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
        context = _error_context(args_list)
        details = {}
        if context["debug"]:
            details = {"type": type(exc).__name__, "message": str(exc)}
        error = CliError("INTERNAL_ERROR", "内部错误。", EXIT_INTERNAL_BUG, details)
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
        return "此参数的值。"
    return f"{label.capitalize()} 的值。"


def _validate_runtime_defaults(args: argparse.Namespace) -> None:
    if args.format not in OUTPUT_FORMATS:
        raise CliError(
            "INVALID_ARGUMENT",
            f"invalid output format: {args.format}",
            EXIT_INVALID_INPUT,
            {"format": args.format},
        )
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
                label="图片已保存至",
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
                label="图片已保存至",
            )
            return
        stdout.write(json.dumps(payload["data"], ensure_ascii=False, indent=2))
        stdout.write("\n")
        return

    error = payload["error"]
    if isinstance(error, dict):
        stderr.write(f"{error['code']}: {error['message']}\n")


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
            stderr.write(f"{ANSI_YELLOW}警告: {_plain_warning_text(warning)}{ANSI_RESET}\n")


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
            description="带有数据和来源的调试包",
            media_type="application/json; charset=utf-8",
            kind="debug",
        )
    except OSError as exc:
        warnings = result.setdefault("warnings", [])
        if isinstance(warnings, list):
            warnings.append(f"调试产物写入失败: {type(exc).__name__}")
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
        "output_dir": _global_option_value(argv, "--output-dir")
        or os.environ.get("GSUID_OUTPUT_DIR"),
        "include_details": _context_render_data_enabled(argv),
    }


def _context_from_args(args: argparse.Namespace) -> dict[str, object]:
    return {
        "command": args.command_name,
        "request_id": args.request_id or str(uuid.uuid4()),
        "format": args.format,
        "region": args.region,
        "debug": args.debug,
        "output_dir": args.output_dir,
        "include_details": _safe_render_data_enabled(args),
    }


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


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
        "--region": {"cn", "os"},
        "--format": OUTPUT_FORMATS,
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
    if option == "--render":
        normalize_render_modes(value)


def _context_render_data_enabled(argv: Sequence[str]) -> bool:
    values = _global_option_values(argv, "--render")
    if not values:
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
