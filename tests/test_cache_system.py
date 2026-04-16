from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from gsuid_cli.core.errors import CliError
from gsuid_cli.core.http import HttpClient


def test_json_cache_is_process_local_without_http_files(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GSUID_HOME", str(home))
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"retcode": 0, "data": {"calls": calls}})

    client = HttpClient(
        timeout=1,
        cache_policy="use",
        transport=httpx.MockTransport(handler),
    )
    kwargs = {
        "provider": "ambr",
        "region": "cn",
        "category": "cache.test",
        "params": {"id": "100"},
    }

    first = client.request_json("GET", "https://example.test/data.json", **kwargs)
    second = client.request_json("GET", "https://example.test/data.json", **kwargs)

    assert first.source["cached"] is False
    assert second.source["cached"] is True
    assert second.payload["data"]["calls"] == 1
    assert calls == 1
    assert not list((home / "cache" / "http").glob("*.json"))

    only_client = HttpClient(
        timeout=1,
        cache_policy="only",
        transport=httpx.MockTransport(handler),
    )
    only = only_client.request_json("GET", "https://example.test/data.json", **kwargs)

    assert only.source["cached"] is True
    assert only.payload["data"]["calls"] == 1
    assert calls == 1

    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "other-home"))
    other_home_client = HttpClient(
        timeout=1,
        cache_policy="only",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(CliError) as exc:
        other_home_client.request_json("GET", "https://example.test/data.json", **kwargs)
    assert exc.value.code == "CACHE_MISS"


def test_byte_cache_persists_flattened_asset_with_metadata(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GSUID_HOME", str(home))
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=b"png-data", headers={"content-type": "image/png"})

    kwargs = {
        "provider": "cdn",
        "region": "cn",
        "category": "asset.test",
        "params": {"id": "100"},
    }
    url = "https://cdn.example.test/icons/avatar.png?token=secret-token"
    client = HttpClient(
        timeout=1,
        cache_policy="use",
        transport=httpx.MockTransport(handler),
    )
    first = client.request_bytes("GET", url, **kwargs)

    only_client = HttpClient(
        timeout=1,
        cache_policy="only",
        transport=httpx.MockTransport(lambda _request: pytest.fail("cache was bypassed")),
    )
    second = only_client.request_bytes("GET", url, **kwargs)

    assets = home / "cache" / "assets"
    image_files = [path for path in assets.iterdir() if path.suffix == ".png"]
    metadata_files = list(assets.glob("avatar.*.metadata.json"))
    metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))

    assert calls == 1
    assert first.source["cached"] is False
    assert second.source["cached"] is True
    assert second.content == b"png-data"
    assert image_files == [Path(metadata["path"])]
    assert image_files[0].parent == assets
    assert image_files[0].name.startswith("avatar.")
    assert image_files[0].name.endswith(".png")
    assert metadata["status"] == "ok"
    assert metadata["media_type"] == "image/png"
    assert metadata["retry_count"] == 0
    assert "secret-token" not in json.dumps(metadata, ensure_ascii=False)


def test_byte_cache_records_retry_metadata_on_failure(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GSUID_HOME", str(home))
    url = "https://cdn.example.test/assets/banner"
    client = HttpClient(
        timeout=1,
        cache_policy="use",
        transport=httpx.MockTransport(lambda _request: httpx.Response(503, text="busy")),
    )

    with pytest.raises(CliError) as exc:
        client.request_bytes(
            "GET",
            url,
            provider="cdn",
            region="cn",
            category="asset.failure",
        )

    metadata_files = list((home / "cache" / "assets").glob("banner.*.metadata.json"))
    metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))

    assert exc.value.code == "UPSTREAM_HTTP_ERROR"
    assert metadata["status"] == "failed"
    assert metadata["retry_count"] == 1
    assert metadata["last_error"]["code"] == "UPSTREAM_HTTP_ERROR"
    assert metadata["last_error"]["status_code"] == 503
    assert metadata["path"] is None
    assert not list((home / "cache" / "assets").glob("*.tmp"))


def test_byte_cache_does_not_store_unexpected_media_type(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GSUID_HOME", str(home))
    client = HttpClient(
        timeout=1,
        cache_policy="use",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                content=b"<html>busy</html>",
                headers={"content-type": "text/html"},
            )
        ),
    )

    with pytest.raises(CliError) as exc:
        client.request_bytes(
            "GET",
            "https://cdn.example.test/map/get_map",
            provider="minigg",
            region="cn",
            category="map.find",
            expected_media_types=("image/",),
        )

    metadata_files = list((home / "cache" / "assets").glob("get_map.*.metadata.json"))
    metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))

    assert exc.value.code == "UPSTREAM_INVALID_RESPONSE"
    assert metadata["status"] == "failed"
    assert metadata["last_error"]["code"] == "UPSTREAM_INVALID_RESPONSE"
    assert not list((home / "cache" / "assets").glob("*.html"))
    assert not [
        path
        for path in (home / "cache" / "assets").iterdir()
        if path.is_file()
        and not path.name.endswith(".metadata.json")
        and not path.name.startswith(".")
    ]
