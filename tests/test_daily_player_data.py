from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from PIL import Image

from gsuid_cli.cli import run
from gsuid_cli.commands import player as player_commands
from gsuid_cli.commands import public_data
from gsuid_cli.core.errors import EXIT_AUTH, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.secrets import SecretStore
from gsuid_cli.providers.mys import RECORD_SALT, MysProvider
from gsuid_cli.renderers.player import summary as player_summary_renderer
from gsuid_cli.renderers.player.summary import (
    FOOTER_TEXT,
    player_profile_picture_url,
    render_player_summary_card,
)


def test_daily_note_requires_cookie(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    code, payload = _run_json(["daily", "note", "--uid", "100000001"])

    assert code == 2
    assert payload["command"] == "daily.note"
    assert payload["error"]["code"] == "AUTH_REQUIRED"


def test_daily_and_player_commands_use_stored_cookie(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.public_data.provider_for_region", _fake_provider)
    monkeypatch.setattr("gsuid_cli.commands.player.provider_for_region", _fake_provider)
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    current_month = f"{datetime.now(UTC).year}-04"
    commands = [
        (["daily", "note", "--uid", "100000001"], "daily.note", "note"),
        (["daily", "signin", "--uid", "100000001"], "daily.signin", "signed"),
        (["player", "summary", "--uid", "100000001"], "player.summary", "summary"),
        (["player", "characters", "--uid", "100000001"], "player.characters", "characters"),
        (
            ["player", "diary", "--uid", "100000001", "--month", current_month],
            "player.diary",
            "diary",
        ),
    ]

    for argv, command, key in commands:
        code, payload = _run_json(argv)

        assert code == 0
        assert payload["command"] == command
        assert payload["data"]["credential_source"] == "keyring"
        assert key in payload["data"]


def test_daily_note_render_image_writes_daily_note_card(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.public_data.provider_for_region", _fake_provider)
    monkeypatch.setattr("gsuid_cli.commands.player.provider_for_region", _fake_provider)
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(
        [
            "daily",
            "note",
            "--uid",
            "100000001",
            "--render",
            "image",
            "--request-id",
            "daily-img",
            "--output-dir",
            str(tmp_path / "artifacts"),
        ]
    )

    assert code == 0
    assert payload["command"] == "daily.note"
    assert payload["data"] == {
        "uid": "100000001",
        "render": "daily/note",
        "artifact_sha256": payload["artifacts"][0]["sha256"],
    }
    artifact = payload["artifacts"][0]
    path = Path(artifact["path"])
    content = path.read_bytes()
    assert path.parent == tmp_path / "artifacts" / "2026-04-29" / "daily-img"
    assert artifact["media_type"] == "image/png"
    assert artifact["sha256"] == hashlib.sha256(content).hexdigest()
    with Image.open(path) as image:
        assert image.size == (700, 1300)
        assert image.getbbox() is not None


def test_daily_note_render_both_preserves_structured_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.public_data.provider_for_region", _fake_provider)
    monkeypatch.setattr("gsuid_cli.commands.player.provider_for_region", _fake_provider)
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(["daily", "note", "--uid", "100000001", "--render", "both"])

    assert code == 0
    assert payload["data"]["note"]["current_resin"] == 1
    assert payload["data"]["artifact_sha256"] == payload["artifacts"][0]["sha256"]


def test_daily_note_render_uses_player_summary_and_daily_signin_status(
    monkeypatch, tmp_path
) -> None:
    captured: dict[str, object] = {}
    calls: list[str] = []
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data.provider_for_region",
        _sign_status_provider(calls, already_signed=True, signed=False),
    )
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data.player_commands.summary_command",
        _player_summary_command(calls),
    )
    monkeypatch.setattr(public_data, "render_daily_note_card", _capturing_renderer(captured))
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(["daily", "note", "--uid", "100000001", "--render", "image"])

    assert code == 0
    assert payload["command"] == "daily.note"
    assert calls == ["daily_note", "player.summary", "daily_signin_status"]
    assert captured["nickname"] == "派蒙"
    assert captured["level"] == 60
    assert captured["signed"] is True


def test_daily_note_render_falls_back_when_player_summary_fails(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}
    calls: list[str] = []
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data.provider_for_region",
        _sign_status_provider(calls, already_signed=False, signed=False),
    )
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data.player_commands.summary_command",
        _failing_player_summary_command(calls),
    )
    monkeypatch.setattr(public_data, "render_daily_note_card", _capturing_renderer(captured))
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(["daily", "note", "--uid", "100000001", "--render", "image"])

    assert code == 0
    assert calls == ["daily_note", "player.summary", "daily_signin_status"]
    assert captured["nickname"] is None
    assert captured["level"] is None
    assert "daily note player header data is unavailable" in payload["warnings"][0]


