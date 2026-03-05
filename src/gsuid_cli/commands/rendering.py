from __future__ import annotations

import argparse
from collections.abc import Callable

from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.models import CommandResult

Renderer = Callable[[dict[str, object]], bytes]


def maybe_render_image(
    args: argparse.Namespace,
    result: CommandResult,
    *,
    renderer: Renderer,
    name: str,
    filename: str,
    description: str,
) -> CommandResult:
    if args.render == "data":
        return result
    artifact = ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name=name,
        filename=filename,
        media_type="image/png",
        content=renderer(result.data),
        description=description,
        kind="image",
    )
    return CommandResult(
        data=result.data,
        source=result.source,
        warnings=result.warnings,
        artifacts=[*result.artifacts, artifact],
        pagination=result.pagination,
    )
