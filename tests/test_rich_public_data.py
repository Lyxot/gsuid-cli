from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import httpx
import pytest
from helpers import debug_json_argv, strip_debug_artifacts

from gsuid_cli.cli import run
from gsuid_cli.core.errors import CliError
from gsuid_cli.core.http import HttpClient, ProviderBytesResponse
from gsuid_cli.core.models import CommandResult
from gsuid_cli.providers.public import PublicDataProvider



def test_map_find_writes_image_artifact(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.public_data._common.PublicDataProvider", FakeProvider)
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")

    code, payload = _run_json(
        [
            "--request-id",
            "map-req",
            "--output-dir",
            str(tmp_path / "artifacts"),
            "map",
            "find",
            "--item",
            "甜甜花",
        ]
    )

    assert code == 0
    artifact = payload["artifacts"][0]
    path = Path(artifact["path"])
    content = path.read_bytes()
    assert path.parent == tmp_path / "artifacts" / "2026-04-29" / "map-req"
    assert artifact["media_type"] == "image/jpeg"
    assert artifact["sha256"] == hashlib.sha256(content).hexdigest()
    assert payload["data"]["marker_count"] is None


def test_map_find_passes_global_cache_policy_to_asset_provider(monkeypatch, tmp_path) -> None:
    class CaptureProvider(FakeProvider):
        cache_policy: str | None = None

        def __init__(self, http_client: HttpClient) -> None:
            self.__class__.cache_policy = http_client.cache_policy

    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", CaptureProvider
    )

    code, _payload = _run_json(["--cache", "only", "map", "find", "--item", "甜甜花"])

    assert code == 0
    assert CaptureProvider.cache_policy == "only"


def test_guide_route_uses_route_provider_category(monkeypatch, tmp_path) -> None:
    class CaptureProvider(FakeProvider):
        category: str | None = None

        def map_image(
            self,
            *,
            item: str,
            map_name: str,
            category: str = "map.find",
        ) -> ProviderBytesResponse:
            self.__class__.category = category
            return super().map_image(item=item, map_name=map_name, category=category)

    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data._common.PublicDataProvider", CaptureProvider
    )

    code, _payload = _run_json(["guide", "route", "--material", "甜甜花"])

    assert code == 0
    assert CaptureProvider.category == "guide.route"


def test_talent_index_must_be_positive(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.public_data._common.PublicDataProvider", FakeProvider)

    code, payload = _run_json(["wiki", "talent", "--character", "Amber", "--talent", "0"])

    assert code == 1
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_resources_sync_command(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.resources.PublicDataProvider", FakeProvider)

    code, payload = _run_json(["resources", "sync", "--scope", "maps"])

    assert code == 0
    assert payload["command"] == "resources.sync"
    assert payload["data"]["scope"] == "maps"
    assert "MiniGG maps are query-specific" in payload["data"]["source_limitations"][0]
    assert "MiniGG maps are query-specific" in payload["warnings"][0]

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(
        ["resources", "sync", "--scope", "maps", "--render", "text", "--format", "plain"],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert "资源同步" in stdout.getvalue()
    assert "MiniGG 地图按查询生成" in stdout.getvalue()
    assert "警告: MiniGG 地图按查询生成" in stderr.getvalue()


def test_provider_character_talent_and_materials_from_ambr() -> None:
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(_ambr_index("10000021", "Amber")),
                _json_response(_ambr_character_detail()),
                _json_response(_ambr_index("10000021", "Amber")),
                _json_response(_ambr_character_detail()),
                _json_response(_ambr_index("10000021", "Amber")),
                _json_response(_ambr_character_detail()),
            ]
        )
    )

    talent = provider.character_talent(character="Amber", talent=1)
    constellation = provider.character_constellation(character="Amber", constellation=1)
    materials = provider.character_materials(character="Amber")

    assert talent.data["talent"]["name"] == "Normal Attack"
    assert constellation.data["constellation"]["name"] == "One Arrow"
    assert materials.data["ascension"] == {"1001": 3}
    assert materials.data["talents"][0]["promote"]["1"]["coinCost"] == 1000


