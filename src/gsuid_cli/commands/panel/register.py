from __future__ import annotations

import argparse

from gsuid_cli.commands.panel.capabilities import _HELPS
from gsuid_cli.commands.panel.impl import (
    artifacts_command,
    compare_command,
    graduation_command,
    list_command,
    refresh_command,
    save_command,
    show_command,
    showcase_command,
)
from gsuid_cli.text import t as _t


def register(groups: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    panel = groups.add_parser("panel", help=_t("gsuid.commands.panel.register.19_44.ecb09034"))
    commands = panel.add_subparsers(dest="panel_command", required=True, metavar="<command>")

    refresh = commands.add_parser("refresh", help=_HELPS["panel.refresh"])
    refresh.add_argument("--uid", dest="command_uid")
    refresh.add_argument("--source", choices=("auto", "enka", "mys"), default="auto")
    refresh.add_argument("--force", action="store_true")
    refresh.set_defaults(handler=refresh_command, command_name="panel.refresh")

    list_parser = commands.add_parser("list", help=_HELPS["panel.list"])
    list_parser.add_argument("--uid", dest="command_uid")
    list_parser.set_defaults(handler=list_command, command_name="panel.list")

    show = commands.add_parser("show", help=_HELPS["panel.show"])
    show.add_argument("--uid", dest="command_uid")
    show.add_argument("--character", required=True)
    show.add_argument("--constellation", type=int)
    show.add_argument("--weapon")
    show.add_argument("--artifact-source-character")
    show.set_defaults(handler=show_command, command_name="panel.show")

    compare = commands.add_parser("compare", help=_HELPS["panel.compare"])
    compare.add_argument("--uid", dest="command_uid")
    compare.add_argument("--build", action="append", required=True)
    compare.set_defaults(handler=compare_command, command_name="panel.compare")

    save = commands.add_parser("save", help=_HELPS["panel.save"])
    save.add_argument("--uid", dest="command_uid")
    save.add_argument("--character", required=True)
    save.add_argument("--name", required=True)
    save.add_argument("--output")
    save.set_defaults(handler=save_command, command_name="panel.save")

    artifacts = commands.add_parser("artifacts", help=_HELPS["panel.artifacts"])
    artifacts.add_argument("--uid", dest="command_uid")
    artifacts.add_argument("--page", type=int, default=1)
    artifacts.set_defaults(handler=artifacts_command, command_name="panel.artifacts")

    showcase = commands.add_parser("showcase", help=_HELPS["panel.showcase"])
    showcase.add_argument("--uid", dest="command_uid")
    showcase.set_defaults(handler=showcase_command, command_name="panel.showcase")

    graduation = commands.add_parser("graduation", help=_HELPS["panel.graduation"])
    graduation.add_argument("--uid", dest="command_uid")
    graduation.set_defaults(handler=graduation_command, command_name="panel.graduation")
