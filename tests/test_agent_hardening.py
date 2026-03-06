from __future__ import annotations

import io
import json

from gsuid_cli.cli import run


def test_batch_run_mixes_success_and_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    batch_file = tmp_path / "batch.jsonl"
    batch_file.write_text(
        "\n".join(
            [
                json.dumps({"id": "ok", "argv": ["meta", "version"]}),
                json.dumps({"id": "bad", "argv": ["meta", "missing"]}),
            ]
        ),
        encoding="utf-8",
    )

    code, payload, stderr = _run_json(
        ["--request-id", "batch-req", "batch", "run", "--file", str(batch_file)]
    )

    assert code == 0
    assert stderr == ""
    assert payload["command"] == "batch.run"
    assert payload["data"]["ok_count"] == 1
    assert payload["data"]["error_count"] == 1
    results = payload["data"]["results"]
    assert results[0]["payload"]["ok"] is True
    assert results[0]["payload"]["request_id"] == "batch-req-0"
    assert results[1]["payload"]["ok"] is False
    assert results[1]["payload"]["error"]["code"] == "INVALID_ARGUMENT"


def test_batch_run_forces_json_and_blocks_nested_batch(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    batch_file = tmp_path / "batch.jsonl"
    batch_file.write_text(
        "\n".join(
            [
                json.dumps({"id": "text", "argv": ["--format=text", "meta", "version"]}),
                json.dumps({"id": "nested", "argv": ["batch", "run", "--file", str(batch_file)]}),
            ]
        ),
        encoding="utf-8",
    )

    code, payload, stderr = _run_json(
        ["--request-id", "batch-req", "batch", "run", "--file", str(batch_file)]
    )

    assert code == 0
    assert stderr == ""
    results = payload["data"]["results"]
    assert results[0]["payload"]["ok"] is True
    assert results[0]["payload"]["command"] == "meta.version"
    assert results[1]["payload"]["ok"] is False
    assert results[1]["payload"]["command"] == "batch.run"
    assert results[1]["payload"]["error"]["code"] == "INVALID_ARGUMENT"
    assert results[1]["argv"] == ["batch", "run", "--file", str(batch_file)]


def test_batch_plan_validates_without_executing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    batch_file = tmp_path / "batch.jsonl"
    batch_file.write_text(
        "\n".join(
            [
                json.dumps({"id": "ok", "command": "meta version"}),
                json.dumps({"id": "bad", "command": "meta missing"}),
            ]
        ),
        encoding="utf-8",
    )

    code, payload, stderr = _run_json(["batch", "plan", "--file", str(batch_file)])

    assert code == 0
    assert stderr == ""
    assert payload["command"] == "batch.plan"
    assert payload["data"]["valid"] is False
    assert payload["data"]["error_count"] == 1
    assert payload["data"]["steps"][0]["command"] == "meta.version"
    assert payload["data"]["steps"][1]["error"]["code"] == "INVALID_ARGUMENT"


def test_batch_plan_blocks_nested_batch(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    batch_file = tmp_path / "batch.jsonl"
    batch_file.write_text(
        json.dumps({"id": "nested", "argv": ["batch", "plan", "--file", str(batch_file)]}),
        encoding="utf-8",
    )

    code, payload, stderr = _run_json(["batch", "plan", "--file", str(batch_file)])

    assert code == 0
    assert stderr == ""
    assert payload["data"]["valid"] is False
    assert payload["data"]["steps"][0]["command"] == "batch.plan"
    assert payload["data"]["steps"][0]["error"]["code"] == "INVALID_ARGUMENT"


def test_batch_file_read_errors_return_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    missing = tmp_path / "missing.jsonl"

    code, payload, stderr = _run_json(["batch", "plan", "--file", str(missing)])

    assert code == 1
    assert stderr == ""
    assert payload["command"] == "batch.plan"
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_batch_invalid_utf8_file_returns_invalid_argument(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    batch_file = tmp_path / "bad.jsonl"
    batch_file.write_bytes(b"\xff\xfe\xfa")

    code, payload, stderr = _run_json(["batch", "run", "--file", str(batch_file)])

    assert code == 1
    assert stderr == ""
    assert payload["command"] == "batch.run"
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_monitor_once_reports_threshold_warnings(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    cache_http = home / "cache" / "http"
    cache_http.mkdir(parents=True)
    (cache_http / "cached.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GSUID_HOME", str(home))

    code, payload, stderr = _run_json(["monitor", "once", "--max-http-cache-files", "0"])

    assert code == 0
    assert stderr == ""
    assert payload["command"] == "monitor.once"
    assert payload["data"]["status"] == "warn"
    by_name = {check["name"]: check for check in payload["data"]["checks"]}
    assert by_name["cache.http_files"]["value"] == 1
    assert by_name["cache.http_files"]["status"] == "warn"
    assert payload["warnings"]


def _run_json(argv: list[str]) -> tuple[int, dict[str, object], str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    return code, json.loads(stdout.getvalue()), stderr.getvalue()
