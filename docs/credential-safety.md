# Credential Safety

`gsuid` handles cookies, stokens, gacha authkey URLs, QR login tickets, and
derived tokens. Treat all of them as secrets.

## Storage Rules

- Stored credentials must use the operating-system keyring.
- The CLI does not provide a plaintext credential fallback.
- If keyring access fails, credential read/write commands fail with
  `KEYRING_UNAVAILABLE`.
- One-shot environment variables may supply credentials for a single command,
  but they are not persisted.

Supported one-shot variables:

```text
GSUID_COOKIE
GSUID_STOKEN
GSUID_GACHA_URL
```

## Redaction Rules

The CLI must not print full cookies, stokens, gacha authkey URLs, game tokens,
QR tickets, or URLs containing authkey query parameters. Success output may
include redacted previews and storage status.

Do not paste full secrets into issues, logs, commits, screenshots, or batch
files. Prefer QR login or environment variables for local testing.

## Recommended Login Flow

Use interactive QR login when possible:

```sh
.venv/bin/python -m gsuid_cli auth qrcode login --uid <UID>
```

This prints scan instructions to stderr, returns one JSON envelope on stdout,
and stores cookie/stoken credentials in keyring.

Manual QR flow is also available for non-interactive orchestration:

```sh
.venv/bin/python -m gsuid_cli --render both auth qrcode start
.venv/bin/python -m gsuid_cli auth qrcode poll --app-id APP --ticket TICKET --device DEVICE
.venv/bin/python -m gsuid_cli auth qrcode complete --uid <UID> --app-id APP --ticket TICKET --device DEVICE
```

The ticket expires quickly. For humans, prefer `auth qrcode login` so polling
starts immediately after the QR code is shown.

## Batch Files

Batch files can invoke authenticated commands. Avoid embedding secrets in batch
input. Reference stored credentials through profile/account state, or pass
short-lived secrets through environment variables outside the JSONL file.

Bad:

```json
{"argv":["auth","cookie","set","--uid","<UID>","--cookie","secret"]}
```

Good:

```json
{"argv":["daily","note","--uid","<UID>"],"request_id":"daily-1"}
```

## Local Files

Default local state is under `$GSUID_HOME`, or `~/.gsuid-cli` when unset:

```text
config.toml
state.sqlite
cache/
artifacts/
logs/
```

The SQLite state file stores non-secret account/profile metadata. Artifacts can
include rendered account data, exported gacha logs, and map images; treat the
artifact directory as local private data.
