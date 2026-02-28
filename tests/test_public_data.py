from __future__ import annotations

import io
import json

import httpx
import pytest

from gsuid_cli.cli import run
from gsuid_cli.core.errors import CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.providers.public import PublicDataProvider, _parse_active_codes


def test_public_wiki_command_returns_json(monkeypatch) -> None:
    monkeypatch.setattr("gsuid_cli.commands.public_data.PublicDataProvider", _fake_provider())

    code, payload = _run_json(["wiki", "character", "--name", "Amber"])

    assert code == 0
    assert payload["command"] == "wiki.character"
    assert payload["data"]["item"]["name"] == "Amber"
    assert payload["source"]["provider"] == "ambr"


def test_public_commands_reject_unsupported_region(monkeypatch) -> None:
    monkeypatch.setattr("gsuid_cli.commands.public_data.PublicDataProvider", _fake_provider())

    code, payload = _run_json(["--region", "os", "wiki", "character", "--name", "Amber"])

    assert code == 1
    assert payload["error"]["code"] == "REGION_UNSUPPORTED"


def test_daily_materials_rejects_conflicting_day_selectors() -> None:
    code, payload = _run_json(["daily", "materials", "--date", "2026-04-29", "--day", "monday"])

    assert code == 1
    assert payload["command"] == "daily.materials"
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_public_list_commands_return_json(monkeypatch) -> None:
    monkeypatch.setattr("gsuid_cli.commands.public_data.PublicDataProvider", _fake_provider())

    for argv, command, key in [
        (["events", "list"], "events.list", "events"),
        (["events", "banners"], "events.banners", "banners"),
        (["codes", "list"], "codes.list", "codes"),
        (["daily", "materials", "--date", "2026-04-29"], "daily.materials", "domains"),
    ]:
        code, payload = _run_json(argv)

        assert code == 0
        assert payload["command"] == command
        assert key in payload["data"]


def test_ambr_wiki_lookup_matches_route_alias() -> None:
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(
                    {
                        "response": 200,
                        "data": {
                            "items": {
                                "10000021": {
                                    "id": 10000021,
                                    "rank": 4,
                                    "name": "安柏",
                                    "element": "Fire",
                                    "weaponType": "WEAPON_BOW",
                                    "icon": "UI_AvatarIcon_Ambor",
                                    "route": "Amber",
                                }
                            }
                        },
                    }
                ),
                _json_response(
                    {
                        "response": 200,
                        "data": {
                            "id": 10000021,
                            "rank": 4,
                            "name": "安柏",
                            "element": "Fire",
                            "weaponType": "WEAPON_BOW",
                            "icon": "UI_AvatarIcon_Ambor",
                            "route": "Amber",
                            "fetter": {"title": "飞行冠军", "detail": "侦察骑士。"},
                        },
                    }
                ),
            ]
        )
    )

    result = provider.wiki_lookup(kind="character", query="amber")

    assert result.data["match"]["id"] == "10000021"
    assert result.data["item"]["title"] == "飞行冠军"


def test_ambr_wiki_lookup_no_result() -> None:
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(
                    {
                        "response": 200,
                        "data": {"items": {"1": {"id": 1, "name": "Amber", "route": "Amber"}}},
                    }
                )
            ]
        )
    )

    with pytest.raises(CliError) as exc:
        provider.wiki_lookup(kind="character", query="Missing")

    assert exc.value.code == "NO_RESULT"
    assert exc.value.exit_code == 6
    assert exc.value.source["provider"] == "ambr"


def test_events_banners_filters_wish_rows() -> None:
    provider = PublicDataProvider(
        _sequence_client(
            [
                _json_response(
                    {
                        "1": {
                            "id": 1,
                            "name": {"CHS": "普通活动"},
                            "nameFull": {"CHS": "普通活动说明"},
                            "startAt": "2026-04-01 00:00:00",
                            "endAt": "2026-05-01 00:00:00",
                            "banner": {"CHS": "https://example.test/event.jpg"},
                        },
                        "2": {
                            "id": 2,
                            "name": {"CHS": "「苍林月祷」祈愿"},
                            "nameFull": {"CHS": "角色活动祈愿"},
                            "startAt": "2026-04-01 00:00:00",
                            "endAt": "2026-05-01 00:00:00",
                            "banner": {"CHS": "https://example.test/wish.jpg"},
                        },
                    }
                )
            ]
        )
    )

    result = provider.event_banners(include_all=True, limit=10)

    assert result.data["count"] == 1
    assert result.data["banners"][0]["id"] == "2"


def test_codes_parser_extracts_active_rows() -> None:
    codes = _parse_active_codes(
        """
==Active Codes==
{{Code Row/Header}}
{{Code Row|GENSHINGIFT|G|Primogem*50;Hero's Wit*3|2020-11-10|indef|Permanent row}}
{{Code Row|YuanShen|CN|Primogem*50|2020-11-10|unknown}}
{{Code Row/Footer}}
==References==
"""
    )

    assert codes[0]["codes"] == ["GENSHINGIFT"]
    assert codes[0]["servers"] == ["America", "Europe", "Asia", "TW/HK/Macao"]
    assert codes[0]["rewards"][0] == {"name": "Primogem", "count": 50}
    assert codes[1]["servers"] == ["China"]


def _run_json(argv: list[str]) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    assert stderr.getvalue() == ""
    return code, json.loads(stdout.getvalue())


def _fake_provider():
    class FakeProvider:
        def __init__(self, _http_client: HttpClient) -> None:
            pass

        def wiki_lookup(self, *, kind: str, query: str) -> CommandResult:
            return CommandResult(
                data={
                    "kind": kind,
                    "query": query,
                    "match": {"id": "1", "name": "Amber"},
                    "item": {"id": "1", "name": "Amber"},
                },
                source=_source("ambr"),
            )

        def events_list(self, *, include_all: bool, limit: int) -> CommandResult:
            return CommandResult(
                data={
                    "events": [
                        {"id": "1", "name": "Event", "banner_url": "https://example.test/a.jpg"}
                    ],
                    "count": min(1, limit),
                    "filter": "all" if include_all else "active",
                },
                source=_source("ambr"),
            )

        def event_banners(self, *, include_all: bool, limit: int) -> CommandResult:
            return CommandResult(
                data={
                    "banners": [
                        {"id": "1", "name": "Event", "banner_url": "https://example.test/a.jpg"}
                    ],
                    "count": min(1, limit),
                    "filter": "all" if include_all else "active",
                },
                source=_source("ambr"),
            )

        def codes_list(self) -> CommandResult:
            return CommandResult(
                data={"codes": [{"codes": ["GENSHINGIFT"]}], "count": 1},
                source=_source("fandom"),
            )

        def daily_materials(self, *, day: str | None, date: str | None = None) -> CommandResult:
            return CommandResult(
                data={
                    "date": date,
                    "day": day,
                    "domains": [{"id": "1", "name": "Domain"}],
                    "count": 1,
                },
                source=_source("ambr"),
            )

    return FakeProvider


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

    return HttpClient(
        timeout=1,
        cache_policy="off",
        transport=httpx.MockTransport(handler),
    )


def _json_response(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, json=payload)
