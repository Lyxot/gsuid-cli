from __future__ import annotations

import argparse

from gsuid_cli.commands._text import mapping_data as _mapping_data
from gsuid_cli.core.errors import EXIT_INVALID_INPUT, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.providers.public import PublicDataProvider

__all__ = [
    "_append_url",
    "_image_ext",
    "_limit",
    "_mapping_data",
    "_optional_bool",
    "_optional_text",
    "_positive",
    "_provider",
]


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
