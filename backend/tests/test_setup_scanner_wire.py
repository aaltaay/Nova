"""The setup scanner's edges (ADR 022): the minute-bar hook it listens on, and
numbers that are not facts -- IBKR's NaN sizes, a snapshot's NaN RVOL -- which
must never become a verdict, a failed pillar or a bare NaN on the socket."""
from __future__ import annotations

import asyncio
import json
import math
from types import SimpleNamespace

import archive.db as archive_db
import archive.write_queue as wq
import ibkr.l1_minute as l1_minute
from scanner_wire import dumps_wire
from setup_scanner import grade as grade_mod
from setup_scanner.engine import SetupEngine
from setup_scanner.store import SetupStore
from setup_scanner.tape_gate import evaluate
from tests.setup_scanner_fixtures import base_morning, leg_up
from tests.test_setup_scanner_engine import SYM, FakeTape

NAN = float("nan")


def _fresh_minutes(monkeypatch, tmp_path):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    l1_minute.reset_for_tests()


def test_l1_minute_listener_hears_every_last_and_each_closed_bar(monkeypatch, tmp_path):
    _fresh_minutes(monkeypatch, tmp_path)
    heard: list[tuple[str, str, dict]] = []
    listener = lambda kind, sym, payload: heard.append((kind, sym, payload))  # noqa: E731
    l1_minute.add_listener(listener)
    try:
        t0 = 1_700_000_040.0
        l1_minute.on_last("abcd", 4.00, t0)
        l1_minute.on_last("abcd", 4.20, t0 + 5)
        l1_minute.on_last("abcd", 4.10, t0 + 60)      # next minute closes the first
    finally:
        l1_minute.remove_listener(listener)
    lasts = [p for k, _, p in heard if k == "last"]
    bars = [p for k, _, p in heard if k == "bar"]
    assert [p["price"] for p in lasts] == [4.00, 4.20, 4.10]
    assert lasts[1]["bar_open"] == 4.00                # the open of the minute it traded in
    assert len(bars) == 1
    assert (bars[0]["o"], bars[0]["h"], bars[0]["l"], bars[0]["c"]) == (4.00, 4.20, 4.00, 4.20)
    assert all(sym == "ABCD" for _, sym, _ in heard)


def test_a_failing_listener_never_costs_the_chart_its_bar(monkeypatch, tmp_path):
    _fresh_minutes(monkeypatch, tmp_path)

    def broken(kind, sym, payload):
        raise RuntimeError("listener bug")

    l1_minute.add_listener(broken)
    try:
        l1_minute.on_last("abcd", 4.00, 1_700_000_040.0)
        l1_minute.on_last("abcd", 4.10, 1_700_000_100.0)
    finally:
        l1_minute.remove_listener(broken)
    assert wq.pending() == 1


def test_tape_gate_drops_nan_levels_and_prints():
    now = 1_000.0
    book = {"bids": [{"price": 4.35, "size": 4000}],
            "asks": [{"price": 4.37, "size": NAN}, {"price": NAN, "size": 900_000}, {"price": 4.38, "size": 2000}]}
    prints = [{"ts": now - 2 + i * 0.3, "size": 300, "side": "ask"} for i in range(4)]
    prints.append({"ts": now - 1, "size": NAN, "side": "bid"})
    out = evaluate(trigger=4.37, now=now, books=[(now - 5, book), (now - 0.2, book)], prints=prints)
    assert out["verdict"] == "go"                      # the NaN 900k "seller" is not a fact
    assert not any("seller" in r and "900" in r for r in out["reasons"])
    assert out["metrics"]["bid_volume"] == 0
    assert all(not (isinstance(v, float) and not math.isfinite(v)) for v in out["metrics"].values())


def test_a_nan_pillar_is_unknown_not_failed(monkeypatch):
    import hod_momo
    import scanner_news_badge

    snap = SimpleNamespace(price=4.35, change_pct=38.0, rvol=NAN, float_shares=float("inf"))
    monkeypatch.setattr(hod_momo, "get_ticker_snapshot", lambda sym: snap)
    monkeypatch.setattr(scanner_news_badge, "headline_for", lambda sym: None)
    pillars = grade_mod.read_pillars(SYM)
    assert pillars["rvol"] is None and pillars["float"] is None
    letter, checks = grade_mod.grade(pillars)
    assert checks["rvol"] is None
    assert letter == "C"


def test_board_frame_states_a_nan_as_null(tmp_path):
    bars = leg_up(base_morning(), [4.08, 4.18, 4.28, 4.38])
    clock = {"t": bars[-1].t + 30}
    eng = SetupEngine(store=SetupStore(tmp_path / "setups.db"), tape=FakeTape(),
                      universe=lambda: [SYM], seed=lambda sym, since: list(bars),
                      replay_desk=lambda: False, audit=lambda **kw: None, clock=lambda: clock["t"])
    asyncio.run(eng.tick(clock["t"]))
    eng.tape_view[SYM] = {"verdict": "blind", "reasons": [], "line": None, "metrics": {"spread": NAN}}
    frame = dumps_wire({"type": "board", **eng.board(clock["t"])})
    row = json.loads(frame)["rows"][0]
    assert row["tape"]["metrics"]["spread"] is None
