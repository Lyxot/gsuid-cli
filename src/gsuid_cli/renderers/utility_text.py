from __future__ import annotations

import shlex
from collections.abc import Mapping, Sequence

from gsuid_cli.renderers._text_helpers import (
    _finish,
    _join,
    _mapping,
    _mapping_list,
    _nullable,
    _text,
    _yes_no,
)
from gsuid_cli.text import t as _t


def render_meta_command_text(command: str, data: Mapping[str, object]) -> str:
    if command == "meta.version":
        return _finish(
            [
                _t("gsuid.renderers.utility_text.21_16.4cb4e572"),
                _t("gsuid.renderers.utility_text.22_16.f81526cd", _text(data.get("package"))),
                _t("gsuid.renderers.utility_text.23_16.738a873d", _text(data.get("version"))),
                (
                    f"Python: {_text(data.get('python_implementation'))} "
                    f"{_text(data.get('python_version'))}"
                ),
                f"Git: {_nullable(data.get('git_revision'))}",
            ]
        )
    if command == "meta.paths":
        lines = [_t("gsuid.renderers.utility_text.32_17.ddbc01a3")]
        for key, label in _PATH_LABELS:
            lines.append(f"{label}: {_text(data.get(key))}")
        return _finish(lines)
    if command == "meta.capabilities":
        commands = _mapping_list(data.get("commands"))
        lines = [
            _t("gsuid.renderers.utility_text.39_12.e0ac46f4"),
            _t("gsuid.renderers.utility_text.40_12.1ac6c192", len(commands)),
            _t("gsuid.renderers.utility_text.41_12.86d0f08a", _join(data.get("regions"))),
            _t("gsuid.renderers.utility_text.42_12.c3a3a4eb", _join(data.get("formats"))),
            _t("gsuid.renderers.utility_text.43_12.812aa539", _text(data.get("default_format"))),
            "",
            _t("gsuid.renderers.utility_text.45_12.0a85fd73"),
        ]
        for item in commands:
            lines.append(
                _t(
                    "gsuid.renderers.utility_text.49_16.23cd0c6a",
                    _text(item.get("command")),
                    _text(item.get("auth")),
                    _join(item.get("render")),
                )
            )
        return _finish(lines)
    if command == "meta.schema":
        commands = data.get("commands")
        if isinstance(commands, Mapping):
            return _finish(
                [
                    _t("gsuid.renderers.utility_text.58_17.a3d6a4dd"),
                    _t("gsuid.renderers.utility_text.40_12.1ac6c192", len(commands)),
                    _t("gsuid.renderers.utility_text.57_78.0f347f90"),
                ]
            )
        lines = [
            _t("gsuid.renderers.utility_text.58_17.a3d6a4dd"),
            _t("gsuid.renderers.utility_text.58_33.84ac991f", _text(data.get("command"))),
        ]
        success = _mapping(data.get("success"))
        error = _mapping(data.get("error"))
        if success:
            lines.append(
                _t("gsuid.renderers.utility_text.62_25.d6e42cff", _join(success.get("required")))
            )
        if error:
            lines.append(
                _t("gsuid.renderers.utility_text.64_25.51cbc90f", _join(error.get("required")))
            )
        return _finish(lines)
    if command == "meta.errors":
        errors = _mapping_list(data.get("errors"))
        lines = [
            _t("gsuid.renderers.utility_text.68_17.e08c1d4f"),
            _t("gsuid.renderers.challenge.text.186_8.a63927f2", len(errors)),
        ]
        if errors:
            lines.extend(["", _t("gsuid.renderers.utility_text.70_30.5c0a00e8")])
        for item in errors:
            lines.append(
                _t(
                    "gsuid.renderers.utility_text.73_16.0cfc3020",
                    _text(item.get("code")),
                    _text(item.get("exit_code")),
                    _yes_no(item.get("retryable")),
                )
            )
        return _finish(lines)
    if command == "meta.doctor":
        return _render_checks(_t("gsuid.renderers.utility_text.79_30.e22545cb"), data)
    return _finish(
        [
            _t("gsuid.renderers.utility_text.80_20.ee1790db"),
            _t("gsuid.renderers.utility_text.58_33.84ac991f", command),
        ]
    )


