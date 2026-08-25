"""hod_tick_feed.py -- extracted HOD active-set tick feed (file-size-limits.mdc)."""
from __future__ import annotations

import hod_momo_active as _hod_active
import hod_tick_feed


def test_feed_hod_on_tick_calls_on_trade_update_for_active_symbol(monkeypatch):
    monkeypatch.setattr(_hod_active, "get_active_symbols", lambda: ["AAA"])
    monkeypatch.setattr(_hod_active, "note_quote", lambda *a, **k: None)
    monkeypatch.setattr("ibkr.ticks.get_day_high", lambda sym: 10.0)
    monkeypatch.setattr("ibkr_bridge._archive_l1_tick", lambda *a, **k: None)

    captured = {}
    monkeypatch.setattr(
        hod_tick_feed._hod_momo, "on_trade_update",
        lambda sym, price, ts, *, volume=None, day_high=None: captured.update(
            symbol=sym, price=price, day_high=day_high,
        ),
    )

    hod_tick_feed.feed_hod_on_tick("AAA", 9.5, 1000, 111.0)

    assert captured["symbol"] == "AAA"
    assert captured["price"] == 9.5
    assert captured["day_high"] == 10.0


def test_feed_hod_on_tick_skips_symbol_not_in_active_set(monkeypatch):
    monkeypatch.setattr(_hod_active, "get_active_symbols", lambda: ["ZZZ"])
    called = []
    monkeypatch.setattr(
        hod_tick_feed._hod_momo, "on_trade_update",
        lambda *a, **k: called.append(True),
    )

    hod_tick_feed.feed_hod_on_tick("AAA", 9.5, 1000, 111.0)

    assert called == []
