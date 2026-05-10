"""Player command group: profile, summary, calendar, inventory, characters."""

from __future__ import annotations

from gsuid_cli.commands.player.impl import CAPABILITIES, register

__all__ = ["CAPABILITIES", "register"]
