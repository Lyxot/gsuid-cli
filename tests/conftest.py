from __future__ import annotations

import os
from collections.abc import Iterator

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

os.environ["GSUID_LANG"] = "zh-CN"


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        try:
            del self.values[(service, username)]
        except KeyError as exc:
            raise PasswordDeleteError("credential not found") from exc


@pytest.fixture(autouse=True)
def memory_keyring() -> Iterator[MemoryKeyring]:
    original = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    try:
        yield backend
    finally:
        keyring.set_keyring(original)
