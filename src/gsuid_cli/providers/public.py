from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from gsuid_cli.core.errors import EXIT_INVALID_INPUT, EXIT_NO_RESULT, EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import HttpClient, ProviderBytesResponse
from gsuid_cli.core.models import CommandResult

AMBR_BASE_URL = "https://gi.yatta.moe"
AMBR_EVENT_URL = f"{AMBR_BASE_URL}/assets/data/event.json"
AMBR_DAILY_URL = f"{AMBR_BASE_URL}/api/v2/chs/dailyDungeon?vh=37F4"
AMBR_UPGRADE_URL = f"{AMBR_BASE_URL}/api/v2/chs/upgrade?vh=40F3"
AMBR_UI_URL = f"{AMBR_BASE_URL}/assets/UI"
AMBR_MONSTER_UI_URL = f"{AMBR_UI_URL}/monster"
FANDOM_CODE_API = "https://genshin-impact.fandom.com/api.php"
FANDOM_CODE_PAGE = "https://genshin-impact.fandom.com/wiki/Promotional_Code"
GENSHINUID_ADV_LIST_URL = (
    "https://raw.githubusercontent.com/KimigaiiWuyi/GenshinUID/"
    "main/GenshinUID/genshinuid_adv/char_adv_list.json"
)
ASSETS_ROOT = Path(__file__).resolve().parents[1] / "assets"
GENSHINUID_ABYSS_JS_PATH = ASSETS_ROOT / "guide" / "abyss" / "data" / "abyss.js"
GENSHINUID_RESOURCE_BASE = "https://example.test/GenshinUID"
GENSHINUID_RESOURCE_ASSET_BASE = f"{GENSHINUID_RESOURCE_BASE}/resource"
HAKUSH_ROLECOMBATS_URL = "https://api.hakush.in/gi/data/rolecombat.json"
HAKUSH_ROLECOMBAT_URL = "https://api.hakush.in/gi/data/zh/rolecombat/{}.json"
HAKUSH_UI_URL = "https://api.hakush.in/gi/UI"
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
DAILY_RESET_OFFSET = timedelta(hours=4)


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

    def daily_materials(
        self,
        *,
        day: str | None,
        date: str | None = None,
        require_upgrade: bool = False,
    ) -> CommandResult:
        response = self._ambr_json(AMBR_DAILY_URL, category="daily.materials")
        warnings: list[str] = []
        data = response.payload.get("data")
        if not isinstance(data, dict):
            raise _invalid("daily.materials", response.source)
        try:
            upgrades = self._daily_material_upgrades()
        except CliError:
            if require_upgrade:
                raise
            upgrades = {}
            warnings.append(
                "daily material upgrade data is unavailable; returned domains without item matches"
            )
        selected_day = _day_from_date(date) or day or _current_daily_day()
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
        domains = [
            _daily_domain(value, upgrades) for value in day_data.values() if isinstance(value, dict)
        ]
        return CommandResult(
            data={"date": date, "day": selected_day, "domains": domains, "count": len(domains)},
            source=response.source,
            warnings=warnings,
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
                "guide_image_url": _genshinuid_resource_url(
                    "wiki/guide",
                    f"{item.get('name')}.png",
                ),
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
        name = _text(item.get("name")) or character
        return CommandResult(
            data={
                "character": name,
                "available": True,
                "reference_panel": {
                    "format": "image",
                    "source": "GenshinUID wiki/ref",
                    "image_url": _genshinuid_resource_url("wiki/ref", f"{name}.jpg"),
                },
            },
            source=base.source,
        )

    def recommend_build(self, *, character: str) -> CommandResult:
        base = self.wiki_lookup(kind="character", query=character)
        item = _dict_value(base.data.get("item"))
        name = _text(item.get("name")) or character
        adv_list, source = self._adv_list()
        matched_name, info = _find_adv_character(adv_list, name)
        if info is None:
            raise CliError(
                "NO_RESULT",
                "No build recommendation matched the character.",
                EXIT_NO_RESULT,
                {"character": character, "resolved_character": name},
                source=source,
            )
        return CommandResult(
            data={
                "character": matched_name,
                "query": character,
                "source": "GenshinUID char_adv_list.json",
                **_build_recommendation_data(info),
            },
            source=source,
        )

    def recommend_holder(self, *, item: str) -> CommandResult:
        adv_list, adv_source = self._adv_list()
        query_names = {item}
        for kind in ("weapon", "artifact"):
            try:
                match = self.wiki_lookup(kind=kind, query=item)
            except CliError as exc:
                if exc.code == "NO_RESULT":
                    continue
                raise
            match_data = _dict_value(match.data.get("match"))
            match_name = _text(match_data.get("name"))
            if match_name:
                query_names.add(match_name)
        matches = _holder_matches(adv_list, query_names)
        if not matches:
            raise CliError(
                "NO_RESULT",
                "No weapon or artifact matched the item query.",
                EXIT_NO_RESULT,
                {"item": item, "queries": sorted(query_names)},
            )
        return CommandResult(
            data={"item": item, "matches": matches, "count": len(matches)},
            source=adv_source,
        )

    def guide_image(self, *, kind: str, character: str) -> ProviderBytesResponse:
        if kind == "character":
            endpoint = "wiki/guide"
            filename = f"{character}.png"
        elif kind == "reference-panel":
            endpoint = "wiki/ref"
            filename = f"{character}.jpg"
        else:
            raise CliError(
                "INVALID_ARGUMENT",
                "Unsupported guide image kind.",
                EXIT_INVALID_INPUT,
                {"kind": kind},
            )
        return self.http.request_bytes(
            "GET",
            _genshinuid_resource_url(endpoint, filename),
            provider="genshinuid-resource",
            region="cn",
            category=f"guide.{kind}.image",
            expected_media_types=("image/",),
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
        abyss_data, source = self._abyss_js()
        selected, selected_warnings = _select_abyss_schedule(
            _list_value(abyss_data.get("_SpiralAbyssSchedule")),
            version,
            source,
        )
        floor_number = floor or 12
        floor_data = _normalize_abyss_floor(
            abyss_data=abyss_data,
            schedule=selected,
            floor=floor_number,
            source=source,
        )
        return CommandResult(
            data={
                "version": selected.get("name"),
                "requested_version": version,
                "floor": floor_number,
                "available": True,
                "schedule": selected,
                "abyss": floor_data,
                "source_limitations": [
                    "abyss guide data is bundled from GenshinUID abyss.js; "
                    "rendered credit is 妮可少年"
                ],
            },
            warnings=selected_warnings,
            source=source,
        )

    def guide_theater(self, *, version: str | None) -> CommandResult:
        index = self.http.request_json(
            "GET",
            HAKUSH_ROLECOMBATS_URL,
            provider="hakush",
            region="cn",
            category="guide.theater.events",
            headers={"User-Agent": "GenshinUID & GsCore"},
        )
        event_id, selected_warnings = _select_theater_event(index.payload, version, index.source)
        detail = self.http.request_json(
            "GET",
            HAKUSH_ROLECOMBAT_URL.format(event_id),
            provider="hakush",
            region="cn",
            category="guide.theater.detail",
            headers={"User-Agent": "GenshinUID & GsCore"},
        )
        warnings = list(selected_warnings)
        try:
            avatar_names = self._avatar_names_by_id()
        except CliError:
            avatar_names = {}
            warnings.append("theater avatar names are unavailable; rendered avatar ids instead")
        theater = _normalize_theater(detail.payload, event_id=event_id, avatar_names=avatar_names)
        return CommandResult(
            data={
                "version": event_id,
                "requested_version": version,
                "available": True,
                "theater": theater,
                "source_limitations": ["theater guide data is sourced from Hakush rolecombat data"],
            },
            warnings=warnings,
            source=detail.source,
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
            expected_media_types=("image/",),
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
                "cache_backend": "process-memory",
                "persistent_json_cache": False,
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

    def _daily_material_upgrades(self) -> dict[str, object]:
        response = self._ambr_json(
            AMBR_UPGRADE_URL,
            category="daily.materials.upgrade",
        )
        upgrades = response.payload.get("data")
        if not isinstance(upgrades, dict):
            raise _invalid("daily.materials.upgrade", response.source)
        return upgrades

    def _adv_list(self) -> tuple[dict[str, object], dict[str, object]]:
        response = self.http.request_bytes(
            "GET",
            GENSHINUID_ADV_LIST_URL,
            provider="genshinuid",
            region="cn",
            category="recommend.adv-list",
            expected_media_types=("application/json", "text/"),
        )
        try:
            payload = json.loads(response.content.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "Provider returned invalid recommendation data.",
                EXIT_UPSTREAM,
                {"url": GENSHINUID_ADV_LIST_URL},
                source=response.source,
            ) from exc
        if not isinstance(payload, dict):
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "Provider returned recommendation data with an unexpected shape.",
                EXIT_UPSTREAM,
                {"url": GENSHINUID_ADV_LIST_URL},
                source=response.source,
            )
        return payload, response.source

    def _abyss_js(self) -> tuple[dict[str, object], dict[str, object]]:
        source = _local_genshinuid_abyss_source()
        try:
            js_code = GENSHINUID_ABYSS_JS_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "Bundled abyss guide data is unavailable.",
                EXIT_UPSTREAM,
                {"path": str(GENSHINUID_ABYSS_JS_PATH)},
                source=source,
            ) from exc
        try:
            payload = _parse_genshinuid_js(js_code)
        except ValueError as exc:
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "Bundled abyss guide data is invalid.",
                EXIT_UPSTREAM,
                {"path": str(GENSHINUID_ABYSS_JS_PATH)},
                source=source,
            ) from exc
        return payload, source

    def _avatar_names_by_id(self) -> dict[str, str]:
        response = self._ambr_json(f"{AMBR_BASE_URL}/api/v2/chs/avatar", category="guide.avatar")
        names: dict[str, str] = {}
        for item in _items(response.payload, "guide.avatar", response.source):
            avatar_id = str(item.get("id") or "")
            name = _text(item.get("name"))
            if avatar_id and name:
                names[avatar_id] = name
        return names


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


