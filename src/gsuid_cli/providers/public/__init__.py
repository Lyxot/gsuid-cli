from __future__ import annotations

import json
import re
from datetime import datetime
from html import unescape
from pathlib import Path

import gsuid_cli.providers.public.common as _public_common
import gsuid_cli.providers.public.daily as _public_daily
import gsuid_cli.providers.public.events as _public_events
import gsuid_cli.providers.public.guide as _public_guide
import gsuid_cli.providers.public.wiki as _public_wiki
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, EXIT_NO_RESULT, EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import (
    HttpClient,
    ProviderBytesResponse,
    ProviderResponse,
    raise_for_retcode,
)
from gsuid_cli.core.models import CommandResult
from gsuid_cli.providers.assets import AssetProvider
from gsuid_cli.providers.public.codes import parse_active_codes as _parse_active_codes

_daily_domain = _public_daily.daily_domain
_day_from_date = _public_daily.day_from_date
_dict_value = _public_common.dict_value
_event_list = _public_events.event_list
_genshinuid_resource_url = _public_common.genshinuid_resource_url
_indexed_item = _public_wiki.indexed_item
_is_banner_event = _public_events.is_banner_event
_list_value = _public_common.list_value
_normalize_abyss_floor = _public_guide.normalize_abyss_floor
_normalize_theater = _public_guide.normalize_theater
_normalize_wiki_item = _public_wiki.normalize_wiki_item
_optional_int = _public_common.optional_int
_ordered_dict_items = _public_wiki.ordered_dict_items
_parse_genshinuid_js = _public_guide.parse_genshinuid_js
_select_abyss_schedule = _public_guide.select_abyss_schedule
_select_theater_event = _public_guide.select_theater_event
_string_list = _public_common.string_list
_talent_materials = _public_wiki.talent_materials
_upgrade_materials = _public_wiki.upgrade_materials

AMBR_BASE_URL = "https://gi.yatta.moe"
AMBR_EVENT_URL = f"{AMBR_BASE_URL}/assets/data/event.json"
AMBR_DAILY_URL = f"{AMBR_BASE_URL}/api/v2/chs/dailyDungeon?vh=37F4"
AMBR_UPGRADE_URL = f"{AMBR_BASE_URL}/api/v2/chs/upgrade?vh=40F3"
AMBR_UI_URL = _public_common.AMBR_UI_URL
AMBR_MONSTER_UI_URL = _public_common.AMBR_MONSTER_UI_URL
MIHOYO_ANNOUNCEMENT_API = "https://hk4e-api-static.mihoyo.com/common/hk4e_cn/announcement/api"
FANDOM_CODE_API = "https://genshin-impact.fandom.com/api.php"
FANDOM_CODE_PAGE = "https://genshin-impact.fandom.com/wiki/Promotional_Code"
GENSHINUID_ADV_LIST_URL = (
    "https://raw.githubusercontent.com/KimigaiiWuyi/GenshinUID/"
    "main/GenshinUID/genshinuid_adv/char_adv_list.json"
)
GENSHINUID_ABYSS_JS_COMMITS_URL = "https://api.github.com/repos/KimigaiiWuyi/GenshinUID/commits"
GENSHINUID_ABYSS_JS_PATH = "GenshinUID/genshinuid_guide/abyss.js"
GENSHINUID_JSDELIVR_BASE = "https://cdn.jsdelivr.net/gh/KimigaiiWuyi/GenshinUID"
GENSHINUID_ACHIEVEMENT_GUIDE_URL = (
    f"{GENSHINUID_JSDELIVR_BASE}@main/GenshinUID/genshinuid_achievement/all_achi.json"
)
GENSHINUID_COMMISSION_GUIDE_URL = (
    f"{GENSHINUID_JSDELIVR_BASE}@main/GenshinUID/genshinuid_achievement/daily_achi.json"
)
ASSETS_ROOT = Path(__file__).resolve().parents[2] / "assets"
PRIMOGEMS_PLAN_ASSET_DIR = ASSETS_ROOT / "misc" / "primogems"
GENSHINUID_RESOURCE_BASE = _public_common.GENSHINUID_RESOURCE_BASE
GENSHINUID_RESOURCE_ASSET_BASE = f"{GENSHINUID_RESOURCE_BASE}resource"
TEYVAT_RETURN_LIST_URL = "https://api.lelaer.com/ys/getRerunList.php"
HAKUSH_ROLECOMBATS_URL = "https://api.hakush.in/gi/data/rolecombat.json"
HAKUSH_ROLECOMBAT_URL = "https://api.hakush.in/gi/data/zh/rolecombat/{}.json"
HAKUSH_UI_URL = _public_common.HAKUSH_UI_URL
MINIGG_MAP_URL = "https://map.minigg.cn/map/get_map"

