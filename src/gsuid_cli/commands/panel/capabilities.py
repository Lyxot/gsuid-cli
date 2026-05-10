from __future__ import annotations

from gsuid_cli.commands._text import helps_from

PANEL_IMAGE_WORKERS = 12

CAPABILITIES = [
    {
        "command": "panel.refresh",
        "description": "刷新面板数据。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "panel.list",
        "description": "列出已缓存的面板。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "panel.show",
        "description": "显示一个已缓存的面板。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "panel.compare",
        "description": "对比已缓存的面板。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "panel.save",
        "description": "保存已缓存面板的 JSON 产物。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "panel.artifacts",
        "description": "列出已缓存的圣遗物。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "panel.showcase",
        "description": "显示已缓存的展柜汇总。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "panel.graduation",
        "description": "汇总本地毕业度数据。",
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
]

_HELPS = helps_from(CAPABILITIES)
