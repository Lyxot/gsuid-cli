from __future__ import annotations

import importlib.util
from pathlib import Path


def test_command_reference_is_generated() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "generate_command_reference.py"
    spec = importlib.util.spec_from_file_location("generate_command_reference", script)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    expected = module.render_command_reference()
    actual = (root / "docs" / "commands.md").read_text(encoding="utf-8")

    assert actual == expected
