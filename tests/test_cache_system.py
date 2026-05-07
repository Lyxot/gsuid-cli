from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from gsuid_cli.core.cache_policy import cache_expires_at, cache_rule_for, cache_version_for
from gsuid_cli.core.errors import CliError
from gsuid_cli.core.http import GAME_VERSION_BUILD_URL, HttpClient


def _is_game_version_request(request: httpx.Request) -> bool:
    return str(request.url) == GAME_VERSION_BUILD_URL


def test_json_cache_persists_http_response_with_expiration(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GSUID_HOME", str(home))
    calls = 0
    tag_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls, tag_calls
        if _is_game_version_request(request):
            tag_calls += 1
            return httpx.Response(200, json={"data": {"tag": "6.5.0"}})
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
    assert tag_calls == 1
    cache_files = list((home / "cache" / "http").glob("*.json"))
    assert len(cache_files) == 2
    all_metadata = [json.loads(path.read_text(encoding="utf-8")) for path in cache_files]
    metadata = next(item for item in all_metadata if item["cache_policy"] == "game-version")
    tag_metadata = next(item for item in all_metadata if item["cache_policy"] == "game-version-tag")
    assert metadata["status"] == "ok"
    assert metadata["cache_policy"] == "game-version"
    assert metadata["expires_at"] is None
    assert metadata["cache_version"] == "6.5.0"
    assert metadata["payload"]["data"]["calls"] == 1
    assert tag_metadata["payload"]["data"]["tag"] == "6.5.0"
    assert tag_metadata["expires_at"]
    assert "CW8GbLNU8f" not in json.dumps(tag_metadata, ensure_ascii=False)

    only_client = HttpClient(
        timeout=1,
        cache_policy="only",
        transport=httpx.MockTransport(handler),
    )
    only = only_client.request_json("GET", "https://example.test/data.json", **kwargs)

    assert only.source["cached"] is True
    assert only.payload["data"]["calls"] == 1
    assert calls == 1
    assert tag_calls == 1

    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "other-home"))
    other_home_client = HttpClient(
        timeout=1,
        cache_policy="only",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(CliError) as exc:
        other_home_client.request_json("GET", "https://example.test/data.json", **kwargs)
    assert exc.value.code == "CACHE_MISS"


def test_json_cache_expires_when_game_version_changes(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GSUID_HOME", str(home))
    current = {"now": "2026-05-06T21:30:00.000Z"}
    current_tag = {"tag": "6.5.0"}
    calls = 0
    tag_calls = 0

    monkeypatch.setattr("gsuid_cli.core.http.utc_now", lambda: current["now"])

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls, tag_calls
        if _is_game_version_request(request):
            tag_calls += 1
            return httpx.Response(200, json={"data": {"tag": current_tag["tag"]}})
        calls += 1
        return httpx.Response(200, json={"retcode": 0, "data": {"calls": calls}})

    kwargs = {
        "provider": "ambr",
        "region": "cn",
        "category": "wiki.character",
    }
    client = HttpClient(
        timeout=1,
        cache_policy="use",
        transport=httpx.MockTransport(handler),
    )
    first = client.request_json("GET", "https://example.test/character.json", **kwargs)

    current_tag["tag"] = "6.6.0"
    current["now"] = "2026-05-06T21:45:00.000Z"
    still_cached = client.request_json("GET", "https://example.test/character.json", **kwargs)

    current["now"] = "2026-05-06T22:01:00.000Z"
    second = client.request_json("GET", "https://example.test/character.json", **kwargs)

    assert first.payload["data"]["calls"] == 1
    assert still_cached.payload["data"]["calls"] == 1
    assert still_cached.source["cached"] is True
    assert second.payload["data"]["calls"] == 2
    assert second.source["cached"] is False
    assert calls == 2
    assert tag_calls == 2


def test_refresh_versioned_json_without_game_version_does_not_persist(
    monkeypatch, tmp_path
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GSUID_HOME", str(home))
    calls = 0
    tag_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls, tag_calls
        if _is_game_version_request(request):
            tag_calls += 1
            return httpx.Response(503, text="busy")
        calls += 1
        return httpx.Response(200, json={"retcode": 0, "data": {"calls": calls}})

    client = HttpClient(
        timeout=1,
        cache_policy="refresh",
        transport=httpx.MockTransport(handler),
    )
    response = client.request_json(
        "GET",
        "https://example.test/character.json",
        provider="ambr",
        region="cn",
        category="wiki.character",
    )

    assert response.payload["data"]["calls"] == 1
    assert calls == 1
    assert tag_calls == 1
    assert not list((home / "cache" / "http").glob("*.json"))


def test_json_cache_expires_at_daily_reset(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GSUID_HOME", str(home))
    current = {"now": "2026-05-06T19:30:00.000Z"}
    calls = 0

    monkeypatch.setattr("gsuid_cli.core.http.utc_now", lambda: current["now"])

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"retcode": 0, "data": {"calls": calls}})

    kwargs = {
        "provider": "ambr",
        "region": "cn",
        "category": "daily.materials",
    }
    client = HttpClient(
        timeout=1,
        cache_policy="use",
        transport=httpx.MockTransport(handler),
    )
    first = client.request_json("GET", "https://example.test/daily.json", **kwargs)

    current["now"] = "2026-05-06T20:01:00.000Z"
    only_client = HttpClient(
        timeout=1,
        cache_policy="only",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(CliError) as exc:
        only_client.request_json("GET", "https://example.test/daily.json", **kwargs)

    assert not list((home / "cache" / "http").glob("*.json"))

    second = client.request_json("GET", "https://example.test/daily.json", **kwargs)

    assert exc.value.code == "CACHE_MISS"
    assert first.payload["data"]["calls"] == 1
    assert second.payload["data"]["calls"] == 2
    assert second.source["cached"] is False
    assert calls == 2


def test_private_short_json_cache_is_memory_only(monkeypatch, tmp_path) -> None:
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
        "provider": "mys",
        "region": "cn",
        "category": "challenge.abyss",
        "params": {"uid": "100000001"},
    }

    first = client.request_json("GET", "https://example.test/abyss", **kwargs)
    second = client.request_json("GET", "https://example.test/abyss", **kwargs)

    assert first.source["cached"] is False
    assert second.source["cached"] is True
    assert second.payload["data"]["calls"] == 1
    assert calls == 1
    assert not list((home / "cache" / "http").glob("*.json"))


def test_cache_policy_expiration_rules() -> None:
    daily = cache_rule_for(
        method="GET",
        provider="ambr",
        category="daily.materials",
        response_kind="json",
    )
    public = cache_rule_for(
        method="GET",
        provider="ambr",
        category="wiki.character",
        response_kind="json",
    )
    private = cache_rule_for(
        method="GET",
        provider="mys",
        category="challenge.abyss",
        response_kind="json",
    )
    action = cache_rule_for(
        method="POST",
        provider="mys",
        category="daily.signin",
        response_kind="json",
    )
    version_tag = cache_rule_for(
        method="GET",
        provider="sophon",
        category="cache.game-version",
        response_kind="json",
    )

    assert daily.name == "daily-reset"
    assert cache_expires_at("2026-05-06T19:30:00.000Z", daily) == "2026-05-06T20:00:00.000Z"
    assert cache_expires_at("2026-05-06T20:30:00.000Z", daily) == "2026-05-07T20:00:00.000Z"
    assert public.name == "game-version"
    assert public.versioned is True
    assert cache_expires_at("2026-05-06T20:30:00.000Z", public) is None
    assert cache_version_for(public, "6.5.0") == "6.5.0"
    assert private.name == "private-short"
    assert private.persist is False
    assert action.name == "no-store"
    assert version_tag.name == "game-version-tag"
    assert cache_expires_at("2026-05-06T21:30:00.000Z", version_tag) == "2026-05-06T22:00:00.000Z"
    assert cache_expires_at("2026-05-06T22:30:00.000Z", version_tag) == "2026-05-07T22:00:00.000Z"


def test_byte_cache_persists_flattened_asset_with_metadata(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GSUID_HOME", str(home))
    calls = 0
    tag_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls, tag_calls
        if _is_game_version_request(request):
            tag_calls += 1
            return httpx.Response(200, json={"data": {"tag": "6.5.0"}})
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
    assert tag_calls == 1
    assert first.source["cached"] is False
    assert second.source["cached"] is True
    assert second.content == b"png-data"
    assert image_files == [Path(metadata["path"])]
    assert image_files[0].parent == assets
    assert image_files[0].name.startswith("avatar.")
    assert image_files[0].name.endswith(".png")
    assert metadata["status"] == "ok"
    assert metadata["media_type"] == "image/png"
    assert metadata["cache_policy"] == "game-version"
    assert metadata["expires_at"] is None
    assert metadata["cache_version"] == "6.5.0"
    assert metadata["retry_count"] == 0
    assert "secret-token" not in json.dumps(metadata, ensure_ascii=False)
    assert (home / "cache" / "icons").exists() is False


def test_byte_cache_expires_static_assets_when_game_version_changes(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GSUID_HOME", str(home))
    current = {"now": "2026-05-06T21:30:00.000Z"}
    current_tag = {"tag": "6.5.0"}
    calls = 0
    tag_calls = 0

    monkeypatch.setattr("gsuid_cli.core.http.utc_now", lambda: current["now"])

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls, tag_calls
        if _is_game_version_request(request):
            tag_calls += 1
            return httpx.Response(200, json={"data": {"tag": current_tag["tag"]}})
        calls += 1
        return httpx.Response(
            200,
            content=f"png-{calls}".encode(),
            headers={"content-type": "image/png"},
        )

    kwargs = {
        "provider": "genshinuid",
        "region": "cn",
        "category": "guide.character.image",
    }
    client = HttpClient(
        timeout=1,
        cache_policy="use",
        transport=httpx.MockTransport(handler),
    )
    first = client.request_bytes("GET", "https://cdn.example.test/guide/amber.png", **kwargs)
    metadata_path = next((home / "cache" / "wiki").glob("amber.*.metadata.json"))
    stale_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    stale_metadata["retry_count"] = 7
    metadata_path.write_text(json.dumps(stale_metadata), encoding="utf-8")

    current_tag["tag"] = "6.6.0"
    current["now"] = "2026-05-06T22:01:00.000Z"
    second = client.request_bytes("GET", "https://cdn.example.test/guide/amber.png", **kwargs)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert first.content == b"png-1"
    assert second.content == b"png-2"
    assert second.source["cached"] is False
    assert calls == 2
    assert tag_calls == 2
    assert metadata["retry_count"] == 0
    assert list((home / "cache" / "wiki").glob("amber.*.png"))


def test_byte_cache_splits_assets_by_usage(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("GSUID_HOME", str(home))
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if _is_game_version_request(request):
            return httpx.Response(200, json={"data": {"tag": "6.5.0"}})
        calls += 1
        return httpx.Response(
            200,
            content=f"asset-{calls}".encode(),
            headers={"content-type": "image/png"},
        )

    client = HttpClient(
        timeout=1,
        cache_policy="use",
        transport=httpx.MockTransport(handler),
    )

    client.request_bytes(
        "GET",
        "https://cdn.example.test/icon/avatar.png",
        provider="mys",
        region="cn",
        category="player.summary.icon",
    )
    client.request_bytes(
        "GET",
        "https://cdn.example.test/map/get_map.png",
        provider="minigg",
        region="cn",
        category="map.find",
    )
    client.request_bytes(
        "GET",
        "https://cdn.example.test/wiki/card.png",
        provider="wiki-assets",
        region="cn",
        category="wiki.character.asset",
    )
    client.request_bytes(
        "GET",
        "https://gi.yatta.moe/assets/UI/UI_ItemIcon_112023.png",
        provider="ambr",
        region="cn",
        category="wiki.weapon.asset",
    )

    assert list((home / "cache" / "icons").glob("avatar.*.png"))
    assert list((home / "cache" / "icons").glob("UI_ItemIcon_112023.*.png"))
    assert list((home / "cache" / "maps").glob("get_map.*.png"))
    assert list((home / "cache" / "wiki").glob("card.*.png"))

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

    metadata_files = list((home / "cache" / "maps").glob("get_map.*.metadata.json"))
    metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))

    assert exc.value.code == "UPSTREAM_INVALID_RESPONSE"
    assert metadata["status"] == "failed"
    assert metadata["last_error"]["code"] == "UPSTREAM_INVALID_RESPONSE"
    assert not list((home / "cache" / "maps").glob("*.html"))
    assert not [
        path
        for path in (home / "cache" / "maps").iterdir()
        if path.is_file()
        and not path.name.endswith(".metadata.json")
        and not path.name.startswith(".")
    ]
