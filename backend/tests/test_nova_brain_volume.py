"""Volume pack -- fixtures only, never places live IBKR orders."""
from __future__ import annotations

import json

import pytest

from bot.packs import assert_pack_can_fire, catalog, default_pack_settings, merge_pack_settings
from constants_bot import (
    BOT_PACK_VOLUME,
    BOT_VOLUME_BASELINE_SEC,
    BOT_VOLUME_COOLDOWN_SEC,
    BOT_VOLUME_MIN_MULT,
    BOT_VOLUME_WINDOW_SEC,
)
from nova_brain.loop import step
from nova_brain.volume import detect_boosts, tick


NOW = 10_000.0
WINDOW = 60.0
BASELINE = 600.0


def _watch(*rows: dict) -> dict:
    return {"symbols": list(rows)}


def _samples(end_vol: int, *, base: int = 10_000, mid: int = 11_000, now: float = NOW) -> list[dict]:
    return [
        {"ts": now - BASELINE - WINDOW, "volume": base},
        {"ts": now - WINDOW, "volume": mid},
        {"ts": now, "volume": end_vol},
    ]


def test_catalog_marks_volume_live():
    rows = {row["id"]: row for row in catalog()}
    assert rows[BOT_PACK_VOLUME]["status"] == "live"
    assert "stub" not in rows[BOT_PACK_VOLUME]["description"].lower()
    assert "5" in rows[BOT_PACK_VOLUME]["description"]
    assert_pack_can_fire(BOT_PACK_VOLUME)


def test_default_pack_settings_define_the_signal():
    settings = default_pack_settings()[BOT_PACK_VOLUME]
    assert settings["enabled"] is True
    assert settings["volume_kind"] == "buy_market"
    assert settings["min_mult"] == BOT_VOLUME_MIN_MULT
    assert settings["window_sec"] == BOT_VOLUME_WINDOW_SEC
    assert settings["baseline_sec"] == BOT_VOLUME_BASELINE_SEC
    assert settings["cooldown_sec"] == BOT_VOLUME_COOLDOWN_SEC
    assert "stub" not in str(settings).lower()


def test_merge_pack_settings_replaces_stub_blob():
    merged = merge_pack_settings(
        {BOT_PACK_VOLUME: {"enabled": False, "note": "stub -- no signal logic yet"}}
    )
    assert merged[BOT_PACK_VOLUME]["min_mult"] == BOT_VOLUME_MIN_MULT
    assert merged[BOT_PACK_VOLUME]["volume_kind"] == "buy_market"
    assert merged[BOT_PACK_VOLUME]["enabled"] is True


def test_detect_boosts_rising_edge_five_x():
    prev = {"ABCD": {"samples": _samples(11_000)[:-1], "boosted": False}}
    watch = _watch({"symbol": "ABCD", "volume": 16_000, "last_update_ts": NOW})
    boosts, nxt = detect_boosts(
        prev, watch, now=NOW, window_sec=WINDOW, baseline_sec=BASELINE, min_mult=5.0
    )
    assert boosts == ["ABCD"]
    assert nxt["ABCD"]["boosted"] is True
    assert nxt["ABCD"]["mult"] >= 5.0


def test_detect_boosts_quiet_and_down_do_not_fire():
    prev = {
        "QUIET": {"samples": _samples(16_000, mid=16_000, base=10_000)[:-1], "boosted": False},
        "DOWN": {
            "samples": [
                {"ts": NOW - BASELINE - WINDOW, "volume": 20_000},
                {"ts": NOW - WINDOW, "volume": 15_000},
            ],
            "boosted": False,
        },
    }
    watch = _watch(
        {"symbol": "QUIET", "volume": 16_600, "last_update_ts": NOW},
        {"symbol": "DOWN", "volume": 14_000, "last_update_ts": NOW},
    )
    boosts, nxt = detect_boosts(
        prev, watch, now=NOW, window_sec=WINDOW, baseline_sec=BASELINE, min_mult=5.0
    )
    assert boosts == []
    assert nxt["QUIET"]["boosted"] is False
    assert nxt["DOWN"]["boosted"] is False


def test_detect_boosts_thin_history_fails_closed():
    prev = {"ABCD": {"samples": [{"ts": NOW - 30.0, "volume": 100}], "boosted": False}}
    watch = _watch({"symbol": "ABCD", "volume": 50_000, "last_update_ts": NOW})
    boosts, nxt = detect_boosts(
        prev, watch, now=NOW, window_sec=WINDOW, baseline_sec=BASELINE, min_mult=5.0
    )
    assert boosts == []
    assert nxt["ABCD"]["boosted"] is False


