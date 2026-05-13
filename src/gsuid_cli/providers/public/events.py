from __future__ import annotations

from datetime import datetime

from gsuid_cli.providers.public.common import CN_TZ

BANNER_EVENT_MARKERS = ("祈愿", "神铸赋形", "wish")


def event_list(
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


def is_banner_event(event: dict[str, object]) -> bool:
    text = f"{event.get('name') or ''} {event.get('name_full') or ''}".casefold()
    return any(marker in text for marker in BANNER_EVENT_MARKERS)


def _event(value: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(value.get("id") or ""),
        "name": _localized(value.get("name")),
        "name_full": _localized(value.get("nameFull")),
        "start_at": str(value.get("startAt") or ""),
        "end_at": str(value.get("endAt") or ""),
        "banner_url": _localized(value.get("banner")),
    }


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
