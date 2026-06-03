from __future__ import annotations

import argparse
import io

from gsuid_cli.cli import build_parser, run
from gsuid_cli.commands.meta import capabilities_command


def test_every_parser_path_has_working_help() -> None:
    for path, parser in _parser_paths(build_parser()):
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run([*path, "--help"], stdout=stdout, stderr=stderr)

        help_text = stdout.getvalue()
        assert code == 0, path
        assert stderr.getvalue() == "", path
        assert "usage: gsuid" in help_text, path
        assert not help_text.lstrip().startswith("{"), path
        for option in _visible_options(parser):
            assert option in help_text, (path, option)
        for child in _child_names(parser):
            assert child in help_text, (path, child)


def test_incomplete_parser_paths_show_help() -> None:
    for path, parser in _parser_paths(build_parser()):
        if not _child_names(parser):
            continue
        if parser.get_default("handler") is not None:
            continue
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(path, stdout=stdout, stderr=stderr)

        usage = "usage: gsuid"
        if path:
            usage = f"{usage} {' '.join(path)}"
        assert code == 0, path
        assert stderr.getvalue() == "", path
        assert usage in stdout.getvalue(), path


def test_qrcode_legacy_app_id_is_hidden_from_help() -> None:
    for path in (
        ("auth", "qrcode", "poll"),
        ("auth", "qrcode", "complete"),
    ):
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run([*path, "--help"], stdout=stdout, stderr=stderr)

        assert code == 0
        assert stderr.getvalue() == ""
        assert "--app-id" not in stdout.getvalue()


def test_capabilities_have_matching_help_paths() -> None:
    parsers_by_path = {tuple(path): parser for path, parser in _parser_paths(build_parser())}
    missing = []
    mismatched = []

    for command in capabilities_command(argparse.Namespace(render="data"))["commands"]:
        command_name = str(command["command"])
        path = tuple(command_name.split("."))
        parser = parsers_by_path.get(path)
        if parser is None:
            missing.append(command_name)
            continue
        if parser.get_default("command_name") != command_name:
            mismatched.append(command_name)

    assert missing == []
    assert mismatched == []


def test_visible_parser_entries_have_help_text() -> None:
    missing = []
    for path, parser in _parser_paths(build_parser()):
        if not parser.description:
            missing.append((*path, "<description>"))
        for action in parser._actions:
            if isinstance(action, argparse._HelpAction):
                continue
            if isinstance(action, argparse._SubParsersAction):
                missing.extend(
                    (*path, choice.dest) for choice in action._choices_actions if not choice.help
                )
                continue
            if action.help in {None, ""}:
                label = action.option_strings[-1] if action.option_strings else action.dest
                missing.append((*path, label))

    assert missing == []


def _parser_paths(
    parser: argparse.ArgumentParser,
    path: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], argparse.ArgumentParser]]:
    paths = [(path, parser)]
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for name, child in action.choices.items():
            paths.extend(_parser_paths(child, (*path, name)))
    return paths


def _visible_options(parser: argparse.ArgumentParser) -> list[str]:
    options = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            continue
        if action.help == argparse.SUPPRESS:
            continue
        options.extend(action.option_strings)
    return options


def _child_names(parser: argparse.ArgumentParser) -> list[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return list(action.choices)
    return []