def test_detect_boosts_missing_volume_does_not_invent():
    prev = {"ABCD": {"samples": _samples(11_000)[:-1], "boosted": False}}
    watch = _watch({"symbol": "ABCD", "volume": None, "last_update_ts": NOW})
    boosts, nxt = detect_boosts(
        prev, watch, now=NOW, window_sec=WINDOW, baseline_sec=BASELINE, min_mult=5.0
    )
    assert boosts == []
    assert nxt["ABCD"]["boosted"] is False


def test_detect_boosts_rising_edge_only():
    prev = {"ABCD": {"samples": _samples(16_000)[:-1], "boosted": True}}
    watch = _watch({"symbol": "ABCD", "volume": 17_000, "last_update_ts": NOW})
    boosts, nxt = detect_boosts(
        prev, watch, now=NOW, window_sec=WINDOW, baseline_sec=BASELINE, min_mult=5.0
    )
    assert boosts == []
    assert nxt["ABCD"]["boosted"] is True


def test_tick_fires_once_with_cooldown():
    fired: list[tuple[str, str]] = []
    proposed: list[dict] = []
    session = {
        "active_pack": BOT_PACK_VOLUME,
        "level": 2,
        "live_fire_ready": True,
        "pack_settings": {
            BOT_PACK_VOLUME: {
                "volume_kind": "buy_market",
                "min_mult": 5.0,
                "window_sec": WINDOW,
                "baseline_sec": BASELINE,
                "cooldown_sec": 60,
            }
        },
    }
    watch = _watch({"symbol": "ABCD", "volume": 16_000, "last_update_ts": NOW})
    prev = {"ABCD": {"samples": _samples(11_000)[:-1], "boosted": False}}
    nxt = tick(
        session=session,
        watch=watch,
        previous=prev,
        last_fire={},
        now=NOW,
        fire=lambda kind, symbol: fired.append((kind, symbol)),
        propose=lambda body: proposed.append(body),
    )
    assert fired == [("buy_market", "ABCD")]
    assert proposed == []
    assert nxt["ABCD"]["boosted"] is True
    tick(
        session=session,
        watch=watch,
        previous={"ABCD": {"samples": _samples(11_000)[:-1], "boosted": False}},
        last_fire={"ABCD": NOW - 30.0},
        now=NOW,
        fire=lambda kind, symbol: fired.append((kind, symbol)),
        propose=lambda body: proposed.append(body),
    )
    assert fired == [("buy_market", "ABCD")]


def test_tick_proposes_at_eyes_and_skips_when_not_active_l2():
    fired: list[tuple[str, str]] = []
    proposed: list[dict] = []
    watch = _watch({"symbol": "ABCD", "volume": 16_000, "last_update_ts": NOW})
    prev = {"ABCD": {"samples": _samples(11_000)[:-1], "boosted": False}}
    tick(
        session={
            "active_pack": BOT_PACK_VOLUME,
            "level": 1,
            "live_fire_ready": False,
            "pack_settings": {
                BOT_PACK_VOLUME: {
                    "min_mult": 5.0,
                    "window_sec": WINDOW,
                    "baseline_sec": BASELINE,
                }
            },
        },
        watch=watch,
        previous=prev,
        last_fire={},
        now=NOW,
        fire=lambda kind, symbol: fired.append((kind, symbol)),
        propose=lambda body: proposed.append(body),
    )
    assert fired == []
    assert proposed[0]["symbol"] == "ABCD"
    assert proposed[0]["side"] == "BUY"
    assert proposed[0]["kind"] == "buy_market"
    assert "volume" in proposed[0]["reason"].lower()

    proposed.clear()
    tick(
        session={
            "active_pack": BOT_PACK_VOLUME,
            "level": 2,
            "live_fire_ready": False,
            "pack_settings": {
                BOT_PACK_VOLUME: {
                    "min_mult": 5.0,
                    "window_sec": WINDOW,
                    "baseline_sec": BASELINE,
                }
            },
        },
        watch=watch,
        previous={"ABCD": {"samples": _samples(11_000)[:-1], "boosted": False}},
        last_fire={},
        now=NOW,
        fire=lambda kind, symbol: fired.append((kind, symbol)),
        propose=lambda body: proposed.append(body),
    )
    assert fired == []
    assert proposed == []


