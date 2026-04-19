# PLAN

## Operating Rules For Future Agents

- Update this file before starting each meaningful stage.
- Update this file after finishing each stage with status, verification, and next stage.
- Keep commits small and conventional. Prefer one commit per completed stage.
- Do not copy GenshinUID code wholesale unless license compatibility and attribution are explicitly handled.
- Preserve behavior first, then improve structure only when the behavior is covered by tests.
- Every command must be non-interactive by default and must be usable by an automated agent.
- Use the repository-local `.venv` for Python commands. Do not commit virtual environment files.

## Product Decision

Build `gsuid`, a Python CLI for Genshin Impact account, wiki, panel, gacha-log, and event data inspired by GenshinUID, but designed for agent/tool use instead of chat-bot use.

Primary interface:

```text
gsuid [GLOBAL_OPTIONS] <group> <command> [COMMAND_OPTIONS]
```

Default output is JSON on stdout. Logs, progress, and warnings that are not part of the result go to stderr. Binary/image outputs are written as files and referenced by path in JSON.

Cache system decisions:

- HTTP JSON/game-record calls should not use persistent cache storage because the data changes rapidly. Keep only a short-lived in-memory cache within one CLI process when useful.
- Static assets are cached permanently under `$GSUID_HOME/cache/assets` until manually cleaned.
- Static asset cache paths should be flattened for easy system preview and cross-command reuse. Use the original file name plus a hash while preserving the corresponding file suffix.
- Store asset metadata, including URL, content type, fetched time, hash, size, status, and retry/failure information.
- Add a file-locking dependency if needed. Support large per-process parallel asset downloads while keeping writes safe across multiple CLI instances.
- Limit asset download concurrency per process only; no cross-process global rate limiter is required.
- Failed or partial asset downloads should clean up unsafe partial files but leave retry metadata for later diagnosis and retry behavior.

## Assumptions

- The first target game is Genshin Impact only.
- The MVP is CN-only. Overseas HoYoLAB support is added later.
- Agents prefer exact English subcommands over chat-style aliases.
- Most commands should work with an explicit `--uid`; local account binding is convenience, not a requirement.
- Credentials are supplied by env, stdin, or local keyring. They are never printed.
- Keyring support is mandatory. Do not implement a plaintext secret fallback.
- Rendered images should aim for visual parity with GenshinUID where the feature is ported.
- `a local GenshinUID reference` is a behavioral and implementation reference. Reusing GenshinUID assets/code is allowed when license-compatible and attributed.
- Agents call the CLI directly, so `--help`, command descriptions, and capability metadata are product-critical.

## Non-Goals

- Do not implement a QQ/OneBot/Telegram/WeChat bot adapter.
- Do not implement interactive prompts as required workflows.
- Do not make chat aliases the canonical command contract.
- Do not implement top-up/payment flows in the MVP.
- Do not implement plugin self-update commands in the MVP.
- Do not add a daemon until one-shot commands and batch mode are stable.

## Repository Bootstrap

- Status: completed.
- Commit: `0ae4d5b chore: bootstrap repository`.
- Result: repository is on `main`, `LICENSE` contains AGPLv3, and `origin` is `git@github.com:<org>/gsuid-cli.git`.
- Verification: `git status --short --branch`, `git remote -v`, and `git log --oneline -1`.

## CLI Contract

### Executable

- Console script: `gsuid`
- Python module entry: `python -m gsuid_cli`
- Package source root: `src/gsuid_cli`

### Global Options

```text
--profile NAME                 Local profile name. Default: default.
--uid UID                      Target Genshin UID. Overrides profile default.
--region cn|os                 Target API region. Default: infer from profile, then UID.
--format json|pretty-json|text Output format. Default: json.
--render data|image|both       Data/artifact preference. Default: data.
--output-dir PATH              Artifact output directory. Default: $GSUID_HOME/artifacts.
--cache use|refresh|only|off   Cache policy. Default: use.
--timeout SECONDS              HTTP timeout. Default: 20.
--request-id ID                Caller-supplied request id. Default: generated UUID.
--quiet                        Suppress non-result stderr logs.
--debug                        Include debug diagnostics in error.details.
--version                      Print version.
--help                         Print help.
```

### Environment Variables

```text
GSUID_HOME                     Default: ~/.gsuid-cli
GSUID_PROFILE                  Default profile when --profile is omitted.
GSUID_FORMAT                   Default output format.
GSUID_REGION                   Default region when profile has none.
GSUID_COOKIE                   Cookie for one command, higher priority than stored cookie.
GSUID_STOKEN                   Stoken for one command, higher priority than stored stoken.
GSUID_GACHA_URL                Gacha authkey URL for gacha refresh.
GSUID_OUTPUT_DIR               Default artifact directory.
```

### Local State Layout

```text
$GSUID_HOME/
  config.toml                  Non-secret defaults.
  state.sqlite                 Accounts, profiles, cache metadata, gacha summaries.
  cache/
    assets/                    Flattened permanent static asset cache.
  artifacts/
    YYYY-MM-DD/
      REQUEST_ID/
  logs/
```

Secret storage rule:

- OS keyring is required for stored credentials.
- If keyring is unavailable, credential write/read commands must fail with a clear keyring error.
- One-shot env/stdin credentials may be used without persisting them.
- Never log secret values, cookie strings, stoken strings, authkeys, or full URLs containing authkeys.

### Exit Codes

```text
0   Success.
1   Invalid input or missing required option.
2   Missing, expired, or insufficient credential.
3   Upstream API rejected the request.
4   Network timeout or connection failure.
5   Cache/resource unavailable when required.
6   Valid request with no matching result.
10  Internal bug.
130 Interrupted.
```