WIKI_PATHS = {
    "character": ("avatar", "avatar"),
    "weapon": ("weapon", "weapon"),
    "artifact": ("reliquary", "reliquary"),
    "enemy": ("monster", "monster"),
    "food": ("food", "food"),
}
DAY_NAMES = _public_daily.DAY_NAMES
CN_TZ = _public_common.CN_TZ
MAP_IDS = {"teyvat": "2", "chasm": "7", "enkanomiya": "9"}
DAILY_RESET_OFFSET = _public_daily.DAILY_RESET_OFFSET
ANNOUNCEMENT_BLACK_IDS = {762, 422, 423, 1263, 495, 1957, 2522, 2388, 2516, 2476}


class PublicDataProvider:
    def __init__(self, http_client: HttpClient) -> None:
        self.http = http_client

    def health_check(self, *, region: str) -> ProviderResponse:
        return self._ambr_json(
            f"{AMBR_BASE_URL}/api/v2/chs/avatar",
            category="meta.doctor.network",
            region=region,
        )

    def weapon_detail(self, *, weapon_id: str, category: str) -> ProviderResponse:
        return self._ambr_json(
            f"{AMBR_BASE_URL}/api/v2/chs/weapon/{weapon_id}",
            category=category,
        )

    def avatar_index(self, *, category: str) -> ProviderResponse:
        return self._ambr_json(f"{AMBR_BASE_URL}/api/v2/chs/avatar", category=category)

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
                "日常材料升级数据不可用；返回的秘境不包含物品匹配"
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
                "此日期没有可用的日常材料数据。",
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
                "没有匹配请求索引的天赋。",
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
                    "没有匹配请求索引的命座。",
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

    def material_names_by_id(self) -> dict[str, str]:
        response = self._ambr_json(
            f"{AMBR_BASE_URL}/api/v2/chs/material",
            category="wiki.material.names",
        )
        names: dict[str, str] = {}
        for item in _items(response.payload, "wiki.material.names", response.source):
            item_id = str(item.get("id") or "")
            name = _text(item.get("name"))
            if item_id and name:
                names[item_id] = name
        return names

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
                    "Project Amber 数据源不提供精选养成建议"
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
                "没有与该角色匹配的养成建议。",
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
                "没有与查询匹配的武器或圣遗物。",
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
                "不支持的攻略图片类型。",
                EXIT_INVALID_INPUT,
                {"kind": kind},
            )
        return AssetProvider(self.http).image(
            _genshinuid_resource_url(endpoint, filename),
            provider="genshinuid-resource",
            region="cn",
            category=f"guide.{kind}.image",
        )

    def announcements_list(self, *, limit: int) -> CommandResult:
        response = self.http.request_json(
            "GET",
            f"{MIHOYO_ANNOUNCEMENT_API}/getAnnList",
            provider="mihoyo-announcement",
            region="cn",
            category="announcements.list",
            params=_announcement_params(),
        )
        data = self._announcement_data(response.payload, response.source, "announcements.list")
        sections, total = _announcement_sections(data, limit=limit)
        announcements = [
            row
            for section in sections
            for row in _list_value(section.get("items"))
            if isinstance(row, dict)
        ]
        return CommandResult(
            data={
                "announcements": announcements,
                "sections": sections,
                "count": len(announcements),
                "total": total,
                "source_limitations": [
                    "announcement rows use the miHoYo announcement API used by GenshinUID; "
                    "GenshinUID hidden announcement ids are filtered"
                ],
            },
            source=response.source,
        )

    def announcement_show(self, *, announcement_id: str) -> CommandResult:
        response = self.http.request_json(
            "GET",
            f"{MIHOYO_ANNOUNCEMENT_API}/getAnnContent",
            provider="mihoyo-announcement",
            region="cn",
            category="announcements.show",
            params=_announcement_params(),
        )
        data = self._announcement_data(response.payload, response.source, "announcements.show")
        for row in _list_value(data.get("list")):
            if isinstance(row, dict) and str(row.get("ann_id") or "") == announcement_id:
                announcement = _announcement_content(row)
                metadata = self._announcement_metadata(announcement_id)
                if metadata:
                    _merge_missing_announcement_fields(announcement, metadata)
                return CommandResult(data={"announcement": announcement}, source=response.source)
        raise CliError(
            "NO_RESULT",
            "没有匹配该 id 的公告。",
            EXIT_NO_RESULT,
            {"id": announcement_id},
            source=response.source,
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
                    "深境螺旋攻略数据通过 jsDelivr 从 GenshinUID abyss.js 获取；"
                    "图片渲染署名为 妮可少年"
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
            warnings.append("幻想真境剧诗角色名称不可用；渲染了角色 id 作为替代")
        theater = _normalize_theater(detail.payload, event_id=event_id, avatar_names=avatar_names)
        return CommandResult(
            data={
                "version": event_id,
                "requested_version": version,
                "available": True,
                "theater": theater,
                "source_limitations": ["幻想真境剧诗攻略数据来源于 Hakush rolecombat 数据"],
            },
            warnings=warnings,
            source=detail.source,
        )

    def achievement_guide(self, *, query: str) -> CommandResult:
        response = self.http.request_json(
            "GET",
            GENSHINUID_ACHIEVEMENT_GUIDE_URL,
            provider="genshinuid",
            region="cn",
            category="guide.achievement.data",
        )
        match = _achievement_guide_match(response.payload, query)
        return CommandResult(
            data={
                "query": query,
                "kind": "achievement",
                "available": True,
                "matches": [match] if match else [],
                "count": 1 if match else 0,
                "source": "GenshinUID all_achi.json",
            },
            source=response.source,
            warnings=[] if match else [f"暂无匹配成就攻略: {query}"],
        )

    def commission_guide(self, *, query: str) -> CommandResult:
        response = self.http.request_json(
            "GET",
            GENSHINUID_COMMISSION_GUIDE_URL,
            provider="genshinuid",
            region="cn",
            category="guide.commission.data",
        )
        match = _commission_guide_match(response.payload, query)
        return CommandResult(
            data={
                "query": query,
                "kind": "commission",
                "available": True,
                "matches": [match] if match else [],
                "count": 1 if match else 0,
                "source": "GenshinUID daily_achi.json",
            },
            source=response.source,
            warnings=[] if match else [f"暂无匹配委托攻略: {query}"],
        )

    def rerun_list(self, *, limit: int) -> CommandResult:
        response = self.http.request_json(
            "GET",
            TEYVAT_RETURN_LIST_URL,
            provider="teyvat",
            region="cn",
            category="rerun.list",
            headers={"User-Agent": "GenshinUID & GsCore"},
        )
        if int(response.payload.get("code") or 0) != 200:
            raise CliError(
                "UPSTREAM_REJECTED",
                "提瓦特复刻列表数据源拒绝了请求。",
                EXIT_UPSTREAM,
                {"code": response.payload.get("code")},
                source=response.source,
            )
        all_groups = _teyvat_rerun_groups(response.payload, response.source)
        all_rows = [item for group in all_groups for item in group["items"]]
        all_rows.sort(key=lambda row: int(row.get("days_since_last_banner") or 0), reverse=True)
        rows = all_rows[:limit]
        groups = _teyvat_rerun_groups_from_rows(rows)
        return CommandResult(
            data={
                "version": _text(response.payload.get("version")),
                "groups": groups,
                "reruns": rows[:limit],
                "count": min(len(rows), limit),
                "total_count": len(all_rows),
            },
            source=response.source,
        )

    def primogems_plan(self, *, version: str | None) -> CommandResult:
        available_versions = _available_primogems_versions()
        selected_version = _select_primogems_version(version, available_versions)
        warnings = []
        if selected_version is None:
            warnings.append("所请求版本的原石获取预估图不可用")
        return CommandResult(
            data={
                "version": version,
                "selected_version": selected_version,
                "available_versions": available_versions,
                "estimate_available": selected_version is not None,
                "estimate": None,
                "source_limitations": [
                    "GenshinUID 提供了静态的版本原石预估图片"
                ],
            },
            warnings=warnings,
            source=_local_primogems_plan_source(),
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
                "MiniGG 返回了非图片的地图响应。",
                EXIT_UPSTREAM,
                {"item": item, "map": map_name, "media_type": response.media_type},
                source=response.source,
            )
        return response

    def _ambr_json(self, url: str, *, category: str, region: str = "cn"):
        response = self.http.request_json(
            "GET",
            url,
            provider="ambr",
            region=region,
            category=category,
        )
        status = response.payload.get("response")
        if status not in (200, "200", None):
            raise CliError(
                "UPSTREAM_REJECTED",
                "数据源拒绝了请求。",
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

    def _announcement_data(
        self,
        payload: dict[str, object],
        source: dict[str, object],
        category: str,
    ) -> dict[str, object]:
        raise_for_retcode(
            payload,
            provider="mihoyo-announcement",
            region="cn",
            category=category,
            source=source,
            debug=self.http.debug,
        )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise _invalid(category, source)
        return data

    def _announcement_metadata(self, announcement_id: str) -> dict[str, object] | None:
        response = self.http.request_json(
            "GET",
            f"{MIHOYO_ANNOUNCEMENT_API}/getAnnList",
            provider="mihoyo-announcement",
            region="cn",
            category="announcements.show.metadata",
            params=_announcement_params(),
        )
        data = self._announcement_data(
            response.payload, response.source, "announcements.show.metadata"
        )
        for section in _list_value(data.get("list")):
            if not isinstance(section, dict):
                continue
            for row in _list_value(section.get("list")):
                if isinstance(row, dict) and str(row.get("ann_id") or "") == announcement_id:
                    return _announcement_row(row, section)
        return None

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
                "数据源返回了无效的建议数据。",
                EXIT_UPSTREAM,
                {"url": GENSHINUID_ADV_LIST_URL},
                source=response.source,
            ) from exc
        if not isinstance(payload, dict):
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "数据源返回了非预期的建议数据格式。",
                EXIT_UPSTREAM,
                {"url": GENSHINUID_ADV_LIST_URL},
                source=response.source,
            )
        return payload, response.source

    def _abyss_js(self) -> tuple[dict[str, object], dict[str, object]]:
        revision = self._genshinuid_abyss_js_revision()
        url = _genshinuid_abyss_js_url(revision)
        response = self.http.request_bytes(
            "GET",
            url,
            provider="genshinuid",
            region="cn",
            category="guide.abyss.data",
            expected_media_types=("application/javascript", "application/x-javascript", "text/"),
        )
        try:
            js_code = response.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "数据源返回了无效的深境螺旋攻略数据编码。",
                EXIT_UPSTREAM,
                {"url": url, "revision": revision},
                source=response.source,
            ) from exc
        try:
            payload = _parse_genshinuid_js(js_code)
        except ValueError as exc:
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "数据源返回了无效的深境螺旋攻略数据。",
                EXIT_UPSTREAM,
                {"url": url, "revision": revision},
                source=response.source,
            ) from exc
        source = dict(response.source)
        source["revision"] = revision
        return payload, source

    def _genshinuid_abyss_js_revision(self) -> str:
        response = self.http.request_bytes(
            "GET",
            GENSHINUID_ABYSS_JS_COMMITS_URL,
            provider="github",
            region="global",
            category="guide.abyss.revision",
            params={
                "path": GENSHINUID_ABYSS_JS_PATH,
                "per_page": "1",
            },
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "gsuid-cli",
            },
            expected_media_types=("application/json",),
        )
        try:
            payload = json.loads(response.content.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "数据源返回了无效的 GenshinUID 修订版本数据。",
                EXIT_UPSTREAM,
                {"url": GENSHINUID_ABYSS_JS_COMMITS_URL, "path": GENSHINUID_ABYSS_JS_PATH},
                source=response.source,
            ) from exc
        if not isinstance(payload, list) or not payload:
            raise CliError(
                "NO_RESULT",
                "未找到 GenshinUID abyss.js 的修订版本。",
                EXIT_NO_RESULT,
                {"url": GENSHINUID_ABYSS_JS_COMMITS_URL, "path": GENSHINUID_ABYSS_JS_PATH},
                source=response.source,
            )
        first = payload[0]
        sha = first.get("sha") if isinstance(first, dict) else None
        if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "数据源返回了无效的 GenshinUID 修订版本。",
                EXIT_UPSTREAM,
                {"url": GENSHINUID_ABYSS_JS_COMMITS_URL, "path": GENSHINUID_ABYSS_JS_PATH},
                source=response.source,
            )
        return sha

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
        f"没有匹配查询的 {kind}。",
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


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _announcement_text(content: str) -> str:
    content = unescape(content).replace("<<", "")
    content = re.sub(r"</(?:p|div|li|h[1-6])\s*>", "\n", content, flags=re.I)
    content = re.sub(r"<br\s*/?>", "\n", content, flags=re.I)
    text = re.sub(r"<[^>]+>", "", content)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _announcement_image_urls(content: str) -> list[str]:
    content = unescape(content)
    return [
        unescape(match.group(1))
        for match in re.finditer(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"'][^>]*>", content, re.I)
    ]


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