def _local_genshinuid_abyss_source() -> dict[str, object]:
    return {
        "provider": "genshinuid",
        "region": "cn",
        "cached": True,
        "fetched_at": None,
        "path": "package:assets/guide/abyss/data/abyss.js",
    }


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


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _genshinuid_resource_url(endpoint: str, filename: str) -> str:
    return f"{GENSHINUID_RESOURCE_BASE}/{endpoint}/{quote(filename)}"


def _find_adv_character(
    adv_list: dict[str, object],
    character: str,
) -> tuple[str, dict[str, object] | None]:
    normalized = _normalize(character)
    for name, raw_info in adv_list.items():
        if normalized == _normalize(name) and isinstance(raw_info, dict):
            return name, raw_info
    for name, raw_info in adv_list.items():
        if normalized in _normalize(name) and isinstance(raw_info, dict):
            return name, raw_info
    return character, None


def _build_recommendation_data(info: dict[str, object]) -> dict[str, object]:
    weapon_groups: list[dict[str, object]] = []
    recommendations: list[dict[str, object]] = []
    weapons = _dict_value(info.get("weapon"))
    for rarity in ("5", "4", "3"):
        items = _string_list(weapons.get(rarity))
        if not items:
            continue
        row = {"type": "weapon", "rarity": int(rarity), "items": items}
        weapon_groups.append({"rarity": int(rarity), "items": items})
        recommendations.append(row)

    artifact_groups: list[dict[str, object]] = []
    artifacts = info.get("artifact")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            sets = _string_list(artifact)
            if not sets:
                continue
            pieces = [4] if len(sets) == 1 else [2 for _ in sets]
            row = {"type": "artifact", "sets": sets, "pieces": pieces}
            artifact_groups.append({"sets": sets, "pieces": pieces})
            recommendations.append(row)

    return {
        "weapons": weapon_groups,
        "artifacts": artifact_groups,
        "remarks": _string_list(info.get("remark")),
        "recommendations": recommendations,
    }