### JSON Success Envelope

All JSON command results must use this envelope:

```json
{
  "ok": true,
  "schema": "gsuid.cli/v1",
  "command": "daily.note",
  "request_id": "uuid-or-caller-id",
  "generated_at": "2026-04-29T10:30:00Z",
  "duration_ms": 1234,
  "warnings": [],
  "data": {},
  "artifacts": [],
  "source": {
    "provider": "mys",
    "region": "cn",
    "cached": false,
    "fetched_at": "2026-04-29T10:29:59Z"
  },
  "pagination": null
}
```

### JSON Error Envelope

Even on failure, JSON mode writes the error envelope to stdout and exits non-zero:

```json
{
  "ok": false,
  "schema": "gsuid.cli/v1",
  "command": "auth.cookie.test",
  "request_id": "uuid-or-caller-id",
  "generated_at": "2026-04-29T10:30:00Z",
  "duration_ms": 211,
  "warnings": [],
  "error": {
    "code": "AUTH_EXPIRED",
    "message": "The stored cookie is expired or rejected by the provider.",
    "details": {
      "uid": "<UID>",
      "region": "cn"
    },
    "retryable": false
  },
  "artifacts": [],
  "source": {
    "provider": "mys",
    "region": "cn",
    "cached": false,
    "fetched_at": null
  }
}
```

### Artifact Format

Images, JSON exports, and downloaded files are returned by path:

```json
{
  "kind": "image",
  "name": "daily_note",
  "path": "~/.gsuid-cli/artifacts/2026-04-29/REQ/daily_note.png",
  "media_type": "image/png",
  "bytes": 123456,
  "sha256": "hex",
  "description": "Rendered daily note card"
}
```

Artifact rules:

- Do not base64-encode artifacts by default.
- Always include absolute paths.
- Use stable filenames per command.
- Include `sha256` after file creation.
- `--render data` should not create images unless the command has no structured implementation yet.
- `--render both` should return structured `data` and rendered artifacts when both are implemented.

### Text Output

Text mode is for humans and is not a compatibility contract. JSON mode is the only stable contract.

## Command Set

### Meta And Diagnostics

```text
gsuid meta version
gsuid meta capabilities
gsuid meta schema [--command COMMAND]
gsuid meta doctor [--check network|storage|credentials|resources|all]
gsuid meta paths
gsuid cache clear [--scope assets|artifacts|all]
gsuid resources sync [--scope wiki|icons|maps|all]
```

Return data:

- `meta.version`: package version, Python version, git revision if available.
- `meta.capabilities`: implemented command list, auth requirements, render support, regions.
- `meta.schema`: JSON schema for the envelope or one command's `data`.
- `meta.doctor`: checks with `name`, `status`, `message`, `details`.
- `meta.paths`: resolved home, cache, data, artifact, and config paths.

### Profiles, Accounts, And Credentials

```text
gsuid profile init [--name NAME] [--region cn|os]
gsuid profile list
gsuid profile show [--name NAME]
gsuid profile default [--name NAME]
gsuid profile delete --name NAME

gsuid account add --uid UID [--region cn|os] [--label LABEL] [--default]
gsuid account list
gsuid account show [--uid UID]
gsuid account default [--uid UID]
gsuid account remove --uid UID

gsuid auth cookie set --uid UID (--cookie-stdin | --cookie-file PATH | --cookie VALUE)
gsuid auth cookie test [--uid UID]
gsuid auth cookie delete --uid UID
gsuid auth stoken set --uid UID (--stoken-stdin | --stoken-file PATH | --stoken VALUE)
gsuid auth stoken test [--uid UID]
gsuid auth stoken delete --uid UID
gsuid auth gacha-url set --uid UID (--url-stdin | --url-file PATH | --url VALUE)
gsuid auth gacha-url test [--uid UID]
gsuid auth gacha-url delete --uid UID
gsuid auth device set --uid UID (--device-stdin | --device-file PATH | --device-json JSON)
gsuid auth device test [--uid UID]
gsuid auth device delete --uid UID
```

Return data:

- `profile.*`: profile name, default UID, default region, account count.
- `account.*`: UID, region, label, default flag, credential availability booleans.
- `auth.*`: UID, credential type, storage backend, validity status, sanitized provider response.

Input rules:

- `--cookie`, `--stoken`, and `--url` are allowed for automation but discouraged because shell history may record them.
- `--cookie-stdin`, `--stoken-stdin`, and `--url-stdin` are preferred.
- Secret values must be redacted in debug output.
- Device payloads may contain stable device identifiers. Prefer
  `--device-stdin` or `--device-file`; command output must redact raw
  `device_id` and `device_fp` values.

### Player And Account Data

```text
gsuid player summary [--uid UID]
gsuid player characters [--uid UID]
gsuid player inventory [--uid UID]
gsuid player calendar [--uid UID]
gsuid player diary [--uid UID] [--month YYYY-MM]
gsuid player register-time [--uid UID]

gsuid daily note [--uid UID]
gsuid daily signin [--uid UID]
gsuid daily bbs-coin [--uid UID]
gsuid daily materials [--date YYYY-MM-DD]
```

Source mapping from GenshinUID:

- `player summary`: `查询`, `uid`, `UID`.
- `player characters`: `角色列表`.
- `player inventory`: `我的背包`, `我的物品`.
- `player calendar`: `个人日历`, `日历`.
- `player diary`: `每月统计`, `当前信息`, `札记`.
- `player register-time`: `原神注册时间`.
- `daily note`: `每日`, `实时便笺`, `便笺`, `当前状态`.
- `daily signin`: `签到`.
- `daily bbs-coin`: `开始获取米游币`.
- `daily materials`: `每日材料`, `今日素材`.

