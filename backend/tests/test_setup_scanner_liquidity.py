"""Too thin to trade (operator decision 2026-10-01, on LPA: "there's no way I will ever trade something like
that with a 20-cent spread ... the volume is almost dead").

LPA's numbers are the morning's own: the leaderboard's day volume and price at its 09:41 first-pullback
trigger, the five minutes before it, and the Level 2 book its 08:43 Session Record kept.
"""
from __future__ import annotations

import asyncio
import sqlite3

from constants_setups import SETUPS_DB_SCHEMA_VERSION
from eyes.lane_fold import LaneFold
from setup_scanner import liquidity
from setup_scanner.readout import evaluate as readout
from setup_scanner.store import SetupStore
from setup_scanner.summary import summarize
from setup_scanner.trade_verdict import of_event, verdict
from setup_templates.store import TemplateStore
from tests.setup_scanner_fixtures import add, base_morning, et_ts, leg_up
from tests.test_setup_scanner_engine import SYM
from tests.test_setup_scanner_lanes import PILLARS, make

LPA_TRIGGER = et_ts(9, 41, "2026-10-01")
# The book LPA's Session Record kept at 08:44: 100 shares at the inside, the next offer 18 cents up.
LPA_ASKS = [{"price": 3.12, "size": 100, "mm": "NSDQ"}, {"price": 3.30, "size": 100, "mm": "ARCA"},
            {"price": 3.33, "size": 200, "mm": "EDGX"}, {"price": 3.41, "size": 200, "mm": "NSDQ"},
            {"price": 3.47, "size": 230, "mm": "MEMX"}]


def test_lpa_at_its_first_trigger_was_too_thin_three_ways():
    qty = liquidity.size_for(20.0, 0.06)                 # the desk's $20 risk per trade over a 6-cent risk
    book = liquidity.walk(LPA_ASKS, qty)
    r = liquidity.judge(day=999_309.0, pace=42_539.0, now=LPA_TRIGGER, book=book, risk=0.06)
    assert qty == 333
    assert book["best_ask"] == 3.12 and book["last"] == 3.33 and not book["short"]
    assert round(book["over_ask"], 2) == 0.14            # 14 cents over the ask on average: 2.3R
    assert r["state"] == "thin" and r["failed"] == ["day", "pace", "book"]
    assert r["reasons"][0] == "traded $999K today, under $2.00M"
    assert r["reasons"][1] == "$43K in the last 5 minutes, under $100K"
    assert r["reasons"][2].startswith("buying 333 shares walks the asks to 3.33: 14c over the 3.12 ask")
    assert liquidity.headline(r).startswith("too thin to trade: traded $999K today")


def test_a_liquid_runner_reads_ok():
    deep = [{"price": 7.10, "size": 4_000}, {"price": 7.11, "size": 9_000}]
    r = liquidity.judge(day=64_090_000.0, pace=7_147_000.0, now=LPA_TRIGGER, book=liquidity.walk(deep, 500), risk=0.10)
    assert r["state"] == "ok" and r["reasons"] == [] and r["walk"]["r"] == 0.0
    assert liquidity.headline(r) is None


def test_a_check_nova_cannot_make_is_unknown_never_thin_never_ok():
    r = liquidity.judge(day=None, pace=500_000.0, now=LPA_TRIGGER)
    assert r["state"] == "unknown" and r["reasons"] == [] and "day" in r["unknown"]
    # ... but a failing check still says thin: one known failure is enough.
    assert liquidity.judge(day=None, pace=10_000.0, now=LPA_TRIGGER)["state"] == "thin"


def test_the_day_is_its_volume_at_the_average_price_of_todays_minutes():
    from setup_scanner.bars import Bar

    now = et_ts(9, 41, "2026-10-01")
    bars = [Bar(et_ts(3, 59, "2026-10-01"), 9, 9, 9, 9.0, 1_000_000),   # before 04:00: yesterday's evening
            Bar(et_ts(9, 30, "2026-10-01"), 2, 2, 2, 2.0, 100), Bar(et_ts(9, 31, "2026-10-01"), 4, 4, 4, 4.0, 300)]
    assert liquidity.day_dollars(1_000, bars, now) == 3_500.0
    assert liquidity.day_dollars(None, bars, now) is None
    assert liquidity.day_dollars(1_000, [], now, price=3.0) == 3_000.0          # no minute yet: the last price


def test_the_pace_counts_the_closed_minutes_in_its_window():
    end = et_ts(9, 41, "2026-10-01")
    bars = [{"t": end - 360, "c": 3.0, "v": 1_000_000}, {"t": end - 300, "c": 3.0, "v": 10_000},
            {"t": end - 60, "c": 3.27, "v": 1_000}, {"t": end, "c": 3.29, "v": 18_150}]   # the forming minute
    assert liquidity.pace_dollars(bars, end) == 3.0 * 10_000 + 3.27 * 1_000