def render_batch_command_text(command: str, data: Mapping[str, object]) -> str:
    if command == "batch.plan":
        steps = _mapping_list(data.get("steps"))
        lines = [
            _t("gsuid.renderers.utility_text.87_12.514a727b"),
            _t("gsuid.renderers.gacha.188_21.1133624e", _text(data.get("file"))),
            _t(
                "gsuid.renderers.gacha.184_8.82609e71",
                _t("gsuid.common.valid_all")
                if data.get("valid")
                else _t("gsuid.common.error_present"),
            ),
            _t(
                "gsuid.renderers.utility_text.90_12.00a71eb9",
                _text(data.get("count")),
                _text(data.get("error_count")),
            ),
        ]
        if steps:
            lines.extend(["", _t("gsuid.renderers.utility_text.93_30.6d70eac4")])
        for step in steps:
            index = _text(step.get("index"))
            row_id = _suffix_id(step.get("id"))
            status = (
                _t("gsuid.renderers.local_auth.266_17.ad385d38")
                if step.get("valid")
                else _t("gsuid.renderers.utility_text.99_54.eb645ab4")
            )
            lines.append(f"  - #{index}{row_id}: {status}，{_text(step.get('command'))}")
            request_id = _text(step.get("request_id"))
            if request_id != "-":
                lines.append(_t("gsuid.renderers.utility_text.104_29.580788eb", request_id))
            _append_argv(lines, step.get("argv"))
            error = _mapping(step.get("error"))
            if error:
                lines.append(
                    _t(
                        "gsuid.renderers.utility_text.108_29.1954b9e4",
                        _text(error.get("code")),
                        _text(error.get("message")),
                    )
                )
        return _finish(lines)

    results = _mapping_list(data.get("results"))
    lines = [
        _t("gsuid.renderers.utility_text.113_8.5d7a8221"),
        _t("gsuid.renderers.gacha.188_21.1133624e", _text(data.get("file"))),
        (
            _t(
                "gsuid.renderers.utility_text.116_12.e5719835",
                _text(data.get("count")),
                _text(data.get("ok_count")),
                _text(data.get("error_count")),
            )
        ),
    ]
    if results:
        lines.extend(["", _t("gsuid.renderers.progress.text.116_26.b2957dbc")])
    for result in results:
        payload = _mapping(result.get("payload"))
        ok = bool(payload.get("ok"))
        index = _text(result.get("index"))
        row_id = _suffix_id(result.get("id"))
        lines.append(
            _t(
                "gsuid.renderers.utility_text.129_12.dd881e6d",
                index,
                row_id,
                _t("gsuid.common.success") if ok else _t("gsuid.common.failed"),
                _text(result.get("exit_code")),
                _text(payload.get("command")),
            )
        )
        _append_argv(lines, result.get("argv"))
        if not ok:
            error = _mapping(payload.get("error"))
            if error:
                lines.append(
                    _t(
                        "gsuid.renderers.utility_text.108_29.1954b9e4",
                        _text(error.get("code")),
                        _text(error.get("message")),
                    )
                )
        stderr = _text(result.get("stderr"))
        if stderr != "-":
            lines.append(_t("gsuid.renderers.utility_text.141_25.64a9411f", stderr))
    return _finish(lines)


def render_cache_clear_text(data: Mapping[str, object]) -> str:
    lines = [
        _t("gsuid.renderers.utility_text.147_8.7dc4dae5"),
        _t("gsuid.renderers.utility_text.148_8.76d5f942", _scope_label(data.get("scope"))),
        _t("gsuid.renderers.utility_text.149_8.b71df350", _text(data.get("removed_files"))),
        _t("gsuid.renderers.utility_text.150_8.b3e5e2f3", _text(data.get("removed_dirs"))),
    ]
    cleared = _mapping_list(data.get("cleared"))
    if cleared:
        lines.extend(["", _t("gsuid.renderers.utility_text.154_26.6e139730")])
    for item in cleared:
        lines.append(
            _t(
                "gsuid.renderers.utility_text.157_12.2d2fce35",
                _scope_label(item.get("scope")),
                _text(item.get("removed_files")),
                _text(item.get("removed_dirs")),
            )
        )
        lines.append(_t("gsuid.renderers.utility_text.161_21.92cd2d6e", _text(item.get("path"))))
    return _finish(lines)


def render_cache_size_text(data: Mapping[str, object]) -> str:
    lines = [
        _t("gsuid.renderers.utility_text.167_8.f05934a4"),
        _t("gsuid.renderers.utility_text.148_8.76d5f942", _scope_label(data.get("scope"))),
        _t("gsuid.renderers.utility_text.169_8.3e5d010d", _text(data.get("size"))),
        _t(
            "gsuid.renderers.utility_text.170_8.4988fbad",
            _text(data.get("files")),
            _text(data.get("dirs")),
        ),
    ]
    entries = _mapping_list(data.get("entries"))
    if entries:
        lines.extend(["", _t("gsuid.renderers.utility_text.154_26.6e139730")])
    for item in entries:
        lines.append(
            _t(
                "gsuid.renderers.utility_text.177_12.0754c33f",
                _scope_label(item.get("scope")),
                _text(item.get("size")),
                _text(item.get("files")),
                _text(item.get("dirs")),
            )
        )
        lines.append(_t("gsuid.renderers.utility_text.161_21.92cd2d6e", _text(item.get("path"))))
    return _finish(lines)