Return data:

- `player.summary`: nickname, level, world level, achievements, abyss stars, exploration summary, character count.
- `player.characters`: list of character ids/names, level, constellation, element, weapon, friendship, owned status.
- `player.inventory`: categorized item counts where provider allows access.
- `player.calendar`: time-limited activities, birthday reminders, resin-relevant items.
- `player.diary`: primogem/mora income totals, categories, month, currency trend.
- `player.register-time`: UID, registration date if available, confidence/source.
- `daily.note`: resin, max resin, realm currency, expeditions, transformer, commissions, discounts, recovery estimates.
- `daily.signin`: already signed flag, reward, day number, provider message.
- `daily.bbs-coin`: task statuses, points received, failures.
- `daily.materials`: weekday, talent domains, weapon domains, character/weapon recommendations when available.

Auth requirements:

- `daily.note`, `daily.signin`, `daily.bbs-coin`, `player.diary`, `player.inventory`, and some `player.summary` fields require cookie.
- `daily.bbs-coin` and gacha-related account flows may require stoken.

### Challenge And Progress Data

```text
gsuid challenge abyss [--uid UID] [--season current|previous] [--floor 9|10|11|12]
gsuid challenge theater [--uid UID] [--season current|previous]
gsuid challenge hard [--uid UID] [--season current|previous]
gsuid challenge hard-rank

gsuid progress completion [--uid UID]
gsuid progress exploration [--uid UID]
gsuid progress collection [--uid UID]
gsuid progress achievements [--uid UID] [--query TEXT]
gsuid progress achievement-guide --query TEXT
gsuid progress commission-guide --query TEXT
gsuid progress gcg [--uid UID]
gsuid progress gcg-deck [--uid UID] [--deck-id N]
```

Source mapping from GenshinUID:

- `challenge abyss`: `深渊`, `查询深渊`, `上期深渊`, `sy`, `sqsy`.
- `challenge theater`: `幻想真境剧诗`, `新深渊`, `剧诗`.
- `challenge hard`: `幽境危战`, `肃靖险乱`, `yjwz`.
- `challenge hard-rank`: `幽境危战排行榜`.
- `progress completion`: `查询完成度`, `wcd`.
- `progress exploration`: `查询探索`, `ts`.
- `progress collection`: `查询收集`, `sj`.
- `progress achievements`: `我的成就`.
- `progress achievement-guide`: `查成就`.
- `progress commission-guide`: `查委托`.
- `progress gcg`: `七圣召唤`.
- `progress gcg-deck`: `我的卡组`.

Return data:

- `challenge.abyss`: season, total stars, floors, chambers, battles, teams, character usage, fastest/strongest stats.
- `challenge.theater`: season, difficulty, stars, rounds, characters, blessings, battle results.
- `challenge.hard`: season, score, teams, bosses, buffs, clear details.
- `challenge.hard-rank`: rank entries with UID redaction if needed.
- `progress.completion`: aggregate completion score and component breakdown.
- `progress.exploration`: regions, exploration percent, offerings, waypoints, oculi, chests where available.
- `progress.collection`: collectible categories and counts.
- `progress.achievements`: completion count, total count, groups, optional query result.
- `progress.*-guide`: matching guide entries with source links if available.
- `progress.gcg`: level, cards, matches, coins, achievements.
- `progress.gcg-deck`: deck id, cards, character cards, action cards.

### Gacha Log

```text
gsuid gacha refresh [--uid UID] [--force] [--full]
gsuid gacha summary [--uid UID] [--banner character|weapon|standard|chronicled|all]
gsuid gacha export [--uid UID] [--format uigf-v4|uigf-v2] [--output PATH]
gsuid gacha import --uid UID --file PATH [--format auto|uigf-v4|uigf-v2]
gsuid gacha authkey [--uid UID]
```

Source mapping from GenshinUID:

- `gacha refresh`: `刷新抽卡记录`, `强制刷新抽卡记录`, `全量刷新抽卡记录`.
- `gacha summary`: `抽卡记录`.
- `gacha export`: `导出抽卡记录`.
- `gacha import`: direct JSON import.
- `gacha authkey`: `导出抽卡记录链接`.

Return data:

- `gacha.refresh`: UID, banners refreshed, new item count, duplicate count, range, source URL validity.
- `gacha.summary`: pity counters, five-star history, four-star history, banner totals, last update.
- `gacha.export`: artifact path, format, item count, UID.
- `gacha.import`: imported count, skipped duplicates, detected format, validation errors.
- `gacha.authkey`: sanitized URL metadata only. Never print raw authkey unless `--unsafe-print-secret` is explicitly added in a future stage.

Storage:

- Store normalized gacha records in SQLite.
- Preserve original imported JSON as an artifact only if requested.
- UIGF v4 is the preferred export format.

### Panels, Enka, And Ranking

```text
gsuid panel refresh [--uid UID] [--source auto|enka|mys] [--force]
gsuid panel list [--uid UID]
gsuid panel show --character NAME [--uid UID] [--constellation N] [--weapon NAME] [--artifact-source-character NAME]
gsuid panel compare --build SPEC --build SPEC [--build SPEC]
gsuid panel save --character NAME --name NAME [--uid UID]
gsuid panel artifacts [--uid UID] [--page N]
gsuid panel showcase [--uid UID]
gsuid panel graduation [--uid UID]

gsuid rank summary [--uid UID]
gsuid rank list [--uid UID]
gsuid rank character --character NAME [--uid UID] [--nearby]
gsuid rank artifact [--sort crit|crit-rate|crit-damage|em|recharge|atk]
```

