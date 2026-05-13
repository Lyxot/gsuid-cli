from __future__ import annotations

from gsuid_cli.commands._text import helps_from
from gsuid_cli.text import t as _t

PANEL_IMAGE_WORKERS = 12

CAPABILITIES = [
    {
        "command": "panel.refresh",
        "description": _t("gsuid.commands.panel.capabilities.10_23.a1e6f01f"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "panel.list",
        "description": _t("gsuid.commands.panel.capabilities.17_23.e20c0ff0"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "panel.show",
        "description": _t("gsuid.commands.panel.capabilities.24_23.0187599f"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "panel.compare",
        "description": _t("gsuid.commands.panel.capabilities.31_23.1c731316"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "panel.save",
        "description": _t("gsuid.commands.panel.capabilities.38_23.fe665f48"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "text", "all"],
    },
    {
        "command": "panel.artifacts",
        "description": _t("gsuid.commands.panel.capabilities.45_23.dfd8b31a"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "panel.showcase",
        "description": _t("gsuid.commands.panel.capabilities.52_23.b03ff5ce"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
    {
        "command": "panel.graduation",
        "description": _t("gsuid.commands.panel.capabilities.59_23.efc5375b"),
        "auth": "none",
        "regions": ["cn"],
        "render": ["data", "image", "text", "all"],
    },
]

_HELPS = helps_from(CAPABILITIES)
