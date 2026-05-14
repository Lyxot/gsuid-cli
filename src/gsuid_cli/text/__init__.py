from __future__ import annotations

import locale
import os
from collections.abc import Mapping

from gsuid_cli.core.config import ConfigError, load_cli_defaults, normalize_language
from gsuid_cli.text.en import TEXT_EN
from gsuid_cli.text.zh_cn import TEXT_ZH_CN

DEFAULT_LANGUAGE = "zh-cn"
SUPPORTED_LANGUAGES = ("zh-cn", "en")
_CATALOGS: dict[str, Mapping[str, str]] = {
    "zh-cn": TEXT_ZH_CN,
    "en": TEXT_EN,
}
TEXT: Mapping[str, str] = TEXT_ZH_CN


def language() -> str:
    selected = _environment_language(("GSUID_LANG", "GSUID_LANGUAGE"))
    if selected and selected != "auto":
        return selected

    configured = None if selected == "auto" else _configured_language()
    if configured and configured != "auto":
        return configured

    selected = _environment_language(("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"))
    if selected and selected != "auto":
        return selected

    try:
        selected = normalize_language(locale.getlocale()[0])
    except ValueError:
        selected = None
    return selected or DEFAULT_LANGUAGE


def catalog() -> Mapping[str, str]:
    return _CATALOGS[language()]


def t(key: str, *args: object, **kwargs: object) -> str:
    value = catalog().get(key, TEXT_ZH_CN[key])
    if args or kwargs:
        return value.format(*args, **kwargs)
    return value


def _configured_language() -> str | None:
    try:
        return load_cli_defaults().language
    except ConfigError:
        return None


def _environment_language(names: tuple[str, ...]) -> str | None:
    for name in names:
        selected = normalize_language(os.environ.get(name))
        if selected:
            return selected
    return None