Source mapping from GenshinUID:

- `panel refresh`: `刷新面板`, `强制刷新`, `mys刷新面板`, `enka刷新面板`.
- `panel show`: `查询[角色]`, with controlled options replacing free-form text mutation.
- `panel compare`: `对比面板`.
- `panel save`: `保存面板`.
- `panel artifacts`: `圣遗物仓库`.
- `panel showcase`: `角色橱窗`.
- `panel graduation`: `毕业度统计`.
- `rank summary`: `排名统计`.
- `rank list`: `排名列表`.
- `rank character`: `角色排名`, `角色排行榜`.
- `rank artifact`: `圣遗物排名`.

Return data:

- `panel.refresh`: source used, refreshed character count, cache paths, failures.
- `panel.list`: cached characters with update timestamps.
- `panel.show`: character stats, weapon, artifacts, talents, constellation, damage estimates if available, artifact path when rendered.
- `panel.compare`: list of builds, normalized stat deltas, artifact path when rendered.
- `panel.save`: saved build name, path, character.
- `panel.artifacts`: page, total pages, artifact list, scores if available.
- `panel.showcase`: top cached builds and rank highlights.
- `panel.graduation`: per-character graduation score and missing improvements.
- `rank.*`: rank entries, percentile, scoring rule, source metadata.

Design rule:

- Do not port the free-form `查询六命心海换护摩` parser as the primary API.
- Convert those behaviors into typed options so agents can construct reliable calls.
- A compatibility parser may be added later under `compat run`, but it must call the typed service layer.

### Wiki, Guides, Events, Maps, And Public Data

```text
gsuid wiki character --name NAME [--level N]
gsuid wiki weapon --name NAME [--level N]
gsuid wiki artifact --name NAME
gsuid wiki food --name NAME
gsuid wiki enemy --name NAME
gsuid wiki talent --character NAME --talent N
gsuid wiki constellation --character NAME [--constellation N]
gsuid wiki character-materials --character NAME
gsuid wiki weapon-materials --weapon NAME

gsuid guide character --name NAME
gsuid guide reference-panel --character NAME
gsuid guide route --material NAME
gsuid guide abyss [--version VERSION] [--floor 11|12]
gsuid guide theater [--version VERSION]
gsuid recommend build --character NAME
gsuid recommend holder --item NAME

gsuid events list
gsuid events banners
gsuid announcements list [--limit N]
gsuid announcements show --id ID
gsuid codes list
gsuid map find --item NAME [--map teyvat|chasm|enkanomiya]
gsuid rerun list
gsuid misc primogems-plan [--version VERSION]
```

Source mapping from GenshinUID:

- `wiki.*`: `角色介绍`, `武器介绍`, `圣遗物介绍`, `食物介绍`, `原魔介绍`, `角色天赋`, `角色命座`, `角色材料`, `武器材料`.
- `guide.character`: `[角色]攻略`, `[角色]推荐`.
- `guide.reference-panel`: `参考面板[角色]`.
- `guide.route`: `[材料]路线`.
- `guide.abyss`: `版本深渊`, `深渊阵容`, `深渊怪物`.
- `guide.theater`: `剧诗版本深渊`.
- `recommend.build`: `[角色]用什么`, `[角色]怎么养`.
- `recommend.holder`: `[武器/圣遗物]给谁用`.
- `events.list`: `活动列表`.
- `events.banners`: `卡池列表`.
- `announcements.*`: `原神公告`.
- `codes.list`: `兑换码`.
- `map.find`: `哪里有[资源]`.
- `rerun.list`: `未复刻列表`.
- `misc.primogems-plan`: `版本规划`, `原石预估`.

Return data:

- Wiki commands return normalized entities: id, name, aliases, rarity, category, description, stats, costs, source.
- Guide commands return guide metadata plus artifact path if the source is image-only.
- Events and announcements return ids, titles, start/end timestamps, status, URLs when available.
- Codes return code, rewards if known, status if known, source, fetched_at.
- Map results return item, map, matched aliases, marker count, bounds if available, artifact path when rendered.
- Rerun list returns entity, last banner date, days since last banner, banner type.

### Automation And Batch Mode

```text
gsuid batch run --file commands.jsonl
gsuid batch plan --file commands.jsonl
gsuid monitor once [--min-free-mb N] [--max-asset-cache-files N] [--max-artifact-files N]
```

Batch input line formats:

```json
{"argv":["daily","note","--uid","<UID>"],"request_id":"req-1"}
{"command":"meta version","request_id":"req-2"}
```

Batch output:

- `batch run` returns one aggregate JSON envelope containing one nested JSON
  envelope per input line. Nested request ids are deterministic when omitted.
- `batch plan` validates commands without executing provider calls.
- Batch commands cannot be nested inside batch input.
- `monitor once` evaluates local health thresholds and returns structured
  `ok`/`warn` checks. It does not send chat messages.

Daemon support is deferred until one-shot monitoring is stable.

## Implementation Architecture

### Package Structure

