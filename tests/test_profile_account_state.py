from __future__ import annotations

import io
import json
import os
import stat

from gsuid_cli.cli import run


def test_profile_init_show_and_default(monkeypatch, tmp_path) -> None:
    home = tmp_path / "gsuid-home"
    monkeypatch.setenv("GSUID_HOME", str(home))

    code, payload = _run_json(["--request-id", "req-profile", "profile", "init", "--name", "main"])

    assert code == 0
    assert payload["command"] == "profile.init"
    assert payload["data"]["created"] is True
    assert payload["data"]["profile"]["name"] == "main"
    assert payload["data"]["profile"]["default"] is True

    code, payload = _run_json(["profile", "show", "--name", "main"])

    assert code == 0
    assert payload["data"]["profile"]["default_region"] == "cn"

    code, payload = _run_json(["profile", "default", "--name", "main"])

    assert code == 0
    assert payload["data"]["profile"]["default"] is True

    if os.name != "nt":
        mode = stat.S_IMODE((home / "state.sqlite").stat().st_mode)
        assert mode == 0o600


def test_account_crud_and_profile_default(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    code, payload = _run_json(
        [
            "--profile",
            "main",
            "account",
            "add",
            "--uid",
            "100000001",
            "--label",
            "Traveler",
            "--default",
        ]
    )

    assert code == 0
    assert payload["data"]["created"] is True
    assert payload["data"]["account"]["uid"] == "100000001"
    assert payload["data"]["account"]["default"] is True
    assert payload["data"]["account"]["has_cookie"] is False

    code, payload = _run_json(["--profile", "main", "account", "show"])

    assert code == 0
    assert payload["data"]["account"]["uid"] == "100000001"

    code, payload = _run_json(["account", "list"])

    assert code == 0
    assert [account["uid"] for account in payload["data"]["accounts"]] == ["100000001"]

    code, payload = _run_json(["account", "remove", "--uid", "100000001"])

    assert code == 0
    assert payload["data"]["deleted"] is True


def test_missing_account_returns_no_result(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    code, payload = _run_json(["account", "show", "--uid", "100000001"])

    assert code == 6
    assert payload["error"]["code"] == "NO_RESULT"


def _run_json(argv: list[str]) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    assert stderr.getvalue() == ""
    return code, json.loads(stdout.getvalue())