def test_provider_sync_resources_from_ambr() -> None:
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(_ambr_index("10000021", "Amber")),
                _json_response(_ambr_index("15501", "Bow")),
                _json_response(_ambr_index("15001", "Artifact")),
                _json_response(_ambr_index("20010101", "Enemy")),
                _json_response(_ambr_index("108001", "Food")),
                _json_response({"response": 200, "data": {"monday": {}, "tuesday": {}}}),
                _json_response({"1": {"id": 1, "name": {"CHS": "Event"}}}),
            ]
        )
    )

    result = provider.sync_resources(scope="all")

    kinds = {row["kind"] for row in result.data["synced"]}
    assert result.data["count"] == 7
    assert {
        "character",
        "weapon",
        "artifact",
        "enemy",
        "food",
        "daily-materials",
        "events",
    } == kinds
    assert result.warnings


def test_provider_map_image_uses_minigg_params() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            headers={"content-type": "Image/JPEG; charset=binary"},
            content=b"jpeg-data",
        )

    provider = PublicDataProvider(
        HttpClient(timeout=1, cache_policy="off", transport=httpx.MockTransport(handler))
    )

    result = provider.map_image(item="甜甜花", map_name="teyvat")

    query = dict(captured["request"].url.params)
    assert result.media_type == "image/jpeg"
    assert query["resource_name"] == "甜甜花"
    assert query["map_id"] == "2"
    assert query["is_cluster"] == "false"


def test_provider_map_image_rejects_non_image() -> None:
    provider = PublicDataProvider(
        HttpClient(
            timeout=1,
            cache_policy="off",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    headers={"content-type": "application/json"},
                    json={"message": "not found"},
                )
            ),
        )
    )

    with pytest.raises(CliError) as exc_info:
        provider.map_image(item="missing", map_name="teyvat", category="guide.route")

    assert exc_info.value.code == "UPSTREAM_INVALID_RESPONSE"
    assert exc_info.value.details["media_type"] == "application/json"


def test_provider_rerun_list_uses_teyvat_return_groups() -> None:
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(
                    {
                        "code": 200,
                        "version": "当前版本:9.9",
                        "result": [
                            [
                                {
                                    "role": "旧角色",
                                    "avatar": "https://example.test/old.png",
                                    "days": 120,
                                    "history": ["9.0上半"],
                                }
                            ],
                            [],
                            [],
                            [],
                        ],
                    }
                )
            ]
        )
    )

    result = provider.rerun_list(limit=5)

    assert result.data["count"] == 1
    assert result.data["version"] == "当前版本:9.9"
    assert result.data["groups"][0]["items"][0]["entity"] == "旧角色"
    assert result.data["reruns"][0]["days_since_last_banner"] == 120