def _announcement_params() -> dict[str, object]:
    return {
        "game": "hk4e",
        "game_biz": "hk4e_cn",
        "lang": "zh-cn",
        "bundle_id": "hk4e_cn",
        "level": 57,
        "platform": "pc",
        "region": "cn_gf01",
        "uid": "114514",
    }


def _announcement_sections(
    data: dict[str, object],
    *,
    limit: int,
) -> tuple[list[dict[str, object]], int]:
    sections: list[dict[str, object]] = []
    remaining = limit
    total = 0
    for section in _list_value(data.get("list")):
        if not isinstance(section, dict):
            continue
        rows: list[dict[str, object]] = []
        for row in _list_value(section.get("list")):
            if not isinstance(row, dict):
                continue
            ann_id = _int_or_none(row.get("ann_id"))
            if ann_id in ANNOUNCEMENT_BLACK_IDS:
                continue
            total += 1
            if remaining <= 0:
                continue
            rows.append(_announcement_row(row, section))
            remaining -= 1
        if rows:
            sections.append(
                {
                    "type_id": _int_or_none(section.get("type_id")),
                    "type_label": _text(section.get("type_label") or section.get("type_name")),
                    "items": rows,
                    "count": len(rows),
                }
            )
    return sections, total


def _announcement_row(row: dict[str, object], section: dict[str, object]) -> dict[str, object]:
    ann_id = str(row.get("ann_id") or "")
    return {
        "id": ann_id,
        "ann_id": ann_id,
        "title": _text(row.get("title")),
        "subtitle": _text(row.get("subtitle")),
        "summary": _text(row.get("content")),
        "banner_url": _text(row.get("banner")),
        "tag": _text(row.get("tag_label")),
        "type_id": _int_or_none(section.get("type_id")),
        "type_label": _text(section.get("type_label") or section.get("type_name")),
        "start_at": _text(row.get("start_time")),
        "end_at": _text(row.get("end_time")),
        "remind": bool(row.get("remind")),
        "source": "mihoyo-announcement",
    }


