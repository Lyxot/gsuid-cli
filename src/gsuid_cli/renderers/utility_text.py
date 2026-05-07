from __future__ import annotations

import shlex
import unicodedata
from collections.abc import Mapping, Sequence


def render_meta_command_text(command: str, data: Mapping[str, object]) -> str:
    if command == "meta.version":
        return _finish(
            [
                "CLI版本",
                f"包名: {_text(data.get('package'))}",
                f"版本: {_text(data.get('version'))}",
                (
                    f"Python: {_text(data.get('python_implementation'))} "
                    f"{_text(data.get('python_version'))}"
                ),
                f"Git: {_nullable(data.get('git_revision'))}",
            ]
        )
    if command == "meta.paths":
        lines = ["本地路径"]
        for key, label in _PATH_LABELS:
            lines.append(f"{label}: {_text(data.get(key))}")
        return _finish(lines)
    if command == "meta.capabilities":
        commands = _mapping_list(data.get("commands"))
        lines = [
            "命令能力",
            f"命令数量: {len(commands)}",
            f"地区: {_join(data.get('regions'))}",
            f"输出格式: {_join(data.get('formats'))}",
            f"默认格式: {_text(data.get('default_format'))}",
            "",
            "命令:",
        ]
        for item in commands:
            lines.append(
                f"  - {_text(item.get('command'))}: "
                f"认证 {_text(item.get('auth'))}，"
                f"渲染 {_join(item.get('render'))}"
            )
        return _finish(lines)
    if command == "meta.schema":
        commands = data.get("commands")
        if isinstance(commands, Mapping):
            return _finish(["结构定义", f"命令数量: {len(commands)}", "范围: 全部命令"])
        lines = ["结构定义", f"命令: {_text(data.get('command'))}"]
        success = _mapping(data.get("success"))
        error = _mapping(data.get("error"))
        if success:
            lines.append(f"成功字段: {_join(success.get('required'))}")
        if error:
            lines.append(f"错误字段: {_join(error.get('required'))}")
        return _finish(lines)
    if command == "meta.errors":
        errors = _mapping_list(data.get("errors"))
        lines = ["错误码", f"数量: {len(errors)}"]
        if errors:
            lines.extend(["", "列表:"])
        for item in errors:
            lines.append(
                f"  - {_text(item.get('code'))}: "
                f"退出码 {_text(item.get('exit_code'))}，"
                f"可重试 {_yes_no(item.get('retryable'))}"
            )
        return _finish(lines)
    if command == "meta.doctor":
        return _render_checks("本地诊断", data)
    return _finish(["元信息", f"命令: {command}"])


def render_batch_command_text(command: str, data: Mapping[str, object]) -> str:
    if command == "batch.plan":
        steps = _mapping_list(data.get("steps"))
        lines = [
            "批处理计划",
            f"文件: {_text(data.get('file'))}",
            f"状态: {'全部有效' if data.get('valid') else '存在错误'}",
            f"总数: {_text(data.get('count'))}，错误: {_text(data.get('error_count'))}",
        ]
        if steps:
            lines.extend(["", "步骤:"])
        for step in steps:
            index = _text(step.get("index"))
            row_id = _suffix_id(step.get("id"))
            lines.append(
                f"  - #{index}{row_id}: "
                f"{'有效' if step.get('valid') else '无效'}，"
                f"{_text(step.get('command'))}"
            )
            request_id = _text(step.get("request_id"))
            if request_id != "-":
                lines.append(f"    请求ID: {request_id}")
            _append_argv(lines, step.get("argv"))
            error = _mapping(step.get("error"))
            if error:
                lines.append(f"    错误: {_text(error.get('code'))}: {_text(error.get('message'))}")
        return _finish(lines)

    results = _mapping_list(data.get("results"))
    lines = [
        "批处理执行",
        f"文件: {_text(data.get('file'))}",
        (
            f"总数: {_text(data.get('count'))}，"
            f"成功: {_text(data.get('ok_count'))}，"
            f"失败: {_text(data.get('error_count'))}"
        ),
    ]
    if results:
        lines.extend(["", "结果:"])
    for result in results:
        payload = _mapping(result.get("payload"))
        ok = bool(payload.get("ok"))
        index = _text(result.get("index"))
        row_id = _suffix_id(result.get("id"))
        lines.append(
            f"  - #{index}{row_id}: "
            f"{'成功' if ok else '失败'}，"
            f"退出码 {_text(result.get('exit_code'))}，"
            f"{_text(payload.get('command'))}"
        )
        _append_argv(lines, result.get("argv"))
        if not ok:
            error = _mapping(payload.get("error"))
            if error:
                lines.append(f"    错误: {_text(error.get('code'))}: {_text(error.get('message'))}")
        stderr = _text(result.get("stderr"))
        if stderr != "-":
            lines.append(f"    标准错误: {stderr}")
    return _finish(lines)


