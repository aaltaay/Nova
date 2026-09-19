"""Quote-spike pack -- fixtures only, never places live IBKR orders."""
from __future__ import annotations

import json

import pytest

from bot.packs import assert_pack_can_fire, catalog, default_pack_settings, merge_pack_settings
from constants_bot import (
    BOT_PACK_QUOTE_SPIKE,
    BOT_QUOTE_SPIKE_COOLDOWN_SEC,
    BOT_QUOTE_SPIKE_MIN_PCT,
    BOT_QUOTE_SPIKE_WINDOW_SEC,
)
from nova_brain.loop import step
from nova_brain.quote_spike import detect_spikes, quote_px, tick


def _watch(*rows: dict) -> dict:
    return {"symbols": list(rows)}


def test_catalog_marks_quote_spike_live():
    rows = {row["id"]: row for row in catalog()}
    assert rows[BOT_PACK_QUOTE_SPIKE]["status"] == "live"
    assert rows["volume"]["status"] == "live"
    assert "stub" not in rows[BOT_PACK_QUOTE_SPIKE]["description"].lower()
    assert "3%" in rows[BOT_PACK_QUOTE_SPIKE]["description"]
    assert_pack_can_fire(BOT_PACK_QUOTE_SPIKE)
    assert_pack_can_fire("volume")


def test_default_pack_settings_define_the_signal():
    settings = default_pack_settings()[BOT_PACK_QUOTE_SPIKE]
    assert settings["spike_kind"] == "buy_market"
    assert settings["min_pct"] == BOT_QUOTE_SPIKE_MIN_PCT
    assert settings["window_sec"] == BOT_QUOTE_SPIKE_WINDOW_SEC
    assert settings["cooldown_sec"] == BOT_QUOTE_SPIKE_COOLDOWN_SEC
    assert "stub" not in str(settings).lower()


def test_merge_pack_settings_replaces_stub_blob():
    merged = merge_pack_settings(
        {BOT_PACK_QUOTE_SPIKE: {"enabled": False, "note": "stub -- no signal logic yet"}}
    )
    assert merged[BOT_PACK_QUOTE_SPIKE]["min_pct"] == BOT_QUOTE_SPIKE_MIN_PCT
    assert merged[BOT_PACK_QUOTE_SPIKE]["spike_kind"] == "buy_market"


def test_quote_px_prefers_mid_when_both_sides_exist():
    assert quote_px({"last": 2.0, "bid": 1.0, "ask": 3.0}) == 2.0
    assert quote_px({"last": 1.5}) == 1.5
    assert quote_px({"last": None, "bid": None, "ask": None}) is None
    assert quote_px({"last": 0, "bid": 0, "ask": 0}) is None


def test_detect_spikes_last_print_up_in_window():
    prev = {"ABCD": {"samples": [{"ts": 96.0, "quote": 1.0}], "spiked": False}}
    watch = _watch({"symbol": "ABCD", "last": 1.04, "last_update_ts": 100.0})
    spikes, nxt = detect_spikes(prev, watch, now=100.0, window_sec=5.0, min_pct=3.0)
    assert spikes == ["ABCD"]
    assert nxt["ABCD"]["spiked"] is True


def test_detect_spikes_uses_mid_not_last_when_book_exists():
    prev = {"ABCD": {"samples": [{"ts": 96.0, "quote": 1.0}], "spiked": False}}
    watch = _watch(
        {
            "symbol": "ABCD",
            "last": 1.01,
            "bid": 1.03,
            "ask": 1.05,
            "last_update_ts": 100.0,
        }
    )
    spikes, nxt = detect_spikes(prev, watch, now=100.0, window_sec=5.0, min_pct=3.0)
    assert spikes == ["ABCD"]
    assert nxt["ABCD"]["samples"][-1]["quote"] == pytest.approx(1.04)


