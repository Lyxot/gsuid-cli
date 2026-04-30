from __future__ import annotations

import argparse
import hashlib
import re
from collections.abc import Mapping

from gsuid_cli.commands.auth import _credential, _uid_and_region
from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.errors import EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.providers import provider_for_region


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    if safe:
        return safe[:80]
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def _mapping_data(result: CommandResult, field: str, command: str) -> Mapping[str, object]:
    value = result.data.get(field)
    if isinstance(value, Mapping):
        return value
    raise CliError(
        "UPSTREAM_INVALID_RESPONSE",
        f"Provider returned {command} data without a renderable {field}.",
        EXIT_UPSTREAM,
        {"command": command},
        source=result.source,
    )


def _cookie_context(args: argparse.Namespace) -> tuple[str, str, str, str, str | None]:
    uid, region = _uid_and_region(args)
    ensure_supported_region(region)
    args.credential_kind = "cookie"
    cookie, credential_source, storage_backend = _credential(args, uid)
    return uid, region, cookie, credential_source, storage_backend


def _provider(args: argparse.Namespace, region: str):
    return provider_for_region(
        region,
        HttpClient(
            timeout=args.timeout,
            cache_policy="off",
            output_dir=args.output_dir,
            debug=args.debug,
        ),
    )


def _add_uid(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--uid", dest="command_uid")


def _write_image_artifact(
    args: argparse.Namespace,
    *,
    name: str,
    filename: str,
    description: str,
    content: bytes,
) -> dict[str, object]:
    return ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name=name,
        filename=filename,
        media_type="image/png",
        content=content,
        description=description,
        kind="image",
    )
