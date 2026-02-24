from __future__ import annotations

import pytest

from gsuid_cli.cli import build_parser
from gsuid_cli.core.errors import CliError


def test_parser_accepts_global_options_for_meta_version() -> None:
    args = build_parser().parse_args(["--request-id", "req-1", "--region", "cn", "meta", "version"])

    assert args.command_name == "meta.version"
    assert args.request_id == "req-1"
    assert args.region == "cn"


def test_parser_help_lists_meta_commands() -> None:
    help_text = build_parser().format_help()

    assert "meta" in help_text
    assert "--request-id" in help_text


def test_parser_errors_use_cli_error() -> None:
    with pytest.raises(CliError) as exc:
        build_parser().parse_args(["meta", "missing"])

    assert exc.value.code == "INVALID_ARGUMENT"
    assert exc.value.exit_code == 1
