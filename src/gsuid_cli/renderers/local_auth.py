from __future__ import annotations

from collections.abc import Mapping

from gsuid_cli.renderers._text_helpers import (
    _finish,
    _mapping,
    _mapping_list,
    _nullable as _nullable_text,
    _text,
    _yes_no,
)


def render_profile_command_text(command: str, data: Mapping[str, object]) -> str:
    if command == "profile.list":
        profiles = _mapping_list(data.get("profiles"))
        lines = ["本地档案列表", f"数量: {len(profiles)}"]
        if not profiles:
            lines.extend(["", "暂无本地档案"])
            return _finish(lines)
        lines.append("")
        for profile in profiles:
            suffix = "（默认）" if profile.get("default") else ""
            lines.append(f"- {_text(profile.get('name'))}{suffix}")
            _append_profile_fields(lines, profile, indent="  ")
        return _finish(lines)

    profile = _mapping(data.get("profile"))
    name = _text(profile.get("name"))
    lines = [f"本地档案 - {name}"]
    status = _profile_status(command, data)
    if status:
        lines.append(f"状态: {status}")
    _append_profile_fields(lines, profile)
    return _finish(lines)


def render_account_command_text(command: str, data: Mapping[str, object]) -> str:
    if command == "account.list":
        accounts = _mapping_list(data.get("accounts"))
        lines = ["本地账号列表", f"数量: {len(accounts)}"]
        if not accounts:
            lines.extend(["", "暂无本地账号"])
            return _finish(lines)
        lines.append("")
        for account in accounts:
            label = _account_label(account)
            suffix = "（默认）" if account.get("default") else ""
            lines.append(f"- {label}{suffix}")
            _append_account_fields(lines, account, indent="  ")
        return _finish(lines)

    account = _mapping(data.get("account"))
    lines = [f"本地账号 - {_account_label(account)}"]
    status = _account_status(command, data)
    if status:
        lines.append(f"状态: {status}")
    _append_account_fields(lines, account)
    return _finish(lines)


def render_auth_command_text(command: str, data: Mapping[str, object]) -> str:
    if command.startswith("auth.qrcode."):
        return _render_qrcode_text(command, data)
    if command.startswith("auth.device."):
        return _render_device_text(command, data)
    return _render_credential_text(data)


def _render_credential_text(data: Mapping[str, object]) -> str:
    credential_type = _text(data.get("credential_type"))
    lines = [f"认证凭据 - {_credential_label(credential_type)}"]
    uid = _text(data.get("uid"))
    if uid != "-":
        lines.append(f"UID: {uid}")
    lines.append(f"状态: {_status_label(data.get('validity_status'))}")
    source = _text(data.get("source"))
    if source != "-":
        lines.append(f"来源: {_source_label(source)}")
    storage_backend = _text(data.get("storage_backend"))
    if storage_backend != "-":
        lines.append(f"存储: {storage_backend}")
    if "deleted" in data:
        lines.append(f"删除: {_yes_no(data.get('deleted'))}")
    lines.append("内容: 已隐藏")
    return _finish(lines)


def _render_qrcode_text(command: str, data: Mapping[str, object]) -> str:
    lines = [_qrcode_title(command)]
    if command in {"auth.qrcode.start", "auth.qrcode.login"}:
        lines.append("请使用米游社APP扫码登录")
    uid = _text(data.get("uid"))
    if uid != "-":
        lines.append(f"UID: {uid}")
    account_id = _text(data.get("account_id"))
    if account_id != "-":
        lines.append(f"米游社账号: {account_id}")
    status = _text(data.get("status"))
    if status != "-":
        lines.append(f"状态: {_status_label(status)}")
    confirmed = data.get("confirmed")
    if confirmed is not None:
        lines.append(f"确认: {_yes_no(confirmed)}")
    credential_types = _credential_types(data.get("credential_types"))
    if credential_types:
        lines.append(f"已保存凭据: {'、'.join(credential_types)}")
    storage_backend = _text(data.get("storage_backend"))
    if storage_backend != "-":
        lines.append(f"存储: {storage_backend}")
    if data.get("stored") is not None:
        lines.append(f"保存: {_yes_no(data.get('stored'))}")
    lines.append("登录链接: 已隐藏")
    lines.append("会话凭据: 已隐藏")
    return _finish(lines)


def _render_device_text(command: str, data: Mapping[str, object]) -> str:
    lines = [_device_title(command)]
    uid = _text(data.get("uid"))
    if uid != "-":
        lines.append(f"UID: {uid}")
    status = data.get("status", data.get("validity_status"))
    if status is not None:
        lines.append(f"状态: {_status_label(status)}")
    if "stored" in data:
        lines.append(f"保存: {_yes_no(data.get('stored'))}")
    if "deleted" in data:
        lines.append(f"删除: {_yes_no(data.get('deleted'))}")
    device = _mapping(data.get("device"))
    brand = _text(device.get("brand"))
    model = _text(device.get("model"))
    if brand != "-" or model != "-":
        lines.append(f"设备: {brand} {model}".rstrip())
    source = _text(data.get("credential_source"))
    if source != "-":
        lines.append(f"凭据来源: {_source_label(source)}")
    storage_backend = _text(data.get("credential_storage_backend"))
    if storage_backend != "-":
        lines.append(f"凭据存储: {storage_backend}")
    storage = _text(data.get("storage"))
    if storage != "-":
        lines.append(f"设备存储: {storage}")
    updated_at = _text(data.get("updated_at"))
    if updated_at != "-":
        lines.append(f"更新时间: {updated_at}")
    lines.append("设备标识: 已隐藏")
    return _finish(lines)


