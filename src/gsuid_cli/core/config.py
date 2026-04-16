from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    home: Path
    config: Path
    state: Path
    data: Path
    cache: Path
    cache_assets: Path
    artifacts: Path
    logs: Path

    def to_json(self) -> dict[str, str]:
        return {
            "home": str(self.home),
            "config": str(self.config),
            "state": str(self.state),
            "data": str(self.data),
            "cache": str(self.cache),
            "cache_assets": str(self.cache_assets),
            "artifacts": str(self.artifacts),
            "logs": str(self.logs),
        }


def resolve_paths(output_dir: str | None = None) -> RuntimePaths:
    home = _path(os.environ.get("GSUID_HOME"), Path.home() / ".gsuid-cli")
    artifacts = _path(output_dir or os.environ.get("GSUID_OUTPUT_DIR"), home / "artifacts")
    cache = home / "cache"
    return RuntimePaths(
        home=home,
        config=home / "config.toml",
        state=home / "state.sqlite",
        data=home,
        cache=cache,
        cache_assets=cache / "assets",
        artifacts=artifacts,
        logs=home / "logs",
    )


def _path(value: str | None, default: Path) -> Path:
    raw = Path(value).expanduser() if value else default
    return raw.resolve()
