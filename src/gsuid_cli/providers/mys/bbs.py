from __future__ import annotations

from gsuid_cli.core.http import ProviderResponse, raise_for_retcode
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.providers.mys.auth import _bbs_headers
from gsuid_cli.providers.mys.constants import (
    BBS_BASE_CN,
    BBS_DETAIL_PATH,
    BBS_LIKE_PATH,
    BBS_LIST_PATH,
    BBS_SHARE_PATH,
    BBS_SIGN_PATH,
    BBS_TASKS_LIST_PATH,
    PROVIDER,
)

BBS_GAMES = [
    {"id": "1", "forum_id": "1", "name": "崩坏3"},
    {"id": "2", "forum_id": "26", "name": "原神"},
    {"id": "3", "forum_id": "30", "name": "崩坏2"},
    {"id": "4", "forum_id": "37", "name": "未定事件簿"},
    {"id": "5", "forum_id": "34", "name": "大别野"},
    {"id": "6", "forum_id": "52", "name": "崩坏：星穹铁道"},
    {"id": "8", "forum_id": "57", "name": "绝区零"},
    {"id": "9", "forum_id": "948", "name": "崩坏：因缘精灵"},
    {"id": "10", "forum_id": "950", "name": "星布谷地"},
]

MISSION_LABELS = {
    "bbs_sign": "讨论区签到",
    "read_posts": "浏览帖子",
    "like_posts": "点赞帖子",
    "share_post": "分享帖子",
}
MISSION_IDS = {
    58: "bbs_sign",
    59: "read_posts",
    60: "like_posts",
    61: "share_post",
}
MISSION_DEFAULT_REMAINING = {
    "read_posts": 7,
    "like_posts": 10,
}


class MysBbsMixin:
    def daily_bbs_coin(
        self,
        *,
        uid: str,
        stoken: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
    ) -> CommandResult:
        ensure_supported_region(region)
        initial = self._bbs_task_state(stoken=stoken, region=region)
        task_state = _task_state(initial.payload)
        failures: list[str] = []
        actions: list[dict[str, object]] = []
        posts: list[dict[str, str]] = []

        if not _all_tasks_done(task_state):
            posts = self._bbs_posts(stoken=stoken, region=region, failures=failures)
        if not task_state["read_posts"]["completed"]:
            self._read_posts(
                stoken=stoken,
                region=region,
                posts=posts,
                count=int(task_state["read_posts"]["remaining"]),
                actions=actions,
                failures=failures,
            )
        if not task_state["share_post"]["completed"]:
            self._share_post(
                stoken=stoken,
                region=region,
                posts=posts,
                actions=actions,
                failures=failures,
            )
        if not task_state["like_posts"]["completed"]:
            self._like_posts(
                stoken=stoken,
                region=region,
                posts=posts,
                count=int(task_state["like_posts"]["remaining"]),
                actions=actions,
                failures=failures,
            )
        if not task_state["bbs_sign"]["completed"]:
            self._sign_games(
                stoken=stoken,
                region=region,
                actions=actions,
                failures=failures,
            )

        final = self._bbs_task_state(stoken=stoken, region=region)
        final_state = _task_state(final.payload)
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "available": True,
                "tasks": _task_rows(final_state),
                "actions": actions,
                "points_received": _data_number(final.payload, "already_received_points"),
                "points_available": _data_number(final.payload, "can_get_points"),
                "total_points": _data_number(final.payload, "total_points"),
                "failures": failures,
                "source": "mihoyo-bbs",
            },
            source=final.source,
            warnings=failures,
        )

    def _bbs_task_state(self, *, stoken: str, region: str) -> ProviderResponse:
        response = self.http.request_json(
            "GET",
            f"{BBS_BASE_CN}{BBS_TASKS_LIST_PATH}",
            provider=PROVIDER,
            region=region,
            category="daily.bbs-coin",
            headers=_bbs_headers(stoken),
        )
        raise_for_retcode(
            response.payload,
            provider=PROVIDER,
            region=region,
            category="daily.bbs-coin",
            source=response.source,
            debug=self.http.debug,
        )
        return response

    def _bbs_posts(
        self,
        *,
        stoken: str,
        region: str,
        failures: list[str],
    ) -> list[dict[str, str]]:
        response = self.http.request_json(
            "GET",
            f"{BBS_BASE_CN}{BBS_LIST_PATH}",
            provider=PROVIDER,
            region=region,
            category="daily.bbs-coin",
            params={
                "forum_id": "26",
                "is_good": "false",
                "is_hot": "false",
                "page_size": 20,
                "sort_type": 1,
            },
            headers=_bbs_headers(stoken),
        )
        if not _ok(response.payload):
            failures.append(_failure("获取帖子列表失败", response.payload))
            return []
        data = _data(response.payload)
        raw_posts = data.get("list")
        posts: list[dict[str, str]] = []
        if isinstance(raw_posts, list):
            for item in raw_posts:
                if not isinstance(item, dict):
                    continue
                post = item.get("post")
                if not isinstance(post, dict):
                    continue
                post_id = str(post.get("post_id") or "")
                if post_id:
                    posts.append({"id": post_id, "subject": str(post.get("subject") or "")})
        if not posts:
            failures.append("未能获取可用于浏览、点赞或分享的米游社帖子")
        return posts[:10]

    def _read_posts(
        self,
        *,
        stoken: str,
        region: str,
        posts: list[dict[str, str]],
        count: int,
        actions: list[dict[str, object]],
        failures: list[str],
    ) -> None:
        ok = 0
        for post in posts[: max(count, 0)]:
            response = self.http.request_json(
                "GET",
                f"{BBS_BASE_CN}{BBS_DETAIL_PATH}",
                provider=PROVIDER,
                region=region,
                category="daily.bbs-coin",
                params={"post_id": post["id"]},
                headers=_bbs_headers(stoken),
            )
            if _ok(response.payload):
                ok += 1
            else:
                failures.append(_failure("浏览帖子失败", response.payload, post["id"]))
        actions.append({"task": "read_posts", "label": MISSION_LABELS["read_posts"], "count": ok})

    def _share_post(
        self,
        *,
        stoken: str,
        region: str,
        posts: list[dict[str, str]],
        actions: list[dict[str, object]],
        failures: list[str],
    ) -> None:
        if not posts:
            failures.append("分享帖子失败: 没有可用帖子")
            return
        post = posts[0]
        response = self.http.request_json(
            "GET",
            f"{BBS_BASE_CN}{BBS_SHARE_PATH}",
            provider=PROVIDER,
            region=region,
            category="daily.bbs-coin",
            params={"entity_id": post["id"], "entity_type": 1},
            headers=_bbs_headers(stoken),
        )
        if _ok(response.payload):
            actions.append({"task": "share_post", "label": MISSION_LABELS["share_post"]})
        else:
            failures.append(_failure("分享帖子失败", response.payload, post["id"]))

    def _like_posts(
        self,
        *,
        stoken: str,
        region: str,
        posts: list[dict[str, str]],
        count: int,
        actions: list[dict[str, object]],
        failures: list[str],
    ) -> None:
        ok = 0
        canceled = 0
        for post in posts[: max(count, 0)]:
            body = {"post_id": post["id"], "is_cancel": False}
            response = self.http.request_json(
                "POST",
                f"{BBS_BASE_CN}{BBS_LIKE_PATH}",
                provider=PROVIDER,
                region=region,
                category="daily.bbs-coin",
                headers=_bbs_headers(stoken, body),
                json_body=body,
            )
            if _ok(response.payload):
                ok += 1
            else:
                failures.append(_failure("点赞帖子失败", response.payload, post["id"]))
                continue
            cancel_body = {"post_id": post["id"], "is_cancel": True}
            cancel = self.http.request_json(
                "POST",
                f"{BBS_BASE_CN}{BBS_LIKE_PATH}",
                provider=PROVIDER,
                region=region,
                category="daily.bbs-coin",
                headers=_bbs_headers(stoken, cancel_body),
                json_body=cancel_body,
            )
            if _ok(cancel.payload):
                canceled += 1
        actions.append(
            {
                "task": "like_posts",
                "label": MISSION_LABELS["like_posts"],
                "count": ok,
                "cancel_count": canceled,
            }
        )

    def _sign_games(
        self,
        *,
        stoken: str,
        region: str,
        actions: list[dict[str, object]],
        failures: list[str],
    ) -> None:
        signed: list[str] = []
        for game in BBS_GAMES:
            body = {"gids": int(game["id"])}
            response = self.http.request_json(
                "POST",
                f"{BBS_BASE_CN}{BBS_SIGN_PATH}",
                provider=PROVIDER,
                region=region,
                category="daily.bbs-coin",
                headers=_bbs_headers(stoken, body),
                json_body=body,
            )
            if _ok(response.payload):
                signed.append(game["name"])
            else:
                failures.append(_failure(f"{game['name']}签到失败", response.payload))
        actions.append(
            {
                "task": "bbs_sign",
                "label": MISSION_LABELS["bbs_sign"],
                "games": signed,
                "count": len(signed),
            }
        )


