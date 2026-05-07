from __future__ import annotations

import argparse
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context

from gsuid_cli.core.errors import CliError
from gsuid_cli.core.http import HttpClient, ProviderBytesResponse


class AssetProvider:
    def __init__(self, http_client: HttpClient) -> None:
        self.http = http_client

    def image(
        self,
        url: str,
        *,
        provider: str,
        region: str,
        category: str,
    ) -> ProviderBytesResponse:
        return self.http.request_bytes(
            "GET",
            url,
            provider=provider,
            region=region,
            category=category,
            expected_media_types=("image/",),
        )

    def json_bytes(
        self,
        url: str,
        *,
        provider: str,
        region: str,
        category: str,
    ) -> ProviderBytesResponse:
        return self.http.request_bytes(
            "GET",
            url,
            provider=provider,
            region=region,
            category=category,
            expected_media_types=("application/json", "text/plain"),
        )


def fetch_render_images(
    args: argparse.Namespace,
    urls: Iterable[str],
    *,
    provider: str,
    region: str,
    category: str,
    unavailable_warning: str,
    max_workers: int = 8,
) -> tuple[dict[str, bytes], list[str]]:
    unique_urls = _unique_urls(urls)
    if not unique_urls:
        return {}, []

    images: dict[str, bytes] = {}
    unavailable = 0
    workers = min(max(max_workers, 1), len(unique_urls))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = []
        for url in unique_urls:
            context = copy_context()
            futures.append(
                executor.submit(context.run, _fetch_image, args, url, provider, region, category)
            )
        for future in as_completed(futures):
            url, content = future.result()
            if content is None:
                unavailable += 1
                continue
            images[url] = content

    warnings = [unavailable_warning.format(count=unavailable)] if unavailable else []
    return images, warnings


def _fetch_image(
    args: argparse.Namespace,
    url: str,
    provider: str,
    region: str,
    category: str,
) -> tuple[str, bytes | None]:
    try:
        response = AssetProvider(
            HttpClient(
                timeout=args.timeout,
                cache_policy=args.cache,
                output_dir=args.output_dir,
                debug=args.debug,
            )
        ).image(
            url,
            provider=provider,
            region=region,
            category=category,
        )
    except CliError:
        return url, None
    return url, response.content


def _unique_urls(urls: Iterable[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        unique.append(url)
    return unique
