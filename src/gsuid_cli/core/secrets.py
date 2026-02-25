from __future__ import annotations

import os
from dataclasses import dataclass

import keyring

from gsuid_cli.core.errors import EXIT_AUTH, CliError

SERVICE_PREFIX = "gsuid-cli"


@dataclass(frozen=True)
class CredentialSpec:
    kind: str
    env_var: str
    label: str


CREDENTIALS = {
    "cookie": CredentialSpec("cookie", "GSUID_COOKIE", "cookie"),
    "stoken": CredentialSpec("stoken", "GSUID_STOKEN", "stoken"),
    "gacha_url": CredentialSpec("gacha_url", "GSUID_GACHA_URL", "gacha authkey URL"),
}


class SecretStore:
    def backend_name(self) -> str:
        backend = keyring.get_keyring()
        return f"{type(backend).__module__}.{type(backend).__name__}"

    def get_secret(self, kind: str, uid: str) -> str | None:
        try:
            return keyring.get_password(_service(kind), uid)
        except Exception as exc:
            raise _keyring_error(exc) from exc

    def set_secret(self, kind: str, uid: str, value: str) -> None:
        try:
            keyring.set_password(_service(kind), uid, value)
        except Exception as exc:
            raise _keyring_error(exc) from exc

    def delete_secret(self, kind: str, uid: str) -> bool:
        existing = self.get_secret(kind, uid)
        if existing is None:
            return False
        try:
            keyring.delete_password(_service(kind), uid)
        except Exception as exc:
            raise _keyring_error(exc) from exc
        return True

    def has_secret(self, kind: str, uid: str) -> bool:
        return self.get_secret(kind, uid) is not None


def env_secret(kind: str) -> str | None:
    value = os.environ.get(CREDENTIALS[kind].env_var)
    if value:
        return value
    return None


def redact_secret(value: str) -> str:
    if not value:
        return "[REDACTED]"
    if len(value) <= 8:
        return "[REDACTED]"
    return f"{value[:4]}...{value[-4:]}"


def credential_presence(uid: str, store: SecretStore | None = None) -> dict[str, bool]:
    store = store or SecretStore()
    result: dict[str, bool] = {}
    for kind in CREDENTIALS:
        try:
            result[kind] = store.has_secret(kind, uid)
        except CliError:
            result[kind] = False
    return result


def _service(kind: str) -> str:
    return f"{SERVICE_PREFIX}:{kind}"


def _keyring_error(exc: Exception) -> CliError:
    return CliError(
        "KEYRING_UNAVAILABLE",
        "OS keyring is unavailable; stored credentials require keyring support.",
        EXIT_AUTH,
        {"backend_error": type(exc).__name__},
    )
