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
from gsuid_cli.text import t as _t


def render_profile_command_text(command: str, data: Mapping[str, object]) -> str:
    if command == "profile.list":
        profiles = _mapping_list(data.get("profiles"))
        lines = [
            _t("gsuid.renderers.local_auth.18_17.1ed502df"),
            _t("gsuid.renderers.challenge.text.186_8.a63927f2", len(profiles)),
        ]
        if not profiles:
            lines.extend(["", _t("gsuid.renderers.local_auth.20_30.8b8ca8df")])
            return _finish(lines)
        lines.append("")
        for profile in profiles:
            suffix = (
                _t("gsuid.renderers.local_auth.24_21.b98bde85") if profile.get("default") else ""
            )
            lines.append(f"- {_text(profile.get('name'))}{suffix}")
            _append_profile_fields(lines, profile, indent="  ")
        return _finish(lines)

    profile = _mapping(data.get("profile"))
    name = _text(profile.get("name"))
    lines = [_t("gsuid.renderers.local_auth.31_13.ce59a35c", name)]
    status = _profile_status(command, data)
    if status:
        lines.append(_t("gsuid.renderers.gacha.184_8.82609e71", status))
    _append_profile_fields(lines, profile)
    return _finish(lines)


def render_account_command_text(command: str, data: Mapping[str, object]) -> str:
    if command == "account.list":
        accounts = _mapping_list(data.get("accounts"))
        lines = [
            _t("gsuid.renderers.local_auth.42_17.41f84336"),
            _t("gsuid.renderers.challenge.text.186_8.a63927f2", len(accounts)),
        ]
        if not accounts:
            lines.extend(["", _t("gsuid.renderers.local_auth.44_30.2f798913")])
            return _finish(lines)
        lines.append("")
        for account in accounts:
            label = _account_label(account)
            suffix = (
                _t("gsuid.renderers.local_auth.24_21.b98bde85") if account.get("default") else ""
            )
            lines.append(f"- {label}{suffix}")
            _append_account_fields(lines, account, indent="  ")
        return _finish(lines)

    account = _mapping(data.get("account"))
    lines = [_t("gsuid.renderers.local_auth.55_13.b4a31176", _account_label(account))]
    status = _account_status(command, data)
    if status:
        lines.append(_t("gsuid.renderers.gacha.184_8.82609e71", status))
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
    lines = [_t("gsuid.renderers.local_auth.73_13.39784741", _credential_label(credential_type))]
    uid = _text(data.get("uid"))
    if uid != "-":
        lines.append(f"UID: {uid}")
    lines.append(
        _t("gsuid.renderers.gacha.184_8.82609e71", _status_label(data.get("validity_status")))
    )
    source = _text(data.get("source"))
    if source != "-":
        lines.append(_t("gsuid.renderers.events.text.53_21.15097066", _source_label(source)))
    refreshed_from = _text(data.get("refreshed_from"))
    if refreshed_from != "-":
        lines.append(
            _t(
                "gsuid.renderers.local_auth.cookie_refresh_source",
                _credential_label(refreshed_from),
            )
        )
    storage_backend = _text(data.get("storage_backend"))
    if storage_backend != "-":
        lines.append(_t("gsuid.renderers.local_auth.83_21.12234f1e", storage_backend))
    if "stored" in data:
        lines.append(_t("gsuid.renderers.gacha.202_21.cf53b8f1", _yes_no(data.get("stored"))))
    if "deleted" in data:
        lines.append(_t("gsuid.renderers.local_auth.85_21.0abdec75", _yes_no(data.get("deleted"))))
    lines.append(_t("gsuid.renderers.gacha.219_17.9cfef6ee"))
    return _finish(lines)


def _render_qrcode_text(command: str, data: Mapping[str, object]) -> str:
    lines = [_qrcode_title(command)]
    if command in {"auth.qrcode.start", "auth.qrcode.login"}:
        lines.append(_t("gsuid.commands.auth.275_29.e60edfed"))
    uid = _text(data.get("uid"))
    if uid != "-":
        lines.append(f"UID: {uid}")
    account_id = _text(data.get("account_id"))
    if account_id != "-":
        lines.append(_t("gsuid.renderers.local_auth.99_21.cf0cfd9c", account_id))
    status = _text(data.get("status"))
    if status != "-":
        lines.append(_t("gsuid.renderers.gacha.184_8.82609e71", _status_label(status)))
    confirmed = data.get("confirmed")
    if confirmed is not None:
        lines.append(_t("gsuid.renderers.local_auth.105_21.5d217282", _yes_no(confirmed)))
    credential_types = _credential_types(data.get("credential_types"))
    if credential_types:
        lines.append(_t("gsuid.renderers.local_auth.108_21.1cc72ae4", "、".join(credential_types)))
    storage_backend = _text(data.get("storage_backend"))
    if storage_backend != "-":
        lines.append(_t("gsuid.renderers.local_auth.83_21.12234f1e", storage_backend))
    if data.get("stored") is not None:
        lines.append(_t("gsuid.renderers.gacha.202_21.cf53b8f1", _yes_no(data.get("stored"))))
    lines.append(_t("gsuid.renderers.local_auth.114_17.2812f4cc"))
    lines.append(_t("gsuid.renderers.local_auth.115_17.04be01f6"))
    return _finish(lines)