def render_cache_clear_text(data: Mapping[str, object]) -> str:
    lines = [
        "缓存清理",
        f"范围: {_scope_label(data.get('scope'))}",
        f"删除文件: {_text(data.get('removed_files'))}",
        f"删除目录: {_text(data.get('removed_dirs'))}",
    ]
    cleared = _mapping_list(data.get("cleared"))
    if cleared:
        lines.extend(["", "明细:"])
    for item in cleared:
        lines.append(
            f"  - {_scope_label(item.get('scope'))}: "
            f"{_text(item.get('removed_files'))} 个文件，"
            f"{_text(item.get('removed_dirs'))} 个目录"
        )
        lines.append(f"    路径: {_text(item.get('path'))}")
    return _finish(lines)


def render_cache_size_text(data: Mapping[str, object]) -> str:
    lines = [
        "缓存大小",
        f"范围: {_scope_label(data.get('scope'))}",
        f"总大小: {_text(data.get('size'))}",
        f"文件: {_text(data.get('files'))}，目录: {_text(data.get('dirs'))}",
    ]
    entries = _mapping_list(data.get("entries"))
    if entries:
        lines.extend(["", "明细:"])
    for item in entries:
        lines.append(
            f"  - {_scope_label(item.get('scope'))}: "
            f"{_text(item.get('size'))}，"
            f"{_text(item.get('files'))} 个文件，"
            f"{_text(item.get('dirs'))} 个目录"
        )
        lines.append(f"    路径: {_text(item.get('path'))}")
    return _finish(lines)


def render_monitor_once_text(data: Mapping[str, object]) -> str:
    return _render_checks("健康检查", data)


def _render_checks(title: str, data: Mapping[str, object]) -> str:
    checks = _mapping_list(data.get("checks"))
    lines = [title, f"状态: {_status_label(data.get('status'))}", f"检查数量: {len(checks)}"]
    thresholds = _mapping(data.get("thresholds"))
    if thresholds:
        lines.append(
            "阈值: "
            f"剩余空间不少于 {_text(thresholds.get('min_free_mb'))} MiB，"
            f"资源缓存文件不超过 {_nullable(thresholds.get('max_asset_cache_files'))}，"
            f"产物文件不超过 {_nullable(thresholds.get('max_artifact_files'))}"
        )
    if checks:
        lines.extend(["", "检查:"])
    for check in checks:
        lines.append(
            f"  - {_text(check.get('name'))}: "
            f"{_status_label(check.get('status'))}，"
            f"{_check_message(check)}"
        )
        details = _mapping(check.get("details"))
        path = _text(details.get("path"))
        if path != "-":
            lines.append(f"    路径: {path}")
    return _finish(lines)


def _check_message(check: Mapping[str, object]) -> str:
    name = str(check.get("name") or "")
    message = str(check.get("message") or "")
    value = check.get("value")
    threshold = check.get("threshold")
    if name == "storage.free_mb":
        return f"剩余 {value} MiB，阈值 {threshold} MiB"
    if name == "cache.asset_files":
        return f"静态资源缓存文件 {value} 个，阈值 {threshold} 个"
    if name == "artifacts.files":
        return f"产物文件 {value} 个，阈值 {threshold} 个"
    if message == "path exists":
        return "路径存在"
    if message == "path does not exist":
        return "路径不存在"
    if message == "asset cache directory exists":
        return "静态资源缓存目录存在"
    if message == "asset cache directory has not been created yet":
        return "静态资源缓存目录尚未创建"
    if message == "keyring backend is available":
        backend = _mapping(check.get("details")).get("backend")
        return f"系统密钥环可用（{_text(backend)}）"
    if message == "public data endpoint is reachable":
        return "公共数据接口可访问"
    return _text(message)


def _append_argv(lines: list[str], value: object) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return
    argv = [str(item) for item in value]
    if argv:
        lines.append(f"    命令: {shlex.join(argv)}")


def _suffix_id(value: object) -> str:
    text = _text(value)
    return "" if text == "-" else f" {text}"


def _scope_label(value: object) -> str:
    return {
        "all": "全部",
        "http": "HTTP响应缓存",
        "assets": "默认资源缓存",
        "artifacts": "产物",
        "icons": "图标",
        "maps": "地图",
        "wiki": "百科数据",
    }.get(str(value), _text(value))


def _status_label(value: object) -> str:
    return {"ok": "正常", "warn": "警告", "error": "错误"}.get(str(value), _text(value))


def _yes_no(value: object) -> str:
    return "是" if bool(value) else "否"


def _nullable(value: object) -> str:
    text = _text(value)
    return "未设置" if text == "-" else text


def _join(value: object) -> str:
    items = [_text(item) for item in _sequence(value)]
    return "、".join(items) if items else "-"


def _text(value: object) -> str:
    if value is None or value == "":
        return "-"
    text = "".join(
        " " if unicodedata.category(char).startswith("C") else char for char in str(value)
    )
    text = " ".join(text.split())
    return text or "-"


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _first_mapping(value: object) -> Mapping[str, object]:
    values = _mapping_list(value)
    return values[0] if values else {}


def _sequence(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return list(value)


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _number_text(value: object) -> str:
    number = _number(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _finish(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"


_PATH_LABELS = (
    ("home", "主目录"),
    ("config", "配置文件"),
    ("state", "状态库"),
    ("data", "数据目录"),
    ("cache", "缓存目录"),
    ("cache_assets", "静态资源缓存"),
    ("artifacts", "产物目录"),
    ("logs", "日志目录"),
)