```text
src/gsuid_cli/
  __init__.py
  __main__.py
  cli.py
  commands/
    meta.py
    profile.py
    account.py
    auth.py
    player.py
    daily.py
    challenge.py
    progress.py
    gacha.py
    panel.py
    rank.py
    wiki.py
    guide.py
    events.py
    map.py
    batch.py
  core/
    envelope.py
    errors.py
    models.py
    time.py
    artifacts.py
    secrets.py
    config.py
    state.py
    cache.py
  providers/
    mys.py
    hoyolab.py
    enka.py
    akasha.py
    wiki.py
    map.py
    codes.py
  services/
    player.py
    daily.py
    challenge.py
    progress.py
    gacha.py
    panel.py
    wiki.py
    events.py
  renderers/
    daily_note.py
    abyss.py
    panel.py
    map.py
tests/
```

### Dependency Decisions

- CLI parser: start with `argparse` to avoid framework behavior leaking into stdout.
- HTTP: `httpx`.
- Secret storage: `keyring`; no plaintext fallback.
- Data validation: dataclasses and explicit serializers first; add Pydantic only if provider models become hard to maintain.
- Storage: `sqlite3` from stdlib for state and cache metadata.
- TOML: `tomllib` for reading, `tomli-w` only if config writing needs it.
- Formatting/linting: `ruff`.
- Tests: `pytest`, `respx` or `pytest-httpx` for mocked HTTP.
- Image rendering: `Pillow`, added only when first renderer stage begins.

### Service Layer Rules

- CLI command modules parse inputs and call services.
- Services return plain Python models, not JSON strings.
- Providers handle HTTP, authentication headers, retries, and upstream quirks.
- Providers never write artifacts directly.
- Renderers consume service models and write artifacts.
- Envelope creation happens once at the command boundary.

### Provider Rules

- Every provider call must have a timeout.
- Every provider response must record provider, URL category, status code, cached flag, fetched_at.
- Cache keys must exclude secrets.
- Retry only safe idempotent GET requests by default.
- POST actions like sign-in must not retry unless the provider response proves idempotency.

### Data Normalization Rules

- UIDs are strings in JSON to avoid accidental numeric coercion.
- Timestamps use UTC ISO 8601 with `Z`.
- Durations use seconds unless field name says otherwise.
- Currency and counts use integers.
- Percent values use numbers from 0 to 100.
- Unknown values are `null`, not omitted, when the field is part of the command schema.

## Staged Roadmap

### Stage 0: Repository Bootstrap — completed.
### Stage 1: Specification Plan — completed.
### Stage 2: Project Skeleton — completed.
### Stage 3: State, Profiles, Accounts, And Secrets — completed.
### Stage 4: Provider Foundation — completed.
### Stage 4.5: QR Login — completed.
### Stage 4.6: Interactive QR Login — completed.
### Stage 4.7: Live Auth Validation Fixes — completed.
### Stage 4.8: MYS Device Login — completed.
### Stage 5: Public Data MVP — completed.
### Stage 6: Authenticated Daily And Player Data — completed.
### Stage 7: Progress And Challenge Data — completed.
### Stage 8: Gacha Log — completed.
### Stage 8.1: Automatic Gacha Authkey URL — completed.
### Stage 8.2: Live Gacha Refresh Normalization — completed.
### Stage 8.3: Gacha Five-Star Intervals — completed.
### Stage 8.4: Gacha Refresh Gap Recovery — completed.
### Stage 9: Enka Panels And Ranking — completed.
### Stage 10: Rendering And Artifacts — completed.
### Stage 11: Guides, Maps, And Rich Public Data — completed.
### Stage 12: Batch And Agent Hardening — completed.
### Stage 13: Documentation, CI, And Release — completed.
### Stage 14: Missing Command Contract Completion — completed.
### Stage 14.1: Source-Limited Player Data Ports — completed.
### Stage 15: Full Global Options — completed.
### Stage 16: Help Information Coverage — completed.
### Stage 16.5: Cache System Redesign — completed.
### Stage 17: GenshinUID Image Parity

- Status: in progress.
- Goal: replace the first-pass local image generation with GenshinUID-parity
  rendering, implemented in small reviewable substages.
- Stage 17a status: completed.
- Stage 17a result: temporarily removed existing generated-image paths for QR start,
  daily note, Spiral Abyss, and panel show; deleted the local Pillow card
  renderer; removed the Pillow runtime dependency; downgraded those command
  capabilities to data-only; and kept non-generated artifact flows such as
  MiniGG map images, JSON exports, and saved panel JSON artifacts intact.
- Verification:
  - `.venv/bin/python -m pytest tests/test_meta_commands.py tests/test_global_options.py tests/test_auth_secrets.py tests/test_rich_public_data.py`
  - `.venv/bin/python -m pytest`
  - `.venv/bin/ruff check .`
  - `.venv/bin/ruff format --check .`
- Review: standalone review agents found stale QR preservation/example wording;
  documentation now states generated renderers are temporarily disabled during
  Stage 17.
- Next intended substage: Stage 17b, choose the first GenshinUID renderer group
  to port and document source/license attribution before adding code.

- Stage 17b status: completed.
- Stage 17b goal: port the `daily` image renderer group from the referenced
  historical GenshinUID-parity commits, starting with `daily.note` and
  `daily.materials`, while adapting all remote asset fetches to the Stage 16.5
  static asset cache.
- Stage 17b scope note: extract only the common renderer and render-asset fetch
  helpers needed by the daily note/materials ports so later image groups can
  reuse the same packaged asset, font, PNG, and static-asset cache paths.
- Stage 17b result: restored attributed GenshinUID daily note/materials assets,
  added shared renderer helpers and common static-image fetch helpers, re-enabled
  `--render image|both` for `daily.note` and `daily.materials`, enriched daily
  materials with AMBR upgrade/icon metadata, and added the read-only MYS daily
  sign-in status used by the note card. Amended with a shared optimized PNG
  compression pass for generated renderer output before writing artifacts.
