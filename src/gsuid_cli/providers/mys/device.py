from __future__ import annotations

import json
import random
import string
import time
import uuid

from gsuid_cli.core.errors import EXIT_INVALID_INPUT, CliError
from gsuid_cli.core.http import raise_for_retcode
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.core.secrets import redact_secret
from gsuid_cli.core.state import state_db
from gsuid_cli.providers.mys.auth import (
    _account_id_from_cookie,
    _fp_headers,
    _generate_seed,
    _headers,
    _passport_ds,
)
from gsuid_cli.providers.mys.constants import (
    APP_VERSION,
    DEVICE_LOGIN_PATH,
    GET_FP_URL,
    NEW_BBS_BASE_CN,
    PROVIDER,
    SAVE_DEVICE_PATH,
)


class MysDeviceMixin:
    def device_login(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
        device_payload: dict[str, object],
    ) -> CommandResult:
        ensure_supported_region(region)
        device = self._device_from_payload(device_payload)
        body = _device_login_body(device["device_id"], device["device_info"])
        headers = _device_login_headers(
            cookie=cookie,
            body=body,
            device_id=device["device_id"],
            device_fp=device["device_fp"],
            device_info=device["device_info"],
        )
        login = self.http.request_json(
            "POST",
            f"{NEW_BBS_BASE_CN}{DEVICE_LOGIN_PATH}",
            provider=PROVIDER,
            region=region,
            category="auth.device.set",
            json_body=body,
            headers=headers,
        )
        raise_for_retcode(
            login.payload,
            provider=PROVIDER,
            region=region,
            category="auth.device.set",
            source=login.source,
            debug=self.http.debug,
        )
        save = self.http.request_json(
            "POST",
            f"{NEW_BBS_BASE_CN}{SAVE_DEVICE_PATH}",
            provider=PROVIDER,
            region=region,
            category="auth.device.save",
            json_body=body,
            headers=headers,
        )
        raise_for_retcode(
            save.payload,
            provider=PROVIDER,
            region=region,
            category="auth.device.save",
            source=save.source,
            debug=self.http.debug,
        )
        return CommandResult(
            data={
                "uid": uid,
                "account_id": _account_id_from_cookie(cookie),
                "status": "bound",
                "credential_source": credential_source,
                "credential_storage_backend": storage_backend,
                "device_id": device["device_id"],
                "device_fp": device["device_fp"],
                "device_info": device["device_info"],
                "device": _device_info_summary(device["device_info"]),
                "generated_fp": device["generated_fp"],
                "redacted": {
                    "device_id": redact_secret(device["device_id"]),
                    "device_fp": redact_secret(device["device_fp"]),
                },
                "provider_response": {
                    "device_set": {
                        "retcode": login.payload.get("retcode"),
                        "message": login.payload.get("message"),
                    },
                    "save_device": {
                        "retcode": save.payload.get("retcode"),
                        "message": save.payload.get("message"),
                    },
                },
            },
            source=save.source,
        )

    def _device_headers(self, uid: str) -> dict[str, str]:
        headers = self._device_headers_by_uid.get(uid)
        if headers is None:
            headers = _stored_device_headers(uid, self.http.output_dir)
            if headers is None:
                device_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"gsuid-cli:mys:{uid}")).lower()
                seed_id = str(uuid.uuid4()).lower()
                seed_time = str(int(time.time() * 1000))
                headers = {
                    "x-rpc-device_id": device_id,
                    "x-rpc-device_fp": self._generate_device_fp(device_id, seed_id, seed_time),
                }
            self._device_headers_by_uid[uid] = headers
        return dict(headers)

    def _generate_device_fp(self, device_id: str, seed_id: str, seed_time: str) -> str:
        response = self.http.request_json(
            "POST",
            GET_FP_URL,
            provider=PROVIDER,
            region="cn",
            category="device.fp",
            headers=_fp_headers(),
            json_body=_device_fp_body(device_id, seed_id, seed_time),
        )
        data = response.payload.get("data")
        if isinstance(data, dict) and data.get("device_fp"):
            return str(data["device_fp"])
        return _random_fp()

    def _device_from_payload(self, payload: dict[str, object]) -> dict[str, object]:
        device_id = _device_payload_value(payload, "device_id") or _device_payload_value(
            payload, "deviceId"
        )
        device_fp = _device_payload_value(payload, "fp")
        if device_id and device_fp:
            return {
                "device_id": device_id,
                "device_fp": device_fp,
                "device_info": _device_payload_value(payload, "device_info")
                or _device_payload_value(payload, "deviceInfo")
                or "Unknown/Unknown/Unknown/Unknown",
                "generated_fp": False,
            }

        device_id = str(uuid.uuid4()).lower()
        seed_id = str(uuid.uuid4()).lower()
        seed_time = str(int(time.time() * 1000))
        device_info = _required_device_payload(payload, "deviceFingerprint")
        device_fp = self._generate_device_fp_from_info(
            device_id,
            seed_id,
            seed_time,
            model_name=_required_device_payload(payload, "deviceModel"),
            device=_required_device_payload(payload, "deviceProduct"),
            device_type=_required_device_payload(payload, "deviceName"),
            board=_required_device_payload(payload, "deviceBoard"),
            oaid=_required_device_payload(payload, "oaid"),
            device_info=device_info,
        )
        return {
            "device_id": device_id,
            "device_fp": device_fp,
            "device_info": device_info,
            "generated_fp": True,
        }

    def _generate_device_fp_from_info(
        self,
        device_id: str,
        seed_id: str,
        seed_time: str,
        *,
        model_name: str,
        device: str,
        device_type: str,
        board: str,
        oaid: str,
        device_info: str,
    ) -> str:
        response = self.http.request_json(
            "POST",
            GET_FP_URL,
            provider=PROVIDER,
            region="cn",
            category="device.fp",
            headers=_fp_headers(),
            json_body=_device_fp_body(
                device_id,
                seed_id,
                seed_time,
                model_name=model_name,
                device=device,
                device_type=device_type,
                board=board,
                oaid=oaid,
                device_info=device_info,
            ),
        )
        data = response.payload.get("data")
        if isinstance(data, dict) and data.get("device_fp"):
            return str(data["device_fp"])
        return _random_fp()