def test_tick_wrong_pack_leaves_state():
    prev = {"ABCD": {"samples": _samples(11_000), "boosted": False}}
    out = tick(
        session={"active_pack": "halt-luld", "live_fire_ready": True},
        watch=_watch({"symbol": "ABCD", "volume": 99_000, "last_update_ts": NOW}),
        previous=prev,
        last_fire={},
        now=NOW,
        fire=lambda *_a: None,
    )
    assert out == prev


class _FakeClient:
    def __init__(self, session: dict, watch: dict | None = None) -> None:
        self._session = session
        self._watch = watch or {"symbols": []}
        self.claims = 0
        self.heartbeats = 0
        self.fired: list[tuple[str, str]] = []
        self.proposed: list[dict] = []

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
        self.fired.append((kind, symbol))
        return {"ok": True, "kind": kind, "symbol": symbol}

    def propose(self, body: dict) -> dict:
        self.proposed.append(dict(body))
        return {"ok": True}


def test_step_volume_l2_claims_and_fires():
    client = _FakeClient(
        {
            "level": 2,
            "armed": True,
            "active_pack": BOT_PACK_VOLUME,
            "live_fire_ready": True,
            "pack_settings": {
                BOT_PACK_VOLUME: {
                    "min_mult": 5.0,
                    "window_sec": WINDOW,
                    "baseline_sec": BASELINE,
                }
            },
        },
        watch=_watch({"symbol": "ABCD", "volume": 16_000, "last_update_ts": NOW}),
    )
    volume_prev = {"ABCD": {"samples": _samples(11_000)[:-1], "boosted": False}}
    last_fire: dict[str, float] = {}
    step(
        client,
        halt_prev={},
        last_fire=last_fire,
        volume_prev=volume_prev,
        now=NOW,
    )
    assert client.claims == 1
    assert client.heartbeats == 1
    assert client.fired == [("buy_market", "ABCD")]
    assert client.proposed == []
    assert volume_prev["ABCD"]["boosted"] is True


def test_step_volume_eyes_proposes_without_claim():
    client = _FakeClient(
        {
            "level": 1,
            "armed": False,
            "active_pack": BOT_PACK_VOLUME,
            "live_fire_ready": False,
            "pack_settings": {
                BOT_PACK_VOLUME: {
                    "min_mult": 5.0,
                    "window_sec": WINDOW,
                    "baseline_sec": BASELINE,
                }
            },
        },
        watch=_watch({"symbol": "ABCD", "volume": 16_000, "last_update_ts": NOW}),
    )
    volume_prev = {"ABCD": {"samples": _samples(11_000)[:-1], "boosted": False}}
    step(client, halt_prev={}, last_fire={}, volume_prev=volume_prev, now=NOW)
    assert client.claims == 0
    assert client.heartbeats == 0
    assert client.fired == []
    assert client.proposed[0]["symbol"] == "ABCD"


def test_persist_migrates_volume_stub_settings():
    from bot import persist

    persist.reset_for_tests()
    persist._session_path().write_text(
        json.dumps(
            {
                "schema_version": 3,
                "level": 0,
                "armed": False,
                "pack_settings": {
                    BOT_PACK_VOLUME: {"enabled": False, "note": "stub -- no signal"}
                },
            }
        ),
        encoding="utf-8",
    )
    persist._session = None
    loaded = persist.load_session()
    settings = loaded["pack_settings"][BOT_PACK_VOLUME]
    assert settings["min_mult"] == BOT_VOLUME_MIN_MULT
    assert settings["volume_kind"] == "buy_market"
    persist.reset_for_tests()


def test_watch_exposes_shared_day_volume(monkeypatch):
    from bot.watch import halt_watch

    monkeypatch.setattr("bot.eligibility.eligible_symbols", lambda _row: ["ABCD"])
    monkeypatch.setattr(
        "ibkr.halt_status.snapshot",
        lambda _sym: {"halted": False},
    )
    monkeypatch.setattr(
        "bot.quotes.eyes_row",
        lambda _sym: {
            "symbol": "ABCD",
            "last": 1.25,
            "last_update_ts": 12.0,
            "bid": 1.24,
            "ask": 1.26,
            "volume": 44_000,
            "has_l1": True,
            "has_depth": True,
        },
    )
    monkeypatch.setattr("ibkr.account.long_qty", lambda _sym: 0.0)
    snap = halt_watch({"symbol_allowlist": ["ABCD"], "trader_live": ["ABCD"]})
    row = snap["symbols"][0]
    assert row["volume"] == 44_000
    assert row["last_update_ts"] == 12.0