- Verification:
  - `.venv/bin/python -m pip install -e '.[dev]'`
  - `.venv/bin/python -m pytest tests/test_public_data.py tests/test_daily_player_data.py tests/test_meta_commands.py -q`
  - `.venv/bin/ruff check .`
  - `.venv/bin/ruff format --check .`
  - `.venv/bin/python -m pytest`
  - `.venv/bin/python scripts/generate_command_reference.py --check`
  - `.venv/bin/python -m gsuid_cli --request-id stage17b-materials --render image daily materials --day wednesday`
  - `.venv/bin/python -m gsuid_cli --request-id stage17b-note --render image daily note --uid <UID>`
  - `.venv/bin/python -m gsuid_cli --request-id stage17b-compress-materials --render image daily materials --day wednesday`
  - `.venv/bin/python -m gsuid_cli --request-id stage17b-compress-note --render image daily note --uid <UID>`
- Live artifacts:
  - `~/.gsuid-cli/artifacts/2026-05-01/stage17b-materials/daily-materials_wednesday_c1b89f84.png`
  - `~/.gsuid-cli/artifacts/2026-05-01/stage17b-note/daily-note_102452098_68affdf2.png`
- Next intended substage: Stage 17c, port the next GenshinUID image renderer
  group after confirming priority.

- Stage 17c status: completed.
- Stage 17c goal: port the GenshinUID `角色列表` player character-list
  renderer to `player characters --render image|both`.
- Stage 17c scope note: adapt the GenshinUID `draw_all_char.py` layout to the
  existing `player.characters` provider data and Stage 16.5 static asset fetch
  strategy, including GenshinUID resource-mirror character portraits, weapon
  icons, and namecard backgrounds; leave the larger full player summary /
  role-info card for a later focused substage.
- Stage 17c result: restored attributed GenshinUID player character-list
  textures and shared v4 background asset, added a reusable v4 background
  helper, added the `player.characters` renderer, fetched GenshinUID
  character/weapon/namecard resources through the static asset cache with MYS
  image fallback, and re-enabled `--render image|both` for the player character
  list.
- Verification:
  - `.venv/bin/python -m pytest tests/test_daily_player_data.py tests/test_meta_commands.py -q`
  - `.venv/bin/ruff check .`
  - `.venv/bin/ruff format --check .`
  - `.venv/bin/python scripts/generate_command_reference.py --check`
  - `.venv/bin/python -m pytest`
  - `.venv/bin/python -m gsuid_cli --request-id stage17c-player-characters --render image player characters --uid <UID>`
  - `.venv/bin/python -m gsuid_cli --request-id stage17c-player-characters-v2 --render image player characters --uid <UID>`
  - `.venv/bin/python -m gsuid_cli --request-id stage17c-player-characters-v3 --render image player characters --uid <UID>`
- Live artifact:
  - `~/.gsuid-cli/artifacts/2026-05-01/stage17c-player-characters/player-characters_102452098.png`
  - `~/.gsuid-cli/artifacts/2026-05-01/stage17c-player-characters-v2/player-characters_102452098.png`
  - `~/.gsuid-cli/artifacts/2026-05-01/stage17c-player-characters-v3/player-characters_102452098.png`
- Next intended substage: Stage 17d, port the larger full player summary /
  role-info card after confirming its data and asset scope.

- Stage 17d status: completed.
- Stage 17d goal: port the GenshinUID full player role-info card to
  `player summary --render image|both`.
- Stage 17d scope note: compose the GenshinUID title, exploration, and
  character-list sections using existing `player.summary` and
  `player.characters` provider data; use deterministic account/avatar assets
  instead of chat-event avatars because the CLI has no bot event context.
- Stage 17d result: restored attributed GenshinUID title/footer/mask and
  exploration assets, added the full player summary renderer, re-enabled
  `--render image|both` for `player.summary`, reused the Stage 17c character
  resource fetch strategy, prefer `role.avatar_icon` for the title avatar and
  fall back to the public player profile picture because the CLI cannot access
  QQ profile images, resolve Enka profile-picture ids through live profile
  picture config data instead of hardcoded profile mappings, made
  missing/future oculus icon assets degrade to placeholders, draw the footer as
  `Created by gsuid-cli & Render style/assets by GenshinUID & Data by 米游社`,
  and forced internal daily-note player-summary lookup to data mode so
  unrelated render modes do not create nested artifacts.
- Verification:
  - `.venv/bin/python -m pytest tests/test_daily_player_data.py::test_player_summary_render_image_writes_full_role_card -q`
  - `.venv/bin/python -m gsuid_cli --request-id stage17d-player-summary-footer --render image player summary --uid <UID>`
  - `.venv/bin/python -m pytest tests/test_daily_player_data.py tests/test_meta_commands.py -q`
  - `.venv/bin/ruff check .`
  - `.venv/bin/ruff format --check .`
  - `.venv/bin/python scripts/generate_command_reference.py --check`
  - `.venv/bin/python -m pytest`
  - `.venv/bin/python -m gsuid_cli --request-id stage17d-player-summary --render image player summary --uid <UID>`
  - `.venv/bin/python -m gsuid_cli --request-id stage17d-player-summary-profile --render image player summary --uid <UID>`
  - `.venv/bin/python -m gsuid_cli --request-id stage17d-player-summary-final --render image player summary --uid <UID>`
  - `.venv/bin/python -m gsuid_cli --request-id stage17d-player-summary-pfp-config --render image player summary --uid <UID>`
