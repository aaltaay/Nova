"""nova-brain client -- fixtures only, never places live IBKR orders."""
from __future__ import annotations

import pytest

from constants_bot import BOT_PACK_HALT_LULD
from nova_brain.halt_luld import detect_resumes, tick
from nova_brain.loop import step


def test_detect_resumes_halted_to_clear():
    prev = {"ABCD": True, "EFGH": True}
    watch = {
        "symbols": [
            {"symbol": "ABCD", "halted": False},
            {"symbol": "EFGH", "halted": True},
        ]
    }
    resumes, nxt = detect_resumes(prev, watch)
    assert resumes == ["ABCD"]
    assert nxt == {"ABCD": False, "EFGH": True}


def test_tick_fires_once_with_cooldown():
    fired: list[tuple[str, str]] = []
    session = {
        "active_pack": BOT_PACK_HALT_LULD,
        "live_fire_ready": True,
        "pack_settings": {BOT_PACK_HALT_LULD: {"resume_kind": "buy_market", "cooldown_sec": 30}},
    }
    watch = {"symbols": [{"symbol": "ABCD", "halted": False}]}
    nxt = tick(
        session=session,
        watch=watch,
        previous={"ABCD": True},
        last_fire={},
        now=100.0,
        fire=lambda kind, symbol: fired.append((kind, symbol)),
    )
    assert fired == [("buy_market", "ABCD")]
    assert nxt["ABCD"] is False
    tick(
        session=session,
        watch=watch,
        previous={"ABCD": True},
        last_fire={"ABCD": 90.0},
        now=100.0,
        fire=lambda kind, symbol: fired.append((kind, symbol)),
    )
    assert fired == [("buy_market", "ABCD")]


def test_tick_skips_when_not_live_fire_ready():
    fired: list[tuple[str, str]] = []
    tick(
        session={"active_pack": BOT_PACK_HALT_LULD, "live_fire_ready": False},
        watch={"symbols": [{"symbol": "ABCD", "halted": False}]},
        previous={"ABCD": True},
        last_fire={},
        now=1.0,
        fire=lambda kind, symbol: fired.append((kind, symbol)),
    )
    assert fired == []


class _FakeClient:
    def __init__(self, session: dict, watch: dict | None = None) -> None:
        self._session = session
        self._watch = watch or {"symbols": []}
        self.claims = 0
        self.heartbeats = 0
        self.patches = 0

    def session_get(self) -> dict:
        return dict(self._session)

    def claim(self) -> dict:
        self.claims += 1
        return dict(self._session)

    def heartbeat(self) -> dict:
        self.heartbeats += 1
        return dict(self._session)

    def watch(self) -> dict:
        return dict(self._watch)

    def fire(self, kind: str, symbol: str) -> dict:
        return {"ok": True, "kind": kind, "symbol": symbol}

    def patch_level(self, level: int) -> None:
        self.patches += 1
        self._session["level"] = level


def test_step_never_raises_autonomy_and_heartbeats():
    client = _FakeClient(
        {
            "level": 2,
            "armed": True,
            "active_pack": BOT_PACK_HALT_LULD,
            "live_fire_ready": False,
        }
    )
    step(client, halt_prev={}, last_fire={})
    assert client.claims == 1
    assert client.heartbeats == 1
    assert client.patches == 0


def test_step_volume_pack_does_not_run_halt():
    client = _FakeClient(
        {
            "level": 2,
            "armed": True,
            "active_pack": "volume",
            "live_fire_ready": True,
        },
        watch={"symbols": [{"symbol": "ABCD", "halted": False, "volume": None}]},
    )
    prev = step(client, halt_prev={"ABCD": True}, last_fire={})
    assert client.heartbeats == 1
    assert client.claims == 1
    assert prev == {"ABCD": True}


def test_run_forever_exits_without_api_key(monkeypatch):
    from nova_brain.client import BotApiClient
    from nova_brain.loop import run_forever

    monkeypatch.delenv("NOVA_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        run_forever(client=BotApiClient(api_key=""), poll_sec=0.01)
    assert exc.value.code == 2


def test_sdk_and_adapter_are_clients_not_core():
    from bot.mcp_adapter import DESK_ONLY, TOOLS, client
    from bot.sdk import BotApiClient

    assert client(api_key="k").__class__ is BotApiClient
    names = {row["name"] for row in TOOLS}
    assert "bot_action" in names
    assert "bot_session_patch" not in names
    desk = {row["path"] for row in DESK_ONLY}
    assert "/api/bot/session/arm" in desk
    assert client(api_key="k").brain_id == "nova-brain"
