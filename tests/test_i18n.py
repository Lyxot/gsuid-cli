from __future__ import annotations

import os
import re
import subprocess
import sys

from gsuid_cli import text
from gsuid_cli.core.config import normalize_language
from gsuid_cli.text.en import TEXT_EN
from gsuid_cli.text.zh_cn import TEXT_ZH_CN

PLACEHOLDER_RE = re.compile(r"\{[^{}]+\}")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
DOMAIN_TERM_EXPECTATIONS = {
    "gsuid.renderers.gacha.102_13.15819363": "Wish Summary - {0}",
    "gsuid.renderers.gacha.52_18.d1a59dd3": "Chronicled Wish",
    "gsuid.renderers.events.text.13_16.2a2b2bee": "Primogems",
    "gsuid.renderers.guide.text.100_62.619c6618": "Artifacts",
    "gsuid.renderers.progress.text.125_13.d0ff2562": "Genius Invokation TCG - {0}",
    "gsuid.renderers.daily.text.20_9.60582a7f": "Inazuma",
    "gsuid.renderers.daily.text.23_9.3fd1306d": "Natlan",
    "gsuid.renderers.daily.text.24_9.b6b55ca3": "Nod-Krai",
    "gsuid.renderers.player.summary.33_4.5bfde491": "The Chasm",
    "gsuid.renderers.player.summary.34_4.3d931c3a": "Enkanomiya",
    "gsuid.renderers.player.summary.44_4.59d5cc2a": "Anemoculus",
    "gsuid.renderers.daily.note.118_24.0c8c7f71": "Realm Currency",
    "gsuid.renderers.panel.text.102_8.c25d88de": (
        "Level: {0}, constellation: {1}, friendship: {2}"
    ),
    "gsuid.providers.akasha.70_4.33e0f20a": "CRIT Rate",
    "gsuid.providers.akasha.68_4.a7a24305": "Energy Recharge",
    "gsuid.renderers.challenge.abyss.162_33.5f63ce42": "Floor {0}",
    "gsuid.renderers.player.diary.28_4.15dd8ad7": "Imaginarium Theater",
    "gsuid.providers.mys.bbs.24_42.023e444c": "Honkai: Star Rail",
}


def test_english_catalog_matches_chinese_contract() -> None:
    assert set(TEXT_EN) == set(TEXT_ZH_CN)
    for key, zh_value in TEXT_ZH_CN.items():
        en_value = TEXT_EN[key]
        assert PLACEHOLDER_RE.findall(en_value) == PLACEHOLDER_RE.findall(zh_value), key
        assert not CJK_RE.search(en_value), key


def test_english_catalog_uses_genshin_domain_terms() -> None:
    for key, expected in DOMAIN_TERM_EXPECTATIONS.items():
        assert TEXT_EN[key] == expected


def test_explicit_environment_language_selects_english(monkeypatch) -> None:
    monkeypatch.setenv("GSUID_LANG", "en_US.UTF-8")

    assert text.language() == "en"
    assert text.t("gsuid.renderers.utility_text.21_16.4cb4e572") == "CLI Version"


def test_standard_locale_environment_selects_english(monkeypatch) -> None:
    _clear_language_environment(monkeypatch)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setattr(text, "_system_language", lambda: None)

    assert text.language() == "en"


def test_configured_language_selects_english(monkeypatch, tmp_path) -> None:
    _clear_language_environment(monkeypatch)
    monkeypatch.setattr(text, "_system_language", lambda: None)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GSUID_HOME", str(home))
    (home / "config.toml").write_text('[defaults]\nlanguage = "en"\n', encoding="utf-8")

    assert text.language() == "en"
    assert text.t("gsuid.renderers.utility_text.21_16.4cb4e572") == "CLI Version"


def test_auto_configured_language_uses_locale_environment(monkeypatch, tmp_path) -> None:
    _clear_language_environment(monkeypatch)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setattr(text, "_system_language", lambda: None)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GSUID_HOME", str(home))
    (home / "config.toml").write_text('[defaults]\nlanguage = "auto"\n', encoding="utf-8")

    assert text.language() == "en"


