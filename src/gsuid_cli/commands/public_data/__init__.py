from __future__ import annotations

import argparse

from gsuid_cli.commands.public_data.daily import (
    CAPABILITIES as _DAILY_CAPS,
)
from gsuid_cli.commands.public_data.daily import (
    daily_bbs_coin_command,
    daily_materials_command,
    daily_note_command,
    daily_signin_command,
)
from gsuid_cli.commands.public_data.daily import (
    register as _register_daily,
)
from gsuid_cli.commands.public_data.events import (
    CAPABILITIES as _EVENTS_CAPS,
)
from gsuid_cli.commands.public_data.events import (
    announcements_list_command,
    announcements_show_command,
    codes_list_command,
    events_banners_command,
    events_list_command,
)
from gsuid_cli.commands.public_data.events import (
    register_announcements as _register_announcements,
)
from gsuid_cli.commands.public_data.events import (
    register_codes as _register_codes,
)
from gsuid_cli.commands.public_data.events import (
    register_events as _register_events,
)
from gsuid_cli.commands.public_data.guide import (
    CAPABILITIES as _GUIDE_CAPS,
)
from gsuid_cli.commands.public_data.guide import (
    guide_abyss_command,
    guide_character_command,
    guide_route_command,
    guide_theater_command,
    map_find_command,
    primogems_plan_command,
    recommend_build_command,
    recommend_holder_command,
    reference_panel_command,
    rerun_list_command,
)
from gsuid_cli.commands.public_data.guide import (
    register_guides as _register_guides,
)
from gsuid_cli.commands.public_data.guide import (
    register_map as _register_map,
)
from gsuid_cli.commands.public_data.guide import (
    register_misc as _register_misc,
)
from gsuid_cli.commands.public_data.guide import (
    register_recommend as _register_recommend,
)
from gsuid_cli.commands.public_data.guide import (
    register_rerun as _register_rerun,
)
from gsuid_cli.commands.public_data.wiki import (
    CAPABILITIES as _WIKI_CAPS,
)
from gsuid_cli.commands.public_data.wiki import (
    character_materials_command,
    constellation_command,
    talent_command,
    weapon_materials_command,
    wiki_command,
)
from gsuid_cli.commands.public_data.wiki import (
    register as _register_wiki,
)

CAPABILITIES = [
    *_WIKI_CAPS,
    *_EVENTS_CAPS,
    *_DAILY_CAPS,
    *_GUIDE_CAPS,
]

__all__ = [
    "CAPABILITIES",
    "register",
    "wiki_command",
    "talent_command",
    "constellation_command",
    "character_materials_command",
    "weapon_materials_command",
    "events_list_command",
    "events_banners_command",
    "codes_list_command",
    "daily_materials_command",
    "daily_note_command",
    "daily_signin_command",
    "daily_bbs_coin_command",
    "guide_character_command",
    "reference_panel_command",
    "guide_route_command",
    "guide_abyss_command",
    "guide_theater_command",
    "recommend_build_command",
    "recommend_holder_command",
    "announcements_list_command",
    "announcements_show_command",
    "map_find_command",
    "rerun_list_command",
    "primogems_plan_command",
]


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    _register_wiki(groups)
    _register_events(groups)
    _register_codes(groups)
    _register_daily(groups)
    _register_guides(groups)
    _register_recommend(groups)
    _register_announcements(groups)
    _register_map(groups)
    _register_rerun(groups)
    _register_misc(groups)
