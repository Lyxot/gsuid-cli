from __future__ import annotations

import locale
import os
from collections.abc import Mapping

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
    for name in ("GSUID_LANG", "GSUID_LANGUAGE"):
        selected = _language_from_value(os.environ.get(name))
        if selected:
            return selected

    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        selected = _language_from_value(os.environ.get(name))
        if selected:
            return selected

    try:
        selected = _language_from_value(locale.getlocale()[0])
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


def _language_from_value(value: str | None) -> str | None:
    if not value:
        return None
    for raw_token in value.split(":"):
        token = raw_token.split(".", maxsplit=1)[0].strip().replace("_", "-").lower()
        if not token or token in {"c", "posix"}:
            continue
        if token.startswith("zh"):
            return "zh-cn"
        if token.startswith("en"):
            return "en"
    return None