def test_daily_note_render_fetches_expedition_avatar_urls(monkeypatch, tmp_path) -> None:
    captured_urls: list[str] = []
    avatar_url = "https://upload.example.test/UI_AvatarIcon_Side_Ambor.png"
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.public_data.provider_for_region",
        _avatar_provider(avatar_url),
    )
    monkeypatch.setattr(
        "gsuid_cli.commands.player.provider_for_region", _avatar_provider(avatar_url)
    )
    monkeypatch.setattr(public_data, "fetch_render_images", _fake_image_fetcher(captured_urls))
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(["daily", "note", "--uid", "100000001", "--render", "image"])

    assert code == 0
    assert captured_urls == [avatar_url]
    with Image.open(payload["artifacts"][0]["path"]) as image:
        red, green, blue, _alpha = image.convert("RGBA").getpixel((101, 1071))
        assert red > 200
        assert green < 80
        assert blue < 80


def test_player_characters_render_image_writes_character_card(monkeypatch, tmp_path) -> None:
    captured_urls: list[str] = []
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.player.provider_for_region", _fake_provider)
    monkeypatch.setattr(player_commands, "fetch_render_images", _fake_image_fetcher(captured_urls))
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(
        [
            "player",
            "characters",
            "--uid",
            "100000001",
            "--render",
            "image",
            "--request-id",
            "player-characters-img",
            "--output-dir",
            str(tmp_path / "artifacts"),
        ]
    )

    assert code == 0
    assert payload["command"] == "player.characters"
    assert payload["data"] == {
        "uid": "100000001",
        "render": "player/characters",
        "character_count": 1,
        "artifact_sha256": payload["artifacts"][0]["sha256"],
    }
    assert captured_urls == [
        "https://example.test/GenshinUID/resource/chars/10000021.png",
        "https://example.test/GenshinUID/resource/char_namecard_pic/10000021.png",
        "https://example.test/GenshinUID/resource/weapon/Bow.png",
    ]
    artifact = payload["artifacts"][0]
    path = Path(artifact["path"])
    content = path.read_bytes()
    assert path.parent == tmp_path / "artifacts" / "2026-04-29" / "player-characters-img"
    assert artifact["media_type"] == "image/png"
    assert artifact["sha256"] == hashlib.sha256(content).hexdigest()
    with Image.open(path) as image:
        assert image.size == (1680, 435)
        assert image.getbbox() is not None


def test_player_characters_render_both_preserves_structured_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.player.provider_for_region", _fake_provider)
    monkeypatch.setattr(player_commands, "fetch_render_images", _fake_image_fetcher([]))
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(["player", "characters", "--uid", "100000001", "--render", "both"])

    assert code == 0
    assert payload["data"]["characters"][0]["name"] == "Amber"
    assert payload["data"]["artifact_sha256"] == payload["artifacts"][0]["sha256"]


