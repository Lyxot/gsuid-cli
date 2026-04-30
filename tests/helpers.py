from __future__ import annotations

import io
import json

import httpx

from gsuid_cli.cli import run
from gsuid_cli.core.http import HttpClient


def run_json(argv: list[str]) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    assert stderr.getvalue() == ""
    return code, json.loads(stdout.getvalue())


def run_json_with_stderr(argv: list[str]) -> tuple[int, dict[str, object], str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    return code, json.loads(stdout.getvalue()), stderr.getvalue()


def mock_client(handler) -> HttpClient:
    return HttpClient(timeout=1, cache_policy="off", transport=httpx.MockTransport(handler))


def json_response(
    payload: dict[str, object],
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(200, json=payload, headers=headers)
