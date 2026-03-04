from __future__ import annotations

from gsuid_cli import __version__
from gsuid_cli.core.errors import EXIT_UPSTREAM, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.region import ensure_supported_region

PROVIDER = "enka"
ENKA_BASE_URL = "https://enka.network"
USER_AGENT = f"gsuid-cli/{__version__} (+https://github.com/<org>/gsuid-cli)"


class EnkaProvider:
    def __init__(self, http_client: HttpClient) -> None:
        self.http = http_client

    def profile(self, *, uid: str, region: str) -> CommandResult:
        ensure_supported_region(region)
        response = self.http.request_json(
            "GET",
            f"{ENKA_BASE_URL}/api/uid/{uid}",
            provider=PROVIDER,
            region=region,
            category="panel.refresh",
            headers={"User-Agent": USER_AGENT},
        )
        player_info = response.payload.get("playerInfo")
        if not isinstance(player_info, dict):
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "Enka returned an unexpected profile shape.",
                EXIT_UPSTREAM,
                {"provider": PROVIDER, "category": "panel.refresh", "uid": uid},
                source=response.source,
            )
        avatars = response.payload.get("avatarInfoList")
        if avatars is not None and not isinstance(avatars, list):
            raise CliError(
                "UPSTREAM_INVALID_RESPONSE",
                "Enka returned an unexpected avatar list shape.",
                EXIT_UPSTREAM,
                {"provider": PROVIDER, "category": "panel.refresh", "uid": uid},
                source=response.source,
            )
        return CommandResult(data=response.payload, source=response.source)