def test_player_summary_render_image_writes_full_role_card(monkeypatch, tmp_path) -> None:
    captured_urls: list[str] = []
    footer_calls = 0
    original_paste_footer = player_summary_renderer._paste_footer

    def spy_paste_footer(image) -> None:
        nonlocal footer_calls
        footer_calls += 1
        original_paste_footer(image)

    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.player.provider_for_region", _fake_provider)
    monkeypatch.setattr(player_commands, "fetch_render_images", _fake_image_fetcher(captured_urls))
    monkeypatch.setattr(player_summary_renderer, "_paste_footer", spy_paste_footer)
    monkeypatch.setattr(
        player_commands,
        "_player_profile_title_avatar_url",
        lambda args, uid, region: (
            "https://enka.network/ui/UI_AvatarIcon_PlayerGirl_Circle.png",
            [],
        ),
    )
    monkeypatch.setattr("gsuid_cli.core.artifacts.utc_now", lambda: "2026-04-29T10:30:00Z")
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(
        [
            "player",
            "summary",
            "--uid",
            "100000001",
            "--render",
            "image",
            "--request-id",
            "player-summary-img",
            "--output-dir",
            str(tmp_path / "artifacts"),
        ]
    )

    assert code == 0
    assert payload["command"] == "player.summary"
    assert payload["data"] == {
        "uid": "100000001",
        "render": "player/summary",
        "character_count": 1,
        "artifact_sha256": payload["artifacts"][0]["sha256"],
    }
    assert captured_urls == [
        "https://example.test/GenshinUID/resource/chars/10000021.png",
        "https://example.test/GenshinUID/resource/char_namecard_pic/10000021.png",
        "https://example.test/GenshinUID/resource/weapon/Bow.png",
        "https://upload.example.test/world.png",
        "https://upload.example.test/offering.png",
        "https://enka.network/ui/UI_AvatarIcon_PlayerGirl_Circle.png",
    ]
    artifact = payload["artifacts"][0]
    path = Path(artifact["path"])
    content = path.read_bytes()
    assert path.parent == tmp_path / "artifacts" / "2026-04-29" / "player-summary-img"
    assert artifact["media_type"] == "image/png"
    assert artifact["sha256"] == hashlib.sha256(content).hexdigest()
    assert (
        FOOTER_TEXT == "Created by gsuid-cli & Render style/assets by GenshinUID & Data by 米游社"
    )
    assert footer_calls == 1
    with Image.open(path) as image:
        assert image.size == (1680, 2115)
        assert image.getbbox() is not None


def test_player_summary_render_both_preserves_structured_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.player.provider_for_region", _fake_provider)
    monkeypatch.setattr(player_commands, "fetch_render_images", _fake_image_fetcher([]))
    monkeypatch.setattr(
        player_commands,
        "_player_profile_title_avatar_url",
        lambda args, uid, region: (None, []),
    )
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(["player", "summary", "--uid", "100000001", "--render", "both"])

    assert code == 0
    assert payload["data"]["summary"]["role"]["nickname"] == "派蒙"
    assert payload["data"]["artifact_sha256"] == payload["artifacts"][0]["sha256"]


def test_player_summary_render_skips_profile_lookup_when_role_avatar_exists(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "gsuid_cli.commands.player.provider_for_region",
        _summary_provider_with_role_avatar,
    )
    monkeypatch.setattr(player_commands, "fetch_render_images", _fake_image_fetcher([]))
    monkeypatch.setattr(
        player_commands,
        "_player_profile_title_avatar_url",
        _unexpected_profile_title_avatar_url,
    )
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(["player", "summary", "--uid", "100000001", "--render", "image"])

    assert code == 0
    assert payload["data"]["render"] == "player/summary"


def test_player_profile_picture_url_uses_live_mapping() -> None:
    assert (
        player_profile_picture_url(
            {"playerInfo": {"profilePicture": {"id": 21}}},
            {"21": {"iconPath": "UI_AvatarIcon_Ayaka_Circle"}},
        )
        == "https://enka.network/ui/UI_AvatarIcon_Ayaka_Circle.png"
    )


def test_player_profile_picture_url_does_not_use_showcase_for_unknown_picture() -> None:
    assert (
        player_profile_picture_url(
            {
                "playerInfo": {
                    "profilePicture": {"id": 900004},
                    "showAvatarInfoList": [{"avatarId": 10000022}],
                }
            }
        )
        is None
    )


