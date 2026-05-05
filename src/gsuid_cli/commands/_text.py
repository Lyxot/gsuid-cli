from __future__ import annotations

import argparse
import hashlib
import re
from collections.abc import Mapping

from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.render import render_result_data, render_text_enabled


def command_text_result(
    args: argparse.Namespace,
    result: CommandResult | Mapping[str, object],
    *,
    name: str,
    filename: str,
    content: str,
    description: str,
) -> CommandResult | Mapping[str, object]:
    if not render_text_enabled(args):
        return result

    command_result = (
        result if isinstance(result, CommandResult) else CommandResult(data=dict(result))
    )
    text_artifact = ArtifactManager(args.request_id, args.output_dir).write_text(
        name=name,
        filename=filename,
        content=content,
        description=description,
        kind="text",
    )
    data = render_result_data(
        args,
        command_result.data,
        {"render": name, "artifact_sha256": text_artifact["sha256"]},
    )
    return CommandResult(
        data=data,
        artifacts=[*command_result.artifacts, text_artifact],
        source=command_result.source,
        warnings=command_result.warnings,
        pagination=command_result.pagination,
    )


def safe_filename_part(value: object) -> str:
    raw = str(value or "result").strip()
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")
    if safe:
        return safe[:80]
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