def test_detect_spikes_ignores_down_move_and_sub_threshold():
    prev = {
        "DOWN": {"samples": [{"ts": 96.0, "quote": 1.0}], "spiked": False},
        "FLAT": {"samples": [{"ts": 96.0, "quote": 1.0}], "spiked": False},
    }
    watch = _watch(
        {"symbol": "DOWN", "last": 0.90, "last_update_ts": 100.0},
        {"symbol": "FLAT", "last": 1.02, "last_update_ts": 100.0},
    )
    spikes, nxt = detect_spikes(prev, watch, now=100.0, window_sec=5.0, min_pct=3.0)
    assert spikes == []
    assert nxt["DOWN"]["spiked"] is False
    assert nxt["FLAT"]["spiked"] is False


def test_detect_spikes_outside_window_is_not_a_spike():
    prev = {"ABCD": {"samples": [{"ts": 90.0, "quote": 1.0}], "spiked": False}}
    watch = _watch({"symbol": "ABCD", "last": 1.10, "last_update_ts": 100.0})
    spikes, _nxt = detect_spikes(prev, watch, now=100.0, window_sec=5.0, min_pct=3.0)
    assert spikes == []


def test_detect_spikes_rising_edge_only():
    prev = {
        "ABCD": {
            "samples": [{"ts": 96.0, "quote": 1.0}, {"ts": 99.0, "quote": 1.04}],
            "spiked": True,
        }
    }
    watch = _watch({"symbol": "ABCD", "last": 1.05, "last_update_ts": 100.0})
    spikes, nxt = detect_spikes(prev, watch, now=100.0, window_sec=5.0, min_pct=3.0)
    assert spikes == []
    assert nxt["ABCD"]["spiked"] is True


def test_tick_fires_once_with_cooldown():
    fired: list[tuple[str, str]] = []
    proposed: list[dict] = []
    session = {
        "active_pack": BOT_PACK_QUOTE_SPIKE,
        "level": 2,
        "live_fire_ready": True,
        "pack_settings": {
            BOT_PACK_QUOTE_SPIKE: {
                "spike_kind": "buy_market",
                "min_pct": 3.0,
                "window_sec": 5.0,
                "cooldown_sec": 30,
            }
        },
    }
    watch = _watch({"symbol": "ABCD", "last": 1.04, "last_update_ts": 100.0})
    prev = {"ABCD": {"samples": [{"ts": 96.0, "quote": 1.0}], "spiked": False}}
    nxt = tick(
        session=session,
        watch=watch,
        previous=prev,
        last_fire={},
        now=100.0,
        fire=lambda kind, symbol: fired.append((kind, symbol)),
        propose=lambda body: proposed.append(body),
    )
    assert fired == [("buy_market", "ABCD")]
    assert proposed == []
    assert nxt["ABCD"]["spiked"] is True
    tick(
        session=session,
        watch=watch,
        previous={"ABCD": {"samples": [{"ts": 96.0, "quote": 1.0}], "spiked": False}},
        last_fire={"ABCD": 90.0},
        now=100.0,
        fire=lambda kind, symbol: fired.append((kind, symbol)),
        propose=lambda body: proposed.append(body),
    )
    assert fired == [("buy_market", "ABCD")]


def test_tick_proposes_at_eyes_and_skips_when_not_active_l2():
    fired: list[tuple[str, str]] = []
    proposed: list[dict] = []
    watch = _watch({"symbol": "ABCD", "last": 1.04, "last_update_ts": 100.0})
    prev = {"ABCD": {"samples": [{"ts": 96.0, "quote": 1.0}], "spiked": False}}
    tick(
        session={
            "active_pack": BOT_PACK_QUOTE_SPIKE,
            "level": 1,
            "live_fire_ready": False,
            "pack_settings": {BOT_PACK_QUOTE_SPIKE: {"min_pct": 3.0, "window_sec": 5.0}},
        },
        watch=watch,
        previous=prev,
        last_fire={},
        now=100.0,
        fire=lambda kind, symbol: fired.append((kind, symbol)),
        propose=lambda body: proposed.append(body),
    )
    assert fired == []
    assert proposed[0]["symbol"] == "ABCD"
    assert proposed[0]["side"] == "BUY"
    assert proposed[0]["kind"] == "buy_market"
    assert "quote spike" in proposed[0]["reason"].lower()

    proposed.clear()
    tick(
        session={
            "active_pack": BOT_PACK_QUOTE_SPIKE,
            "level": 2,
            "live_fire_ready": False,
            "pack_settings": {BOT_PACK_QUOTE_SPIKE: {"min_pct": 3.0, "window_sec": 5.0}},
        },
        watch=watch,
        previous={"ABCD": {"samples": [{"ts": 96.0, "quote": 1.0}], "spiked": False}},
        last_fire={},
        now=100.0,
        fire=lambda kind, symbol: fired.append((kind, symbol)),
        propose=lambda body: proposed.append(body),
    )
    assert fired == []
    assert proposed == []


