from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from gsuid_cli.core.errors import EXIT_INVALID_INPUT, EXIT_NO_RESULT, EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult

AMBR_BASE_URL = "https://gi.yatta.moe"
AMBR_EVENT_URL = f"{AMBR_BASE_URL}/assets/data/event.json"
AMBR_DAILY_URL = f"{AMBR_BASE_URL}/api/v2/chs/dailyDungeon?vh=37F4"
FANDOM_CODE_API = "https://genshin-impact.fandom.com/api.php"
FANDOM_CODE_PAGE = "https://genshin-impact.fandom.com/wiki/Promotional_Code"

WIKI_PATHS = {
    "character": ("avatar", "avatar"),
    "weapon": ("weapon", "weapon"),
    "artifact": ("reliquary", "reliquary"),
    "enemy": ("monster", "monster"),
}
DAY_NAMES = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
CN_TZ = timezone(timedelta(hours=8))


class PublicDataProvider:
    def __init__(self, http_client: HttpClient) -> None:
        self.http = http_client

    def wiki_lookup(self, *, kind: str, query: str) -> CommandResult:
        list_path, detail_path = WIKI_PATHS[kind]
        index = self._ambr_json(
            f"{AMBR_BASE_URL}/api/v2/chs/{list_path}",
            category=f"wiki.{kind}.list",
        )
        item = _find_item(
            _items(index.payload, f"wiki.{kind}.list", index.source),
            kind,
            query,
            index.source,
        )
        detail = self._ambr_json(
            f"{AMBR_BASE_URL}/api/v2/chs/{detail_path}/{item['id']}",
            category=f"wiki.{kind}",
        )
        data = detail.payload.get("data")
        if not isinstance(data, dict):
            data = item
        normalized = _normalize_wiki_item(kind, data)
        return CommandResult(
            data={
                "kind": kind,
                "query": query,
                "match": {"id": normalized["id"], "name": normalized["name"]},
                "item": normalized,
            },
            source=detail.source,
        )

    def events_list(self, *, include_all: bool, limit: int) -> CommandResult:
        response = self.http.request_json(
            "GET",
            AMBR_EVENT_URL,
            provider="ambr",
            region="cn",
            category="events.list",
        )
        events = _event_list(response.payload, include_all=include_all, limit=limit)
        return CommandResult(
            data={
                "events": events,
                "count": len(events),
                "filter": "all" if include_all else "active",
            },
            source=response.source,
        )

    def event_banners(self, *, include_all: bool, limit: int) -> CommandResult:
        response = self.http.request_json(
            "GET",
            AMBR_EVENT_URL,
            provider="ambr",
            region="cn",
            category="events.banners",
        )
        events = _event_list(response.payload, include_all=include_all, limit=1000)
        banners = [
            {
                "id": event["id"],
                "name": event["name"],
                "start_at": event["start_at"],
                "end_at": event["end_at"],
                "banner_url": event["banner_url"],
            }
            for event in events
            if event["banner_url"] and _is_banner_event(event)
        ][:limit]
        return CommandResult(
            data={
                "banners": banners,
                "count": len(banners),
                "filter": "all" if include_all else "active",
            },
            source=response.source,
        )

    def daily_materials(self, *, day: str | None, date: str | None = None) -> CommandResult:
        response = self._ambr_json(AMBR_DAILY_URL, category="daily.materials")
        data = response.payload.get("data")
        if not isinstance(data, dict):
            raise _invalid("daily.materials", response.source)
        selected_day = _day_from_date(date) or day or datetime.now(CN_TZ).strftime("%A").lower()
        if selected_day not in DAY_NAMES:
            raise CliError(
                "INVALID_ARGUMENT",
                "day must be a weekday name",
                EXIT_INVALID_INPUT,
                {"day": selected_day},
            )
        day_data = data.get(selected_day)
        if not isinstance(day_data, dict):
            raise CliError(
                "NO_RESULT",
                "No daily material data is available for this day.",
                EXIT_NO_RESULT,
                {"day": selected_day},
                source=response.source,
            )
        domains = [_daily_domain(value) for value in day_data.values() if isinstance(value, dict)]
        return CommandResult(
            data={"date": date, "day": selected_day, "domains": domains, "count": len(domains)},
            source=response.source,
        )

    def codes_list(self) -> CommandResult:
        response = self.http.request_json(
            "GET",
            FANDOM_CODE_API,
            provider="fandom",
            region="cn",
            category="codes.list",
            params={
                "action": "parse",
                "page": "Promotional_Code",
                "prop": "wikitext",
                "format": "json",
                "formatversion": "2",
            },
        )
        parse = response.payload.get("parse")
        wikitext = parse.get("wikitext") if isinstance(parse, dict) else None
        if not isinstance(wikitext, str):
            raise _invalid("codes.list", response.source)
        codes = _parse_active_codes(wikitext)
        return CommandResult(
            data={"codes": codes, "count": len(codes), "source_url": FANDOM_CODE_PAGE},
            source=response.source,
        )

    def _ambr_json(self, url: str, *, category: str):
        response = self.http.request_json(
            "GET",
            url,
            provider="ambr",
            region="cn",
            category=category,
        )
        status = response.payload.get("response")
        if status not in (200, "200", None):
            raise CliError(
                "UPSTREAM_REJECTED",
                "Provider rejected the request.",
                EXIT_UPSTREAM,
                {"provider": "ambr", "category": category, "response": status},
                source=response.source,
            )
        return response


