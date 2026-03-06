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
MINIGG_MAP_URL = "https://map.minigg.cn/map/get_map"

WIKI_PATHS = {
    "character": ("avatar", "avatar"),
    "weapon": ("weapon", "weapon"),
    "artifact": ("reliquary", "reliquary"),
    "enemy": ("monster", "monster"),
    "food": ("food", "food"),
}
DAY_NAMES = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
CN_TZ = timezone(timedelta(hours=8))
MAP_IDS = {"teyvat": "2", "chasm": "7", "enkanomiya": "9"}


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

    def character_talent(self, *, character: str, talent: int) -> CommandResult:
        base = self.wiki_lookup(kind="character", query=character)
        item = _dict_value(base.data.get("item"))
        talents = _dict_value(item.get("talent"))
        talent_item = _indexed_item(talents, talent)
        if talent_item is None:
            raise CliError(
                "NO_RESULT",
                "No talent matched the requested index.",
                EXIT_NO_RESULT,
                {"character": character, "talent": talent},
                source=base.source,
            )
        return CommandResult(
            data={
                "character": item.get("name"),
                "talent": {"index": talent, **talent_item},
            },
            source=base.source,
        )

    def character_constellation(
        self,
        *,
        character: str,
        constellation: int | None,
    ) -> CommandResult:
        base = self.wiki_lookup(kind="character", query=character)
        item = _dict_value(base.data.get("item"))
        constellations = _dict_value(item.get("constellation"))
        if constellation is not None:
            constellation_item = _indexed_item(constellations, constellation)
            if constellation_item is None:
                raise CliError(
                    "NO_RESULT",
                    "No constellation matched the requested index.",
                    EXIT_NO_RESULT,
                    {"character": character, "constellation": constellation},
                    source=base.source,
                )
            payload: object = {"index": constellation, **constellation_item}
        else:
            payload = [
                {"index": index + 1, **item}
                for index, item in enumerate(_ordered_dict_items(constellations))
            ]
        return CommandResult(
            data={"character": item.get("name"), "constellation": payload},
            source=base.source,
        )

    def character_materials(self, *, character: str) -> CommandResult:
        base = self.wiki_lookup(kind="character", query=character)
        item = _dict_value(base.data.get("item"))
        return CommandResult(
            data={
                "character": item.get("name"),
                "ascension": item.get("ascension") or {},
                "upgrade": _upgrade_materials(item.get("upgrade")),
                "talents": _talent_materials(item.get("talent")),
            },
            source=base.source,
        )

    def weapon_materials(self, *, weapon: str) -> CommandResult:
        base = self.wiki_lookup(kind="weapon", query=weapon)
        item = _dict_value(base.data.get("item"))
        return CommandResult(
            data={
                "weapon": item.get("name"),
                "ascension": item.get("ascension") or {},
                "upgrade": _upgrade_materials(item.get("upgrade")),
            },
            source=base.source,
        )

    def guide_character(self, *, character: str) -> CommandResult:
        base = self.wiki_lookup(kind="character", query=character)
        item = _dict_value(base.data.get("item"))
        return CommandResult(
            data={
                "character": item.get("name"),
                "source": "project-amber",
                "overview": {
                    "title": item.get("title"),
                    "element": item.get("element"),
                    "weapon_type": item.get("weapon_type"),
                    "description": item.get("description"),
                },
                "materials": {
                    "ascension": item.get("ascension") or {},
                    "upgrade": _upgrade_materials(item.get("upgrade")),
                    "talents": _talent_materials(item.get("talent")),
                },
                "recommendations": [],
                "source_limitations": [
                    "curated builds are not available from the Project Amber source"
                ],
            },
            source=base.source,
        )

    def reference_panel(self, *, character: str) -> CommandResult:
        base = self.wiki_lookup(kind="character", query=character)
        item = _dict_value(base.data.get("item"))
        return CommandResult(
            data={
                "character": item.get("name"),
                "available": False,
                "reference_panel": None,
                "source_limitations": ["no stable public reference-panel provider is configured"],
            },
            warnings=["reference-panel targets are not available from the public data source"],
            source=base.source,
        )

    def recommend_build(self, *, character: str) -> CommandResult:
        guide = self.guide_character(character=character)
        return CommandResult(
            data={
                "character": guide.data["character"],
                "recommendations": [],
                "basis": "Project Amber facts only; curated build data unavailable",
                "source_limitations": guide.data["source_limitations"],
            },
            warnings=[
                "curated build recommendations are not available from the public data source"
            ],
            source=guide.source,
        )

    def recommend_holder(self, *, item: str) -> CommandResult:
        matches: list[dict[str, object]] = []
        source = None
        for kind in ("weapon", "artifact"):
            try:
                match = self.wiki_lookup(kind=kind, query=item)
            except CliError as exc:
                if exc.code == "NO_RESULT":
                    continue
                raise
            if source is None:
                source = match.source
            matches.append(
                {
                    "kind": kind,
                    "match": match.data["match"],
                    "holders": [],
                    "source_limitations": [
                        "holder recommendations require curated guide data not available here"
                    ],
                }
            )
        if not matches:
            raise CliError(
                "NO_RESULT",
                "No weapon or artifact matched the item query.",
                EXIT_NO_RESULT,
                {"item": item},
            )
        return CommandResult(
            data={"item": item, "matches": matches, "count": len(matches)},
            warnings=[
                "curated holder recommendations are not available from the public data source"
            ],
            source=source,
        )

    def announcements_list(self, *, limit: int) -> CommandResult:
        result = self.events_list(include_all=True, limit=limit)
        events = result.data.get("events")
        announcements = (
            [_announcement(event) for event in events if isinstance(event, dict)]
            if isinstance(events, list)
            else []
        )
        return CommandResult(
            data={"announcements": announcements, "count": len(announcements)}, source=result.source
        )

    def announcement_show(self, *, announcement_id: str) -> CommandResult:
        result = self.events_list(include_all=True, limit=1000)
        events = result.data.get("events")
        if isinstance(events, list):
            for event in events:
                if isinstance(event, dict) and str(event.get("id") or "") == announcement_id:
                    return CommandResult(
                        data={"announcement": _announcement(event)}, source=result.source
                    )
        raise CliError(
            "NO_RESULT",
            "No announcement matched the id.",
            EXIT_NO_RESULT,
            {"id": announcement_id},
            source=result.source,
        )

    def guide_abyss(self, *, version: str | None, floor: int | None) -> CommandResult:
        result = self.event_banners(include_all=True, limit=100)
        return CommandResult(
            data={
                "version": version,
                "floor": floor,
                "available": False,
                "related_banners": result.data.get("banners", []),
                "source_limitations": [
                    "public abyss guide rotations are not available from the configured sources"
                ],
            },
            warnings=["abyss guide data is not available from the configured public sources"],
            source=result.source,
        )

    def guide_theater(self, *, version: str | None) -> CommandResult:
        result = self.events_list(include_all=True, limit=100)
        return CommandResult(
            data={
                "version": version,
                "available": False,
                "related_events": result.data.get("events", []),
                "source_limitations": [
                    "public theater guide rotations are not available from the configured sources"
                ],
            },
            warnings=["theater guide data is not available from the configured public sources"],
            source=result.source,
        )

    def rerun_list(self, *, limit: int) -> CommandResult:
        result = self.event_banners(include_all=True, limit=1000)
        banners = result.data.get("banners")
        now = datetime.now(CN_TZ).replace(tzinfo=None)
        rows = []
        if isinstance(banners, list):
            rows = [
                _rerun_row(banner)
                for banner in banners
                if isinstance(banner, dict)
                and datetime.min < _parse_time(banner.get("end_at")) <= now
            ]
        rows.sort(key=lambda row: str(row.get("last_banner_end_at") or ""), reverse=True)
        return CommandResult(
            data={"reruns": rows[:limit], "count": min(len(rows), limit)}, source=result.source
        )

    def primogems_plan(self, *, version: str | None) -> CommandResult:
        events = self.events_list(include_all=False, limit=100)
        return CommandResult(
            data={
                "version": version,
                "estimate_available": False,
                "estimate": None,
                "active_event_count": events.data.get("count", 0),
                "source_limitations": [
                    "public reward totals are not available from the configured sources"
                ],
            },
            warnings=["primogem estimate unavailable from configured public sources"],
            source=events.source,
        )

    def map_image(self, *, item: str, map_name: str, category: str = "map.find"):
        map_id = MAP_IDS[map_name]
        response = self.http.request_bytes(
            "GET",
            MINIGG_MAP_URL,
            provider="minigg",
            region="cn",
            category=category,
            params={"resource_name": item, "map_id": map_id, "is_cluster": "false"},
        )
        if not response.media_type.startswith("image/"):
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "MiniGG returned a non-image map response.",
                EXIT_UPSTREAM,
                {"item": item, "map": map_name, "media_type": response.media_type},
                source=response.source,
            )
        return response

    def sync_resources(self, *, scope: str) -> CommandResult:
        synced: list[dict[str, object]] = []
        warnings: list[str] = []
        source: dict[str, object] | None = None

        if scope in {"wiki", "icons", "all"}:
            for kind, (list_path, _detail_path) in WIKI_PATHS.items():
                response = self._ambr_json(
                    f"{AMBR_BASE_URL}/api/v2/chs/{list_path}",
                    category=f"resources.sync.{kind}",
                )
                source = response.source
                synced.append(
                    {
                        "scope": "wiki",
                        "kind": kind,
                        "count": len(
                            _items(response.payload, f"resources.sync.{kind}", response.source)
                        ),
                    }
                )
            daily = self._ambr_json(AMBR_DAILY_URL, category="resources.sync.daily-materials")
            source = daily.source
            daily_data = daily.payload.get("data")
            synced.append(
                {
                    "scope": "wiki",
                    "kind": "daily-materials",
                    "count": len(daily_data) if isinstance(daily_data, dict) else 0,
                }
            )
            events = self.http.request_json(
                "GET",
                AMBR_EVENT_URL,
                provider="ambr",
                region="cn",
                category="resources.sync.events",
            )
            source = events.source
            synced.append(
                {
                    "scope": "wiki",
                    "kind": "events",
                    "count": len(
                        [value for value in events.payload.values() if isinstance(value, dict)]
                    ),
                }
            )

        if scope in {"icons", "all"}:
            warnings.append(
                "icon sync refreshes wiki icon references; binary icon files are not downloaded"
            )
        if scope in {"maps", "all"}:
            warnings.append(
                "MiniGG maps are query-specific; "
                "use map find or guide route to create map artifacts"
            )

        return CommandResult(
            data={
                "scope": scope,
                "synced": synced,
                "count": len(synced),
                "source_limitations": warnings,
            },
            warnings=warnings,
            source=source,
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
            "ascension": item.get("ascension"),
            "upgrade": item.get("upgrade"),
            "talent": item.get("talent"),
            "constellation": item.get("constellation"),
        }
    if kind == "weapon":
        return {
            **common,
            "weapon_type": item.get("type"),
            "description": item.get("description"),
            "affixes": _affixes(item.get("affix")),
            "ascension": item.get("ascension"),
            "upgrade": item.get("upgrade"),
        }
    if kind == "artifact":
        return {
            **common,
            "level_list": item.get("levelList"),
            "bonuses": item.get("affixList") or item.get("setBonus"),
        }
    if kind == "food":
        return {
            **common,
            "description": item.get("description"),
            "effect": item.get("effect"),
            "recipe": item.get("recipe"),
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


def _dict_value(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _ordered_dict_items(value: dict[str, object]) -> list[dict[str, object]]:
    rows = [item for item in value.values() if isinstance(item, dict)]
    return rows


def _indexed_item(value: dict[str, object], index: int) -> dict[str, object] | None:
    rows = _ordered_dict_items(value)
    if index < 1 or index > len(rows):
        return None
    return rows[index - 1]


def _upgrade_materials(value: object) -> dict[str, object]:
    upgrade = _dict_value(value)
    return {
        "promote": upgrade.get("promote") or [],
        "prop": upgrade.get("prop") or [],
        "awaken_cost": upgrade.get("awakenCost") or [],
    }


def _talent_materials(value: object) -> list[dict[str, object]]:
    talents = _dict_value(value)
    rows = []
    for index, talent in enumerate(_ordered_dict_items(talents), start=1):
        promote = _dict_value(talent.get("promote"))
        rows.append(
            {
                "index": index,
                "name": talent.get("name"),
                "type": talent.get("type"),
                "promote": promote,
            }
        )
    return rows


def _announcement(event: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(event.get("id") or ""),
        "title": event.get("name"),
        "summary": event.get("name_full"),
        "start_at": event.get("start_at"),
        "end_at": event.get("end_at"),
        "banner_url": event.get("banner_url"),
        "source": "project-amber-event",
    }


def _rerun_row(banner: dict[str, object]) -> dict[str, object]:
    end_at = banner.get("end_at")
    parsed_end = _parse_time(end_at)
    days_since = (
        None
        if parsed_end == datetime.min
        else (datetime.now(CN_TZ).replace(tzinfo=None) - parsed_end).days
    )
    return {
        "entity": banner.get("name"),
        "banner_type": "wish",
        "last_banner_id": banner.get("id"),
        "last_banner_start_at": banner.get("start_at"),
        "last_banner_end_at": end_at,
        "days_since_last_banner": days_since,
        "source_limitations": [
            "entity names are derived from banner titles; no character-level parsing is applied"
        ],
    }


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
