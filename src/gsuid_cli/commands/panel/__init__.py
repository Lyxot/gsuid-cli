"""Panel command group: Enka-backed local cache workflows."""

from __future__ import annotations

from gsuid_cli.commands.panel.capabilities import CAPABILITIES, PANEL_IMAGE_WORKERS
from gsuid_cli.commands.panel.register import register

__all__ = ["CAPABILITIES", "PANEL_IMAGE_WORKERS", "register"]
