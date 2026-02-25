from __future__ import annotations

from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.region import ensure_supported_region
from gsuid_cli.providers.mys import MysProvider


def provider_for_region(region: str, http_client: HttpClient) -> MysProvider:
    ensure_supported_region(region)
    return MysProvider(http_client)
