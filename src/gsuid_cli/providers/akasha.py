from __future__ import annotations

from copy import deepcopy
from urllib.parse import unquote

from gsuid_cli.core.errors import (
    EXIT_INVALID_INPUT,
    EXIT_NO_RESULT,
    CliError,
)
from gsuid_cli.core.http import HttpClient, ProviderResponse
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.core.time import utc_now

PROVIDER = "akasha"
BASE_URL = "https://akasha.cv/api"
MAIN_API = f"{BASE_URL}/filters/accounts/"
DATA_API = f"{BASE_URL}/user/{{}}"
REFRESH_API = f"{BASE_URL}/user/refresh/{{}}"
RANK_API = f"{BASE_URL}/getCalculationsForUser/{{}}"
BUILDS_API = f"{BASE_URL}/builds"
LEADERBOARD_API = f"{BASE_URL}/v2/leaderboards/categories"
SORT_API = f"{BASE_URL}/leaderboards"
ARTIFACT_API = f"{BASE_URL}/artifacts"
DEFAULT_SESSION_ID = "NVybrjSdSZISA0JRuKFoZIndoCfDWdA2"
HEADERS = {
    "User-Agent": "GsCore / GenshinUID / 6.2.0",
    "Accept-Language": "en-US,en;q=0.9",
}

STAT_MAP = {
    "maxHp": "maxHP",
    "atk": "maxATK",
    "def": "maxDEF",
    "elementalMastery": "elementalMastery",
    "energyRecharge": "energyRecharge",
    "healingBonus": "healingBonus",
    "critRate": "critRate",
    "critDamage": "critDMG",
}

ARTIFACT_SORT_MAP = {
    "crit": "critValue",
    "cv": "critValue",
    "双爆": "critValue",
    "atk": "substats.ATK%",
    "atk-percent": "substats.ATK%",
    "百分比攻击力": "substats.ATK%",
    "hp": "substats.HP%",
    "hp-percent": "substats.HP%",
    "百分比血量": "substats.HP%",
    "def": "substats.DEF%",
    "def-percent": "substats.DEF%",
    "百分比防御": "substats.DEF%",
    "flat-atk": "substats.Flat ATK",
    "固定攻击力": "substats.Flat ATK",
    "flat-hp": "substats.Flat HP",
    "固定血量": "substats.Flat HP",
    "固定生命": "substats.Flat HP",
    "flat-def": "substats.Flat DEF",
    "固定防御力": "substats.Flat DEF",
    "em": "substats.Elemental Mastery",
    "元素精通": "substats.Elemental Mastery",
    "recharge": "substats.Energy Recharge",
    "元素充能效率": "substats.Energy Recharge",
    "crit-rate": "substats.Crit RATE",
    "暴击率": "substats.Crit RATE",
    "crit-damage": "substats.Crit DMG",
    "暴击伤害": "substats.Crit DMG",
}
ARTIFACT_SORT_LABELS = {
    "critValue": "双爆",
    "substats.ATK%": "百分比攻击力",
    "substats.HP%": "百分比血量",
    "substats.DEF%": "百分比防御",
    "substats.Flat ATK": "固定攻击力",
    "substats.Flat HP": "固定血量",
    "substats.Flat DEF": "固定防御力",
    "substats.Elemental Mastery": "元素精通",
    "substats.Energy Recharge": "元素充能效率",
    "substats.Crit RATE": "暴击率",
    "substats.Crit DMG": "暴击伤害",
}