def test_player_profile_title_avatar_resolves_pfps_mapping(monkeypatch) -> None:
    class FakeEnkaProvider:
        def __init__(self, _http_client: HttpClient) -> None:
            pass

        def profile(self, *, uid: str, region: str) -> CommandResult:
            del uid
            return CommandResult(
                data={
                    "playerInfo": {
                        "profilePicture": {"id": 21},
                        "showAvatarInfoList": [{"avatarId": 10000022}],
                    }
                },
                source=_source(region),
            )

    class Args:
        timeout = 20
        cache = "use"
        output_dir = None
        debug = False

    monkeypatch.setattr(player_commands, "EnkaProvider", FakeEnkaProvider)
    monkeypatch.setattr(
        player_commands,
        "_profile_picture_icons",
        lambda args, region: {"21": {"iconPath": "UI_AvatarIcon_Ayaka_Circle"}},
    )

    url, warnings = player_commands._player_profile_title_avatar_url(Args(), "100000001", "cn")

    assert warnings == []
    assert url == "https://enka.network/ui/UI_AvatarIcon_Ayaka_Circle.png"


def test_player_profile_picture_config_honors_cache_policy(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeHttpClient:
        def __init__(
            self,
            *,
            timeout: float,
            cache_policy: str,
            output_dir: str | None,
            debug: bool,
        ) -> None:
            captured.update(
                {
                    "timeout": timeout,
                    "cache_policy": cache_policy,
                    "output_dir": output_dir,
                    "debug": debug,
                }
            )

        def request_bytes(self, *args, **kwargs):
            captured["request"] = (args, kwargs)
            return type(
                "Response",
                (),
                {
                    "content": b'[{"id":21,"iconPath":"UI_AvatarIcon_PlayerGirl_Circle"}]',
                    "source": _source("cn"),
                },
            )()

    class Args:
        timeout = 7
        cache = "only"
        output_dir = "/tmp/gsuid-cache-test"
        debug = True

    monkeypatch.setattr(player_commands, "HttpClient", FakeHttpClient)

    icons = player_commands._profile_picture_icons(Args(), "cn")

    assert captured["cache_policy"] == "only"
    assert icons == {"21": {"iconPath": "UI_AvatarIcon_PlayerGirl_Circle"}}


def test_player_summary_render_handles_missing_oculus_texture() -> None:
    png = render_player_summary_card(
        uid="100000001",
        summary={"role": {}, "stats": {"cryoculus_number": 1}},
        characters=[],
    )

    with Image.open(io.BytesIO(png)) as image:
        assert image.getbbox() is not None


def test_player_summary_render_prefers_role_avatar_icon() -> None:
    role_avatar = _solid_png((220, 10, 10, 255))
    player_avatar = _solid_png((10, 220, 10, 255))
    png = render_player_summary_card(
        uid="100000001",
        summary={
            "role": {"avatar_icon": "https://upload.example.test/role.png"},
            "stats": {},
        },
        characters=[],
        asset_images={
            "https://upload.example.test/role.png": role_avatar,
            "https://enka.network/ui/UI_AvatarIcon_PlayerGirl_Circle.png": player_avatar,
        },
        title_avatar_url="https://enka.network/ui/UI_AvatarIcon_PlayerGirl_Circle.png",
    )

    with Image.open(io.BytesIO(png)) as image:
        assert image.getpixel((840, 260)) == (220, 10, 10)


def test_player_characters_render_fetches_mys_fallbacks_for_missing_resources(
    monkeypatch, tmp_path
) -> None:
    captured_urls: list[str] = []
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.player.provider_for_region", _fake_provider)
    monkeypatch.setattr(
        player_commands,
        "fetch_render_images",
        _missing_character_resource_fetcher(captured_urls),
    )
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(["player", "characters", "--uid", "100000001", "--render", "image"])

    assert code == 0
    assert captured_urls == [
        "https://example.test/GenshinUID/resource/chars/10000021.png",
        "https://example.test/GenshinUID/resource/char_namecard_pic/10000021.png",
        "https://example.test/GenshinUID/resource/weapon/Bow.png",
        "https://upload.example.test/amber.png",
        "https://upload.example.test/amber-icon.png",
    ]
    assert payload["warnings"] == ["1 mirror miss"]


def test_daily_command_surfaces_expired_cookie(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("gsuid_cli.commands.public_data.provider_for_region", _expired_provider)
    SecretStore().set_secret("cookie", "100000001", "account_id=1;cookie_token=secret")

    code, payload = _run_json(["daily", "note", "--uid", "100000001"])

    assert code == 2
    assert payload["error"]["code"] == "AUTH_EXPIRED"


def test_player_diary_validates_month_before_cookie_lookup(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSUID_HOME", str(tmp_path / "home"))

    code, payload = _run_json(["player", "diary", "--uid", "100000001", "--month", "bad"])

    assert code == 1
    assert payload["command"] == "player.diary"
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_mys_daily_signin_is_idempotent_when_already_signed() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _json_response(
            {
                "retcode": 0,
                "message": "OK",
                "data": {"is_sign": True, "total_sign_day": 3},
            }
        )

    provider = MysProvider(_mock_client(handler))

    result = provider.daily_signin(
        uid="100000001",
        cookie="account_id=1;cookie_token=secret",
        region="cn",
        credential_source="keyring",
        storage_backend="tests.MemoryKeyring",
    )

    assert result.data["already_signed"] is True
    assert result.data["signed"] is False
    assert len(requests) == 1
    assert requests[0].url.path == "/event/luna/info"
    assert result.data["day_number"] == 3
    assert result.data["provider_message"] == "OK"


def test_mys_daily_signin_success_normalizes_reward_and_message() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return _json_response(
                {
                    "retcode": 0,
                    "message": "OK",
                    "data": {
                        "is_sign": False,
                        "total_sign_day": 2,
                        "awards": [
                            {"name": "Mora", "cnt": 1000, "icon": "mora.png"},
                            {"name": "Ore", "cnt": 3, "icon": "ore.png"},
                            {"name": "Primogem", "cnt": 20, "icon": "primogem.png"},
                        ],
                    },
                }
            )
        return _json_response({"retcode": 0, "message": "OK", "data": {"success": 0}})

    provider = MysProvider(_mock_client(handler))

    result = provider.daily_signin(
        uid="100000001",
        cookie="account_id=1;cookie_token=secret",
        region="cn",
        credential_source="keyring",
        storage_backend="tests.MemoryKeyring",
    )

    assert result.data["already_signed"] is False
    assert result.data["signed"] is True
    assert result.data["day_number"] == 3
    assert result.data["reward"] == {"name": "Primogem", "count": 20, "icon": "primogem.png"}
    assert result.data["provider_message"] == "OK"
    assert len(requests) == 2


def test_mys_daily_signin_status_is_read_only() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _json_response(
            {
                "retcode": 0,
                "message": "OK",
                "data": {"is_sign": False, "total_sign_day": 3},
            }
        )

    provider = MysProvider(_mock_client(handler))

    result = provider.daily_signin_status(
        uid="100000001",
        cookie="account_id=1;cookie_token=secret",
        region="cn",
        credential_source="keyring",
        storage_backend="tests.MemoryKeyring",
    )

    assert result.data["already_signed"] is False
    assert result.data["signed"] is False
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/event/luna/info"


def test_mys_player_summary_uses_account_card_identity_when_index_omits_it() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return _device_fp_response()
        if len(requests) == 2:
            return _json_response(
                {
                    "retcode": 0,
                    "message": "OK",
                    "data": {"stats": {"active_day_number": 1}, "avatars": []},
                }
            )
        return _json_response(
            {
                "retcode": 0,
                "message": "OK",
                "data": {
                    "list": [
                        {
                            "game_id": 2,
                            "game_role_id": "100000001",
                            "nickname": "派蒙",
                            "level": 60,
                            "region": "cn_gf01",
                            "region_name": "天空岛",
                        }
                    ]
                },
            }
        )

    provider = MysProvider(_mock_client(handler))

    result = provider.player_summary(
        uid="100000001",
        cookie="account_id=1;cookie_token=secret",
        region="cn",
        credential_source="keyring",
        storage_backend="tests.MemoryKeyring",
    )

    role = result.data["summary"]["role"]
    assert role["nickname"] == "派蒙"
    assert role["level"] == 60
    assert role["region_name"] == "天空岛"
    assert [request.url.path for request in requests] == [
        "/device-fp/api/getFp",
        "/game_record/app/genshin/api/index",
        "/game_record/card/wapi/getGameRecordCard",
    ]


def test_mys_player_characters_fetches_detail_for_index_avatars() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return _device_fp_response()
        if len(requests) == 2:
            return _json_response(
                {
                    "retcode": 0,
                    "message": "OK",
                    "data": {
                        "avatars": [{"id": 10000021, "name": "Amber", "level": 80, "rarity": 4}]
                    },
                }
            )
        return _json_response(
            {
                "retcode": 0,
                "message": "OK",
                "data": {
                    "list": [
                        {
                            "id": 10000021,
                            "name": "Amber",
                            "element": "Pyro",
                            "level": 80,
                            "rarity": 4,
                            "weapon": {"id": 1, "name": "Bow", "level": 80},
                        }
                    ]
                },
            }
        )

    provider = MysProvider(_mock_client(handler))

    result = provider.player_characters(
        uid="100000001",
        cookie="account_id=1;cookie_token=secret",
        region="cn",
        credential_source="keyring",
        storage_backend="tests.MemoryKeyring",
    )

    detail_body_text = requests[2].content.decode()
    detail_body = json.loads(detail_body_text)
    timestamp, random_value, digest = requests[2].headers["ds"].split(",")
    expected_digest = hashlib.md5(
        f"salt={RECORD_SALT}&t={timestamp}&r={random_value}&b={detail_body_text}&q=".encode()
    ).hexdigest()
    assert result.data["count"] == 1
    assert result.data["characters"][0]["name"] == "Amber"
    assert detail_body == {
        "character_ids": [10000021],
        "role_id": "100000001",
        "server": "cn_gf01",
    }
    assert (
        detail_body_text == '{"character_ids":[10000021],"role_id":"100000001","server":"cn_gf01"}'
    )
    assert digest == expected_digest
    assert requests[2].headers["x-rpc-device_fp"] == "device-fp-1"


def test_mys_player_diary_rejects_invalid_month() -> None:
    provider = MysProvider(
        _mock_client(lambda _request: _json_response({"retcode": 0, "message": "OK", "data": {}}))
    )

    with pytest.raises(CliError) as exc:
        provider.player_diary(
            uid="100000001",
            cookie="account_id=1;cookie_token=secret",
            region="cn",
            credential_source="keyring",
            storage_backend="tests.MemoryKeyring",
            month="2026-13",
        )

    assert exc.value.code == "INVALID_ARGUMENT"


def _run_json(argv: list[str]) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(argv, stdout=stdout, stderr=stderr)
    assert stderr.getvalue() == ""
    return code, json.loads(stdout.getvalue())


def _fake_provider(_region: str, _http_client: HttpClient):
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
                    "cookie_seen": cookie.startswith("account_id="),
                    "note": {"current_resin": 1},
                },
                source=_source(region),
            )

        def daily_signin(
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
                    "signed": False,
                    "already_signed": True,
                },
                source=_source(region),
            )

        def daily_signin_status(
            self,
            *,
            uid: str,
            cookie: str,
            region: str,
            credential_source: str,
            storage_backend: str | None,
        ) -> CommandResult:
            return self.daily_signin(
                uid=uid,
                cookie=cookie,
                region=region,
                credential_source=credential_source,
                storage_backend=storage_backend,
            )

        def player_summary(
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
                    "summary": {
                        "role": {"nickname": "派蒙", "level": 60},
                        "stats": {
                            "active_day_number": 10,
                            "achievement_number": 20,
                            "spiral_abyss": "1-1",
                        },
                        "avatars": [{"id": 10000021, "name": "Amber"}],
                        "world_explorations": [
                            {
                                "id": 1,
                                "name": "蒙德",
                                "level": 8,
                                "exploration_percentage": 1000,
                                "icon": "https://upload.example.test/world.png",
                                "offerings": [
                                    {
                                        "name": "忍冬之树",
                                        "level": 12,
                                        "icon": "https://upload.example.test/offering.png",
                                    }
                                ],
                            }
                        ],
                    },
                },
                source=_source(region),
            )

        def player_characters(
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
                    "characters": [
                        {
                            "id": 10000021,
                            "name": "Amber",
                            "level": 80,
                            "rarity": 4,
                            "fetter": 10,
                            "actived_constellation_num": 2,
                            "image": "https://upload.example.test/amber.png",
                            "icon": "https://upload.example.test/amber-icon.png",
                            "weapon": {
                                "name": "Bow",
                                "rarity": 4,
                                "level": 80,
                                "affix_level": 1,
                                "icon": "https://upload.example.test/bow.png",
                            },
                        }
                    ],
                    "count": 1,
                },
                source=_source(region),
            )

        def player_diary(
            self,
            *,
            uid: str,
            cookie: str,
            region: str,
            credential_source: str,
            storage_backend: str | None,
            month: str | None,
        ) -> CommandResult:
            return CommandResult(
                data={
                    "uid": uid,
                    "credential_source": credential_source,
                    "storage_backend": storage_backend,
                    "requested_month": month,
                    "diary": {"month": 4},
                },
                source=_source(region),
            )

    return FakeProvider()


