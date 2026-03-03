from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from pathlib import Path

from gsuid_cli import __version__
from gsuid_cli.commands.auth import _credential, _uid_and_region
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.state import state_db
from gsuid_cli.core.time import utc_now
from gsuid_cli.providers import provider_for_region

CAPABILITIES = [
    {
        "command": "gacha.refresh",
        "description": "Refresh local gacha logs from a stored authkey URL.",
        "auth": "gacha_url",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "gacha.summary",
        "description": "Summarize local gacha logs.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "gacha.export",
        "description": "Export local gacha logs as UIGF JSON.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "gacha.import",
        "description": "Import UIGF JSON into local gacha storage.",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
    {
        "command": "gacha.authkey",
        "description": "Show stored gacha authkey URL availability without revealing it.",
        "auth": "gacha_url",
        "regions": ["cn"],
        "render": ["data"],
        "cache": "off",
    },
]

GACHA_TYPES = ("100", "200", "301", "302", "400", "500")
BANNER_TYPES = {
    "all": None,
    "character": {"301", "400"},
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

    authkey = commands.add_parser("authkey", help="Show stored gacha authkey URL status.")
    authkey.add_argument("--uid", dest="command_uid")
    authkey.set_defaults(handler=authkey_command, command_name="gacha.authkey")


def refresh_command(args: argparse.Namespace) -> CommandResult:
    uid, region = _uid_and_region(args)
    args.credential_kind = "gacha_url"
    authkey_url, credential_source, storage_backend = _credential(args, uid)
    provider = provider_for_region(region, _http_client(args))
    totals = {"fetched": 0, "inserted": 0, "duplicates": 0}
    per_type = []

    with state_db(args.output_dir) as conn:
        for gacha_type in GACHA_TYPES:
            end_id = "0"
            page = 1
            fetched_type = inserted_type = duplicate_type = 0
            while page <= _refresh_page_limit(args):
                result = provider.gacha_log_page(
                    uid=uid,
                    authkey_url=authkey_url,
                    region=region,
                    gacha_type=gacha_type,
                    page=page,
                    end_id=end_id,
                )
                items = _provider_items(result.data)
                if not items:
                    break
                stats = _insert_items(conn, uid, items)
                fetched_type += len(items)
                inserted_type += stats["inserted"]
                duplicate_type += stats["duplicates"]
                end_id = str(items[-1]["id"])
                if stats["duplicates"] and not args.force and not args.full:
                    break
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


def summary_command(args: argparse.Namespace) -> dict[str, object]:
    uid, _region = _uid_and_region(args)
    with state_db(args.output_dir) as conn:
        return {"uid": uid, "banner": args.banner, "summary": _summary(conn, uid, args.banner)}


def export_command(args: argparse.Namespace) -> CommandResult:
    uid, _region = _uid_and_region(args)
    with state_db(args.output_dir) as conn:
        items = _items_for_uid(conn, uid)
    payload = _export_payload(uid, items, args.export_format)
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    artifact = _write_export(args, uid, args.export_format, content)
    return CommandResult(
        data={
            "uid": uid,
            "format": args.export_format,
            "count": len(items),
            "exported": True,
        },
        artifacts=[artifact],
    )


def import_command(args: argparse.Namespace) -> dict[str, object]:
    uid, _region = _uid_and_region(args)
    payload = _load_json(Path(args.file))
    items, detected_format = _uigf_items(payload, uid, args.import_format)
    with state_db(args.output_dir) as conn:
        stats = _insert_items(conn, uid, items)
    return {
        "uid": uid,
        "format": detected_format,
        "total": len(items),
        **stats,
    }


def authkey_command(args: argparse.Namespace) -> dict[str, object]:
    uid, _region = _uid_and_region(args)
    args.credential_kind = "gacha_url"
    value, source, storage_backend = _credential(args, uid)
    return {
        "uid": uid,
        "credential_type": "gacha_url",
        "source": source,
        "storage_backend": storage_backend,
        "available": True,
        "redacted": "[REDACTED_URL]",
    }


def _http_client(args: argparse.Namespace) -> HttpClient:
    return HttpClient(
        timeout=args.timeout,
        cache_policy="off",
        output_dir=args.output_dir,
        debug=args.debug,
    )


def _refresh_page_limit(args: argparse.Namespace) -> int:
    return 500 if args.full else 50


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
) -> dict[str, int]:
    inserted = duplicates = 0
    now = utc_now()
    for item in items:
        normalized = _normalize_item(uid, item, now)
        existing = _find_existing(conn, uid, str(normalized["id"]))
        if existing is not None:
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


def _normalize_item(uid: str, item: dict[str, object], imported_at: str) -> dict[str, object]:
    missing = sorted(field for field in REQUIRED_ITEM_FIELDS if not item.get(field))
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
    rows = _item_rows(conn, uid, banner)
    by_rank: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_gacha_type: dict[str, int] = {}
    pity_by_type: dict[str, int] = {}
    last_five_by_type: dict[str, dict[str, object]] = {}
    for row in rows:
        rank = str(row["rank_type"] or "")
        item_type = str(row["item_type"] or "")
        gacha_type = str(row["gacha_type"] or "")
        by_rank[rank] = by_rank.get(rank, 0) + 1
        by_type[item_type] = by_type.get(item_type, 0) + 1
        by_gacha_type[gacha_type] = by_gacha_type.get(gacha_type, 0) + 1
        pity_by_type[gacha_type] = pity_by_type.get(gacha_type, 0) + 1
        if rank == "5":
            last_five_by_type[gacha_type] = _row_item(row)
            pity_by_type[gacha_type] = 0
    return {
        "total": len(rows),
        "by_rank": by_rank,
        "by_item_type": by_type,
        "by_gacha_type": by_gacha_type,
        "pity_by_gacha_type": pity_by_type,
        "last_five_star_by_gacha_type": last_five_by_type,
    }


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
        WHERE uid = ? AND gacha_type IN ({placeholders})
        ORDER BY time ASC, CAST(id AS INTEGER) ASC
        """,
        (uid, *sorted(types)),
    ).fetchall()


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