def test_explicit_language_environment_overrides_config(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GSUID_HOME", str(home))
    monkeypatch.setenv("GSUID_LANG", "zh-CN")
    (home / "config.toml").write_text('[defaults]\nlanguage = "en"\n', encoding="utf-8")

    assert text.language() == "zh-cn"


def test_explicit_auto_language_environment_skips_config(monkeypatch, tmp_path) -> None:
    _clear_language_environment(monkeypatch)
    monkeypatch.setenv("GSUID_LANG", "auto")
    monkeypatch.setenv("LANG", "C.UTF-8")
    monkeypatch.setattr(text, "_system_language", lambda: None)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GSUID_HOME", str(home))
    (home / "config.toml").write_text('[defaults]\nlanguage = "en"\n', encoding="utf-8")

    assert text.language() == "zh-cn"


def test_unsupported_environment_language_falls_back_to_chinese(monkeypatch) -> None:
    _clear_language_environment(monkeypatch)
    monkeypatch.setenv("LANG", "C.UTF-8")
    monkeypatch.setattr(text, "_system_language", lambda: None)

    assert text.language() == "zh-cn"
    assert text.t("gsuid.renderers.utility_text.21_16.4cb4e572") == "CLI版本"


def test_system_language_prefers_macos_preferred_languages(monkeypatch) -> None:
    monkeypatch.setattr(text.sys, "platform", "darwin")
    monkeypatch.setattr(text, "_macos_language", lambda: "zh-cn")

    assert text._system_language() == "zh-cn"


def test_language_normalization_uses_locale_parser() -> None:
    assert normalize_language("zh_Hans_CN.UTF-8") == "zh-cn"
    assert normalize_language("zh-Hans-US") == "zh-cn"
    assert normalize_language("en-Latn-US") == "en"
    assert normalize_language("enochian") is None
    assert normalize_language("fr-FR") is None


def test_invalid_configured_language_returns_config_error(monkeypatch, tmp_path) -> None:
    _clear_language_environment(monkeypatch)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("GSUID_HOME", str(home))
    (home / "config.toml").write_text('[defaults]\nlanguage = "fr"\n', encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "gsuid_cli", "meta", "version"],
        check=False,
        capture_output=True,
        env=_subprocess_env(home),
        text=True,
    )

    assert result.returncode == 1
    assert "INVALID_ARGUMENT" in result.stdout


def test_cli_process_uses_environment_language(monkeypatch, tmp_path) -> None:
    env = os.environ.copy()
    env["GSUID_LANG"] = "en"
    env["GSUID_HOME"] = str(tmp_path / "home")
    monkeypatch.setenv("GSUID_LANG", "zh-CN")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gsuid_cli",
            "meta",
            "version",
            "--render",
            "text",
            "--format",
            "plain",
        ],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert "CLI Version" in result.stdout
    assert "CLI版本" not in result.stdout


def test_cli_process_uses_configured_language(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text('[defaults]\nlanguage = "en"\n', encoding="utf-8")
    monkeypatch.setenv("GSUID_LANG", "zh-CN")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gsuid_cli",
            "meta",
            "version",
            "--render",
            "text",
            "--format",
            "plain",
        ],
        check=False,
        capture_output=True,
        env=_subprocess_env(home),
        text=True,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert "CLI Version" in result.stdout
    assert "CLI版本" not in result.stdout


def _clear_language_environment(monkeypatch) -> None:
    for name in ("GSUID_LANG", "GSUID_LANGUAGE", "LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)


def _subprocess_env(home) -> dict[str, str]:
    env = os.environ.copy()
    env["GSUID_HOME"] = str(home)
    env["LANG"] = "C.UTF-8"
    for name in ("GSUID_LANG", "GSUID_LANGUAGE", "LANGUAGE", "LC_ALL", "LC_MESSAGES"):
        env.pop(name, None)
    return env