class AkashaProvider:
    def __init__(self, http_client: HttpClient) -> None:
        self.http = http_client

    def user_rank(self, *, uid: str, region: str) -> CommandResult:
        ensure_supported_region(region)
        session_id = self._session_id(region)
        user = self._request_json(
            "GET",
            DATA_API.format(uid),
            region=region,
            category="rank.user",
            params={"sessionID": session_id},
        )
        self._request_json(
            "GET",
            REFRESH_API.format(uid),
            region=region,
            category="rank.refresh",
            params={"sessionID": session_id},
        )
        calculations = self._request_json(
            "GET",
            RANK_API.format(uid),
            region=region,
            category="rank.calculations",
        )
        builds = self._request_json(
            "GET",
            BUILDS_API,
            region=region,
            category="rank.builds",
            params={"uid": uid},
        )
        rank_data, characters = _rank_data(calculations.payload, builds.payload)
        if not characters:
            raise CliError(
                "NO_RESULT",
                "No Akasha rank data is available for this UID.",
                EXIT_NO_RESULT,
                {"uid": uid},
                source=calculations.source,
            )
        return CommandResult(
            data={
                "uid": uid,
                "source": PROVIDER,
                "player": _player(user.payload),
                "rank_data": rank_data,
                "characters": characters,
                "count": len(characters),
            },
            source=calculations.source,
        )

    def character_leaderboard(
        self,
        *,
        character_id: str,
        region: str,
        calculation_id: str | None = None,
        combo: float | None = None,
    ) -> CommandResult:
        ensure_supported_region(region)
        categories = self._leaderboard_categories(character_id, region)
        calculation_id, count = _calculation_info(categories, calculation_id)
        if not calculation_id or count == 0:
            raise CliError(
                "NO_RESULT",
                "No Akasha leaderboard is available for this character.",
                EXIT_NO_RESULT,
                {"character_id": character_id},
            )
        response = self._request_json(
            "GET",
            SORT_API,
            region=region,
            category="rank.character",
            params={
                "sort": "calculation.result",
                "calculationId": calculation_id,
                "order": "-1",
                "size": 20,
                "page": 1,
                "filter": "",
                "uids": "",
                "fromId": "",
                "p": f"lt|{combo}" if combo is not None else "",
            },
        )
        entries = _list_of_dicts(response.payload.get("data"))
        if not entries:
            raise CliError(
                "NO_RESULT",
                "No Akasha leaderboard rows matched this character.",
                EXIT_NO_RESULT,
                {"character_id": character_id, "calculation_id": calculation_id},
                source=response.source,
            )
        return CommandResult(
            data={
                "source": PROVIDER,
                "character_id": character_id,
                "calculation_id": calculation_id,
                "total_count": count,
                "entries": entries,
                "count": len(entries),
            },
            source=response.source,
        )

    def artifact_leaderboard(self, *, sort_by: str, region: str) -> CommandResult:
        ensure_supported_region(region)
        akasha_sort = artifact_sort_key(sort_by)
        response = self._request_json(
            "GET",
            ARTIFACT_API,
            region=region,
            category="rank.artifact",
            params={
                "sort": akasha_sort,
                "p": "",
                "order": "-1",
                "size": 20,
                "page": 1,
                "filter": "",
                "uids": "",
                "fromId": "",
            },
        )
        artifacts = _list_of_dicts(response.payload.get("data"))
        if not artifacts:
            raise CliError(
                "NO_RESULT",
                "No Akasha artifact leaderboard rows matched this sort.",
                EXIT_NO_RESULT,
                {"sort": sort_by, "akasha_sort": akasha_sort},
                source=response.source,
            )
        return CommandResult(
            data={
                "source": PROVIDER,
                "sort": artifact_sort_label(akasha_sort),
                "sort_input": sort_by,
                "akasha_sort": akasha_sort,
                "artifacts": artifacts,
                "count": len(artifacts),
            },
            source=response.source,
        )

    def _session_id(self, region: str) -> str:
        response = self._request_json(
            "GET",
            MAIN_API,
            region=region,
            category="rank.session",
        )
        raw = response.cookies.get("connect.sid") or DEFAULT_SESSION_ID
        return unquote(str(raw)).split(".")[0].split(":")[-1]

    def _leaderboard_categories(self, character_id: str, region: str) -> list[dict[str, object]]:
        response = self._request_json(
            "GET",
            LEADERBOARD_API,
            region=region,
            category="rank.character.categories",
            params={"characterId": character_id},
        )
        categories = _list_of_dicts(response.payload.get("data"))
        if not categories:
            raise CliError(
                "NO_RESULT",
                "No Akasha leaderboard category matched this character.",
                EXIT_NO_RESULT,
                {"character_id": character_id},
                source=response.source,
            )
        return categories

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        region: str,
        category: str,
        params: dict[str, object] | None = None,
    ) -> ProviderResponse:
        return self.http.request_json(
            method,
            url,
            provider=PROVIDER,
            region=region,
            category=category,
            params=params,
            headers=HEADERS,
        )


def artifact_sort_key(sort_by: str | None) -> str:
    key = (sort_by or "双爆").strip()
    if key.startswith(("critValue", "substats.")):
        return key
    mapped = ARTIFACT_SORT_MAP.get(key)
    if mapped:
        return mapped
    for name, value in ARTIFACT_SORT_MAP.items():
        if key and key in name:
            return value
    raise CliError(
        "INVALID_ARGUMENT",
        "Unsupported Akasha artifact sort.",
        EXIT_INVALID_INPUT,
        {"sort": sort_by, "supported": sorted(ARTIFACT_SORT_MAP)},
    )


def artifact_sort_label(akasha_sort: str) -> str:
    return ARTIFACT_SORT_LABELS.get(akasha_sort, akasha_sort)


