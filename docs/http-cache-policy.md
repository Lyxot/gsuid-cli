# HTTP Cache Policy

This file is the source policy for provider HTTP response caching. If the policy changes, update `src/gsuid_cli/core/cache_policy.py` to match it; if GenshinUID mirror selection changes, update `src/gsuid_cli/providers/resource_mirror.py`.

## Runtime Semantics

- `--cache use`: use a fresh cached response when available, otherwise request the provider and store the response if the matching rule is cacheable.
- `--cache refresh`: request the provider and replace the cached response if the matching rule is cacheable; versioned responses are persisted only when the Sophon tag lookup succeeds.
- `--cache only`: return a fresh cached response only; expired or missing cache entries fail with `CACHE_MISS`.
- `--cache off`: bypass cache reads and writes.
- Non-GET requests are never cached.
- Persistent JSON responses are stored under `$GSUID_HOME/cache/http`.
- Binary/static assets are stored under `$GSUID_HOME/cache/<usage>`.
- Asset usage buckets are `assets`, `icons`, `maps`, and `wiki`.
- `game-version` entries store `cache_version`; they expire when the refreshed Sophon build tag differs.
- Expired or version-stale persistent cache entries are deleted when encountered.
- Cache keys must use sanitized URLs and must never include secrets.
- The current Sophon build tag comes from `https://api-takumi.mihoyo.com/downloader/sophon_chunk/api/getBuild?branch=main&package_id=8xfMve0uwQ&password=CW8GbLNU8f&plat_app=ddxf5qt290cg` at `["data"]["tag"]`.
- GenshinUID resource URLs under `genshinuid://` are logical URLs. They are resolved lazily through the fastest reachable resource mirror, while binary asset cache keys keep the logical URL so cached files are reused across mirror changes.
- The GenshinUID mirror selection cache is stored under `$GSUID_HOME/cache/http/resource-mirror.genshinuid.json`. `--cache refresh` re-probes and replaces it, `--cache off` probes without storing it, and `--cache only` does not probe mirrors.

## Expiration Rules

| Rule | Expiration | Intended Data |
| --- | --- | --- |
| `no-store` | Never cache. | Auth/token/device actions and other side-effecting requests. |
| `private-short` | 60 seconds after fetch, process-memory only. | Authenticated player state, challenge state, progress state, and gacha refresh pages. |
| `public-short` | 5 minutes after fetch. | Fast-changing public rank/panel lookups and lightweight health checks. |
| `public-dynamic` | 6 hours after fetch. | Public events, announcements, rerun rows, and redeem codes. |
| `daily-reset` | Next 04:00 UTC+8 after fetch. | Daily material schedule data. |
| `game-version-tag` | Next 06:00 UTC+8 after fetch. | Sophon build-tag lookup used by `game-version` freshness checks. |
| `game-version` | When stored `cache_version` differs from the Sophon build tag refreshed by `game-version-tag`. | Public wiki/guide/recommendation data and static render assets that usually change with game versions. |
| `resource-mirror` | 6 hours after probe. | GenshinUID resource mirror selection; asset payloads still use the `game-version` rule. |

## URL Family Mapping

| URL Family | Rule | Notes |
| --- | --- | --- |
| `auth.*`, `device.*`, `daily.signin*`, `gacha.authkey.refresh` | `no-store` | Login, token, sign-in, and device mutation/status data must be live. |
| `daily.note*` | `private-short` | Resin, expeditions, commissions, and similar player state should not stay stale or persist on disk. |
| `player.*`, `challenge.*`, `progress.*`, `gacha.refresh` | `private-short` | Prevents duplicate immediate requests without hiding normal account changes or persisting private payloads. |
| `rank.*`, Akasha provider JSON | `public-short` | Leaderboards move frequently. |
| `panel.refresh`, Enka provider JSON | `public-short` | Showcase panels can change after a player updates display characters. |
| `daily.materials`, `daily.materials.upgrade` | `daily-reset` | Daily domain schedule should roll over at CN daily reset. |
| `codes.*`, `events.*`, `announcements.*`, `rerun.*` | `public-dynamic` | Public but can change during a version. |
| Sophon `getBuild` URL | `game-version-tag` | Uses `data.tag`; the cached lookup refreshes daily at 06:00 UTC+8. |
| `genshinuid://*` logical resource URLs | `resource-mirror` for mirror selection, normal request-category rule for fetched assets | Resolves to the fastest available GenshinUID resource mirror only when the asset is needed. Public static render assets usually use `game-version`; private/player categories may use shorter category rules. |
| `wiki.*`, `guide.*`, `recommend.*` | `game-version` | Static public data normally changes when game data updates. |
| GenshinUID GitHub/jsDelivr raw files for `guide.*` | `game-version` | Raw guide data such as `GenshinUID/genshinuid_guide/abyss.js` resolves the latest commit for that path on GenshinUID's default branch history, then fetches the raw file through jsDelivr instead of bundling it in the package. |
| Static binary assets fetched through `request_bytes` | `game-version` | Includes GenshinUID, AMBR, Hakush, MiniGG, MYS icon, and render-resource URLs unless a stricter rule is added. |
| `meta.doctor.network` | `public-short` | Only checks provider reachability. |

## Asset Usage Mapping

| Usage | URL Families |
| --- | --- |
| `icons` | URL families containing `icon`, ending with `.avatar`, containing `profile_picture`, AMBR/Hakush/MYS UI icon assets, and `genshinuid://resource/icon*` families. |
| `maps` | MiniGG provider assets and `map.*` URL families. |
| `wiki` | `genshinuid://wiki/*`, wiki, guide, event, announcement, recommendation, rerun, and daily-material assets that are not icon-like UI assets. |
| `assets` | Default bucket for other binary assets, including shared `genshinuid://resource/*` character, weapon, card, and render resources. |

## Modification Workflow

1. Edit this markdown policy first.
2. Update `src/gsuid_cli/core/cache_policy.py` to match.
3. Add or update focused cache tests.
4. Run the focused cache tests and the command reference check when command surface changes.