def _holder_matches(
    adv_list: dict[str, object],
    query_names: set[str],
) -> list[dict[str, object]]:
    weapon_holders: dict[str, set[str]] = {}
    artifact_holders: dict[str, set[str]] = {}
    for character, raw_info in adv_list.items():
        if not isinstance(raw_info, dict):
            continue
        weapons = _dict_value(raw_info.get("weapon"))
        for rarity in ("5", "4", "3"):
            for weapon in _string_list(weapons.get(rarity)):
                if _matches_any_name(weapon, query_names):
                    weapon_holders.setdefault(weapon, set()).add(character)
        artifacts = raw_info.get("artifact")
        if not isinstance(artifacts, list):
            continue
        for artifact_group in artifacts:
            for artifact in _string_list(artifact_group):
                if _matches_any_name(artifact, query_names):
                    artifact_holders.setdefault(artifact, set()).add(character)

    matches: list[dict[str, object]] = []
    for name in sorted(weapon_holders):
        matches.append({"kind": "weapon", "match": name, "holders": sorted(weapon_holders[name])})
    for name in sorted(artifact_holders):
        matches.append(
            {"kind": "artifact", "match": name, "holders": sorted(artifact_holders[name])}
        )
    return matches


def _matches_any_name(candidate: str, query_names: set[str]) -> bool:
    normalized_candidate = _normalize(candidate)
    for query in query_names:
        normalized_query = _normalize(query)
        if normalized_query and normalized_query in normalized_candidate:
            return True
    return False


