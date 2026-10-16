"""IBKR capacity (desk-ops.md, "IBKR capacity on the desk"): what the strip reads, and who comes first."""
from __future__ import annotations

import asyncio

import pytest

from ibkr import capacity, historical_service, l1_refused
from ibkr.historical_pacing import HistoricalPacing, kind_of


def test_pacing_names_what_spent_the_window():
    clock = {"t": 1000.0}
    p = HistoricalPacing(now_fn=lambda: clock["t"])
    for sym, key in (("AAPL", "1Min"), ("AAPL", "ticks:TRADES"), ("XLK", "1Day:rth"), ("CONTFUT:ES", "ref:5 mins")):
        p.record(sym, key, "d")
        clock["t"] += 3
    assert p.snapshot()["by_kind"] == {"charts": 1, "tape": 1, "daily": 1, "market": 1}
    clock["t"] += 601
    assert p.snapshot()["by_kind"] == {"charts": 0, "tape": 0, "daily": 0, "market": 0}
    assert kind_of("bars:1min:TRADES") == "tape" and kind_of("1Day:all") == "daily"


def test_the_view_reads_every_cap(monkeypatch):
    from ibkr import tape_admission, ticks
    from line_lending import view as lending_view

    monkeypatch.setattr(ticks, "ticker_budget_status", lambda: {
        "reqMktData_lines": 48, "reqMktData_limit": 100, "reqMktData_cap": 53, "reqMktData_refused": 0,
        "reqMktData_by_owner": {"scanner": 45, "hod": 23, "live_trader": 2, "depth": 0}})
    monkeypatch.setattr(lending_view, "build", lambda: {"cap": 3, "lines": [{"symbol": "AAPL", "held_by": "tab"}]})
    monkeypatch.setattr(historical_service, "pacing_snapshot", lambda: {
        "window_used": 60, "window_max": 60, "window_sec": 600.0, "next_token_wait_sec": 102.5,
        "by_kind": {"charts": 5, "tape": 10, "daily": 40, "market": 5}})
    monkeypatch.setattr(tape_admission, "view", lambda: {"limit": None, "used": 4, "active": ["AAPL", "NFLX"],
                                                          "pending": [], "uncertain": []})
    v = capacity.view(now=1.0)
    assert v["l1"] == {"used": 48, "cap": 53, "cap_learned": True, "reserve": 5, "refused": 0,
                       "by_owner": {"scanner": 45, "hod": 23, "live_trader": 2}}
    assert v["l2"] == {"used": 1, "cap": 3, "symbols": [{"symbol": "AAPL", "held_by": "tab"}]}
    assert v["history"]["used"] == 60 and v["history"]["next_free_sec"] == 102.5
    assert v["tape"] == {"used": 4, "cap": None, "symbols": ["AAPL", "NFLX"]}


def test_a_refused_bot_line_is_asked_again_before_the_scanners():
    subs = {s: {"owners": {o}, "refused": {"at": i, "retry_at": 0.0}} for i, (s, o) in
            enumerate((("HODX", "hod"), ("SCAN", "scanner"), ("TSLA", "live_trader")))}
    assert l1_refused.due(subs, now=1.0)[0] == "TSLA"


def test_a_background_chart_fill_leaves_the_last_requests(monkeypatch):
    import bars_store

    historical_service.reset_for_testing()
    monkeypatch.setattr(bars_store, "read", lambda *a, **k: None)
    monkeypatch.setattr(historical_service, "assert_ib_loop", lambda: None)
    monkeypatch.setattr(historical_service, "_left", lambda: 10)
    with pytest.raises(historical_service.HistoricalShed, match="kept for open charts"):
        asyncio.run(historical_service.request_bars("AAPL", "1Min", 100, priority="background"))


def test_fills_admitted_together_recheck_the_reserve_before_they_send(monkeypatch):
    """Codex review, PR #1021: fills that all passed the first check at 11 left must not spend the reserve."""
    import bars_store
    from ibkr import bars as ibkr_bars

    historical_service.reset_for_testing()
    monkeypatch.setattr(bars_store, "read", lambda *a, **k: None)
    monkeypatch.setattr(bars_store, "write_payload", lambda *a, **k: None)   # never the desk's own bar store
    monkeypatch.setattr(historical_service, "assert_ib_loop", lambda: None)
    left = {"n": 11}
    monkeypatch.setattr(historical_service, "_left", lambda: left["n"])
    sent: list[str] = []

    async def fetch(symbol, timeframe, limit, interactive=False):
        sent.append(symbol)
        left["n"] -= 1
        return {"symbol": symbol, "timeframe": timeframe, "bars": []}

    monkeypatch.setattr(ibkr_bars, "fetch_bars_async", fetch)

    async def both():
        return await asyncio.gather(
            *(historical_service.request_bars(s, "1Min", 100, priority="background") for s in ("AAA", "BBB")),
            return_exceptions=True)

    got = asyncio.run(both())
    assert sent == ["AAA"]
    assert isinstance(got[1], historical_service.HistoricalShed)
