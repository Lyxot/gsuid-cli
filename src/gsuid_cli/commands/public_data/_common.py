from __future__ import annotations

import argparse
import hashlib

from gsuid_cli.core.errors import EXIT_INVALID_INPUT, EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.providers.public import PublicDataProvider


def _provider(args: argparse.Namespace) -> PublicDataProvider:
    ensure_supported_region(args.region)
    return PublicDataProvider(
        HttpClient(
            timeout=args.timeout,
            cache_policy=args.cache,
            output_dir=args.output_dir,
            debug=args.debug,
        )
    )


def _mapping_data(result: CommandResult, field: str, command: str) -> dict[str, object]:
    value = result.data.get(field)
    if isinstance(value, dict):
        return value
    raise CliError(
        "UPSTREAM_INVALID_RESPONSE",
        f"Provider returned {command} data without a renderable {field}.",
        EXIT_UPSTREAM,
        {"command": command, "field": field},
        source=result.source,
    )


def _safe_filename(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    safe = safe.strip("_")[:60] or "item"
    return f"{safe}_{digest}"


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _image_ext(media_type: str) -> str:
    if media_type == "image/jpeg":
        return "jpg"
    if media_type == "image/png":
        return "png"
    return "bin"


def _limit(value: int) -> int:
    if value <= 0:
        raise CliError(
            "INVALID_ARGUMENT",
            "limit must be greater than 0",
            EXIT_INVALID_INPUT,
            {"limit": value},
        )
    return value


def _positive(value: int, name: str) -> int:
    if value <= 0:
        raise CliError(
            "INVALID_ARGUMENT",
            f"{name} must be greater than 0",
            EXIT_INVALID_INPUT,
            {name: value},
        )
    return value


def _append_url(urls: list[str], value: object) -> None:
    url = _optional_text(value)
    if url and url not in urls:
        urls.append(url)