def _items(
    payload: dict[str, object],
    category: str,
    source: dict[str, object],
) -> list[dict[str, object]]:
    data = payload.get("data")
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, dict):
        raise _invalid(category, source)
    return [item for item in items.values() if isinstance(item, dict)]


def _find_item(
    items: list[dict[str, object]],
    kind: str,
    query: str,
    source: dict[str, object],
) -> dict[str, object]:
    normalized_query = _normalize(query)
    for item in items:
        if normalized_query == str(item.get("id") or ""):
            return item
    for item in items:
        names = [item.get("name"), item.get("route")]
        if normalized_query in {_normalize(str(name)) for name in names if name}:
            return item
    for item in items:
        names = [item.get("name"), item.get("route")]
        if any(normalized_query in _normalize(str(name)) for name in names if name):
            return item
    raise CliError(
        "NO_RESULT",
        f"No {kind} matched the query.",
        EXIT_NO_RESULT,
        {"kind": kind, "query": query},
        source=source,
    )


def _normalize(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def _normalize_wiki_item(kind: str, item: dict[str, object]) -> dict[str, object]:
    common = {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or ""),
        "rank": item.get("rank"),
        "icon": item.get("icon"),
        "route": item.get("route"),
    }
    if kind == "character":
        return {
            **common,
            "element": item.get("element"),
            "weapon_type": item.get("weaponType"),
            "region": item.get("region"),
            "birthday": item.get("birthday"),
            "release": item.get("release"),
            "title": _nested(item, "fetter", "title"),
            "description": _nested(item, "fetter", "detail"),
        }
    if kind == "weapon":
        return {
            **common,
            "weapon_type": item.get("type"),
            "description": item.get("description"),
            "affixes": _affixes(item.get("affix")),
        }
    if kind == "artifact":
        return {
            **common,
            "level_list": item.get("levelList"),
            "bonuses": item.get("affixList") or item.get("setBonus"),
        }
    return {
        **common,
        "enemy_type": item.get("type"),
        "title": item.get("title"),
        "special_name": item.get("specialName"),
        "description": item.get("description"),
        "tips": item.get("tips"),
    }


def _nested(item: dict[str, object], key: str, nested_key: str) -> object | None:
    value = item.get(key)
    if not isinstance(value, dict):
        return None
    return value.get(nested_key)