- Live artifact:
  - `~/.gsuid-cli/artifacts/2026-05-01/stage17d-player-summary/player-summary_102452098.png`
  - `~/.gsuid-cli/artifacts/2026-05-01/stage17d-player-summary-profile/player-summary_102452098.png`
  - `~/.gsuid-cli/artifacts/2026-05-01/stage17d-player-summary-final/player-summary_102452098.png`
  - `~/.gsuid-cli/artifacts/2026-05-01/stage17d-player-summary-pfp-config/player-summary_102452098.png`
- Next intended substage: Stage 17e, port the next GenshinUID image renderer
  group after confirming priority.

- Stage 17e status: completed.
- Stage 17e goal: finish GenshinUID-parity image rendering for the `player`
  command group by porting the remaining GenshinUID player-related renderers.
- Stage 17e result:
  - Add `player inventory --render image|both` from GenshinUID `我的背包`.
  - Add `player calendar --render image|both` from GenshinUID `个人日历`.
  - Add `player diary --render image|both` from GenshinUID `原石札记`.
  - Reused shared player title/avatar/footer helpers for the new renderers,
    packaged and attributed the copied GenshinUID assets, and updated
    capabilities/docs to advertise the new image render support.
  - Keep `player register-time` data-only because GenshinUID returns text for
    `原神注册时间` and no GenshinUID image renderer is available to port.
- Stage 17e review:
  - Standalone review agent completed; two medium visual-parity gaps were fixed
    before commit: diary now uses the GenshinUID color background/avatar ring,
    and calendar no longer truncates pool items after the fourth entry.
- Stage 17e verification:
  - `.venv/bin/python -m pytest tests/test_daily_player_data.py::test_player_inventory_calendar_diary_render_images tests/test_daily_player_data.py::test_player_calendar_renderer_keeps_pool_items_after_four tests/test_meta_commands.py::test_meta_capabilities_lists_implemented_commands -q`
  - `.venv/bin/python -m pytest`
  - `.venv/bin/ruff check .`
  - `.venv/bin/ruff format --check .`
  - `.venv/bin/python scripts/generate_command_reference.py --check`
  - `git diff --check`
  - `.venv/bin/python -m build`
  - `.venv/bin/python -m gsuid_cli --request-id stage17e-inventory-final --render image player inventory --uid <UID>`
  - `.venv/bin/python -m gsuid_cli --request-id stage17e-calendar-final --render image player calendar --uid <UID>`
  - `.venv/bin/python -m gsuid_cli --request-id stage17e-diary-final --render image player diary --uid <UID>`
- Stage 17e live artifacts:
  - `~/.gsuid-cli/artifacts/2026-05-02/stage17e-inventory-final/player-inventory_102452098.png`
  - `~/.gsuid-cli/artifacts/2026-05-02/stage17e-calendar-final/player-calendar_102452098.png`
  - `~/.gsuid-cli/artifacts/2026-05-02/stage17e-diary-final/player-diary_102452098.png`
- Next intended substage: Stage 17f, continue porting the next image-render
  group selected from the remaining PLAN coverage.

- Stage 17f status: completed.
- Stage 17f goal: port GenshinUID-style image rendering for the `challenge`
  command group.
- Stage 17f result:
  - Add `challenge abyss --render image|both` using the GenshinUID Spiral Abyss
    renderer layout and assets, adapted to the CLI's normalized abyss payload.
  - Add `challenge theater --render image|both` using the GenshinUID
    `幻想真境剧诗` renderer layout and assets, adapted to the selected theater
    session payload.
  - Add `challenge hard --render image|both` using the GenshinUID
    `新新深渊`/`幽境危战` renderer layout and assets.
  - Keep `challenge hard-rank` data-only because the configured source still
    reports ranking support as unavailable.
  - Reuse shared GenshinUID-style challenge render helpers, copied/attributed
    GenshinUID challenge textures and character-card assets, and package them in
    the wheel/sdist.
  - Fix Abyss image overview parity so lower floors omitted by skipped or
    floor-filtered payloads render as skipped rather than locked.
  - Switch `challenge hard` to the same `/hard_challenge?need_detail=true`
    endpoint used by GenshinUID `新新深渊`/`幽境危战`, normalize the
    `data[0].single.challenge` payload, and render the fixed 900x1900
    GenshinUID hard-challenge card for the current three-boss layout.
  - Do not emit an Abyss image artifact when the provider returns no Abyss floor
    data; return `NO_RESULT` with no artifacts instead.
  - Use the same title profile-image selection logic as `player summary`, with
    role avatar first and Enka profile-picture fallback when the role avatar is
    absent.
- Stage 17f review:
  - Standalone review agent completed. One medium Abyss visual-parity issue was
    fixed before commit: missing lower floors now synthesize GenshinUID-style
    skipped floor slots for the overview.
  - A second standalone review after the hard-endpoint/profile-image correction
    found no blocking issues.
- Stage 17f verification:
  - `.venv/bin/python -m pytest tests/test_challenge_progress_data.py::test_challenge_abyss_overview_marks_missing_lower_floors_as_skipped tests/test_challenge_progress_data.py::test_challenge_render_images -q`
  - `.venv/bin/python -m pytest tests/test_challenge_progress_data.py tests/test_meta_commands.py tests/test_docs.py -q`
  - `.venv/bin/python -m pytest`
  - `.venv/bin/ruff check .`
  - `.venv/bin/ruff format --check .`
  - `.venv/bin/python scripts/generate_command_reference.py --check`
  - `git diff --check`
  - `.venv/bin/python -m build`
  - `.venv/bin/python -m gsuid_cli --request-id stage17f-hard-data-v2 challenge hard --uid <UID>`
  - `.venv/bin/python -m gsuid_cli --request-id stage17f-hard-image-v5 --render image challenge hard --uid <UID>`
  - `.venv/bin/python -m gsuid_cli --request-id stage17f-abyss-no-data-v2 --render image challenge abyss --uid <UID>` exits 6 with `NO_RESULT` and no artifacts for the current no-floor data.
  - `.venv/bin/python -m gsuid_cli --request-id stage17f-theater-final --render image challenge theater --uid <UID>`