def _sign_status_provider(calls: list[str], *, already_signed: bool, signed: bool):
    def provider_for_region(_region: str, _http_client: HttpClient):
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
                calls.append("daily_note")
                return CommandResult(
                    data={
                        "uid": uid,
                        "credential_source": credential_source,
                        "storage_backend": storage_backend,
                        "cookie_seen": cookie.startswith("account_id="),
                        "note": {"current_resin": 1},
                    },
                    source=_source(region),
                )

            def daily_signin_status(
                self,
                *,
                uid: str,
                cookie: str,
                region: str,
                credential_source: str,
                storage_backend: str | None,
            ) -> CommandResult:
                calls.append("daily_signin_status")
                return CommandResult(
                    data={
                        "uid": uid,
                        "credential_source": credential_source,
                        "storage_backend": storage_backend,
                        "already_signed": already_signed,
                        "signed": signed,
                    },
                    source=_source(region),
                )

        return FakeProvider()

    return provider_for_region


def _avatar_provider(avatar_url: str):
    def provider_for_region(_region: str, _http_client: HttpClient):
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
                        "cookie_seen": cookie.startswith("account_id="),
                        "note": {
                            "current_resin": 1,
                            "max_resin": 200,
                            "resin_recovery_time": 3600,
                            "expeditions": [
                                {
                                    "avatar_side_icon": avatar_url,
                                    "status": "Finished",
                                    "remained_time": 0,
                                }
                            ],
                        },
                    },
                    source=_source(region),
                )

            def player_summary(
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
                        "summary": {"role": {"nickname": "安柏", "level": 60}},
                    },
                    source=_source(region),
                )

            def daily_signin_status(
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
                        "already_signed": False,
                        "signed": False,
                    },
                    source=_source(region),
                )

        return FakeProvider()

    return provider_for_region


