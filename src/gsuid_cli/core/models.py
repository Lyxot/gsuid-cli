from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CommandResult:
    data: dict[str, object]
    source: dict[str, object] | None = None
    warnings: list[str] = field(default_factory=list)
    artifacts: list[dict[str, object]] = field(default_factory=list)
    pagination: dict[str, object] | None = None