- Stage 17f live artifacts:
  - `~/.gsuid-cli/artifacts/2026-05-02/stage17f-hard-image-v5/challenge-hard_102452098.png`
  - `~/.gsuid-cli/artifacts/2026-05-02/stage17f-theater-final/challenge-theater_102452098.png`
- Next intended substage: Stage 17g, port GenshinUID-style progress image
  renderers.

- Stage 17g status: completed.
- Stage 17g goal: port GenshinUID-style image rendering for the `progress`
  command group.
- Stage 17g result:
  - Add `progress completion --render image|both` using the shared
    GenshinUID-style player exploration/completion section.
  - Add `progress exploration --render image|both` using the GenshinUID old
    `查询探索` slider layout, including the `获得角色数` row and player-summary
    title avatar fallback logic.
  - Add `progress collection --render image|both` using the GenshinUID old
    `查询收集` slider layout.
  - Add `progress achievements --render image|both` using the GenshinUID
    `我的成就` category renderer layout and textures.
  - Add `progress gcg --render image|both` and
    `progress gcg-deck --render image|both` using the GenshinUID
    `七圣召唤` overview/deck renderer layouts and textures.
  - Keep `progress achievement-guide` and `progress commission-guide`
    data-only because they are guide/status lookups without compatible live
    renderer payloads.
  - Copy and attribute progress achievement, collection/exploration slider, and
    GCG textures from GenshinUID, and package them in wheel/sdist.
  - Match GenshinUID `get_color_bg` backgrounds and white-ring title avatars
    for the old collection/exploration and GCG-deck renderers.
- Stage 17g review:
  - Standalone review agent found three issues before commit; all were fixed:
    missing `获得角色数` row in exploration, ambiguous default GCG deck image
    metadata, and unclamped malformed achievement percentages.
- Stage 17g verification:
  - `.venv/bin/python -m pytest tests/test_challenge_progress_data.py::test_progress_render_images tests/test_meta_commands.py::test_meta_capabilities_lists_implemented_commands -q`
  - `.venv/bin/python -m pytest`
  - `.venv/bin/ruff check .`
  - `.venv/bin/ruff format --check .`
  - `.venv/bin/python scripts/generate_command_reference.py --check`
  - `git diff --check`
  - `.venv/bin/python -m build`
  - `.venv/bin/python -m gsuid_cli --request-id stage17g-completion-final --render image progress completion --uid <UID>`
  - `.venv/bin/python -m gsuid_cli --request-id stage17g-exploration-reviewfix --render image progress exploration --uid <UID>`
  - `.venv/bin/python -m gsuid_cli --request-id stage17g-collection-final --render image progress collection --uid <UID>`
  - `.venv/bin/python -m gsuid_cli --request-id stage17g-achievements-final --render image progress achievements --uid <UID>`
  - `.venv/bin/python -m gsuid_cli --request-id stage17g-gcg-final --render image progress gcg --uid <UID>`
  - `.venv/bin/python -m gsuid_cli --request-id stage17g-gcg-deck-reviewfix --render image progress gcg-deck --uid <UID>`
- Stage 17g live artifacts:
  - `~/.gsuid-cli/artifacts/2026-05-02/stage17g-completion-final/progress-completion_102452098.png`
  - `~/.gsuid-cli/artifacts/2026-05-02/stage17g-exploration-reviewfix/progress-exploration_102452098.png`
  - `~/.gsuid-cli/artifacts/2026-05-02/stage17g-collection-final/progress-collection_102452098.png`
  - `~/.gsuid-cli/artifacts/2026-05-02/stage17g-achievements-final/progress-achievements_102452098.png`
  - `~/.gsuid-cli/artifacts/2026-05-02/stage17g-gcg-final/progress-gcg_102452098.png`
  - `~/.gsuid-cli/artifacts/2026-05-02/stage17g-gcg-deck-reviewfix/progress-gcg-deck_102452098.png`
- Next intended substage: Stage 17h, select the next remaining GenshinUID image
  renderer group from PLAN coverage.

## MVP Cut Line

The first usable MVP is complete after Stage 6 if these commands work:

```text
gsuid meta version
gsuid meta capabilities
gsuid profile init
gsuid account add
gsuid auth cookie set
gsuid auth cookie test
gsuid wiki character
gsuid wiki weapon
gsuid events list
gsuid codes list
gsuid daily materials
gsuid daily note
gsuid player summary
gsuid player characters
```

MVP success criteria:

- Every implemented command returns the JSON envelope.
- Missing auth produces exit code 2 and `AUTH_REQUIRED`.
- Invalid options produce exit code 1 and `INVALID_ARGUMENT`.
- Provider failures are not Python tracebacks unless `--debug` is used.
- Tests cover parser, envelope, errors, and provider mocks.

## User Decisions

- MVP is CN-only; overseas HoYoLAB support is later work.
- Keyring is mandatory; do not add plaintext local secret fallback.
- Rendered images should aim for visual parity with GenshinUID.
- Reusing GenshinUID assets/code is allowed when license-compatible and attributed.
- Agents call the CLI directly; no MCP server is planned for now, and high-quality help output is required.
