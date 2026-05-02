from __future__ import annotations

from collections.abc import Iterable, Mapping

from gsuid_cli.core.errors import EXIT_INVALID_INPUT, CliError

RENDER_CHOICES = {"data", "image", "text", "all"}
EXPANDED_ALL = ("data", "image", "text")


def normalize_render_modes(value: object) -> list[str]:
    raw_values = _raw_values(value)
    modes: list[str] = []
    for raw in raw_values:
        for part in raw.split(","):
            mode = part.strip()
            if not mode:
                continue
            if mode not in RENDER_CHOICES:
                allowed = ", ".join(sorted(RENDER_CHOICES))
                raise CliError(
                    "INVALID_ARGUMENT",
                    f"argument --render: invalid choice: {mode!r} (choose from {allowed})",
                    EXIT_INVALID_INPUT,
                    {"render": mode},
                )
            if mode == "all":
                for expanded in EXPANDED_ALL:
                    if expanded not in modes:
                        modes.append(expanded)
                continue
            if mode not in modes:
                modes.append(mode)
    return modes or ["data"]


def render_data_enabled(args: object) -> bool:
    return "data" in normalize_render_modes(getattr(args, "render", None))


def render_image_enabled(args: object) -> bool:
    return "image" in normalize_render_modes(getattr(args, "render", None))


def render_text_enabled(args: object) -> bool:
    return "text" in normalize_render_modes(getattr(args, "render", None))


def render_result_data(
    args: object,
    original: Mapping[str, object],
    render_data: Mapping[str, object],
) -> dict[str, object]:
    if render_data_enabled(args):
        return {**original, **render_data}
    return dict(render_data)


def _raw_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value]
    return [str(value)]