def _rank_data(
    calculations_payload: dict[str, object], builds_payload: dict[str, object]
) -> tuple[dict[str, object], list[dict[str, object]]]:
    builds = {str(item.get("_id")): item for item in _list_of_dicts(builds_payload.get("data"))}
    rank_data: dict[str, object] = {}
    characters: list[dict[str, object]] = []
    now = utc_now()
    for item in _list_of_dicts(calculations_payload.get("data")):
        character_id = str(item.get("characterId") or "")
        calculations = deepcopy(_dict_value(item.get("calculations")))
        fit = deepcopy(_dict_value(calculations.get("fit")))
        if not character_id or not fit:
            continue
        stats = _dict_value(fit.get("stats")) or _build_stats(builds.get(str(item.get("_id"))))
        fit["stats"] = stats
        calculations["fit"] = fit
        rank_data[character_id] = {"calculations": calculations, "time": now}
        characters.append(_character_summary(character_id, item, fit))
    characters.sort(key=lambda row: _percent(row))
    return rank_data, characters


def _build_stats(build: dict[str, object] | None) -> dict[str, object]:
    if build is None:
        return {"critValue": 0, "maxHP": 0, "maxATK": 0, "maxDEF": 0, "DMG": 0}
    stats: dict[str, object] = {
        "critValue": _number(build.get("critValue")),
        "maxHP": 0,
        "maxATK": 0,
        "maxDEF": 0,
    }
    dmg = 0.0
    for key, value in _dict_value(build.get("stats")).items():
        number = _number(_dict_value(value).get("value") if isinstance(value, dict) else value)
        mapped = STAT_MAP.get(key)
        if mapped:
            stats[mapped] = number
        elif key.endswith("DamageBonus") and number > 0:
            dmg = number
        else:
            stats[key] = number
    stats["DMG"] = dmg
    return stats


def _character_summary(
    character_id: str, item: dict[str, object], fit: dict[str, object]
) -> dict[str, object]:
    ranking = _rank_value(fit.get("ranking"))
    out_of = _number(fit.get("outOf"))
    return {
        "avatar_id": character_id,
        "name": item.get("name"),
        "calculation_id": fit.get("calculationId"),
        "short": fit.get("short"),
        "variant": fit.get("variant"),
        "result": _number(fit.get("result")),
        "rank": ranking,
        "out_of": int(out_of),
        "percent": round((ranking / out_of) * 100, 4) if out_of else None,
        "constellation": item.get("constellation"),
        "weapon": fit.get("weapon"),
        "stats": fit.get("stats"),
        "artifact_sets": item.get("artifactSets"),
        "icon": item.get("icon"),
    }


def _calculation_info(
    categories: list[dict[str, object]], calculation_id: str | None
) -> tuple[str | None, int]:
    if calculation_id:
        for category in categories:
            for weapon in _list_of_dicts(category.get("weapons")):
                if str(weapon.get("calculationId")) == str(calculation_id):
                    return calculation_id, int(_number(category.get("count")))
        return calculation_id, 0
    first = categories[0]
    weapons = _list_of_dicts(first.get("weapons"))
    if not weapons:
        return None, 0
    return str(weapons[0].get("calculationId") or ""), int(_number(first.get("count")))


def _player(payload: dict[str, object]) -> dict[str, object]:
    data = _dict_value(payload.get("data"))
    account = _dict_value(data.get("account"))
    player = _dict_value(account.get("playerInfo"))
    owned_characters = account.get("ownedCharacters")
    if not isinstance(owned_characters, list):
        owned_characters = []
    profile_url = data.get("profilePictureLink") or _player_profile_url(player)
    namecard_url = data.get("nameCardLink") or _player_namecard_url(player)
    return {
        "nickname": player.get("nickname"),
        "level": player.get("level"),
        "region": player.get("region"),
        "profile_picture_url": profile_url,
        "namecard_url": namecard_url,
        "owned_characters": owned_characters,
        "owned_character_count": len(owned_characters),
        "max_friendship_count": player.get("maxFriendshipCount"),
        "abyss_floor": player.get("towerFloorIndex"),
        "abyss_chamber": player.get("towerLevelIndex"),
        "theater": player.get("theater"),
        "stygian_index": player.get("stygianIndex"),
        "stygian_seconds": player.get("stygianSeconds"),
    }


def _player_profile_url(player: dict[str, object]) -> str | None:
    profile = _dict_value(player.get("profilePicture"))
    assets = _dict_value(profile.get("assets"))
    icon = assets.get("oldIcon") or assets.get("icon")
    return _enka_ui_url(icon)


def _player_namecard_url(player: dict[str, object]) -> str | None:
    namecard = _dict_value(player.get("nameCardId"))
    assets = _dict_value(namecard.get("assets"))
    pic_path = assets.get("picPath")
    if isinstance(pic_path, list) and pic_path:
        return _enka_ui_url(pic_path[-1])
    return _enka_ui_url(player.get("nameCard"))


def _enka_ui_url(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if value.startswith("http"):
        return value
    return f"https://enka.network/ui/{value}.png"


def _percent(row: dict[str, object]) -> float:
    value = row.get("percent")
    return float(value) if isinstance(value, int | float) else 100.0


def _rank_value(value: object) -> int:
    if isinstance(value, str) and value.startswith("~"):
        value = value[1:]
    return int(_number(value))


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _dict_value(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
