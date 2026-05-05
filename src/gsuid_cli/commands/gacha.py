from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from pathlib import Path

from gsuid_cli import __version__
from gsuid_cli.commands.auth import _credential, _uid_and_region
from gsuid_cli.commands.render_assets import fetch_render_images
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.render import render_image_enabled, render_result_data, render_text_enabled
from gsuid_cli.core.secrets import SecretStore
from gsuid_cli.core.state import state_db
from gsuid_cli.core.time import utc_now
from gsuid_cli.providers import provider_for_region
from gsuid_cli.renderers.gacha import (
    gacha_summary_item_urls,
    gacha_summary_missing_icon_count,
    render_gacha_authkey_text,
    render_gacha_export_text,
    render_gacha_import_text,
    render_gacha_refresh_text,
    render_gacha_summary_card,
    render_gacha_summary_text,
)

CAPABILITIES = [
    {
        "command": "gacha.refresh",
        "description": "Refresh local gacha logs from a stored authkey URL.",
        "auth": "gacha_url",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
        "cache": "off",
    },
    {
        "command": "gacha.summary",
        "description": "Summarize local gacha logs.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
        "cache": "off",
    },
    {
        "command": "gacha.export",
        "description": "Export local gacha logs as UIGF JSON.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
        "cache": "off",
    },
    {
        "command": "gacha.import",
        "description": "Import UIGF JSON into local gacha storage.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
        "cache": "off",
    },
    {
        "command": "gacha.authkey",
        "description": "Show stored gacha authkey URL availability without revealing it.",
        "auth": "gacha_url",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
        "cache": "off",
    },
    {
        "command": "gacha.authkey.refresh",
        "description": "Generate and store a gacha authkey URL from cookie and stoken.",
        "auth": "cookie+stoken",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
        "cache": "off",
    },
]

GACHA_TYPES = ("100", "200", "301", "302", "400", "500")
GACHA_REFRESH_REQUEST_DELAY_SECONDS = 0.9
GACHA_REFRESH_CONTINUE_DELAY_SECONDS = 0.5
BANNER_TYPES = {
    "all": None,
    "character": {"301"},
    "weapon": {"302"},
    "standard": {"200"},
    "chronicled": {"500"},
    "novice": {"100"},
}
UIGF_GACHA_TYPE_BY_GACHA_TYPE = {
    "100": "100",
    "200": "200",
    "301": "301",
    "302": "302",
    "400": "301",
    "500": "500",
}
REQUIRED_ITEM_FIELDS = {
    "gacha_type",
    "item_id",
    "count",
    "time",
    "name",
    "item_type",
    "rank_type",
    "id",
}


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    gacha = groups.add_parser("gacha", help="Manage local gacha logs.")
    commands = gacha.add_subparsers(dest="gacha_command", required=True, metavar="<command>")

    refresh = commands.add_parser("refresh", help="Refresh local gacha logs.")
    refresh.add_argument("--uid", dest="command_uid")
    refresh.add_argument("--force", action="store_true")
    refresh.add_argument("--full", action="store_true")
    refresh.set_defaults(handler=refresh_command, command_name="gacha.refresh")

    summary = commands.add_parser("summary", help="Summarize local gacha logs.")
    summary.add_argument("--uid", dest="command_uid")
    summary.add_argument("--banner", choices=tuple(BANNER_TYPES), default="all")
    summary.set_defaults(handler=summary_command, command_name="gacha.summary")

    export = commands.add_parser("export", help="Export local gacha logs.")
    export.add_argument("--uid", dest="command_uid")
    export.add_argument(
        "--format",
        choices=("uigf-v4", "uigf-v2"),
        default="uigf-v4",
        dest="export_format",
    )
    export.add_argument("--output")
    export.set_defaults(handler=export_command, command_name="gacha.export")

    import_parser = commands.add_parser("import", help="Import UIGF gacha logs.")
    import_parser.add_argument("--uid", dest="command_uid")
    import_parser.add_argument("--file", required=True)
    import_parser.add_argument(
        "--format",
        choices=("auto", "uigf-v4", "uigf-v2"),
        default="auto",
        dest="import_format",
    )
    import_parser.set_defaults(handler=import_command, command_name="gacha.import")

    authkey = commands.add_parser(
        "authkey",
        help="Show or refresh stored gacha authkey URL status.",
        description="Show stored gacha authkey URL status. With no action, status is returned.",
    )
    authkey.add_argument("--uid", dest="command_uid")
    authkey.set_defaults(handler=authkey_command, command_name="gacha.authkey")
    authkey_actions = authkey.add_subparsers(dest="authkey_action", metavar="<action>")
    authkey_status = authkey_actions.add_parser(
        "status",
        help="Show stored gacha authkey URL status.",
    )
    authkey_status.add_argument("--uid", dest="command_uid")
    authkey_status.set_defaults(handler=authkey_command, command_name="gacha.authkey")
    authkey_refresh = authkey_actions.add_parser(
        "refresh",
        help="Generate and store a gacha authkey URL.",
    )
    authkey_refresh.add_argument("--uid", dest="command_uid")
    authkey_refresh.set_defaults(
        handler=authkey_refresh_command,
        command_name="gacha.authkey.refresh",
    )


