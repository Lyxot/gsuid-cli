from __future__ import annotations

import argparse
import hashlib
import re
from collections.abc import Callable, Mapping

from gsuid_cli.core.artifacts import ArtifactManager
from gsuid_cli.core.errors import EXIT_UPSTREAM, CliError
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
    has_image = any(artifact.get("kind") == "image" for artifact in command_result.artifacts)
    if has_image:
        data = {**command_result.data, "text_artifact_sha256": text_artifact["sha256"]}
    else:
        data = render_result_data(
            args,
            command_result.data,
            {"render": name, "artifact_sha256": text_artifact["sha256"]},
        )
    return CommandResult(
        data=data,
        artifacts=[*command_result.artifacts, text_artifact],
        source=command_result.source,
        sources=command_result.sources,
        warnings=command_result.warnings,
        pagination=command_result.pagination,
    )


def write_text_artifact(
    args: argparse.Namespace,
    *,
    name: str,
    filename: str,
    content: str,
    description: str,
) -> dict[str, object]:
    """Write a text artifact via ArtifactManager and return its descriptor."""
    return ArtifactManager(args.request_id, args.output_dir).write_text(
        name=name,
        filename=filename,
        content=content,
        description=description,
        kind="text",
    )


def write_image_artifact(
    args: argparse.Namespace,
    *,
    name: str,
    filename: str,
    content: bytes,
    description: str,
    media_type: str = "image/png",
) -> dict[str, object]:
    """Write a raster (or other bytes) image artifact and return its descriptor."""
    return ArtifactManager(args.request_id, args.output_dir).write_bytes(
        name=name,
        filename=filename,
        media_type=media_type,
        content=content,
        description=description,
        kind="image",
    )


def record_primary_image(
    render_data: dict[str, object],
    image_artifact: Mapping[str, object],
) -> None:
    """Set JSON ``render`` / ``artifact_sha256`` for the primary image output."""
    render_data["render"] = str(image_artifact["name"])
    render_data["artifact_sha256"] = image_artifact["sha256"]


def record_text_artifact(
    render_data: dict[str, object],
    text_artifact: Mapping[str, object],
    *,
    image_enabled: bool,
) -> None:
    """Merge a text artifact into ``render_data`` for dual-render flows.

    When an image artifact is already present, only the ``text_artifact_sha256``
    field is added (so the primary render keys remain pointing at the image).
    Otherwise the text artifact becomes the primary render and contributes both
    ``render`` and ``artifact_sha256``.
    """
    if image_enabled:
        render_data["text_artifact_sha256"] = text_artifact["sha256"]
        return
    render_data.update(
        {
            "render": text_artifact["name"],
            "artifact_sha256": text_artifact["sha256"],
        }
    )


def safe_filename_part(value: object) -> str:
    raw = str(value or "result").strip()
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")
    if safe:
        return safe[:80]
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def helps_from(capabilities: list[dict[str, object]]) -> dict[str, str]:
    return {str(c["command"]): str(c["description"]) for c in capabilities}


def command_subject_text_result(
    args: argparse.Namespace,
    result: CommandResult | Mapping[str, object],
    *,
    subject: object,
    render_fn: Callable[[str, Mapping[str, object]], str],
    description: str,
) -> CommandResult | Mapping[str, object]:
    """Wrap command_text_result, deriving name/filename from args.command_name.

    Use when the command produces a single text artifact whose name follows the
    convention ``<group>/<action>-text`` and filename ``<group>-<action>_<subject>.txt``.
    Commands with non-conforming naming (e.g. nested verbs like auth.cookie.set)
    should call command_text_result directly.
    """
    command = str(getattr(args, "command_name", ""))
    group = command.split(".", 1)[0] or "result"
    action = command.rsplit(".", 1)[-1]
    data = result.data if isinstance(result, CommandResult) else dict(result)
    return command_text_result(
        args,
        result,
        name=f"{group}/{action}-text",
        filename=f"{group}-{action}_{safe_filename_part(subject)}.txt",
        content=render_fn(command, data),
        description=description,
    )


def mapping_data(result: CommandResult, field: str, command: str) -> Mapping[str, object]:
    value = result.data.get(field)
    if isinstance(value, Mapping):
        return value
    raise CliError(
        "UPSTREAM_INVALID_RESPONSE",
        f"Provider returned {command} data without a renderable {field}.",
        EXIT_UPSTREAM,
        {"command": command, "field": field},
        source=result.source,
    )