def _parse_genshinuid_js(js_code: str) -> dict[str, object]:
    source = re.sub(r"(?m)^\s*//.*$", "", js_code).replace("Auto Generated", "")

    def replace_var(match: re.Match[str]) -> str:
        return f'"{match.group(1)}": {match.group(2)}'

    source = re.sub(
        r"var\s+(\w+)\s*=\s*(.*?)(?=\nvar|\Z)",
        replace_var,
        source,
        flags=re.DOTALL,
    )
    source = re.sub(r'(?<=\})(?=\s*"\w)', ",", source)
    source = re.sub(r'(?<=\])(?=\s*"\w)', ",", source)
    payload = json.loads(f"{{{source.strip()}}}")
    if not isinstance(payload, dict):
        raise ValueError("unexpected GenshinUID JS payload")
    return payload


def _select_abyss_schedule(
    schedules: list[object],
    version: str | None,
    source: dict[str, object],
) -> tuple[dict[str, object], list[str]]:
    schedule_rows = [row for row in schedules if isinstance(row, dict)]
    if version:
        for row in schedule_rows:
            name = str(row.get("Name") or row.get("Show") or "")
            if version in name:
                return _abyss_schedule(row), []
        raise CliError(
            "NO_RESULT",
            "No abyss guide schedule matched the requested version.",
            EXIT_NO_RESULT,
            {"version": version},
            source=source,
        )

    now = datetime.now(CN_TZ).replace(tzinfo=None)
    dated_rows: list[tuple[datetime, datetime, dict[str, object]]] = []
    for row in schedule_rows:
        date_range = _parse_abyss_open_time(row.get("OpenTime"))
        if date_range is None:
            continue
        start, end = date_range
        dated_rows.append((start, end, row))
        if start <= now <= end:
            return _abyss_schedule(row), []
    if dated_rows:
        dated_rows.sort(key=lambda item: item[0])
        for start, _end, row in reversed(dated_rows):
            if start <= now:
                selected = _abyss_schedule(row)
                return selected, [
                    "no current abyss guide schedule matched today's date; "
                    f"used latest known GenshinUID schedule {selected['name']}"
                ]
    if schedule_rows:
        selected = _abyss_schedule(schedule_rows[-1])
        return selected, [
            "no dated abyss guide schedule is available; used latest GenshinUID schedule"
        ]
    raise CliError(
        "NO_RESULT",
        "No abyss guide schedules are available.",
        EXIT_NO_RESULT,
        source=source,
    )


def _parse_abyss_open_time(value: object) -> tuple[datetime, datetime] | None:
    if not isinstance(value, str) or " - " not in value:
        return None
    start_text, end_text = value.split(" - ", 1)
    try:
        start = datetime.strptime(start_text.strip(), "%Y/%m/%d")
        end = datetime.strptime(end_text.strip(), "%Y/%m/%d")
    except ValueError:
        return None
    return start, end


def _abyss_schedule(row: dict[str, object]) -> dict[str, object]:
    return {
        "name": row.get("Name"),
        "show": row.get("Show") or row.get("Name"),
        "generation": row.get("Generation"),
        "open_time": row.get("OpenTime"),
        "floors": _list_value(row.get("Floors")),
    }


