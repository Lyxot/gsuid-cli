from __future__ import annotations

import json
import re
from datetime import datetime

from gsuid_cli.core.errors import EXIT_NO_RESULT, CliError
from gsuid_cli.providers.public.common import (
    CN_TZ,
    dict_value,
    genshinuid_resource_url,
    hakush_ui_url,
    list_value,
    monster_icon_url,
    optional_int,
    optional_text,
    sort_key,
)


def parse_genshinuid_js(js_code: str) -> dict[str, object]:
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


def select_abyss_schedule(
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


def normalize_abyss_floor(
    *,
    abyss_data: dict[str, object],
    schedule: dict[str, object],
    floor: int,
    source: dict[str, object],
) -> dict[str, object]:
    floor_index = floor - 9
    floors = list_value(schedule.get("floors"))
    if floor_index < 0 or floor_index >= len(floors):
        raise CliError(
            "NO_RESULT",
            "No abyss guide floor matched the request.",
            EXIT_NO_RESULT,
            {"version": schedule.get("name"), "floor": floor},
            source=source,
        )
    floor_id = str(floors[floor_index])
    configs = dict_value(abyss_data.get("_SpiralAbyssFloorConfig"))
    floor_config = dict_value(configs.get(floor_id))
    if not floor_config:
        raise CliError(
            "NO_RESULT",
            "No abyss guide floor config matched the schedule.",
            EXIT_NO_RESULT,
            {"version": schedule.get("name"), "floor": floor, "floor_id": floor_id},
            source=source,
        )
    monsters = dict_value(abyss_data.get("_Monsters"))
    chambers = [
        _normalize_abyss_chamber(chamber, monsters)
        for chamber in list_value(floor_config.get("Chambers"))
        if isinstance(chamber, dict)
    ]
    return {
        "floor": floor,
        "floor_id": floor_id,
        "disorder": _clean_markup(floor_config.get("Disorder")),
        "chambers": chambers,
        "chamber_count": len(chambers),
    }


def select_theater_event(
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


def normalize_theater(
    payload: dict[str, object],
    *,
    event_id: str,
    avatar_names: dict[str, str],
) -> dict[str, object]:
    avatar_config = dict_value(payload.get("AvatarConfig"))
    difficulty = dict_value(payload.get("DifficultyConfig"))
    difficulty_rows = [value for value in difficulty.values() if isinstance(value, dict)]
    selected_difficulty = difficulty_rows[-1] if difficulty_rows else {}
    rooms = dict_value(selected_difficulty.get("Room"))
    return {
        "event_id": event_id,
        "begin_time": payload.get("BeginTime"),
        "end_time": payload.get("EndTime"),
        "buff_description": _clean_markup(
            _nested_list_dict(avatar_config.get("BuffAvatarList"), 0, "Desc")
        ),
        "buff_avatars": [
            _theater_avatar(avatar.get("Id"), avatar_names)
            for avatar in list_value(avatar_config.get("BuffAvatarList"))
            if isinstance(avatar, dict)
        ],
        "invite_avatars": [
            _theater_avatar(avatar_id, avatar_names)
            for avatar_id in list_value(avatar_config.get("InviteAvatarList"))
        ],
        "rooms": [
            _theater_room(room_id, room)
            for room_id, room in sorted(rooms.items(), key=lambda item: sort_key(item[0]))
            if isinstance(room, dict)
        ],
    }


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
        "floors": list_value(row.get("Floors")),
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
    for index, wave in enumerate(list_value(value), start=1):
        if not isinstance(wave, dict):
            continue
        waves.append(
            {
                "index": index,
                "wave_desc": wave.get("WaveDesc"),
                "extra_desc": _clean_markup(_nested_dict(wave, "ExtraDesc", "CH")),
                "monsters": [
                    _normalize_abyss_monster(monster, monsters)
                    for monster in list_value(wave.get("Monsters"))
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
    config = dict_value(monsters.get(monster_id))
    name = _localized(monster.get("Name")) or optional_text(config.get("Name")) or "未知怪物"
    icon = _first_text(config.get("Icon")) or optional_text(monster.get("Icon"))
    if monster.get("Mark"):
        name = f"*{name}"
    return {
        "id": monster_id,
        "name": name.replace("-", "·").replace("·光", "·芒"),
        "count": optional_int(monster.get("Num")) or 1,
        "icon": icon,
        "icon_url": monster_icon_url(icon),
    }


def _parse_theater_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _theater_avatar(value: object, avatar_names: dict[str, str]) -> dict[str, object]:
    avatar_id = str(value or "")
    return {
        "id": avatar_id,
        "name": avatar_names.get(avatar_id) or avatar_id,
        "image_url": genshinuid_resource_url("resource/chars", f"{avatar_id}.png")
        if avatar_id
        else None,
    }


def _theater_room(room_id: object, room: dict[str, object]) -> dict[str, object]:
    title = optional_text(room.get("Title"))
    return {
        "id": str(room_id),
        "title": title,
        "description": _clean_markup(room.get("Desc")) if title else None,
        "monster_level": room.get("MonsterLevel"),
        "monsters": [
            _theater_monster(monster)
            for monster in list_value(room.get("MonsterPreviewList"))
            if isinstance(monster, dict)
        ],
    }


def _theater_monster(monster: dict[str, object]) -> dict[str, object]:
    icon = optional_text(monster.get("Icon"))
    name = optional_text(monster.get("Name")) or "未知怪物"
    if "·" in name:
        name = name.split("·")[-1]
    return {
        "id": str(monster.get("Id") or ""),
        "name": name,
        "hp": optional_int(monster.get("Hp")) or 0,
        "icon": icon,
        "icon_url": monster_icon_url(icon),
        "icon_urls": [url for url in (monster_icon_url(icon), hakush_ui_url(icon)) if url],
    }


def _nested_dict(value: dict[str, object], key: str, nested_key: str) -> object | None:
    nested = value.get(key)
    if not isinstance(nested, dict):
        return None
    return nested.get(nested_key)


def _nested_list_dict(value: object, index: int, key: str) -> object | None:
    items = list_value(value)
    if index < 0 or index >= len(items):
        return None
    item = items[index]
    if not isinstance(item, dict):
        return None
    return item.get(key)


def _first_text(value: object) -> str | None:
    if isinstance(value, list):
        for item in value:
            text = optional_text(item)
            if text:
                return text
        return None
    return optional_text(value)


def _clean_markup(value: object) -> str:
    text = optional_text(value) or ""
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<.*?>", "", text)
    return text.replace("@", "").replace("#", "").strip()


def _localized(value: object) -> str | None:
    if isinstance(value, dict):
        for key in ("CHS", "EN", "JP", "KR"):
            text = value.get(key)
            if isinstance(text, str) and text:
                return text
    if isinstance(value, str):
        return value
    return None