def _summary_provider_with_role_avatar(_region: str, _http_client: HttpClient):
    class FakeProvider:
        def player_summary(
            self,
            *,
            uid: str,
            cookie: str,
            region: str,
            credential_source: str,
            storage_backend: str | None,
        ) -> CommandResult:
            del cookie
            return CommandResult(
                data={
                    "uid": uid,
                    "credential_source": credential_source,
                    "storage_backend": storage_backend,
                    "summary": {
                        "role": {
                            "nickname": "派蒙",
                            "level": 60,
                            "avatar_icon": "https://upload.example.test/role-avatar.png",
                        },
                        "stats": {"active_day_number": 10},
                    },
                },
                source=_source(region),
            )

        def player_characters(
            self,
            *,
            uid: str,
            cookie: str,
            region: str,
            credential_source: str,
            storage_backend: str | None,
        ) -> CommandResult:
            del cookie
            return CommandResult(
                data={
                    "uid": uid,
                    "credential_source": credential_source,
                    "storage_backend": storage_backend,
                    "characters": [],
                },
                source=_source(region),
            )

    return FakeProvider()


def _unexpected_profile_title_avatar_url(*_args, **_kwargs):
    raise AssertionError("profile picture fallback should not be resolved")


def _player_summary_command(calls: list[str]):
    def command(args) -> CommandResult:
        calls.append("player.summary")
        assert args.command_name == "player.summary"
        return CommandResult(
            data={
                "uid": args.command_uid,
                "credential_source": "keyring",
                "storage_backend": "tests.MemoryKeyring",
                "summary": {"role": {"nickname": "派蒙", "level": 60}},
            },
            source=_source(args.region),
        )

    return command