def _append_profile_fields(
    lines: list[str],
    profile: Mapping[str, object],
    *,
    indent: str = "",
) -> None:
    lines.append(f"{indent}默认档案: {_yes_no(profile.get('default'))}")
    lines.append(f"{indent}默认地区: {_region_label(profile.get('default_region'))}")
    lines.append(f"{indent}默认 UID: {_nullable_text(profile.get('default_uid'))}")
    lines.append(f"{indent}账号数量: {_text(profile.get('account_count'))}")
    _append_time_fields(lines, profile, indent=indent)


def _append_account_fields(
    lines: list[str],
    account: Mapping[str, object],
    *,
    indent: str = "",
) -> None:
    lines.append(f"{indent}UID: {_text(account.get('uid'))}")
    lines.append(f"{indent}地区: {_region_label(account.get('region'))}")
    label = _nullable_text(account.get("label"))
    if label != "未设置":
        lines.append(f"{indent}标签: {label}")
    lines.append(f"{indent}默认账号: {_yes_no(account.get('default'))}")
    lines.append(f"{indent}凭据: {_account_credentials(account)}")
    _append_time_fields(lines, account, indent=indent)


def _append_time_fields(
    lines: list[str],
    data: Mapping[str, object],
    *,
    indent: str,
) -> None:
    created_at = _text(data.get("created_at"))
    updated_at = _text(data.get("updated_at"))
    if created_at != "-":
        lines.append(f"{indent}创建时间: {created_at}")
    if updated_at != "-":
        lines.append(f"{indent}更新时间: {updated_at}")


def _profile_status(command: str, data: Mapping[str, object]) -> str:
    if command == "profile.init":
        return "已创建" if data.get("created") else "已更新"
    if command == "profile.default":
        return "已设为默认"
    if command == "profile.delete":
        return "已删除"
    return "当前信息"


def _account_status(command: str, data: Mapping[str, object]) -> str:
    if command == "account.add":
        return "已创建" if data.get("created") else "已更新"
    if command == "account.default":
        return "已设为默认"
    if command == "account.remove":
        return "已删除"
    return "当前信息"


def _account_credentials(account: Mapping[str, object]) -> str:
    parts = [
        f"Cookie {_saved_label(account.get('has_cookie'))}",
        f"Stoken {_saved_label(account.get('has_stoken'))}",
        f"祈愿链接 {_saved_label(account.get('has_gacha_url'))}",
        f"设备 {_saved_label(account.get('has_device'))}",
    ]
    return "，".join(parts)


def _account_label(account: Mapping[str, object]) -> str:
    uid = _text(account.get("uid"))
    label = _text(account.get("label"))
    return uid if label == "-" else f"{uid} - {label}"


def _qrcode_title(command: str) -> str:
    return {
        "auth.qrcode.start": "扫码登录会话",
        "auth.qrcode.poll": "扫码登录状态",
        "auth.qrcode.complete": "扫码登录完成",
        "auth.qrcode.login": "扫码登录完成",
    }.get(command, "扫码登录")


def _device_title(command: str) -> str:
    return {
        "auth.device.set": "设备绑定",
        "auth.device.test": "设备绑定状态",
        "auth.device.delete": "设备绑定删除",
    }.get(command, "设备绑定")


def _credential_types(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_credential_label(str(item)) for item in value if str(item)]


def _credential_label(value: object) -> str:
    return {
        "cookie": "Cookie",
        "stoken": "Stoken",
        "gacha_url": "祈愿链接",
        "device": "设备信息",
    }.get(str(value), str(value) if value else "-")


def _status_label(value: object) -> str:
    return {
        "stored": "已保存",
        "valid": "有效",
        "available": "可用",
        "deleted": "已删除",
        "missing": "未保存",
        "created": "已创建",
        "init": "待扫码",
        "scanned": "已扫码",
        "confirmed": "已确认",
        "bound": "已绑定",
    }.get(str(value), _text(value))


def _source_label(value: object) -> str:
    return {
        "keyring": "系统密钥环",
        "environment": "环境变量",
        "stdin": "标准输入",
        "file": "文件",
    }.get(str(value), _text(value))


def _region_label(value: object) -> str:
    return {"cn": "国服", "os": "国际服"}.get(str(value), _text(value))


def _saved_label(value: object) -> str:
    return "已保存" if bool(value) else "未保存"