def _affixes(value: object) -> list[dict[str, object]]:
    if not isinstance(value, dict):
        return []
    return [
        {"id": str(key), "name": affix.get("name")}
        for key, affix in value.items()
        if isinstance(affix, dict)
    ]


def _event_list(
    payload: dict[str, object],
    *,
    include_all: bool,
    limit: int,
) -> list[dict[str, object]]:
    events = [_event(value) for value in payload.values() if isinstance(value, dict)]
    if not include_all:
        now = datetime.now(CN_TZ).replace(tzinfo=None)
        events = [event for event in events if _parse_time(event["end_at"]) >= now]
    events.sort(key=lambda event: event["start_at"] or "", reverse=True)
    return events[:limit]


def _event(value: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(value.get("id") or ""),
        "name": _localized(value.get("name")),
        "name_full": _localized(value.get("nameFull")),
        "start_at": str(value.get("startAt") or ""),
        "end_at": str(value.get("endAt") or ""),
        "banner_url": _localized(value.get("banner")),
    }


def _is_banner_event(event: dict[str, object]) -> bool:
    text = f"{event.get('name') or ''} {event.get('name_full') or ''}".casefold()
    markers = ("祈愿", "神铸赋形", "wish")
    return any(marker in text for marker in markers)


def _localized(value: object) -> str | None:
    if isinstance(value, dict):
        for key in ("CHS", "EN", "JP", "KR"):
            text = value.get(key)
            if isinstance(text, str) and text:
                return text
    if isinstance(value, str):
        return value
    return None


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        return datetime.min
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.min


def _daily_domain(value: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(value.get("id") or ""),
        "name": value.get("name"),
        "city": value.get("city"),
        "reward_item_ids": value.get("reward") if isinstance(value.get("reward"), list) else [],
    }


def _day_from_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%A").lower()
    except ValueError as exc:
        raise CliError(
            "INVALID_ARGUMENT",
            "date must use YYYY-MM-DD format",
            EXIT_INVALID_INPUT,
            {"date": value},
        ) from exc


def _parse_active_codes(wikitext: str) -> list[dict[str, object]]:
    start = wikitext.find("==Active Codes==")
    end = wikitext.find("{{Code Row/Footer}}", start)
    if start < 0 or end < 0:
        return []
    section = re.sub(r"<!--.*?-->", "", wikitext[start:end], flags=re.DOTALL)
    rows = re.findall(r"\{\{Code Row\|([^{}]+)\}\}", section)
    codes = []
    for row in rows:
        code = _code_row(row)
        if code is not None:
            codes.append(code)
    return codes


def _code_row(row: str) -> dict[str, object] | None:
    parts = [part.strip() for part in row.split("|")]
    if len(parts) < 5:
        return None
    return {
        "codes": [code.strip() for code in parts[0].split(";") if code.strip()],
        "servers": _servers(parts[1]),
        "rewards": _rewards(parts[2]),
        "discovered_at": parts[3] or None,
        "expires_at": None if parts[4] in {"unknown", "indef"} else parts[4],
        "expiry_status": parts[4] or "unknown",
        "notes": parts[5] if len(parts) > 5 and parts[5] else None,
    }


def _servers(value: str) -> list[str]:
    return {
        "G": ["America", "Europe", "Asia", "TW/HK/Macao"],
        "A": ["America", "Europe", "Asia", "TW/HK/Macao", "China"],
        "CN": ["China"],
    }.get(value, [value])


def _rewards(value: str) -> list[dict[str, object]]:
    rewards = []
    for part in value.split(";"):
        name, _separator, count = part.partition("*")
        if name.strip():
            rewards.append({"name": name.strip(), "count": int(count) if count.isdigit() else None})
    return rewards


def _invalid(category: str, source: dict[str, object]) -> CliError:
    return CliError(
        "UPSTREAM_INVALID_RESPONSE",
        "Provider returned an unexpected response shape.",
        EXIT_UPSTREAM,
        {"provider": "public", "category": category},
        source=source,
    )