def _normalize_abyss_floor(
    *,
    abyss_data: dict[str, object],
    schedule: dict[str, object],
    floor: int,
    source: dict[str, object],
) -> dict[str, object]:
    floor_index = floor - 9
    floors = _list_value(schedule.get("floors"))
    if floor_index < 0 or floor_index >= len(floors):
        raise CliError(
            "NO_RESULT",
            "No abyss guide floor matched the request.",
            EXIT_NO_RESULT,
            {"version": schedule.get("name"), "floor": floor},
            source=source,
        )
    floor_id = str(floors[floor_index])
    configs = _dict_value(abyss_data.get("_SpiralAbyssFloorConfig"))
    floor_config = _dict_value(configs.get(floor_id))
    if not floor_config:
        raise CliError(
            "NO_RESULT",
            "No abyss guide floor config matched the schedule.",
            EXIT_NO_RESULT,
            {"version": schedule.get("name"), "floor": floor, "floor_id": floor_id},
            source=source,
        )
    monsters = _dict_value(abyss_data.get("_Monsters"))
    chambers = [
        _normalize_abyss_chamber(chamber, monsters)
        for chamber in _list_value(floor_config.get("Chambers"))
        if isinstance(chamber, dict)
    ]
    return {
        "floor": floor,
        "floor_id": floor_id,
        "disorder": _clean_markup(floor_config.get("Disorder")),
        "chambers": chambers,
        "chamber_count": len(chambers),
    }


def _normalize_abyss_chamber(
    chamber: dict[str, object],
    monsters: dict[str, object],
) -> dict[str, object]:
    return {
        "name": chamber.get("Name"),
        "level": chamber.get("Level"),
        "upper": _normalize_abyss_half(chamber.get("Upper"), monsters),
        "lower": _normalize_abyss_half(chamber.get("Lower"), monsters),
    }


def _normalize_abyss_half(value: object, monsters: dict[str, object]) -> list[dict[str, object]]:
    waves: list[dict[str, object]] = []
    for index, wave in enumerate(_list_value(value), start=1):
        if not isinstance(wave, dict):
            continue
        waves.append(
            {
                "index": index,
                "wave_desc": wave.get("WaveDesc"),
                "extra_desc": _clean_markup(_nested_dict(wave, "ExtraDesc", "CH")),
                "monsters": [
                    _normalize_abyss_monster(monster, monsters)
                    for monster in _list_value(wave.get("Monsters"))
                    if isinstance(monster, dict)
                ],
            }
        )
    return waves


def _normalize_abyss_monster(
    monster: dict[str, object],
    monsters: dict[str, object],
) -> dict[str, object]:
    monster_id = str(monster.get("ID") or "")
    config = _dict_value(monsters.get(monster_id))
    name = _localized(monster.get("Name")) or _text(config.get("Name")) or "未知怪物"
    icon = _first_text(config.get("Icon")) or _text(monster.get("Icon"))
    if monster.get("Mark"):
        name = f"*{name}"
    return {
        "id": monster_id,
        "name": name.replace("-", "·").replace("·光", "·芒"),
        "count": _optional_int(monster.get("Num")) or 1,
        "icon": icon,
        "icon_url": _monster_icon_url(icon),
    }


def _select_theater_event(
    payload: dict[str, object],
    version: str | None,
    source: dict[str, object],
) -> tuple[str, list[str]]:
    events = {str(key): value for key, value in payload.items() if isinstance(value, dict)}
    if version:
        if version in events:
            return version, []
        raise CliError(
            "NO_RESULT",
            "No theater guide event matched the requested version.",
            EXIT_NO_RESULT,
            {"version": version},
            source=source,
        )

    now = datetime.now(CN_TZ).replace(tzinfo=None)
    dated: list[tuple[datetime, datetime, str]] = []
    for event_id, event in events.items():
        start = _parse_theater_time(event.get("live_begin") or event.get("begin"))
        end = _parse_theater_time(event.get("live_end") or event.get("end"))
        if start is None or end is None:
            continue
        dated.append((start, end, event_id))
        if start <= now <= end:
            return event_id, []
    if dated:
        dated.sort(key=lambda item: item[0])
        for start, _end, event_id in reversed(dated):
            if start <= now:
                return event_id, [
                    "no current theater guide event matched today's date; "
                    f"used latest known Hakush rolecombat event {event_id}"
                ]
    if events:
        event_id = sorted(events, key=lambda key: int(key) if key.isdigit() else 0)[-1]
        return event_id, ["no dated theater guide event is available; used latest event id"]
    raise CliError(
        "NO_RESULT",
        "No theater guide events are available.",
        EXIT_NO_RESULT,
        source=source,
    )


