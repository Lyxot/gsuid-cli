# gsuid-cli

`gsuid` is an agent-oriented CLI for Genshin Impact account and public data. The
current implementation is a project skeleton with JSON envelopes and meta
commands.

## Development

Install the package into the repository-local virtual environment:

```sh
.venv/bin/python -m pip install -e ".[dev]"
```

Run the available commands:

```sh
.venv/bin/python -m gsuid_cli meta version
.venv/bin/python -m gsuid_cli meta paths
.venv/bin/python -m gsuid_cli meta capabilities
```

Validate the skeleton:

```sh
.venv/bin/python -m pytest
.venv/bin/ruff check .
```