def refresh_command(args: argparse.Namespace) -> CommandResult:
    uid, region = _uid_and_region(args)
    args.credential_kind = "gacha_url"
    authkey_url, credential_source, storage_backend = _credential(args, uid)
    try:
        result = _refresh_with_authkey(
            args,
            uid=uid,
            region=region,
            authkey_url=authkey_url,
            credential_source=credential_source,
            storage_backend=storage_backend,
        )
        return _refresh_render_result(args, result) if render_text_enabled(args) else result
    except CliError as exc:
        if not _is_expired_gacha_authkey_error(exc):
            raise
        refreshed_url, refreshed = _refresh_gacha_authkey_url(args, uid, region)
        refreshed_storage_backend = refreshed.data.get("storage_backend")
        result = _refresh_with_authkey(
            args,
            uid=uid,
            region=region,
            authkey_url=refreshed_url,
            credential_source="keyring",
            storage_backend=(
                refreshed_storage_backend if isinstance(refreshed_storage_backend, str) else None
            ),
        )
        recovered = CommandResult(
            data=result.data,
            source=result.source,
            warnings=[
                "祈愿记录 authkey 已过期，已自动刷新",
                *refreshed.warnings,
                *result.warnings,
            ],
            artifacts=result.artifacts,
            pagination=result.pagination,
        )
        return _refresh_render_result(args, recovered) if render_text_enabled(args) else recovered


def _is_expired_gacha_authkey_error(error: CliError) -> bool:
    if error.code == "AUTH_EXPIRED":
        return True
    if error.code != "UPSTREAM_REJECTED":
        return False
    details = error.details
    return (
        str(details.get("category") or "") == "gacha.refresh"
        and str(details.get("retcode") or "") == "-101"
        and str(details.get("message") or "").strip().lower() == "authkey timeout"
    )


def _refresh_with_authkey(
    args: argparse.Namespace,
    *,
    uid: str,
    region: str,
    authkey_url: str,
    credential_source: str,
    storage_backend: str | None,
) -> CommandResult:
    provider = provider_for_region(region, _http_client(args))
    totals = {"fetched": 0, "inserted": 0, "duplicates": 0}
    per_type = []

    with state_db(args.output_dir) as conn:
        for gacha_type in GACHA_TYPES:
            end_id = "0"
            page = 1
            page_limit = _refresh_page_limit(args)
            fetched_type = inserted_type = duplicate_type = 0
            while page <= page_limit:
                result = provider.gacha_log_page(
                    uid=uid,
                    authkey_url=authkey_url,
                    region=region,
                    gacha_type=gacha_type,
                    page=page,
                    end_id=end_id,
                )
                time.sleep(GACHA_REFRESH_REQUEST_DELAY_SECONDS)
                items = _provider_items(result.data)
                if not items:
                    break
                oldest_existed = _oldest_item_exists(conn, uid, items)
                stats = _insert_items(conn, uid, items, require_item_id=False)
                fetched_type += len(items)
                inserted_type += stats["inserted"]
                duplicate_type += stats["duplicates"]
                end_id = str(items[-1]["id"])
                if _should_stop_incremental_refresh(args, oldest_existed):
                    break
                if page < page_limit:
                    time.sleep(GACHA_REFRESH_CONTINUE_DELAY_SECONDS)
                page += 1

            totals["fetched"] += fetched_type
            totals["inserted"] += inserted_type
            totals["duplicates"] += duplicate_type
            _update_sync(conn, uid, gacha_type)
            per_type.append(
                {
                    "gacha_type": gacha_type,
                    "fetched": fetched_type,
                    "inserted": inserted_type,
                    "duplicates": duplicate_type,
                }
            )

    return CommandResult(
        data={
            "uid": uid,
            "credential_source": credential_source,
            "storage_backend": storage_backend,
            "redacted": "[REDACTED_URL]",
            "types": per_type,
            **totals,
        },
    )