def test_tick_wrong_pack_leaves_state():
    prev = {"ABCD": {"samples": [{"ts": 1.0, "quote": 1.0}], "spiked": False}}
    out = tick(
        session={"active_pack": "halt-luld", "live_fire_ready": True},
        watch=_watch({"symbol": "ABCD", "last": 9.0, "last_update_ts": 10.0}),
        previous=prev,
        last_fire={},
        now=10.0,
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

    def health(self) -> dict:
        return {"status": "ok"}

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


def test_step_quote_spike_l2_claims_and_fires():
    client = _FakeClient(
        {
            "level": 2,
            "armed": True,
            "active_pack": BOT_PACK_QUOTE_SPIKE,
            "live_fire_ready": True,
            "pack_settings": {BOT_PACK_QUOTE_SPIKE: {"min_pct": 3.0, "window_sec": 5.0}},
        },
        watch=_watch({"symbol": "ABCD", "last": 1.04, "last_update_ts": 100.0}),
    )
    quote_prev = {"ABCD": {"samples": [{"ts": 96.0, "quote": 1.0}], "spiked": False}}
    last_fire: dict[str, float] = {}
    step(
        client,
        halt_prev={},
        last_fire=last_fire,
        quote_prev=quote_prev,
        now=100.0,
    )
    assert client.claims == 1
    assert client.heartbeats == 1
    assert client.fired == [("buy_market", "ABCD")]
    assert client.proposed == []
    assert quote_prev["ABCD"]["spiked"] is True


def test_step_quote_spike_eyes_proposes_without_claim():
    client = _FakeClient(
        {
            "level": 1,
            "armed": False,
            "active_pack": BOT_PACK_QUOTE_SPIKE,
            "live_fire_ready": False,
            "pack_settings": {BOT_PACK_QUOTE_SPIKE: {"min_pct": 3.0, "window_sec": 5.0}},
        },
        watch=_watch({"symbol": "ABCD", "last": 1.04, "last_update_ts": 100.0}),
    )
    quote_prev = {"ABCD": {"samples": [{"ts": 96.0, "quote": 1.0}], "spiked": False}}
    step(client, halt_prev={}, last_fire={}, quote_prev=quote_prev, now=100.0)
    assert client.claims == 0
    assert client.heartbeats == 0
    assert client.fired == []
    assert client.proposed[0]["symbol"] == "ABCD"


def test_persist_migrates_quote_spike_stub_settings():
    from bot import persist

    persist.reset_for_tests()
    persist._session_path().write_text(
        json.dumps(
            {
                "schema_version": 3,
                "level": 0,
                "armed": False,
                "pack_settings": {
                    BOT_PACK_QUOTE_SPIKE: {"enabled": False, "note": "stub -- no signal"}
                },
            }
        ),
        encoding="utf-8",
    )
    persist._session = None
    loaded = persist.load_session()
    settings = loaded["pack_settings"][BOT_PACK_QUOTE_SPIKE]
    assert settings["min_pct"] == BOT_QUOTE_SPIKE_MIN_PCT
    assert settings["spike_kind"] == "buy_market"
    persist.reset_for_tests()


def test_watch_exposes_shared_quote_fields(monkeypatch):
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
            "has_l1": True,
            "has_depth": True,
        },
    )
    monkeypatch.setattr("ibkr.account.long_qty", lambda _sym: 0.0)
    snap = halt_watch({"symbol_allowlist": ["ABCD"], "trader_live": ["ABCD"]})
    row = snap["symbols"][0]
    assert row["last"] == 1.25
    assert row["bid"] == 1.24
    assert row["ask"] == 1.26
    assert row["last_update_ts"] == 12.0
