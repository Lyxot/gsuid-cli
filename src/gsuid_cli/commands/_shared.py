from __future__ import annotations

import argparse

from gsuid_cli.commands._text import (
    mapping_data as _mapping_data,
    write_image_artifact as _write_image_artifact,
)
from gsuid_cli.commands.auth import _credential, _uid_and_region
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.providers import provider_for_region

__all__ = [
    "_add_uid",
    "_cookie_context",
    "_mapping_data",
    "_provider",
    "_write_image_artifact",
]


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