def summary_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    uid, region = _uid_and_region(args)
    with state_db(args.output_dir) as conn:
        rows = _item_rows(conn, uid, args.banner)
        summary = _summary_from_rows(rows)
    data = {"uid": uid, "banner": args.banner, "summary": summary}
    if not (render_image_enabled(args) or render_text_enabled(args)):
        return data
    return _summary_render_result(args, data, [_row_item(row) for row in rows], region=region)


def export_command(args: argparse.Namespace) -> CommandResult:
    uid, _region = _uid_and_region(args)
    with state_db(args.output_dir) as conn:
        items = _items_for_uid(conn, uid)
    payload = _export_payload(uid, items, args.export_format)
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    artifact = _write_export(args, uid, args.export_format, content)
    result = CommandResult(
        data={
            "uid": uid,
            "format": args.export_format,
            "count": len(items),
            "exported": True,
        },
        artifacts=[artifact],
    )
    if not render_text_enabled(args):
        return result
    return _export_render_result(args, result, artifact)


def import_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    uid, _region = _uid_and_region(args)
    payload = _load_json(Path(args.file))
    items, detected_format = _uigf_items(payload, uid, args.import_format)
    with state_db(args.output_dir) as conn:
        stats = _insert_items(conn, uid, items)
    data = {
        "uid": uid,
        "format": detected_format,
        "total": len(items),
        **stats,
    }
    if not render_text_enabled(args):
        return data
    result = CommandResult(data=data)
    return _text_render_result(
        args,
        result=result,
        render_name="gacha/import-text",
        filename=f"gacha-import_{uid}.txt",
        content=render_gacha_import_text(data),
        description="Human-readable gacha import status",
        render_data={"uid": uid},
    )


def authkey_command(args: argparse.Namespace) -> CommandResult | dict[str, object]:
    uid, _region = _uid_and_region(args)
    args.credential_kind = "gacha_url"
    _value, source, storage_backend = _credential(args, uid)
    data = {
        "uid": uid,
        "credential_type": "gacha_url",
        "source": source,
        "storage_backend": storage_backend,
        "available": True,
        "redacted": "[REDACTED_URL]",
    }
    if not render_text_enabled(args):
        return data
    result = CommandResult(data=data)
    return _text_render_result(
        args,
        result=result,
        render_name="gacha/authkey-text",
        filename=f"gacha-authkey_{uid}.txt",
        content=render_gacha_authkey_text(data),
        description="Human-readable gacha authkey status",
        render_data={"uid": uid},
    )


def authkey_refresh_command(args: argparse.Namespace) -> CommandResult:
    uid, region = _uid_and_region(args)
    _gacha_url, result = _refresh_gacha_authkey_url(args, uid, region)
    if not render_text_enabled(args):
        return result
    return _text_render_result(
        args,
        result=result,
        render_name="gacha/authkey-refresh-text",
        filename=f"gacha-authkey-refresh_{uid}.txt",
        content=render_gacha_authkey_text(result.data, refreshed=True),
        description="Human-readable gacha authkey refresh status",
        render_data={"uid": uid},
    )


def _refresh_gacha_authkey_url(
    args: argparse.Namespace,
    uid: str,
    region: str,
) -> tuple[str, CommandResult]:
    args.credential_kind = "cookie"
    cookie, cookie_source, cookie_storage_backend = _credential(args, uid)
    args.credential_kind = "stoken"
    stoken, stoken_source, stoken_storage_backend = _credential(args, uid)

    result = provider_for_region(region, _http_client(args)).generate_gacha_authkey_url(
        uid=uid,
        cookie=cookie,
        stoken=stoken,
        region=region,
    )
    gacha_url = _generated_gacha_url(result)
    store = SecretStore()
    store.set_secret("gacha_url", uid, gacha_url)
    command_result = CommandResult(
        data={
            **result.data,
            "uid": uid,
            "credential_type": "gacha_url",
            "credential_sources": {
                "cookie": cookie_source,
                "stoken": stoken_source,
            },
            "credential_storage_backends": {
                "cookie": cookie_storage_backend,
                "stoken": stoken_storage_backend,
            },
            "storage_backend": store.backend_name(),
            "stored": True,
            "available": True,
            "redacted": "[REDACTED_URL]",
        },
        source=result.source,
        warnings=result.warnings,
    )
    return gacha_url, command_result