def _announcement_content(row: dict[str, object]) -> dict[str, object]:
    content = _text(row.get("content")) or ""
    ann_id = str(row.get("ann_id") or "")
    return {
        "id": ann_id,
        "ann_id": ann_id,
        "title": _text(row.get("title")),
        "subtitle": _text(row.get("subtitle")),
        "banner_url": _text(row.get("banner")),
        "start_at": _text(row.get("start_time")),
        "end_at": _text(row.get("end_time")),
        "content_html": content,
        "text": _announcement_text(content),
        "image_urls": _announcement_image_urls(content),
        "source": "mihoyo-announcement",
    }


def _merge_missing_announcement_fields(
    announcement: dict[str, object],
    metadata: dict[str, object],
) -> None:
    for key, value in metadata.items():
        if key not in announcement or announcement[key] in (None, ""):
            announcement[key] = value


def _teyvat_rerun_groups(
    payload: dict[str, object], source: dict[str, object]
) -> list[dict[str, object]]:
    result = payload.get("result")
    if not isinstance(result, list) or len(result) < 4:
        raise CliError(
            "UPSTREAM_INVALID_RESPONSE",
            "提瓦特复刻列表响应未包含四个复刻组。",
            EXIT_UPSTREAM,
            {"result_type": type(result).__name__},
            source=source,
        )
    specs = [
        ("character", 5, "五星角色"),
        ("character", 4, "四星角色"),
        ("weapon", 5, "五星武器"),
        ("weapon", 4, "四星武器"),
    ]
    groups: list[dict[str, object]] = []
    for index, (kind, rarity, label) in enumerate(specs):
        raw_items = result[index]
        items = [
            _teyvat_rerun_item(item, kind=kind, rarity=rarity, group_index=index)
            for item in raw_items
            if isinstance(item, dict)
        ]
        items.sort(key=lambda item: int(item.get("days_since_last_banner") or 0), reverse=True)
        groups.append({"kind": kind, "rarity": rarity, "label": label, "items": items})
    return groups


