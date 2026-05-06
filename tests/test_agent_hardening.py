from __future__ import annotations

import io
import json

from helpers import run_json_with_stderr as _run_json

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
                json.dumps({"id": "plain", "argv": ["--format=plain", "meta", "version"]}),
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


def test_batch_commands_render_text_plain(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    batch_file = tmp_path / "batch.jsonl"
    batch_file.write_text(json.dumps({"id": "ok", "command": "meta version"}), encoding="utf-8")

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(
        ["batch", "plan", "--file", str(batch_file), "--render", "text", "--format", "plain"],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert stderr.getvalue() == ""
    assert "批处理计划" in stdout.getvalue()
    assert "meta.version" in stdout.getvalue()

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(
        ["batch", "run", "--file", str(batch_file), "--render", "text", "--format", "plain"],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert stderr.getvalue() == ""
    assert "批处理执行" in stdout.getvalue()
    assert "成功: 1" in stdout.getvalue()


def test_batch_plan_accepts_late_global_options(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    batch_file = tmp_path / "batch.jsonl"
    batch_file.write_text(
        json.dumps({"id": "late", "argv": ["meta", "version", "--request-id", "row-req"]}),
        encoding="utf-8",
    )

    code, payload, stderr = _run_json(["batch", "plan", "--file", str(batch_file)])

    assert code == 0
    assert stderr == ""
    assert payload["data"]["valid"] is True
    step = payload["data"]["steps"][0]
    assert step["command"] == "meta.version"
    assert step["request_id"] == "row-req"


def test_batch_run_preserves_gacha_command_format(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    batch_file = tmp_path / "batch.jsonl"
    export_file = tmp_path / "gacha.json"
    batch_file.write_text(
        json.dumps(
            {
                "id": "gacha",
                "argv": [
                    "gacha",
                    "export",
                    "--uid",
                    "100000001",
                    "--format",
                    "uigf-v2",
                    "--output",
                    str(export_file),
                ],
            }
        ),
        encoding="utf-8",
    )

    code, payload, stderr = _run_json(["batch", "run", "--file", str(batch_file)])

    assert code == 0
    assert stderr == ""
    result = payload["data"]["results"][0]
    assert result["payload"]["ok"] is True
    assert result["payload"]["data"]["format"] == "uigf-v2"
    exported = json.loads(export_file.read_text(encoding="utf-8"))
    assert exported["info"]["uigf_version"] == "v2.4"


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
    cache_assets = home / "cache" / "assets"
    cache_assets.mkdir(parents=True)
    (cache_assets / "icon.1234.png").write_text("asset", encoding="utf-8")
    (cache_assets / "icon.1234.metadata.json").write_text("{}", encoding="utf-8")
    (cache_assets / ".1234.lock").write_text("", encoding="utf-8")
    monkeypatch.setenv("GSUID_HOME", str(home))

    code, payload, stderr = _run_json(["monitor", "once", "--max-asset-cache-files", "0"])

    assert code == 0
    assert stderr == ""
    assert payload["command"] == "monitor.once"
    assert payload["data"]["status"] == "warn"
    by_name = {check["name"]: check for check in payload["data"]["checks"]}
    assert by_name["cache.asset_files"]["value"] == 1
    assert by_name["cache.asset_files"]["status"] == "warn"
    assert by_name["cache.asset_files"]["message"] == "1 cached asset files"
    assert payload["data"]["thresholds"]["max_asset_cache_files"] == 0
    assert payload["warnings"] == ["1 cached asset files"]


def test_monitor_once_render_text_plain_prints_chinese_warning(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    cache_assets = home / "cache" / "assets"
    cache_assets.mkdir(parents=True)
    (cache_assets / "icon.1234.png").write_text("asset", encoding="utf-8")
    monkeypatch.setenv("GSUID_HOME", str(home))

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(
        [
            "monitor",
            "once",
            "--max-asset-cache-files",
            "0",
            "--render",
            "text",
            "--format",
            "plain",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert "健康检查" in stdout.getvalue()
    assert "静态资源缓存文件 1 个" in stdout.getvalue()
    assert "警告: 静态资源缓存文件 1 个" in stderr.getvalue()
