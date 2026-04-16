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
from gsuid_cli.commands import public_data
from gsuid_cli.core.errors import EXIT_AUTH, CliError
from gsuid_cli.core.http import HttpClient
from gsuid_cli.core.models import CommandResult
from gsuid_cli.core.secrets import SecretStore
from gsuid_cli.providers.mys import RECORD_SALT, MysProvider


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
            return CommandResult(
                data={
                    "uid": uid,
                    "credential_source": credential_source,
                    "storage_backend": storage_backend,
                    "characters": [{"id": 10000021, "name": "Amber"}],
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


def _png_bytes() -> bytes:
    image = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
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