def _teyvat_rerun_item(
    item: dict[str, object],
    *,
    kind: str,
    rarity: int,
    group_index: int,
) -> dict[str, object]:
    raw_history = item.get("history")
    history = (
        [str(value) for value in raw_history if value] if isinstance(raw_history, list) else []
    )
    last_banner = history[-1] if history else None
    days = _optional_int(item.get("days"))
    role = _text(item.get("role"))
    return {
        "entity": role,
        "kind": kind,
        "rarity": rarity,
        "group_index": group_index,
        "banner_type": "wish",
        "icon_url": _text(item.get("avatar")),
        "days_since_last_banner": days,
        "intro": _text(item.get("intro")),
        "history": history,
        "last_banner_version": last_banner,
        "average_gap_days": _optional_int(item.get("avg_days")),
        "up_times": _optional_int(item.get("up_times")),
        "max_gap_days": _optional_int(item.get("max_gap_days")),
        "max_gap_pool": _text(item.get("max_gap_pool")),
        "min_gap_days": _optional_int(item.get("min_gap_days")),
        "min_gap_pool": _text(item.get("min_gap_pool")),
        "width": _optional_int(item.get("width")),
        "width_rate": _optional_int(item.get("width_rate")),
    }


def _teyvat_rerun_groups_from_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    specs = [
        (0, "character", 5, "五星角色"),
        (1, "character", 4, "四星角色"),
        (2, "weapon", 5, "五星武器"),
        (3, "weapon", 4, "四星武器"),
    ]
    groups = []
    for group_index, kind, rarity, label in specs:
        groups.append(
            {
                "kind": kind,
                "rarity": rarity,
                "label": label,
                "items": [row for row in rows if int(row.get("group_index") or 0) == group_index],
            }
        )
    return groups