def _render_device_text(command: str, data: Mapping[str, object]) -> str:
    lines = [_device_title(command)]
    uid = _text(data.get("uid"))
    if uid != "-":
        lines.append(f"UID: {uid}")
    status = data.get("status", data.get("validity_status"))
    if status is not None:
        lines.append(_t("gsuid.renderers.gacha.184_8.82609e71", _status_label(status)))
    if "stored" in data:
        lines.append(_t("gsuid.renderers.gacha.202_21.cf53b8f1", _yes_no(data.get("stored"))))
    if "deleted" in data:
        lines.append(_t("gsuid.renderers.local_auth.85_21.0abdec75", _yes_no(data.get("deleted"))))
    device = _mapping(data.get("device"))
    brand = _text(device.get("brand"))
    model = _text(device.get("model"))
    if brand != "-" or model != "-":
        lines.append(_t("gsuid.renderers.local_auth.135_21.77d3b23f", brand, model).rstrip())
    source = _text(data.get("credential_source"))
    if source != "-":
        lines.append(_t("gsuid.renderers.gacha.137_21.03d4aea9", _source_label(source)))
    storage_backend = _text(data.get("credential_storage_backend"))
    if storage_backend != "-":
        lines.append(_t("gsuid.renderers.local_auth.141_21.32d33571", storage_backend))
    storage = _text(data.get("storage"))
    if storage != "-":
        lines.append(_t("gsuid.renderers.local_auth.144_21.0f0cab9e", storage))
    updated_at = _text(data.get("updated_at"))
    if updated_at != "-":
        lines.append(_t("gsuid.renderers.local_auth.147_21.86b85f57", updated_at))
    lines.append(_t("gsuid.renderers.local_auth.148_17.bd57baad"))
    return _finish(lines)


def _append_profile_fields(
    lines: list[str],
    profile: Mapping[str, object],
    *,
    indent: str = "",
) -> None:
    lines.append(
        _t("gsuid.renderers.local_auth.158_17.369b7a94", indent, _yes_no(profile.get("default")))
    )
    lines.append(
        _t(
            "gsuid.renderers.local_auth.159_17.0168a7c6",
            indent,
            _region_label(profile.get("default_region")),
        )
    )
    lines.append(
        _t(
            "gsuid.renderers.local_auth.160_17.daf56a03",
            indent,
            _nullable_text(profile.get("default_uid")),
        )
    )
    lines.append(
        _t(
            "gsuid.renderers.local_auth.161_17.a9736f7e",
            indent,
            _text(profile.get("account_count")),
        )
    )
    _append_time_fields(lines, profile, indent=indent)


def _append_account_fields(
    lines: list[str],
    account: Mapping[str, object],
    *,
    indent: str = "",
) -> None:
    lines.append(f"{indent}UID: {_text(account.get('uid'))}")
    lines.append(
        _t(
            "gsuid.renderers.local_auth.172_17.1d7c6a7b",
            indent,
            _region_label(account.get("region")),
        )
    )
    label = _nullable_text(account.get("label"))
    if label != _t("gsuid.renderers.text_helpers.54_11.55a04b58"):
        lines.append(_t("gsuid.renderers.local_auth.175_21.6bc79641", indent, label))
    lines.append(
        _t("gsuid.renderers.local_auth.176_17.c73b081d", indent, _yes_no(account.get("default")))
    )
    lines.append(
        _t("gsuid.renderers.local_auth.177_17.3668832c", indent, _account_credentials(account))
    )
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
        lines.append(_t("gsuid.renderers.local_auth.190_21.2994ff01", indent, created_at))
    if updated_at != "-":
        lines.append(_t("gsuid.renderers.local_auth.192_21.2417f239", indent, updated_at))


def _profile_status(command: str, data: Mapping[str, object]) -> str:
    if command == "profile.init":
        return (
            _t("gsuid.renderers.local_auth.197_15.62cfc535")
            if data.get("created")
            else _t("gsuid.renderers.local_auth.197_55.112f9867")
        )
    if command == "profile.default":
        return _t("gsuid.renderers.local_auth.199_15.3b96c80f")
    if command == "profile.delete":
        return _t("gsuid.renderers.local_auth.201_15.fb5fe1e2")
    return _t("gsuid.renderers.local_auth.202_11.ed05538d")


