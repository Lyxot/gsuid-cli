from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_DEFAULT_KEYS = {
    "profile",
    "region",
    "format",
    "render",
    "output_dir",
    "cache",
    "timeout",
    "quiet",
    "debug",
    "language",
}
SUPPORTED_LANGUAGES = ("auto", "zh-cn", "en")


class ConfigError(ValueError):
    def __init__(self, message: str, *, path: Path) -> None:
        super().__init__(message)
        self.path = path


@dataclass(frozen=True)
class CliDefaults:
    profile: str = "default"
    region: str = "auto"
    format: str = "json"
    render: tuple[str, ...] | None = None
    output_dir: str | None = None
    cache: str = "use"
    timeout: float = 20.0
    quiet: bool = False
    debug: bool = False
    language: str = "auto"


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


def load_cli_defaults() -> CliDefaults:
    path = resolve_paths().config
    if not path.exists():
        return CliDefaults()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{path}: {exc}", path=path) from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}", path=path) from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: root must be a TOML table", path=path)
    unknown_sections = set(raw) - {"defaults"}
    if unknown_sections:
        keys = ", ".join(sorted(str(key) for key in unknown_sections))
        raise ConfigError(f"{path}: unknown section: {keys}", path=path)
    defaults = raw.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ConfigError(f"{path}: [defaults] must be a table", path=path)
    unknown_keys = set(defaults) - CONFIG_DEFAULT_KEYS
    if unknown_keys:
        keys = ", ".join(sorted(str(key) for key in unknown_keys))
        raise ConfigError(f"{path}: unknown [defaults] key: {keys}", path=path)
    return CliDefaults(
        profile=_string_default(defaults, "profile", "default", path=path),
        region=_string_default(defaults, "region", "auto", path=path),
        format=_string_default(defaults, "format", "json", path=path),
        render=_render_default(defaults.get("render"), path=path),
        output_dir=_path_default(defaults.get("output_dir"), base=path.parent, path=path),
        cache=_string_default(defaults, "cache", "use", path=path),
        timeout=_timeout_default(defaults.get("timeout"), path=path),
        quiet=_bool_default(defaults, "quiet", False, path=path),
        debug=_bool_default(defaults, "debug", False, path=path),
        language=_language_default(defaults.get("language"), path=path),
    )


def _path(value: str | None, default: Path) -> Path:
    raw = Path(value).expanduser() if value else default
    return raw.resolve()


def _string_default(
    values: dict[str, Any],
    key: str,
    fallback: str,
    *,
    path: Path,
) -> str:
    value = values.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path}: [defaults].{key} must be a non-empty string", path=path)
    return value


def _render_default(value: object, *, path: Path) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        parts = tuple(part.strip() for part in value.split(",") if part.strip())
    elif isinstance(value, list):
        parts = tuple(_render_part(part, path=path) for part in value)
    else:
        raise ConfigError(f"{path}: [defaults].render must be a string or string list", path=path)
    if not parts:
        raise ConfigError(f"{path}: [defaults].render must not be empty", path=path)
    return parts


def _render_part(value: object, *, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(
            f"{path}: [defaults].render entries must be non-empty strings",
            path=path,
        )
    return value.strip()


def _path_default(value: object, *, base: Path, path: Path) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path}: [defaults].output_dir must be a non-empty string", path=path)
    raw = Path(value).expanduser()
    if not raw.is_absolute():
        raw = base / raw
    return str(raw.resolve())


def _timeout_default(value: object, *, path: Path) -> float:
    if value is None:
        return 20.0
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"{path}: [defaults].timeout must be a number", path=path)
    timeout = float(value)
    if timeout <= 0:
        raise ConfigError(f"{path}: [defaults].timeout must be greater than 0", path=path)
    return timeout


def _bool_default(
    values: dict[str, Any],
    key: str,
    fallback: bool,
    *,
    path: Path,
) -> bool:
    value = values.get(key, fallback)
    if not isinstance(value, bool):
        raise ConfigError(f"{path}: [defaults].{key} must be a boolean", path=path)
    return value


def _language_default(value: object, *, path: Path) -> str:
    if value is None:
        return "auto"
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path}: [defaults].language must be a non-empty string", path=path)
    language = normalize_language(value)
    if language is None:
        allowed = ", ".join(SUPPORTED_LANGUAGES)
        raise ConfigError(
            f"{path}: [defaults].language must be one of: {allowed}",
            path=path,
        )
    return language


def normalize_language(value: str | None) -> str | None:
    if not value:
        return None
    for raw_token in value.split(":"):
        token = raw_token.split(".", maxsplit=1)[0].strip().replace("_", "-").lower()
        if not token or token in {"c", "posix"}:
            continue
        if token == "auto":
            return "auto"
        if token.startswith("zh"):
            return "zh-cn"
        if token.startswith("en"):
            return "en"
    return None