def _available_primogems_versions() -> list[str]:
    if not PRIMOGEMS_PLAN_ASSET_DIR.exists():
        return []
    versions = [path.stem for path in PRIMOGEMS_PLAN_ASSET_DIR.glob("*.png")]
    versions.sort(key=_version_sort_key)
    return versions


def _select_primogems_version(version: str | None, available_versions: list[str]) -> str | None:
    if version:
        return version if version in available_versions else None
    return available_versions[-1] if available_versions else None


def _version_sort_key(version: str) -> tuple[int, ...]:
    parts = []
    for part in re.findall(r"\d+", version):
        parts.append(int(part))
    return tuple(parts)


def _genshinuid_abyss_js_url(revision: str) -> str:
    return f"{GENSHINUID_JSDELIVR_BASE}@{revision}/{GENSHINUID_ABYSS_JS_PATH}"


def _local_primogems_plan_source() -> dict[str, object]:
    return {
        "provider": "genshinuid",
        "region": "cn",
        "cached": True,
        "fetched_at": None,
        "path": "package:assets/misc/primogems",
    }


def _achievement_guide_match(
    payload: dict[str, object],
    query: str,
) -> dict[str, object] | None:
    name, detail = _guide_match(payload, query)
    if detail is None:
        return None
    return {
        "name": name,
        "book": _text(detail.get("book")),
        "description": _text(detail.get("desc")),
        "guide": _text(detail.get("guide")),
        "link": _text(detail.get("link")),
    }