def _account_status(command: str, data: Mapping[str, object]) -> str:
    if command == "account.add":
        return (
            _t("gsuid.renderers.local_auth.197_15.62cfc535")
            if data.get("created")
            else _t("gsuid.renderers.local_auth.197_55.112f9867")
        )
    if command == "account.default":
        return _t("gsuid.renderers.local_auth.199_15.3b96c80f")
    if command == "account.remove":
        return _t("gsuid.renderers.local_auth.201_15.fb5fe1e2")
    return _t("gsuid.renderers.local_auth.202_11.ed05538d")


def _account_credentials(account: Mapping[str, object]) -> str:
    parts = [
        f"Cookie {_saved_label(account.get('has_cookie'))}",
        f"Stoken {_saved_label(account.get('has_stoken'))}",
        _t("gsuid.renderers.local_auth.219_8.715e8a6e", _saved_label(account.get("has_gacha_url"))),
        _t("gsuid.renderers.local_auth.220_8.065e16e8", _saved_label(account.get("has_device"))),
    ]
    return "，".join(parts)


def _account_label(account: Mapping[str, object]) -> str:
    uid = _text(account.get("uid"))
    label = _text(account.get("label"))
    return uid if label == "-" else f"{uid} - {label}"


def _qrcode_title(command: str) -> str:
    return {
        "auth.qrcode.start": _t("gsuid.renderers.local_auth.233_29.f4c00549"),
        "auth.qrcode.poll": _t("gsuid.renderers.local_auth.234_28.c00a1160"),
        "auth.qrcode.complete": _t("gsuid.renderers.local_auth.235_32.49bbb608"),
        "auth.qrcode.login": _t("gsuid.renderers.local_auth.235_32.49bbb608"),
    }.get(command, _t("gsuid.renderers.local_auth.237_19.22e398e5"))


def _device_title(command: str) -> str:
    return {
        "auth.device.set": _t("gsuid.renderers.local_auth.245_19.93270589"),
        "auth.device.test": _t("gsuid.renderers.local_auth.243_28.fc124517"),
        "auth.device.delete": _t("gsuid.renderers.local_auth.244_30.ec1ee6c2"),
    }.get(command, _t("gsuid.renderers.local_auth.245_19.93270589"))


def _credential_types(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_credential_label(str(item)) for item in value if str(item)]


def _credential_label(value: object) -> str:
    return {
        "cookie": "Cookie",
        "stoken": "Stoken",
        "gacha_url": _t("gsuid.renderers.local_auth.258_21.a5bb6bf8"),
        "device": _t("gsuid.renderers.local_auth.259_18.b6f86d39"),
    }.get(str(value), str(value) if value else "-")


def _status_label(value: object) -> str:
    return {
        "stored": _t("gsuid.renderers.local_auth.292_11.cdfab96f"),
        "valid": _t("gsuid.renderers.local_auth.266_17.ad385d38"),
        "refreshed": _t("gsuid.renderers.local_auth.cookie_refreshed"),
        "available": _t("gsuid.renderers.daily.text.222_15.e91365cf"),
        "deleted": _t("gsuid.renderers.local_auth.201_15.fb5fe1e2"),
        "missing": _t("gsuid.renderers.local_auth.292_43.4123f1fa"),
        "created": _t("gsuid.renderers.local_auth.197_15.62cfc535"),
        "init": _t("gsuid.renderers.local_auth.271_16.d9e14206"),
        "scanned": _t("gsuid.renderers.local_auth.272_19.83fa27c0"),
        "confirmed": _t("gsuid.renderers.local_auth.273_21.d9fea67a"),
        "bound": _t("gsuid.renderers.local_auth.274_17.b3addb5e"),
    }.get(str(value), _text(value))


def _source_label(value: object) -> str:
    return {
        "keyring": _t("gsuid.renderers.local_auth.280_19.d5ee082d"),
        "environment": _t("gsuid.renderers.gacha.676_15.8da07705"),
        "stdin": _t("gsuid.renderers.local_auth.282_17.acfe4148"),
        "file": _t("gsuid.renderers.local_auth.283_16.49deaf7d"),
    }.get(str(value), _text(value))


def _region_label(value: object) -> str:
    return {
        "auto": _t("gsuid.renderers.local_auth.288_20.4afad877"),
        "cn": _t("gsuid.renderers.events.text.184_17.ca2c0218"),
        "os": _t("gsuid.renderers.local_auth.288_52.73df937f"),
    }.get(str(value), _text(value))


def _saved_label(value: object) -> str:
    return (
        _t("gsuid.renderers.local_auth.292_11.cdfab96f")
        if bool(value)
        else _t("gsuid.renderers.local_auth.292_43.4123f1fa")
    )