def test_the_walk_sums_venue_rows_and_a_short_book_under_the_limit_is_unknown():
    book = liquidity.walk([{"price": 5.00, "size": 100}, {"price": 5.00, "size": 200}, {"price": 5.01, "size": 100}],
                          1_000)
    assert book["shown"] == 400 and book["short"] and book["last"] == 5.01
    r = liquidity.judge(day=5e6, pace=5e5, now=LPA_TRIGGER, book=book, risk=0.10)
    assert r["state"] == "ok" and "book" in r["unknown"]                     # 0.25c over the ask: not judged thin


def test_a_thin_stock_is_not_a_trade_for_every_reader():
    thin = liquidity.judge(day=999_309.0, pace=42_539.0, now=LPA_TRIGGER)
    judged = verdict(grade="A", liquidity=thin)
    assert not judged["ok"] and judged["reasons"][0].startswith("too thin to trade: traded $999K today")
    assert verdict(grade="A", liquidity=liquidity.judge(day=5e6, pace=5e5, now=LPA_TRIGGER))["ok"]
    event = {"grade": "A", "setup": {"risk": 0.06}, "tape": {"verdict": "go"}, "liquidity": thin}
    assert not of_event(event)["ok"]


def _armed(tmp_path, volume):
    eng, audits, journal, clock = make(tmp_path, add(leg_up(base_morning(), [4.08, 4.18, 4.28, 4.38]),
                                                      4.38, 4.37, 4.30, 4.32, 30_000),
                                       TemplateStore(tmp_path / "t.json"))
    eng.pillars = lambda sym, now: {**PILLARS, "volume": volume}
    eng.risk_usd = lambda: 20.0
    asyncio.run(eng.tick(clock["t"]))
    return eng, audits, journal, clock


def test_a_thin_stock_arms_on_the_record_but_never_proposes_and_its_trigger_says_not_a_trade(tmp_path):
    eng, audits, journal, clock = _armed(tmp_path, volume=10_000)            # $43K traded all day
    eng.on_l1_minute("last", SYM, {"price": 4.35, "ts": clock["t"], "bar_open": 4.32})
    asyncio.run(eng.tick(clock["t"]))
    row = eng.board(clock["t"])["rows"][0]
    assert row["state"] == "near" and row["liquidity"]["state"] == "thin"
    assert eng.playing.tape_view[SYM]["verdict"] == "go" and eng.proposals == {}       # go, and still no proposal
    assert not [a for a in audits if a.get("action") == "setup_proposal"]
    armed = next(e for e in journal if e["event"] == "armed" and e["template"] == "default")
    assert armed["liquidity"]["state"] == "thin" and armed["liquidity"]["failed"] == ["day"]
    heard: list[dict] = []
    eng.add_trigger_listener(heard.append)
    eng.on_l1_minute("last", SYM, {"price": 4.39, "ts": clock["t"] + 1, "bar_open": 4.32})
    asyncio.run(eng.tick(clock["t"] + 1))
    [event] = heard
    assert event["liquidity"]["state"] == "thin" and not of_event(event)["ok"]
    stored = next(r for r in eng.store.rows() if r["template_id"] == "default")
    assert stored["triggered_at"] and stored["liquidity"]["state"] == "thin"            # still scored, kept thin


def test_a_liquid_stock_proposes_as_before(tmp_path):
    eng, _audits, _journal, clock = _armed(tmp_path, volume=2_000_000)        # $8.6M traded today
    eng.on_l1_minute("last", SYM, {"price": 4.35, "ts": clock["t"], "bar_open": 4.32})
    asyncio.run(eng.tick(clock["t"]))
    assert eng.board(clock["t"])["rows"][0]["liquidity"]["state"] == "ok"
    assert len(eng.proposals) == 1


def test_a_changed_verdict_at_a_closed_minute_is_journalled_and_the_playback_folds_it(tmp_path):
    from setup_scanner.bars import Bar
    from tests.test_setup_scanner_engine import bar_msg

    volume = {"v": 10_000}
    eng, _audits, journal, clock = _armed(tmp_path, volume=10_000)
    eng.pillars = lambda sym, now: {**PILLARS, "volume": volume["v"]}
    volume["v"] = 2_000_000                                                  # the stock wakes up
    last = eng.bars[SYM].completed[-1]
    nxt = Bar(last.t + 60, 4.32, 4.34, 4.31, 4.33, 40_000)
    clock["t"] = nxt.t + 61
    eng.on_l1_minute("bar", SYM, bar_msg(nxt))
    asyncio.run(eng.tick(clock["t"]))
    lines = [e for e in journal if e["event"] == "liquidity" and e["template"] == "default"]
    assert [ln["liquidity"]["state"] for ln in lines] == ["ok"]
    fold = LaneFold("first_pullback", "default")
    for e in journal:
        if e.get("template") == "default" and e.get("symbol") == SYM:
            fold.apply(e["event"], SYM, e, e["ts"])
    [row] = fold.board_rows(clock["t"], {SYM: 4.33})
    assert row["liquidity"]["state"] == eng.board(clock["t"])["rows"][0]["liquidity"]["state"] == "ok"