def _failing_player_summary_command(calls: list[str]):
    def command(_args) -> CommandResult:
        calls.append("player.summary")
        raise CliError("AUTH_EXPIRED", "Player summary unavailable.", EXIT_AUTH)

    return command


def _capturing_renderer(captured: dict[str, object]):
    def render(**kwargs) -> bytes:
        captured.update(kwargs)
        image = Image.new("RGBA", (1, 1), (255, 255, 255, 255))
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    return render


def _fake_image_fetcher(requested_urls: list[str]):
    def fetcher(
        _args,
        urls,
        *,
        provider: str,
        region: str,
        category: str,
        unavailable_warning: str,
        max_workers: int = 8,
    ) -> tuple[dict[str, bytes], list[str]]:
        del provider, region, category, unavailable_warning, max_workers
        requested_urls.extend(urls)
        return {url: _png_bytes() for url in urls}, []

    return fetcher


def _missing_character_resource_fetcher(requested_urls: list[str]):
    def fetcher(
        _args,
        urls,
        *,
        provider: str,
        region: str,
        category: str,
        unavailable_warning: str,
        max_workers: int = 8,
    ) -> tuple[dict[str, bytes], list[str]]:
        del region, unavailable_warning, max_workers
        url_list = list(urls)
        requested_urls.extend(url_list)
        if provider == "genshinuid":
            return {
                url: _png_bytes()
                for url in url_list
                if "/chars/" not in url and category == "player.characters.resource"
            }, ["1 mirror miss"]
        return {url: _png_bytes() for url in url_list}, []

    return fetcher


def _png_bytes() -> bytes:
    return _solid_png((255, 0, 0, 255))


def _solid_png(color: tuple[int, int, int, int]) -> bytes:
    image = Image.new("RGBA", (32, 32), color)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _expired_provider(_region: str, _http_client: HttpClient):
    class ExpiredProvider:
        def daily_note(self, **_kwargs) -> CommandResult:
            raise CliError(
                "AUTH_EXPIRED",
                "The cookie is expired or rejected by the provider.",
                EXIT_AUTH,
            )

    return ExpiredProvider()


def _source(region: str) -> dict[str, object]:
    return {
        "provider": "mys",
        "region": region,
        "cached": False,
        "fetched_at": "2026-04-29T10:30:00Z",
    }


def _mock_client(handler) -> HttpClient:
    return HttpClient(
        timeout=1,
        cache_policy="off",
        transport=httpx.MockTransport(handler),
    )


def _json_response(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, json=payload)


def _device_fp_response() -> httpx.Response:
    return _json_response(
        {
            "retcode": 0,
            "message": "OK",
            "data": {"device_fp": "device-fp-1", "code": 200, "msg": "ok"},
        }
    )