def _http_client(args: argparse.Namespace) -> HttpClient:
    return HttpClient(
        timeout=args.timeout,
        cache_policy="off",
        output_dir=args.output_dir,
        debug=args.debug,
    )


def _generated_gacha_url(result: CommandResult) -> str:
    value = result.data.pop("gacha_url", None)
    if not isinstance(value, str) or not value:
        raise CliError(
            "UPSTREAM_INVALID_RESPONSE",
            "Provider did not return a gacha authkey URL.",
            EXIT_UPSTREAM,
            {"credential_type": "gacha_url"},
            source=result.source,
        )
    return value


def _refresh_page_limit(args: argparse.Namespace) -> int:
    return 500 if args.full else 50


def _oldest_item_exists(
    conn: sqlite3.Connection,
    uid: str,
    items: list[dict[str, object]],
) -> bool:
    item_id = str(items[-1].get("id") or "")
    return bool(item_id) and _find_existing(conn, uid, item_id) is not None


def _should_stop_incremental_refresh(args: argparse.Namespace, oldest_existed: bool) -> bool:
    return oldest_existed and not args.force and not args.full


def _provider_items(data: dict[str, object]) -> list[dict[str, object]]:
    items = data.get("list")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _load_json(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CliError(
            "INVALID_ARGUMENT",
            "gacha import file is not valid JSON",
            EXIT_INVALID_INPUT,
            {"path": str(path)},
        ) from exc
    if not isinstance(data, dict):
        raise CliError(
            "INVALID_ARGUMENT",
            "gacha import file must contain a JSON object",
            EXIT_INVALID_INPUT,
            {"path": str(path)},
        )
    return data


def _uigf_items(
    payload: dict[str, object],
    uid: str,
    requested_format: str,
) -> tuple[list[dict[str, object]], str]:
    if requested_format in {"auto", "uigf-v4"} and _looks_like_v4(payload):
        return _uigf_v4_items(payload, uid), "uigf-v4"
    if requested_format in {"auto", "uigf-v2"} and _looks_like_v2(payload):
        return _uigf_v2_items(payload, uid), "uigf-v2"
    raise CliError(
        "INVALID_ARGUMENT",
        "unsupported or invalid UIGF gacha file",
        EXIT_INVALID_INPUT,
        {"format": requested_format},
    )


def _looks_like_v4(payload: dict[str, object]) -> bool:
    info = payload.get("info")
    version = info.get("version") if isinstance(info, dict) else None
    return isinstance(payload.get("hk4e"), list) or str(version).lower().startswith("v4")


def _looks_like_v2(payload: dict[str, object]) -> bool:
    return isinstance(payload.get("list"), list)


def _uigf_v4_items(payload: dict[str, object], uid: str) -> list[dict[str, object]]:
    accounts = payload.get("hk4e")
    if not isinstance(accounts, list):
        return []
    items: list[dict[str, object]] = []
    for account in accounts:
        if not isinstance(account, dict) or str(account.get("uid") or "") != uid:
            continue
        account_items = account.get("list")
        if isinstance(account_items, list):
            items.extend(item for item in account_items if isinstance(item, dict))
    return items


def _uigf_v2_items(payload: dict[str, object], uid: str) -> list[dict[str, object]]:
    info = payload.get("info")
    file_uid = info.get("uid") if isinstance(info, dict) else None
    if file_uid and str(file_uid) != uid:
        return []
    items = payload.get("list")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _insert_items(
    conn: sqlite3.Connection,
    uid: str,
    items: list[dict[str, object]],
    *,
    require_item_id: bool = True,
) -> dict[str, int]:
    inserted = duplicates = 0
    now = utc_now()
    for item in items:
        normalized = _normalize_item(uid, item, now, require_item_id=require_item_id)
        existing = _find_existing(conn, uid, str(normalized["id"]))
        if existing is not None:
            if not require_item_id and _same_draw_with_incomplete_item_id(existing, normalized):
                duplicates += 1
                continue
            if _can_backfill_item_id(existing, normalized):
                conn.execute(
                    """
                    UPDATE gacha_items
                    SET item_id = ?, imported_at = ?
                    WHERE uid = ? AND id = ?
                    """,
                    (normalized["item_id"], now, uid, normalized["id"]),
                )
                duplicates += 1
                continue
            if _row_conflicts(existing, normalized):
                raise CliError(
                    "INVALID_ARGUMENT",
                    "gacha import contains a conflicting duplicate item id",
                    EXIT_INVALID_INPUT,
                    {"uid": uid, "id": normalized["id"]},
                )
            duplicates += 1
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO gacha_items(
                uid, id, gacha_type, uigf_gacha_type, item_id, count, time,
                name, lang, item_type, rank_type, imported_at
            )
            VALUES(
                :uid, :id, :gacha_type, :uigf_gacha_type, :item_id, :count, :time,
                :name, :lang, :item_type, :rank_type, :imported_at
            )
            """,
            normalized,
        )
        inserted += 1
    return {"inserted": inserted, "duplicates": duplicates}


def _normalize_item(
    uid: str,
    item: dict[str, object],
    imported_at: str,
    *,
    require_item_id: bool,
) -> dict[str, object]:
    required = REQUIRED_ITEM_FIELDS - {"item_id"}
    missing = sorted(field for field in required if not item.get(field))
    if require_item_id and not item.get("item_id"):
        missing.append("item_id")
    missing = sorted(missing)
    if missing:
        raise CliError(
            "INVALID_ARGUMENT",
            "gacha item is missing required fields",
            EXIT_INVALID_INPUT,
            {"uid": uid, "missing": missing},
        )
    item_id = str(item.get("id") or "")
    gacha_type = str(item.get("gacha_type") or "")
    return {
        "uid": uid,
        "id": item_id,
        "gacha_type": gacha_type,
        "uigf_gacha_type": _uigf_gacha_type(item, gacha_type),
        "item_id": str(item.get("item_id") or ""),
        "count": _int_value(item.get("count"), default=1),
        "time": str(item.get("time") or ""),
        "name": str(item.get("name") or ""),
        "lang": str(item.get("lang") or "zh-cn"),
        "item_type": str(item.get("item_type") or ""),
        "rank_type": str(item.get("rank_type") or ""),
        "imported_at": imported_at,
    }


def _uigf_gacha_type(item: dict[str, object], gacha_type: str) -> str:
    if gacha_type in UIGF_GACHA_TYPE_BY_GACHA_TYPE:
        return UIGF_GACHA_TYPE_BY_GACHA_TYPE[gacha_type]
    return str(item.get("uigf_gacha_type") or gacha_type)


def _find_existing(conn: sqlite3.Connection, uid: str, item_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM gacha_items WHERE uid = ? AND id = ?",
        (uid, item_id),
    ).fetchone()


def _row_conflicts(row: sqlite3.Row, item: dict[str, object]) -> bool:
    for key in (
        "gacha_type",
        "uigf_gacha_type",
        "item_id",
        "time",
        "name",
        "item_type",
        "rank_type",
    ):
        if str(row[key] or "") != str(item[key] or ""):
            return True
    return int(row["count"]) != int(item["count"])


def _can_backfill_item_id(row: sqlite3.Row, item: dict[str, object]) -> bool:
    if row["item_id"] or not item["item_id"]:
        return False
    for key in (
        "gacha_type",
        "uigf_gacha_type",
        "time",
        "name",
        "item_type",
        "rank_type",
    ):
        if str(row[key] or "") != str(item[key] or ""):
            return False
    return int(row["count"]) == int(item["count"])


def _same_draw_with_incomplete_item_id(row: sqlite3.Row, item: dict[str, object]) -> bool:
    if row["item_id"] == item["item_id"]:
        return False
    if row["item_id"] and item["item_id"]:
        return False
    for key in (
        "gacha_type",
        "uigf_gacha_type",
        "time",
        "name",
        "item_type",
        "rank_type",
    ):
        if str(row[key] or "") != str(item[key] or ""):
            return False
    return int(row["count"]) == int(item["count"])


def _int_value(value: object, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _update_sync(conn: sqlite3.Connection, uid: str, gacha_type: str) -> None:
    row = conn.execute(
        """
        SELECT id FROM gacha_items
        WHERE uid = ? AND gacha_type = ?
        ORDER BY time DESC, CAST(id AS INTEGER) DESC
        LIMIT 1
        """,
        (uid, gacha_type),
    ).fetchone()
    conn.execute(
        """
        INSERT INTO gacha_sync(uid, gacha_type, last_id, updated_at)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(uid, gacha_type) DO UPDATE SET
            last_id = excluded.last_id,
            updated_at = excluded.updated_at
        """,
        (uid, gacha_type, row["id"] if row else None, utc_now()),
    )


def _summary(conn: sqlite3.Connection, uid: str, banner: str) -> dict[str, object]:
    return _summary_from_rows(_item_rows(conn, uid, banner))


def _summary_from_rows(rows: list[sqlite3.Row]) -> dict[str, object]:
    by_rank: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_gacha_type: dict[str, int] = {}
    pity_by_type: dict[str, int] = {}
    last_five_by_type: dict[str, dict[str, object]] = {}
    five_star_intervals_by_type: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        rank = str(row["rank_type"] or "")
        item_type = str(row["item_type"] or "")
        gacha_type = _row_summary_gacha_type(row)
        by_rank[rank] = by_rank.get(rank, 0) + 1
        by_type[item_type] = by_type.get(item_type, 0) + 1
        by_gacha_type[gacha_type] = by_gacha_type.get(gacha_type, 0) + 1
        pity_by_type[gacha_type] = pity_by_type.get(gacha_type, 0) + 1
        if rank == "5":
            item = _row_item(row)
            interval = pity_by_type[gacha_type]
            last_five_by_type[gacha_type] = item
            five_star_intervals_by_type.setdefault(gacha_type, []).append(
                {
                    "records_since_previous_five_star": interval,
                    "record_number_in_gacha_type": by_gacha_type[gacha_type],
                    "item": item,
                }
            )
            pity_by_type[gacha_type] = 0
    return {
        "total": len(rows),
        "by_rank": by_rank,
        "by_item_type": by_type,
        "by_gacha_type": by_gacha_type,
        "pity_by_gacha_type": pity_by_type,
        "last_five_star_by_gacha_type": last_five_by_type,
        "five_star_intervals_by_gacha_type": five_star_intervals_by_type,
    }


def _summary_render_result(
    args: argparse.Namespace,
    data: dict[str, object],
    items: list[dict[str, object]],
    *,
    region: str,
) -> CommandResult:
    uid = str(data["uid"])
    banner = str(data["banner"])
    artifacts: list[dict[str, object]] = []
    warnings: list[str] = []
    render_data: dict[str, object] = {"uid": uid, "banner": banner}
    if render_image_enabled(args):
        title_summary, title_images, title_avatar_url, title_warnings = _gacha_title_context(
            args,
            uid=uid,
            region=region,
        )
        asset_images, _asset_warnings = fetch_render_images(
            args,
            gacha_summary_item_urls(items),
            provider="gacha-assets",
            region="cn",
            category="gacha.summary.asset",
            unavailable_warning="{count} optional gacha item icon candidates unavailable",
            max_workers=8,
        )
        missing = gacha_summary_missing_icon_count(items, asset_images)
        warnings.extend([f"{missing} 个祈愿物品图标不可用，已使用占位图"] if missing else [])
        warnings.extend(title_warnings)
        png = render_gacha_summary_card(
            uid=uid,
            items=items,
            asset_images={**asset_images, **title_images},
            summary=title_summary,
            title_avatar_url=title_avatar_url,
        )
        image_artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
            name="gacha/summary",
            filename=f"gacha-summary_{uid}_{banner}.png",
            media_type="image/png",
            content=png,
            description="GenshinUID-style gacha summary card",
            kind="image",
        )
        artifacts.append(image_artifact)
        render_data.update(
            {
                "render": "gacha/summary",
                "artifact_sha256": image_artifact["sha256"],
            }
        )
    if render_text_enabled(args):
        text_artifact = ArtifactManager(args.request_id, args.output_dir).write_text(
            name="gacha/summary-text",
            filename=f"gacha-summary_{uid}_{banner}.txt",
            content=render_gacha_summary_text(
                uid=uid,
                banner=banner,
                items=items,
                summary=_summary_mapping(data),
            ),
            description="Human-readable gacha summary text",
            kind="text",
        )
        artifacts.append(text_artifact)
        _record_text_artifact(render_data, text_artifact, image_enabled=render_image_enabled(args))
    return CommandResult(
        data=render_result_data(args, data, render_data),
        artifacts=artifacts,
        warnings=warnings,
    )


def _gacha_title_context(
    args: argparse.Namespace,
    *,
    uid: str,
    region: str,
) -> tuple[dict[str, object], dict[str, bytes], str | None, list[str]]:
    previous_kind = getattr(args, "credential_kind", None)
    args.credential_kind = "cookie"
    try:
        cookie, credential_source, storage_backend = _credential(args, uid)
    except CliError as exc:
        if previous_kind is not None:
            args.credential_kind = previous_kind
        if exc.code == "AUTH_REQUIRED":
            return {}, {}, None, []
        return {}, {}, None, ["玩家资料凭据读取失败，已使用默认头像"]
    finally:
        if previous_kind is None and hasattr(args, "credential_kind"):
            delattr(args, "credential_kind")
    if previous_kind is not None:
        args.credential_kind = previous_kind
    try:
        from gsuid_cli.commands.player import (
            _player_profile_image_assets,
            _player_profile_title_avatar_url,
            _player_title_mys_icon_urls,
            _player_title_summary_context,
        )
        from gsuid_cli.renderers.player.summary import player_summary_genshinuid_resource_urls

        summary, summary_warnings = _player_title_summary_context(
            provider=provider_for_region(region, _http_client(args)),
            uid=uid,
            region=region,
            cookie=cookie,
            credential_source=credential_source,
            storage_backend=storage_backend,
            category_prefix="gacha.summary",
        )
        title_avatar_url, profile_warnings = _player_profile_title_avatar_url(args, uid, region)
        resource_urls = player_summary_genshinuid_resource_urls(summary)
        if title_avatar_url and not title_avatar_url.startswith(_enka_ui_base()):
            resource_urls.append(title_avatar_url)
        resource_images, resource_warnings = fetch_render_images(
            args,
            resource_urls,
            provider="genshinuid",
            region=region,
            category="gacha.summary.title.resource",
            unavailable_warning="玩家标题资源不可用，已使用默认头像",
            max_workers=8,
        )
        icon_images, icon_warnings = fetch_render_images(
            args,
            _player_title_mys_icon_urls(summary),
            provider="mys",
            region=region,
            category="gacha.summary.title.icon",
            unavailable_warning="玩家标题图标不可用，已使用默认头像",
            max_workers=8,
        )
        profile_images, profile_image_warnings = _player_profile_image_assets(
            args,
            title_avatar_url,
            region,
        )
    except CliError:
        return {}, {}, None, ["玩家资料不可用，已使用默认头像"]
    return (
        dict(summary),
        {**resource_images, **icon_images, **profile_images},
        title_avatar_url,
        _gacha_title_warnings(
            [
                *summary_warnings,
                *profile_warnings,
                *resource_warnings,
                *icon_warnings,
                *profile_image_warnings,
            ]
        ),
    )


def _enka_ui_base() -> str:
    from gsuid_cli.renderers.player.summary import ENKA_UI_BASE

    return f"{ENKA_UI_BASE}/"


def _gacha_title_warnings(warnings: list[str]) -> list[str]:
    translated = []
    for warning in warnings:
        if "profile picture map" in warning:
            translated.append("玩家头像配置不可用，已使用默认头像")
        elif "profile picture" in warning:
            translated.append("玩家头像不可用，已使用默认头像")
        elif "profile unavailable" in warning:
            translated.append("玩家资料不可用，已使用默认头像")
        elif "title resources" in warning:
            translated.append("玩家标题资源不可用，已使用默认头像")
        elif "title icons" in warning:
            translated.append("玩家标题图标不可用，已使用默认头像")
        else:
            translated.append(warning)
    return translated


def _refresh_render_result(args: argparse.Namespace, result: CommandResult) -> CommandResult:
    uid = str(result.data.get("uid") or "unknown")
    return _text_render_result(
        args,
        result=result,
        render_name="gacha/refresh-text",
        filename=f"gacha-refresh_{uid}.txt",
        content=render_gacha_refresh_text(result.data),
        description="Human-readable gacha refresh status",
        render_data={"uid": uid},
    )


def _export_render_result(
    args: argparse.Namespace,
    result: CommandResult,
    export_artifact: dict[str, object],
) -> CommandResult:
    uid = str(result.data.get("uid") or "unknown")
    return _text_render_result(
        args,
        result=result,
        render_name="gacha/export-text",
        filename=f"gacha-export_{uid}.txt",
        content=render_gacha_export_text(
            result.data,
            artifact_path=export_artifact.get("path"),
        ),
        description="Human-readable gacha export status",
        render_data={"uid": uid},
    )


def _text_render_result(
    args: argparse.Namespace,
    *,
    result: CommandResult,
    render_name: str,
    filename: str,
    content: str,
    description: str,
    render_data: dict[str, object],
) -> CommandResult:
    text_artifact = ArtifactManager(args.request_id, args.output_dir).write_text(
        name=render_name,
        filename=filename,
        content=content,
        description=description,
        kind="text",
    )
    data = render_result_data(
        args,
        result.data,
        {
            **render_data,
            "render": render_name,
            "artifact_sha256": text_artifact["sha256"],
        },
    )
    return CommandResult(
        data=data,
        artifacts=[*result.artifacts, text_artifact],
        source=result.source,
        warnings=result.warnings,
        pagination=result.pagination,
    )


def _record_text_artifact(
    render_data: dict[str, object],
    text_artifact: dict[str, object],
    *,
    image_enabled: bool,
) -> None:
    if image_enabled:
        render_data["text_artifact_sha256"] = text_artifact["sha256"]
        return
    render_data.update(
        {
            "render": text_artifact["name"],
            "artifact_sha256": text_artifact["sha256"],
        }
    )


def _summary_mapping(data: dict[str, object]) -> dict[str, object]:
    summary = data.get("summary")
    return summary if isinstance(summary, dict) else {}


def _item_rows(conn: sqlite3.Connection, uid: str, banner: str) -> list[sqlite3.Row]:
    types = BANNER_TYPES[banner]
    if types is None:
        return conn.execute(
            "SELECT * FROM gacha_items WHERE uid = ? ORDER BY time ASC, CAST(id AS INTEGER) ASC",
            (uid,),
        ).fetchall()
    placeholders = ",".join("?" for _ in types)
    return conn.execute(
        f"""
        SELECT * FROM gacha_items
        WHERE uid = ? AND {_summary_gacha_type_sql()} IN ({placeholders})
        ORDER BY time ASC, CAST(id AS INTEGER) ASC
        """,
        (uid, *sorted(types)),
    ).fetchall()


def _summary_gacha_type_sql() -> str:
    return """
        COALESCE(
            NULLIF(uigf_gacha_type, ''),
            CASE WHEN gacha_type = '400' THEN '301' ELSE gacha_type END
        )
    """


def _row_summary_gacha_type(row: sqlite3.Row) -> str:
    uigf_gacha_type = str(row["uigf_gacha_type"] or "")
    if uigf_gacha_type:
        return uigf_gacha_type
    gacha_type = str(row["gacha_type"] or "")
    return UIGF_GACHA_TYPE_BY_GACHA_TYPE.get(gacha_type, gacha_type)


def _items_for_uid(conn: sqlite3.Connection, uid: str) -> list[dict[str, object]]:
    rows = conn.execute(
        "SELECT * FROM gacha_items WHERE uid = ? ORDER BY time ASC, CAST(id AS INTEGER) ASC",
        (uid,),
    ).fetchall()
    return [_row_item(row) for row in rows]


def _row_item(row: sqlite3.Row) -> dict[str, object]:
    return {
        "uid": row["uid"],
        "gacha_type": row["gacha_type"],
        "uigf_gacha_type": row["uigf_gacha_type"],
        "item_id": row["item_id"],
        "count": str(row["count"]),
        "time": row["time"],
        "name": row["name"],
        "lang": row["lang"],
        "item_type": row["item_type"],
        "rank_type": row["rank_type"],
        "id": row["id"],
    }


def _export_payload(
    uid: str,
    items: list[dict[str, object]],
    export_format: str,
) -> dict[str, object]:
    if export_format == "uigf-v2":
        return {
            "info": {
                "uid": uid,
                "lang": "zh-cn",
                "export_app": "gsuid-cli",
                "export_time": utc_now(),
                "uigf_version": "v2.4",
            },
            "list": items,
        }
    return {
        "info": {
            "version": "v4.0",
            "export_app": "gsuid-cli",
            "export_app_version": __version__,
            "export_timestamp": int(time.time()),
            "region_time_zone": 8,
        },
        "hk4e": [
            {
                "uid": uid,
                "timezone": 8,
                "list": items,
            }
        ],
    }


def _write_export(
    args: argparse.Namespace,
    uid: str,
    export_format: str,
    content: bytes,
) -> dict[str, object]:
    filename = f"gacha_{uid}_{export_format}.json"
    if args.output:
        path = Path(args.output).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return _artifact_for_path(path, content)
    return ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name="gacha_export",
        filename=filename,
        media_type="application/json",
        content=content,
        description=f"Gacha log export ({export_format})",
        kind="json",
    )


def _artifact_for_path(path: Path, content: bytes) -> dict[str, object]:
    return {
        "kind": "json",
        "name": "gacha_export",
        "path": str(path),
        "media_type": "application/json",
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "description": "Gacha log export",
    }