def _commission_guide_match(
    payload: dict[str, object],
    query: str,
) -> dict[str, object] | None:
    name, detail = _guide_match(payload, query)
    if detail is None:
        return None
    return {
        "name": name,
        "achievement": _text(detail.get("achievement")),
        "description": _text(detail.get("desc")),
        "guide": _text(detail.get("guide")),
        "link": _text(detail.get("link")),
    }


def _guide_match(
    payload: dict[str, object],
    query: str,
) -> tuple[str, dict[str, object] | None]:
    if query in payload and isinstance(payload[query], dict):
        return query, payload[query]
    query_chars = set(_chinese_text(query))
    best_name = ""
    best_detail: dict[str, object] | None = None
    best_score = 0
    for name, value in payload.items():
        if not isinstance(value, dict):
            continue
        normalized_name = _chinese_text(str(name))
        normalized_name = normalized_name.replace("每日委托", "").replace("世界任务", "")
        if not normalized_name:
            continue
        score = len(set(normalized_name) & query_chars)
        if score >= len(normalized_name) / 2 and score > best_score:
            best_score = score
            best_name = str(name)
            best_detail = value
    return best_name, best_detail


def _chinese_text(value: str) -> str:
    return "".join(re.findall("[\u4e00-\u9fa5]", value))


def _current_daily_day() -> str:
    return (datetime.now(CN_TZ) - DAILY_RESET_OFFSET).strftime("%A").lower()


def _invalid(category: str, source: dict[str, object]) -> CliError:
    return CliError(
        "UPSTREAM_INVALID_RESPONSE",
        "数据源返回了非预期的响应数据格式。",
        EXIT_UPSTREAM,
        {"provider": "public", "category": category},
        source=source,
    )
