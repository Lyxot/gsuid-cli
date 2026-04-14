# gsuid-cli

`gsuid` is an agent-oriented CLI for Genshin Impact account, public data,
panel, gacha-log, and event workflows. It is CN-only for the current MVP.

The stable contract is JSON on stdout. Warnings, progress, and human scan
instructions go to stderr. Files such as rendered images, map images, and
exports are written to disk and returned as absolute artifact paths in the JSON
envelope.

Image rendering is being reworked for GenshinUID visual parity. During the
temporary Stage 17 port, `meta capabilities` is the source of truth for which
commands currently return image artifacts.

## Install For Development

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

Use the local virtual environment for all commands:

```sh
.venv/bin/python -m gsuid_cli meta version
.venv/bin/python -m gsuid_cli meta paths
.venv/bin/python -m gsuid_cli meta capabilities
```

The console script is also installed as:

```sh
.venv/bin/gsuid meta version
```

## Quickstart

Create local profile/account state:

```sh
.venv/bin/python -m gsuid_cli profile init --name default --region cn
.venv/bin/python -m gsuid_cli account add --uid <UID> --region cn
.venv/bin/python -m gsuid_cli account default --uid <UID>
```

Login with QR code and store credentials in the OS keyring:

```sh
.venv/bin/python -m gsuid_cli auth qrcode login --uid <UID>
```

Run public commands without credentials:

```sh
.venv/bin/python -m gsuid_cli wiki character --name Amber
.venv/bin/python -m gsuid_cli daily materials
.venv/bin/python -m gsuid_cli codes list
```

Run authenticated commands after login:

```sh
.venv/bin/python -m gsuid_cli daily note --uid <UID>
.venv/bin/python -m gsuid_cli player summary --uid <UID>
.venv/bin/python -m gsuid_cli player diary --uid <UID>
```

Global options can be placed before, between, or after command tokens:

```sh
.venv/bin/python -m gsuid_cli meta version --format pretty-json
.venv/bin/python -m gsuid_cli player summary --uid <UID> --timeout 30
```

Run agent batch mode with JSONL input:

```sh
printf '%s\n' \
  '{"id":"version","argv":["meta","version"]}' \
  '{"id":"paths","command":"meta paths"}' \
  | .venv/bin/python -m gsuid_cli --request-id batch-1 batch run --file -
```

## Output Contract

Successful JSON output uses the envelope:

```json
{
  "ok": true,
  "schema": "gsuid.cli/v1",
  "command": "meta.version",
  "request_id": "req",
  "generated_at": "2026-04-29T10:30:00Z",
  "duration_ms": 5,
  "warnings": [],
  "data": {},
  "artifacts": [],
  "source": {"provider": "local", "region": "cn", "cached": false, "fetched_at": "2026-04-29T10:30:00Z"},
  "pagination": null
}
```

On failure, JSON mode still writes a JSON error envelope to stdout and exits
non-zero.

Useful metadata commands:

```sh
.venv/bin/python -m gsuid_cli meta capabilities
.venv/bin/python -m gsuid_cli meta schema --command daily.note
.venv/bin/python -m gsuid_cli meta errors
```

## Documentation

- [Command reference](docs/commands.md)
- [Credential safety](docs/credential-safety.md)
- [Project plan](PLAN.md)

Regenerate command docs after capability changes:

```sh
.venv/bin/python scripts/generate_command_reference.py
.venv/bin/python scripts/generate_command_reference.py --check
```

## Verification

```sh
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python scripts/generate_command_reference.py --check
```

Build check:

```sh
.venv/bin/python -m pip install build
.venv/bin/python -m build
```
