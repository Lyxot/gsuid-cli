from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

from PIL import Image

from gsuid_cli.cli import run
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.secrets import SecretStore


def test_daily_note_render_writes_png_artifact(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")
    monkeypatch.setattr("gsuid_cli.commands.public_data.provider_for_region", _provider)
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(
        [
            "--request-id",
            "daily-render",
            "--render",
            "image",
            "--output-dir",
            str(tmp_path / "artifacts"),
            "daily",
            "note",
            "--uid",
            "100000001",
        ]
    )

    assert code == 0
    assert payload["command"] == "daily.note"
    _assert_png_artifact(payload, (960, 540), tmp_path / "artifacts", "daily-render")


def test_abyss_render_writes_png_artifact(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")
    monkeypatch.setattr("gsuid_cli.commands.challenge.provider_for_region", _provider)
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(
        [
            "--request-id",
            "abyss-render",
            "--render",
            "both",
            "--output-dir",
            str(tmp_path / "artifacts"),
            "challenge",
            "abyss",
            "--uid",
            "100000001",
        ]
    )

    assert code == 0
    assert payload["command"] == "challenge.abyss"
    assert payload["data"]["abyss"]["total_star"] == 36
    _assert_png_artifact(payload, (960, 540), tmp_path / "artifacts", "abyss-render")


def test_panel_show_render_writes_png_artifact(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")
    monkeypatch.setattr("gsuid_cli.commands.panel.EnkaProvider", FakeEnkaProvider)

    code, _payload = _run_json(["panel", "refresh", "--uid", "100000001"])
    assert code == 0

    code, payload = _run_json(
        [
            "--request-id",
            "panel-render",
            "--render",
            "image",
            "--output-dir",
            str(tmp_path / "artifacts"),
            "panel",
            "show",
            "--uid",
            "100000001",
            "--character",
            "Amber",
        ]
    )

    assert code == 0
    assert payload["command"] == "panel.show"
    _assert_png_artifact(payload, (1080, 720), tmp_path / "artifacts", "panel-render")


def _assert_png_artifact(
    payload: dict[str, object],
    size: tuple[int, int],
    output_dir: Path,
    request_id: str,
) -> None:
    artifacts = payload["artifacts"]
    assert isinstance(artifacts, list)
    artifact = artifacts[0]
    assert artifact["kind"] == "image"
    assert artifact["media_type"] == "image/png"
    path = Path(str(artifact["path"]))
    assert path.is_absolute()
    assert path.parent == output_dir.resolve() / "2026-04-29" / request_id
    assert path.exists()
    content = path.read_bytes()
    assert content.startswith(b"\x89PNG\r\n\x1a\n")
    assert artifact["bytes"] == path.stat().st_size
    assert artifact["sha256"] == hashlib.sha256(content).hexdigest()
    with Image.open(path) as image:
        assert image.size == size


def _provider(_region, _http_client):
    return FakeProvider()


class FakeProvider:
    def daily_note(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
    ) -> CommandResult:
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "note": {
                    "current_resin": 80,
                    "max_resin": 200,
                    "finished_task_num": 4,
                    "total_task_num": 4,
                    "current_expedition_num": 2,
                    "max_expedition_num": 5,
                    "current_home_coin": 1200,
                    "max_home_coin": 2400,
                    "remain_resin_discount_num": 2,
                    "resin_discount_num_limit": 3,
                },
            },
            source=_source("mys"),
        )

    def challenge_abyss(
        self,
        *,
        uid: str,
        cookie: str,
        region: str,
        credential_source: str,
        storage_backend: str | None,
        season: str,
        floor: int | None,
    ) -> CommandResult:
        return CommandResult(
            data={
                "uid": uid,
                "credential_source": credential_source,
                "storage_backend": storage_backend,
                "season": season,
                "floor": floor,
                "abyss": {
                    "total_star": 36,
                    "max_floor": "12-3",
                    "total_battle_times": 20,
                    "total_win_times": 12,
                    "floors": [{"index": 12, "star": 9}, {"index": 11, "star": 9}],
                    "floor_count": 2,
                },
            },
            source=_source("mys"),
        )


class FakeEnkaProvider:
    def __init__(self, _http_client) -> None:
        pass

    def profile(self, *, uid: str, region: str) -> CommandResult:
        return CommandResult(
            data={
                "uid": uid,
                "ttl": 300,
                "playerInfo": {"nickname": "Traveler", "level": 60},
                "avatarInfoList": [
                    {
                        "avatarId": 10000021,
                        "name": "Amber",
                        "level": 80,
                        "talentIdList": [1, 2],
                        "fetterInfo": {"expLevel": 10},
                        "fightPropMap": {"20": 0.5, "22": 1.0, "23": 1.3, "4": 800},
                        "equipList": [
                            {
                                "itemId": 10000021,
                                "weapon": {"level": 90},
                                "flat": {
                                    "name": "Favonius Warbow",
                                    "itemType": "ITEM_WEAPON",
                                    "rankLevel": 4,
                                },
                            },
                            {
                                "itemId": 76543,
                                "reliquary": {"level": 20},
                                "flat": {
                                    "name": "Amber Flower",
                                    "itemType": "ITEM_RELIQUARY",
                                    "equipType": "EQUIP_BRACER",
                                    "rankLevel": 5,
                                    "reliquarySubstats": [
                                        {"appendPropId": "FIGHT_PROP_CRITICAL", "statValue": 3.9},
                                        {
                                            "appendPropId": "FIGHT_PROP_CRITICAL_HURT",
                                            "statValue": 7.8,
                                        },
                                    ],
                                },
                            },
                        ],
                    }
                ],
            },
            source=_source("enka"),
        )


def _source(provider: str) -> dict[str, object]:
    return {
        "provider": provider,
        "region": "cn",
        "cached": False,
        "fetched_at": "2026-04-29T10:30:00Z",
    }


def _run_json(argv: list[str]) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    assert stderr.getvalue() == ""
    return code, json.loads(stdout.getvalue())
