from __future__ import annotations

from gsuid_cli.text.zh_cn import TEXT_ZH_CN

TEXT: dict[str, str] = TEXT_ZH_CN


def t(key: str, *args: object, **kwargs: object) -> str:
    value = TEXT[key]
    if args or kwargs:
        return value.format(*args, **kwargs)
    return value
