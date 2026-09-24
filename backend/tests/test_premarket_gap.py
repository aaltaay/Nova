"""The premarket gap is never yesterday's open (operator report, 2026-09-24).

GCTK at 07:45 ET: the Stock Quote read $4.13 +103.46% on the 2.03 prior close,
while the Focus rail (Gappers) read +9.9% and never moved as the price did.
IBKR's open tick (14) is "the current session's opening price; before open
will refer to previous day", so (2.231 - 2.03) / 2.03 = +9.9% was yesterday's
open-to-close move. Every L1 patch carried it onto the Gappers row; every
Gappers roster replace put the real move back -- the flicker.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

import ibkr.open_tick as open_tick
import ibkr.scanner_l1 as scanner_l1
from ibkr import gapper_view
from ibkr.quote_rows import mover_row_from_quote, reprice_mover_row
from ibkr.ticks_handler import on_ticker_update
from market import ET, regular_session_opened_at

PREV_CLOSE = 2.03
YESTERDAY_OPEN = 2.231  # (2.231 - 2.03) / 2.03 = the rail's frozen +9.9%
PREMARKET = datetime(2026, 9, 24, 7, 45, tzinfo=ET)  # Thursday
AFTER_OPEN = datetime(2026, 9, 24, 9, 31, tzinfo=ET)


def _at(monkeypatch, when: datetime) -> None:
    monkeypatch.setattr(open_tick, "now_et", lambda: when)


@pytest.mark.parametrize(("when", "opened"), [
    (PREMARKET, False),
    (datetime(2026, 9, 24, 9, 29, tzinfo=ET), False),
    (datetime(2026, 9, 24, 9, 30, tzinfo=ET), True),
    (datetime(2026, 9, 24, 18, 0, tzinfo=ET), True),
    (datetime(2026, 9, 26, 11, 0, tzinfo=ET), False),   # Saturday
    (datetime(2026, 11, 26, 11, 0, tzinfo=ET), False),  # Thanksgiving
])
def test_today_has_an_open_only_once_the_regular_session_opened(when, opened):
    assert regular_session_opened_at(when) is opened


def test_the_open_tick_is_not_todays_open_before_0930(monkeypatch):
    _at(monkeypatch, PREMARKET)
    assert open_tick.todays_open(YESTERDAY_OPEN) is None
    _at(monkeypatch, AFTER_OPEN)
    assert open_tick.todays_open(4.20) == 4.20
    assert open_tick.todays_open(None) is None
    assert open_tick.todays_open(0.0) is None


def _ticker(**kw):
    base = dict(last=None, close=None, open=None, volume=None, high=None, lastTimestamp=None,
                rtTime=None, time=None, lastSize=None, rtVolume=None, ticks=[])
    return SimpleNamespace(**{**base, **kw})


def test_the_streaming_line_hands_on_no_open_in_premarket(monkeypatch):
    opens: list = []

    def listener(symbol, price, volume, prev_close, ts, *, quote_quality=None, open_price=None, last_size=None):
        opens.append(open_price)

    def update(last: float) -> None:
        on_ticker_update(
            _ticker(last=last, close=PREV_CLOSE, open=YESTERDAY_OPEN), "GCTK",
            subs={"GCTK": {"last_price": None}}, quote_listeners=[listener],
            find_cache_row=None, broadcast=None, owner_detail="detail",
        )

    _at(monkeypatch, PREMARKET)
    update(4.13)
    _at(monkeypatch, AFTER_OPEN)
    update(4.16)
    assert opens == [None, YESTERDAY_OPEN]


def test_a_premarket_gainer_row_has_no_gap_and_moves_with_its_price():
    row = mover_row_from_quote("GCTK", {"price": 4.13, "prev_close": PREV_CLOSE, "volume": 10, "open": None})
    assert row["gap_percent"] is None
    assert round(row["change_pct"], 4) == round((4.13 - PREV_CLOSE) / PREV_CLOSE, 4)  # +103.45%
    later = reprice_mover_row(row, {"price": 4.16, "prev_close": PREV_CLOSE, "volume": 20})
    assert later["gap_percent"] is None
    assert later["change_pct"] > row["change_pct"]


def test_todays_open_replaces_an_open_the_row_kept_from_before():
    """A row restored from a snapshot written before the fix holds yesterday's open."""
    stale = {"symbol": "GCTK", "prev_close": PREV_CLOSE, "open": YESTERDAY_OPEN,
             "gap_percent": (YESTERDAY_OPEN - PREV_CLOSE) / PREV_CLOSE}
    out = reprice_mover_row(stale, {"price": 4.30, "prev_close": PREV_CLOSE, "volume": 1, "open": 4.20})
    assert out["open"] == 4.20
    assert round(out["gap_percent"], 4) == round((4.20 - PREV_CLOSE) / PREV_CLOSE, 4)


def test_a_mover_row_built_from_a_quote_keeps_the_scan_arithmetic():
    row = mover_row_from_quote("CRE", {"price": 6.77, "prev_close": 2.57, "volume": 10, "open": 3.0,
                                       "exchange": "NASDAQ"})
    assert row == {
        "symbol": "CRE", "price": 6.77, "change_pct": (6.77 - 2.57) / 2.57, "change_abs": 6.77 - 2.57,
        "volume": 10, "gap_percent": (3.0 - 2.57) / 2.57, "prev_close": 2.57, "open": 3.0,
        "exchange": "NASDAQ",
    }


def test_a_gappers_patch_carries_the_move_other_tables_pass_through():
    patch = {"symbol": "GCTK", "price": 4.16, "change_pct": 1.0493, "gap_percent": 0.099}
    assert gapper_view.patch_for_table("gappers", patch)["gap_percent"] == 1.0493
    assert gapper_view.patch_for_table("gainers", patch) is patch
    bare = {"symbol": "GCTK", "price": 4.16}
    assert gapper_view.patch_for_table("gappers", bare) is bare


def test_flush_sends_the_gappers_table_its_own_gap(monkeypatch):
    scanner_l1._pending.clear()
    scanner_l1._pending_started_ns = None
    scanner_l1._active_tab_tables.clear()
    scanner_l1._active_tab_tables.update({"GCTK": "gappers", "SRZN": "gainers"})
    scanner_l1._pending["GCTK"] = {"symbol": "GCTK", "price": 4.16, "change_pct": 1.0493, "gap_percent": 0.099}
    scanner_l1._pending["SRZN"] = {"symbol": "SRZN", "price": 20.59, "change_pct": 0.27, "gap_percent": 0.2}
    monkeypatch.setattr(scanner_l1, "IBKR_L1_BATCH_FLUSH_SEC", 0.01)
    pushed: list[dict] = []

    async def push(payload):
        pushed.append(payload)

    async def run():
        task = asyncio.create_task(scanner_l1.flush_loop(push))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
    scanner_l1._active_tab_tables.clear()
    rows = {p["table"]: p["rows"][0] for p in pushed}
    assert rows["gappers"]["gap_percent"] == 1.0493
    assert rows["gainers"]["gap_percent"] == 0.2