def _parse_theater_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _normalize_theater(
    payload: dict[str, object],
    *,
    event_id: str,
    avatar_names: dict[str, str],
) -> dict[str, object]:
    avatar_config = _dict_value(payload.get("AvatarConfig"))
    difficulty = _dict_value(payload.get("DifficultyConfig"))
    difficulty_rows = [value for value in difficulty.values() if isinstance(value, dict)]
    selected_difficulty = difficulty_rows[-1] if difficulty_rows else {}
    rooms = _dict_value(selected_difficulty.get("Room"))
    return {
        "event_id": event_id,
        "begin_time": payload.get("BeginTime"),
        "end_time": payload.get("EndTime"),
        "buff_description": _clean_markup(
            _nested_list_dict(avatar_config.get("BuffAvatarList"), 0, "Desc")
        ),
        "buff_avatars": [
            _theater_avatar(avatar.get("Id"), avatar_names)
            for avatar in _list_value(avatar_config.get("BuffAvatarList"))
            if isinstance(avatar, dict)
        ],
        "invite_avatars": [
            _theater_avatar(avatar_id, avatar_names)
            for avatar_id in _list_value(avatar_config.get("InviteAvatarList"))
        ],
        "rooms": [
            _theater_room(room_id, room)
            for room_id, room in sorted(rooms.items(), key=lambda item: _sort_key(item[0]))
            if isinstance(room, dict)
        ],
    }


def _theater_avatar(value: object, avatar_names: dict[str, str]) -> dict[str, object]:
    avatar_id = str(value or "")
    return {
        "id": avatar_id,
        "name": avatar_names.get(avatar_id) or avatar_id,
        "image_url": _genshinuid_resource_url("resource/chars", f"{avatar_id}.png")
        if avatar_id
        else None,
    }


def _theater_room(room_id: object, room: dict[str, object]) -> dict[str, object]:
    title = _text(room.get("Title"))
    return {
        "id": str(room_id),
        "title": title,
        "description": _clean_markup(room.get("Desc")) if title else None,
        "monster_level": room.get("MonsterLevel"),
        "monsters": [
            _theater_monster(monster)
            for monster in _list_value(room.get("MonsterPreviewList"))
            if isinstance(monster, dict)
        ],
    }


def _theater_monster(monster: dict[str, object]) -> dict[str, object]:
    icon = _text(monster.get("Icon"))
    name = _text(monster.get("Name")) or "未知怪物"
    if "·" in name:
        name = name.split("·")[-1]
    return {
        "id": str(monster.get("Id") or ""),
        "name": name,
        "hp": _optional_int(monster.get("Hp")) or 0,
        "icon": icon,
        "icon_url": _monster_icon_url(icon),
        "icon_urls": [url for url in (_monster_icon_url(icon), _hakush_ui_url(icon)) if url],
    }


def _nested_dict(value: dict[str, object], key: str, nested_key: str) -> object | None:
    nested = value.get(key)
    if not isinstance(nested, dict):
        return None
    return nested.get(nested_key)


def _nested_list_dict(value: object, index: int, key: str) -> object | None:
    items = _list_value(value)
    if index < 0 or index >= len(items):
        return None
    item = items[index]
    if not isinstance(item, dict):
        return None
    return item.get(key)


def _first_text(value: object) -> str | None:
    if isinstance(value, list):
        for item in value:
            text = _text(item)
            if text:
                return text
        return None
    return _text(value)


def _clean_markup(value: object) -> str:
    text = _text(value) or ""
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<.*?>", "", text)
    return text.replace("@", "").replace("#", "").strip()


def _monster_icon_url(icon: str | None) -> str | None:
    if not icon or not icon.startswith("UI_"):
        return None
    return f"{AMBR_MONSTER_UI_URL}/{quote(icon)}.png"


def _hakush_ui_url(icon: str | None) -> str | None:
    return f"{HAKUSH_UI_URL}/{quote(icon)}.webp" if icon else None


def _sort_key(value: object) -> tuple[int, str]:
    text = str(value)
    return (int(text), text) if text.isdigit() else (0, text)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _text(item))]