def _task_state(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    data = _data(payload)
    tasks = {
        key: {
            "key": key,
            "label": label,
            "completed": False,
            "happened_times": 0,
            "remaining": MISSION_DEFAULT_REMAINING.get(key, 1),
        }
        for key, label in MISSION_LABELS.items()
    }
    if _number(data.get("can_get_points")) == 0:
        for task in tasks.values():
            task["completed"] = True
            task["remaining"] = 0
        return tasks
    states = data.get("states")
    if not isinstance(states, list):
        return tasks
    for state in states:
        if not isinstance(state, dict):
            continue
        key = MISSION_IDS.get(int(_number(state.get("mission_id"))))
        if key is None:
            continue
        task = tasks[key]
        happened = int(_number(state.get("happened_times")))
        completed = bool(state.get("is_get_award"))
        task["completed"] = completed
        task["happened_times"] = happened
        default_remaining = int(MISSION_DEFAULT_REMAINING.get(key, 1))
        task["remaining"] = 0 if completed else max(default_remaining - happened, 0)
    return tasks


def _task_rows(state: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    return [state[key] for key in ("bbs_sign", "read_posts", "like_posts", "share_post")]


def _all_tasks_done(state: dict[str, dict[str, object]]) -> bool:
    return all(bool(task.get("completed")) for task in state.values())


def _data(payload: dict[str, object]) -> dict[str, object]:
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _data_number(payload: dict[str, object], key: str) -> int:
    return int(_number(_data(payload).get(key)))


def _ok(payload: dict[str, object]) -> bool:
    return payload.get("retcode") in (0, "0") and str(payload.get("message") or "OK") != ""


def _failure(action: str, payload: dict[str, object], target: str | None = None) -> str:
    target_text = f": {target}" if target else ""
    retcode = payload.get("retcode")
    message = payload.get("message") or "UNKNOWN"
    return f"{action}{target_text} (retcode={retcode}, message={message})"


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