def _row(rid, verdict_at, liquid, r):
    return {"id": rid, "kind": "first_pullback", "triggered_at": 1_000.0 + len(rid), "risk": 0.10, "bar_r": r,
            "outcome": "target_first" if r > 0 else "stop_first", "trigger_tape": {"verdict": verdict_at},
            "liquidity": None if liquid is None else {"state": liquid}}


def test_the_read_out_leaves_out_thin_triggers_and_counts_them():
    rows = [_row("a", "go", "ok", 1.0), _row("bb", "go", "thin", -1.0), _row("ccc", "blind", "thin", -1.0),
            _row("dddd", "blind", None, 0.5)]
    out = readout(rows)
    assert out["thin_left_out"] == 2
    assert out["go"]["triggered"] == 1 and out["control"]["triggered"] == 1
    by = summarize(rows)["by"]["liquidity"]
    assert {k: v["triggered"] for k, v in by.items()} == {"ok": 1, "thin": 2, "unknown": 1}


def test_a_schema_4_scoreboard_is_migrated_and_its_rows_carry_no_reading(tmp_path):
    from setup_scanner.store import COLUMNS, _type

    path = tmp_path / "setups.db"
    con = sqlite3.connect(path)
    v4 = [c for c in COLUMNS[3:] if c != "liquidity"]
    con.executescript("CREATE TABLE setups (id TEXT PRIMARY KEY, session_date TEXT NOT NULL, symbol TEXT NOT NULL, "
                      + ", ".join(f"{c} {_type(c)}" for c in v4) + ");"
                      "INSERT INTO setups (id, session_date, symbol, kind, armed_at) VALUES ('OLD', '2026-09-30', 'X',"
                      " 'first_pullback', 1);")
    con.execute("PRAGMA user_version = 4")
    con.commit()
    con.close()
    store = SetupStore(path)
    [row] = store.rows()
    assert row["liquidity"] is None
    store.upsert({"id": "NEW", "session_date": "2026-10-01", "symbol": "LPA", "armed_at": 2.0,
                  "liquidity": {"state": "thin", "reasons": ["traded $999K today, under $2.00M"]}})
    assert next(r for r in store.rows() if r["id"] == "NEW")["liquidity"]["state"] == "thin"
    assert sqlite3.connect(path).execute("PRAGMA user_version").fetchone()[0] == SETUPS_DB_SCHEMA_VERSION == 5


def test_the_traders_plan_reads_a_thin_stock_as_not_a_trade_and_the_in_play_tile_says_so():
    from stock_read import plan as plan_mod
    from stock_read import plan_liquidity
    from stock_read import read as read_mod
    from tests.test_setup_scanner_grade_visible import AVAT_LANE, CTX, TRIGGERED_AT

    lane = {**AVAT_LANE, "state": "near", "grade": "B", "distance": 0.01, "trigger_tape": None,
            "tape": {"verdict": "go", "reasons": []}, "outcome": None, "outcome_at": None, "bar_r": None,
            "pillars": {"checks": {"price": True, "change": True, "rvol": True, "news": False, "float": True}}}
    m0 = TRIGGERED_AT // 60 * 60
    bars = [{"t": m0 - 60 * i, "o": 1.99, "h": 1.99, "l": 1.99, "c": 1.99, "v": 2_000} for i in range(5, 0, -1)]
    ctx = {**CTX, "spread": 0.01, "bars": bars, "volume": 300_000, "risk_usd": 20.0,
           "asks": [{"price": 1.99, "size": 100}, {"price": 2.08, "size": 100}]}
    plan = plan_mod.build([lane], ctx, now=TRIGGERED_AT)
    assert plan["liquidity"]["state"] == "thin" and plan["liquidity"]["failed"] == ["day", "pace", "book"]
    assert plan["checks"][0]["id"] == "liquidity" and plan["checks"][0]["state"] == "bad"
    assert plan["trade"]["ok"] is False and plan["trade"]["reasons"][-1].startswith("too thin to trade: traded $597K")
    row = plan_liquidity.row(plan["liquidity"])
    assert row["value"] == "Too thin" and row["state"] == "bad"
    assert read_mod._verdict("in_play", [row], {}, plan) == ("bad", "Too thin")


def test_stored_minutes_that_stop_early_leave_the_pace_unknown():
    from stock_read import plan_liquidity

    now = et_ts(9, 50, "2026-10-01")
    bars = [{"t": now - 600 - 60 * i, "c": 3.0, "v": 100} for i in range(5)]     # the store stops ten minutes ago
    r = plan_liquidity.read({"bars": bars, "volume": 1_000_000, "price": 3.0}, now)
    assert r["pace_dollars"] is None and r["unknown"]["pace"] == "the chart's minutes stop 9 minutes ago"
    assert r["state"] == "unknown"                                                # $3.0M today, pace unknown
