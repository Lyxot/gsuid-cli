from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gsuid_cli.commands.meta import capabilities_command  # noqa: E402

OUTPUT = ROOT / "docs" / "commands.md"


def render_command_reference() -> str:
    capabilities = capabilities_command(argparse.Namespace())["commands"]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for command in capabilities:
        group = str(command["command"]).split(".", 1)[0]
        grouped[group].append(command)

    lines = [
        "# 命令参考文档 (Command Reference)",
        "",
        "本文档由 `gsuid meta capabilities` 命令自动生成。",
        "",
        "| 命令 | 权限 | 渲染支持 | 描述 |",
        "| --- | --- | --- | --- |",
    ]
    for group in sorted(grouped):
        for command in sorted(grouped[group], key=lambda item: str(item["command"])):
            lines.append(
                "| `{command}` | `{auth}` | `{render}` | {description} |".format(
                    command=command["command"],
                    auth=command["auth"],
                    render=", ".join(command["render"]),
                    description=_escape_pipes(_description(command)),
                )
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate docs/commands.md.")
    parser.add_argument("--check", action="store_true", help="Fail if docs are not current.")
    args = parser.parse_args()
    content = render_command_reference()
    if args.check:
        existing = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if existing != content:
            print("docs/commands.md is out of date", file=sys.stderr)
            return 1
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding="utf-8")
    return 0


def _escape_pipes(value: str) -> str:
    return value.replace("|", "\\|")


def _description(command: dict[str, Any]) -> str:
    description = str(command["description"])
    coverage = command.get("coverage")
    if coverage:
        description += f" Coverage: `{coverage}`."
    availability = command.get("availability")
    if availability:
        description += f" 区服: `{availability}`."
    limitations = command.get("limitations")
    if isinstance(limitations, list) and limitations:
        description += " 限制: " + "; ".join(str(item) for item in limitations)
    return description


if __name__ == "__main__":
    raise SystemExit(main())