def render_monitor_once_text(data: Mapping[str, object]) -> str:
    return _render_checks(_t("gsuid.renderers.utility_text.187_26.fa5cbe6b"), data)


def _render_checks(title: str, data: Mapping[str, object]) -> str:
    checks = _mapping_list(data.get("checks"))
    lines = [
        title,
        _t("gsuid.renderers.gacha.184_8.82609e71", _status_label(data.get("status"))),
        _t("gsuid.renderers.utility_text.192_68.a9447ece", len(checks)),
    ]
    thresholds = _mapping(data.get("thresholds"))
    if thresholds:
        lines.append(
            _t(
                "gsuid.renderers.utility_text.196_12.53a23fff",
                _text(thresholds.get("min_free_mb")),
                _nullable(thresholds.get("max_asset_cache_files")),
                _nullable(thresholds.get("max_artifact_files")),
            )
        )
    if checks:
        lines.extend(["", _t("gsuid.renderers.utility_text.202_26.51b7c8f3")])
    for check in checks:
        lines.append(
            f"  - {_text(check.get('name'))}: "
            f"{_status_label(check.get('status'))}，"
            f"{_check_message(check)}"
        )
        details = _mapping(check.get("details"))
        path = _text(details.get("path"))
        if path != "-":
            lines.append(_t("gsuid.renderers.utility_text.161_21.92cd2d6e", path))
    return _finish(lines)


def _check_message(check: Mapping[str, object]) -> str:
    name = str(check.get("name") or "")
    message = str(check.get("message") or "")
    value = check.get("value")
    threshold = check.get("threshold")
    if name == "storage.free_mb":
        return _t("gsuid.renderers.utility_text.222_15.613d15f1", value, threshold)
    if name == "cache.asset_files":
        return _t("gsuid.renderers.utility_text.224_15.ceb02b81", value, threshold)
    if name == "artifacts.files":
        return _t("gsuid.renderers.utility_text.226_15.bb8e3d40", value, threshold)
    if message == "path exists":
        return _t("gsuid.renderers.utility_text.228_15.feddc4eb")
    if message == "path does not exist":
        return _t("gsuid.renderers.utility_text.230_15.6d97c12d")
    if message == "asset cache directory exists":
        return _t("gsuid.renderers.utility_text.232_15.98e67b13")
    if message == "asset cache directory has not been created yet":
        return _t("gsuid.renderers.utility_text.234_15.0a979957")
    if message == "keyring backend is available":
        backend = _mapping(check.get("details")).get("backend")
        return _t("gsuid.renderers.utility_text.237_15.90e011f6", _text(backend))
    if message == "public data endpoint is reachable":
        return _t("gsuid.renderers.utility_text.239_15.2d0fd84c")
    return _text(message)


def _append_argv(lines: list[str], value: object) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return
    argv = [str(item) for item in value]
    if argv:
        lines.append(_t("gsuid.renderers.utility_text.248_21.67b58e8d", shlex.join(argv)))


def _suffix_id(value: object) -> str:
    text = _text(value)
    return "" if text == "-" else f" {text}"


def _scope_label(value: object) -> str:
    return {
        "all": _t("gsuid.renderers.events.text.10_11.778fc8f9"),
        "http": _t("gsuid.renderers.utility_text.259_16.b52d79d7"),
        "assets": _t("gsuid.renderers.utility_text.260_18.fadfa411"),
        "artifacts": _t("gsuid.renderers.utility_text.261_21.0fc6c7ff"),
        "icons": _t("gsuid.renderers.utility_text.262_17.1f24c1e5"),
        "maps": _t("gsuid.renderers.utility_text.263_16.46e1efeb"),
        "wiki": _t("gsuid.renderers.utility_text.264_16.a1944284"),
    }.get(str(value), _text(value))


def _status_label(value: object) -> str:
    return {
        "ok": _t("gsuid.renderers.utility_text.269_18.f78d037a"),
        "warn": _t("gsuid.renderers.utility_text.269_36.5521e368"),
        "error": _t("gsuid.renderers.utility_text.269_55.b859c7be"),
    }.get(str(value), _text(value))


def _sequence(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return list(value)


_PATH_LABELS = (
    ("home", _t("gsuid.renderers.utility_text.279_13.ec378e18")),
    ("config", _t("gsuid.renderers.utility_text.280_15.51595603")),
    ("state", _t("gsuid.renderers.utility_text.281_14.5f7d5b62")),
    ("data", _t("gsuid.renderers.utility_text.282_13.9742cd9f")),
    ("cache", _t("gsuid.renderers.utility_text.283_14.21128183")),
    ("cache_assets", _t("gsuid.renderers.utility_text.284_21.b62c5c4a")),
    ("artifacts", _t("gsuid.renderers.utility_text.285_18.b425e5a0")),
    ("logs", _t("gsuid.renderers.utility_text.286_13.5dc77ebd")),
)
