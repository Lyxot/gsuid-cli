from __future__ import annotations

import io
import json
import os
import re
import tempfile
from pathlib import Path

import httpx

from gsuid_cli.cli import run
from gsuid_cli.core.http import HttpClient

_TEST_HOME = Path(tempfile.mkdtemp(prefix="gsuid-cli-tests-"))
os.environ.setdefault("GSUID_HOME", str(_TEST_HOME))
UUIDV7_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def run_json(argv: list[str]) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(debug_json_argv(argv), stdout=stdout, stderr=stderr)
    assert stderr.getvalue() == ""
    return code, strip_debug_artifacts(json.loads(stdout.getvalue()))


def run_json_with_stderr(argv: list[str]) -> tuple[int, dict[str, object], str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(debug_json_argv(argv), stdout=stdout, stderr=stderr)
    return code, strip_debug_artifacts(json.loads(stdout.getvalue())), stderr.getvalue()


def debug_json_argv(argv: list[str]) -> list[str]:
    if any(token == "--debug" or token.startswith("--debug=") for token in argv):
        return argv
    return ["--debug", *argv]


def strip_debug_artifacts(payload: dict[str, object]) -> dict[str, object]:
    artifacts = payload.get("artifacts")
    if isinstance(artifacts, list):
        payload["artifacts"] = [
            artifact
            for artifact in artifacts
            if not (isinstance(artifact, dict) and artifact.get("name") == "debug-envelope")
        ]
    data = payload.get("data")
    if isinstance(data, dict):
        _strip_nested_payloads(data)
    return payload


def _strip_nested_payloads(value: object) -> None:
    if isinstance(value, dict):
        if isinstance(value.get("payload"), dict):
            strip_debug_artifacts(value["payload"])
        for item in value.values():
            _strip_nested_payloads(item)
    elif isinstance(value, list):
        for item in value:
            _strip_nested_payloads(item)


def mock_client(handler) -> HttpClient:
    return HttpClient(timeout=1, cache_policy="off", transport=httpx.MockTransport(handler))


def json_response(
    payload: dict[str, object],
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(200, json=payload, headers=headers)


def assert_artifact_parent(
    path: Path,
    base: Path,
    *,
    date: str = "2026-04-29",
) -> None:
    assert path.parent.parent == base / date
    assert UUIDV7_RE.fullmatch(path.parent.name)