class FakeProvider:
    def __init__(self, _http_client: HttpClient) -> None:
        pass

    def wiki_lookup(self, *, kind: str, query: str) -> CommandResult:
        return CommandResult(
            data={
                "kind": kind,
                "query": query,
                "match": {"id": "1", "name": query},
                "item": {"id": "1", "name": query},
            },
            source=_source("ambr"),
        )

    def character_talent(self, *, character: str, talent: int) -> CommandResult:
        return CommandResult(
            data={"character": character, "talent": {"index": talent}}, source=_source("ambr")
        )

    def character_constellation(
        self,
        *,
        character: str,
        constellation: int | None,
    ) -> CommandResult:
        return CommandResult(
            data={"character": character, "constellation": {"index": constellation}},
            source=_source("ambr"),
        )

    def character_materials(self, *, character: str) -> CommandResult:
        return CommandResult(data={"character": character, "ascension": {}}, source=_source("ambr"))

    def weapon_materials(self, *, weapon: str) -> CommandResult:
        return CommandResult(data={"weapon": weapon, "upgrade": {}}, source=_source("ambr"))

    def guide_character(self, *, character: str) -> CommandResult:
        return CommandResult(data={"character": character, "overview": {}}, source=_source("ambr"))

    def reference_panel(self, *, character: str) -> CommandResult:
        return CommandResult(
            data={"character": character, "available": False}, source=_source("ambr")
        )

    def guide_abyss(self, *, version: str | None, floor: int | None) -> CommandResult:
        return CommandResult(
            data={"version": version, "floor": floor, "available": False}, source=_source("ambr")
        )

    def guide_theater(self, *, version: str | None) -> CommandResult:
        return CommandResult(data={"version": version, "available": False}, source=_source("ambr"))

    def recommend_build(self, *, character: str) -> CommandResult:
        return CommandResult(
            data={"character": character, "recommendations": []}, source=_source("ambr")
        )

    def recommend_holder(self, *, item: str) -> CommandResult:
        return CommandResult(data={"item": item, "matches": []}, source=_source("ambr"))

    def announcements_list(self, *, limit: int) -> CommandResult:
        return CommandResult(
            data={"announcements": [_announcement()], "count": limit}, source=_source("ambr")
        )

    def announcement_show(self, *, announcement_id: str) -> CommandResult:
        return CommandResult(data={"announcement": _announcement()}, source=_source("ambr"))

    def rerun_list(self, *, limit: int) -> CommandResult:
        return CommandResult(
            data={"reruns": [_announcement()], "count": limit}, source=_source("ambr")
        )

    def primogems_plan(self, *, version: str | None) -> CommandResult:
        return CommandResult(data={"version": version, "estimate": None}, source=_source("ambr"))

    def sync_resources(self, *, scope: str) -> CommandResult:
        return CommandResult(
            data={
                "scope": scope,
                "synced": [],
                "count": 0,
                "source_limitations": [
                    "MiniGG maps are query-specific; "
                    "use map find or guide route to create map artifacts"
                ],
            },
            warnings=[
                "MiniGG maps are query-specific; "
                "use map find or guide route to create map artifacts"
            ],
            source=_source("local"),
        )

    def map_image(
        self,
        *,
        item: str,
        map_name: str,
        category: str = "map.find",
    ) -> ProviderBytesResponse:
        return ProviderBytesResponse(
            content=b"\xff\xd8fake-jpeg",
            media_type="image/jpeg",
            source=_source("minigg"),
            status_code=200,
        )


def _announcement() -> dict[str, object]:
    return {"id": "1", "title": "Event", "end_at": "2026-05-01 00:00:00"}


def _ambr_index(item_id: str, name: str) -> dict[str, object]:
    return {
        "response": 200,
        "data": {"items": {item_id: {"id": int(item_id), "name": name, "route": name}}},
    }


def _ambr_character_detail() -> dict[str, object]:
    return {
        "response": 200,
        "data": {
            "id": 10000021,
            "name": "Amber",
            "route": "Amber",
            "fetter": {"title": "Champion", "detail": "Scout."},
            "ascension": {"1001": 3},
            "upgrade": {"promote": [{"costItems": {"1001": 3}}]},
            "talent": {
                "a": {
                    "name": "Normal Attack",
                    "type": 0,
                    "promote": {"1": {"coinCost": 1000}},
                }
            },
            "constellation": {"c1": {"name": "One Arrow", "description": "More arrows."}},
        },
    }


def _event_payload(
    event_id: int,
    name: str,
    start_at: str,
    end_at: str,
) -> dict[str, object]:
    return {
        "id": event_id,
        "name": {"CHS": name},
        "nameFull": {"CHS": name},
        "startAt": start_at,
        "endAt": end_at,
        "banner": {"CHS": "https://example.test/banner.jpg"},
    }


def _run_json(argv: list[str]) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(debug_json_argv(argv), stdout=stdout, stderr=stderr)
    assert stderr.getvalue() == ""
    return code, strip_debug_artifacts(json.loads(stdout.getvalue()))


def _source(provider: str) -> dict[str, object]:
    return {
        "provider": provider,
        "region": "cn",
        "cached": False,
        "fetched_at": "2026-04-29T10:30:00Z",
    }


def _sequence_client(responses: list[httpx.Response]) -> HttpClient:
    remaining = list(responses)

    def handler(_request: httpx.Request) -> httpx.Response:
        return remaining.pop(0)

    return HttpClient(timeout=1, cache_policy="off", transport=httpx.MockTransport(handler))


def _json_response(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, json=payload)
