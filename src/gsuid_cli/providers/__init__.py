from __future__ import annotations

from gsuid_cli.core.http import HttpClient
from gsuid_cli.providers.mys import MysProvider


def provider_for_region(_region: str, http_client: HttpClient) -> MysProvider:
    return MysProvider(http_client)