def _random_device_id() -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=64))


def _stored_device_headers(uid: str, output_dir: str | None) -> dict[str, str] | None:
    with state_db(output_dir) as conn:
        row = conn.execute(
            "SELECT device_id, device_fp FROM accounts WHERE uid = ?",
            (uid,),
        ).fetchone()
    if row is None or not row["device_id"] or not row["device_fp"]:
        return None
    return {
        "x-rpc-device_id": str(row["device_id"]),
        "x-rpc-device_fp": str(row["device_fp"]),
    }


def _device_payload_value(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_device_payload(payload: dict[str, object], key: str) -> str:
    value = _device_payload_value(payload, key)
    if value is None:
        raise CliError(
            "INVALID_ARGUMENT",
            "device payload is missing a required field",
            EXIT_INVALID_INPUT,
            {"field": key},
        )
    return value


def _device_login_body(device_id: object, device_info: object) -> dict[str, object]:
    brand, model_name = _device_info_parts(str(device_info))
    return {
        "app_version": APP_VERSION,
        "device_id": str(device_id),
        "device_name": f"{brand}{model_name}",
        "os_version": "33",
        "platform": "Android",
        "registration_id": _generate_seed(19),
    }


def _device_login_headers(
    *,
    cookie: str,
    body: dict[str, object],
    device_id: object,
    device_fp: object,
    device_info: object,
) -> dict[str, str]:
    brand, model_name = _device_info_parts(str(device_info))
    return {
        **_headers(cookie),
        "x-rpc-device_id": str(device_id),
        "x-rpc-device_fp": str(device_fp),
        "x-rpc-device_name": f"{brand} {model_name}",
        "x-rpc-device_model": model_name,
        "x-rpc-csm_source": "myself",
        "Referer": "https://app.mihoyo.com",
        "Host": "bbs-api.miyoushe.com",
        "DS": _passport_ds(body=body),
    }


def _device_info_summary(device_info: object) -> dict[str, object]:
    brand, model_name = _device_info_parts(str(device_info))
    return {
        "brand": brand,
        "model": model_name,
        "has_device_info": bool(str(device_info).strip()),
    }


def _device_info_parts(device_info: str) -> tuple[str, str]:
    parts = [part.strip() for part in device_info.split("/") if part.strip()]
    brand = parts[0] if parts else "Unknown"
    model_name = parts[1] if len(parts) > 1 else brand
    return brand, model_name


def _device_fp_body(
    device_id: str,
    seed_id: str,
    seed_time: str,
    *,
    model_name: str = "PHK110",
    device: str = "PHK110",
    device_type: str = "OP5913L1",
    board: str = "taro",
    oaid: str = "1f1971b188c472f0",
    device_info: str = (
        "OnePlus/PHK110/OP5913L1:13/SKQ1.221119.001/T.1328291_b9_41:user/release-keys"
    ),
) -> dict[str, object]:
    # Ported from gsuid_core.utils.api.mys.base_request.generate_fake_fp.
    device_brand = device_info.split("/")[0]
    random_data = random.randint(400000, 600000)
    random_data2 = random.randint(150000, 300000)
    now_ms = int(time.time() * 1000)
    ext_fields = {
        "proxyStatus": 0,
        "isRoot": 1,
        "romCapacity": "512",
        "deviceName": "PrivatePhone",
        "productName": device,
        "romRemain": "491",
        "hostname": "dg02-pool06-kvm82",
        "screenSize": "1264x2640",
        "isTablet": 0,
        "aaid": _generate_id(),
        "model": model_name,
        "brand": device_brand,
        "hardware": "qcom",
        "deviceType": device_type,
        "devId": "REL",
        "serialNumber": "unknown",
        "sdCapacity": random_data,
        "buildTime": "1717740969000",
        "buildUser": "root",
        "simState": 5,
        "ramRemain": str(random_data2),
        "appUpdateTimeDiff": now_ms,
        "deviceInfo": device_info,
        "vaid": _generate_id(),
        "buildType": "user",
        "sdkVersion": "34",
        "ui_mode": "UI_MODE_TYPE_NORMAL",
        "isMockLocation": 0,
        "cpuType": "arm64-v8a",
        "isAirMode": 0,
        "ringMode": 1,
        "chargeStatus": 1,
        "manufacturer": device_brand,
        "emulatorStatus": 0,
        "appMemory": "512",
        "osVersion": "14",
        "vendor": "ChinaUnicom",
        "accelerometer": "-1.3004991x6.38764x7.19103",
        "sdRemain": random_data2,
        "buildTags": "release-keys",
        "packageName": "com.mihoyo.hyperion",
        "networkType": "WiFi",
        "oaid": oaid,
        "debugStatus": 1,
        "ramCapacity": str(random_data),
        "magnetometer": "27.1084x-48.5804x-24.8758",
        "display": f"{model_name}_14.0.0.810(CN01)",
        "appInstallTimeDiff": str(now_ms),
        "packageVersion": "2.20.2",
        "gyroscope": "-0.02543317x0.005725792x0.003195791",
        "batteryStatus": 50,
        "hasKeyboard": 0,
        "board": board,
    }
    return {
        "device_id": _generate_seed(16),
        "seed_id": seed_id,
        "platform": "2",
        "seed_time": seed_time,
        "ext_fields": json.dumps(ext_fields, separators=(",", ":")),
        "app_name": "bbs_cn",
        "bbs_device_id": device_id,
        "device_fp": _random_fp(),
    }


def _generate_id(length: int = 64) -> str:
    return "".join(random.choices(string.digits + string.ascii_uppercase, k=length))


def _random_fp(length: int = 13) -> str:
    return _generate_seed(length)