def _normalize_wiki_item(kind: str, item: dict[str, object]) -> dict[str, object]:
    common = {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or ""),
        "rank": item.get("rank"),
        "icon": item.get("icon"),
        "icon_url": _ambr_ui_icon_url(item.get("icon")),
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
            "special_prop": item.get("specialProp"),
            "affixes": _affixes(item.get("affix")),
            "ascension": item.get("ascension"),
            "upgrade": item.get("upgrade"),
        }
    if kind == "artifact":
        return {
            **common,
            "level_list": item.get("levelList"),
            "bonuses": item.get("affixList") or item.get("setBonus"),
            "suit": _artifact_suit(item.get("suit")),
            "source": item.get("source"),
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
        {
            "id": str(key),
            "name": affix.get("name"),
            "upgrade": affix.get("upgrade"),
        }
        for key, affix in value.items()
        if isinstance(affix, dict)
    ]


def _artifact_suit(value: object) -> list[dict[str, object]]:
    if not isinstance(value, dict):
        return []
    slot_names = {
        "EQUIP_BRACER": "flower",
        "EQUIP_NECKLACE": "plume",
        "EQUIP_SHOES": "sands",
        "EQUIP_RING": "goblet",
        "EQUIP_DRESS": "circlet",
    }
    parts: list[dict[str, object]] = []
    for key in ("EQUIP_BRACER", "EQUIP_NECKLACE", "EQUIP_SHOES", "EQUIP_RING", "EQUIP_DRESS"):
        part = value.get(key)
        if not isinstance(part, dict):
            continue
        icon = part.get("icon")
        parts.append(
            {
                "slot": slot_names[key],
                "name": part.get("name"),
                "description": part.get("description"),
                "max_level": part.get("maxLevel"),
                "icon": icon,
                "icon_url": _ambr_ui_icon_url(icon),
            }
        )
    return parts


def _dict_value(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _list_value(value: object) -> list[object]:
    return value if isinstance(value, list) else []


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


def _daily_domain(value: dict[str, object], upgrades: dict[str, object]) -> dict[str, object]:
    reward_ids = value.get("reward") if isinstance(value.get("reward"), list) else []
    name = value.get("name")
    material_id = reward_ids[-1] if reward_ids else None
    item_type = "weapon" if "炼武" in str(name or "") else "avatar"
    return {
        "id": str(value.get("id") or ""),
        "name": name,
        "city": value.get("city"),
        "reward_item_ids": reward_ids,
        "domain_icon_url": _ambr_item_icon_url(material_id),
        "items": _daily_domain_items(reward_ids, upgrades, item_type),
    }


def _daily_domain_items(
    reward_ids: list[object],
    upgrades: dict[str, object],
    item_type: str,
) -> list[dict[str, object]]:
    data = upgrades.get(item_type)
    if not isinstance(data, dict):
        return []
    reward_ints = {_optional_int(item_id) for item_id in reward_ids}
    reward_ints.discard(None)

    items: list[dict[str, object]] = []
    seen: set[str] = set()
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        costs = value.get("items")
        if not isinstance(costs, dict):
            continue
        if not any(_optional_int(cost_id) in reward_ints for cost_id in costs):
            continue
        item_id = str(value.get("id") or key)
        if item_id in seen:
            continue
        seen.add(item_id)
        icon = value.get("icon")
        items.append(
            {
                "id": item_id,
                "type": item_type,
                "name": value.get("name"),
                "rank": value.get("rank"),
                "icon": icon,
                "icon_url": _ambr_ui_icon_url(icon),
            }
        )
    return items


def _ambr_item_icon_url(item_id: object) -> str | None:
    if item_id is None:
        return None
    text = str(item_id).strip()
    return f"{AMBR_UI_URL}/UI_ItemIcon_{text}.png" if text else None


def _ambr_ui_icon_url(icon: object) -> str | None:
    if not isinstance(icon, str) or not icon:
        return None
    if icon.startswith("UI_RelicIcon_"):
        return f"{AMBR_UI_URL}/reliquary/{icon}.png"
    return f"{AMBR_UI_URL}/{icon}.png"


def _optional_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


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


def _current_daily_day() -> str:
    return (datetime.now(CN_TZ) - DAILY_RESET_OFFSET).strftime("%A").lower()


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
