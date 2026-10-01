"""The 5-minute chart's read on a 1-minute setup (trial T8, operator ask 2026-09-30): made on the clock from
the session's closed minutes, recorded when a setup arms and when it triggers, shown on its row, split on
the scoreboard -- and gating nothing."""
from __future__ import annotations

import sqlite3

from setup_scanner import five_minute
from setup_scanner.bars import Bar
from setup_scanner.store import SetupStore
from setup_scanner.summary import summarize
from setup_templates.store import TemplateStore
from tests.setup_scanner_fixtures import et_ts
from tests.test_setup_scanner_engine import SYM
from tests.test_setup_scanner_lanes import armed_bars, make, run
from constants_setups import SETUPS_DB_SCHEMA_VERSION


def minutes(hh: int, mm: int, closes: list[float], v: float = 1_000) -> list[Bar]:
    t0 = et_ts(hh, mm)
    return [Bar(t0 + 60 * i, c, c + 0.01, c - 0.01, c, v) for i, c in enumerate(closes)]


def test_five_minute_candles_are_on_the_clock_from_four_and_complete_once_their_minutes_are_over():
    bars = minutes(3, 58, [1.0, 1.0]) + minutes(4, 0, [2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6])   # 04:00 .. 04:06
    done = five_minute.candles(bars, now=et_ts(4, 7))
    assert [c["t"] for c in done] == [et_ts(4, 0)]               # 04:05 is still forming; 03:58 is yesterday's side
    assert (done[0]["o"], done[0]["c"], done[0]["v"]) == (2.0, 2.4, 5_000)
    assert five_minute.context(bars, now=et_ts(4, 4)) is None   # no complete candle yet: unknown
    assert len(five_minute.candles(bars, now=et_ts(4, 10))) == 2


def test_the_five_minute_chart_agrees_over_its_9_ema_with_the_macd_up_and_not_otherwise():
    rising = minutes(4, 0, [2.0 + 0.01 * i for i in range(120)])
    up = five_minute.context(rising, now=et_ts(6, 0))
    assert up["agrees"] is True and up["above_ema9"] and up["macd_up"] and up["candles"] == 24
    assert up["as_of"] == et_ts(5, 55) and up["close"] == round(rising[-1].c, 4)
    falling = minutes(4, 0, [4.0 - 0.01 * i for i in range(120)])
    down = five_minute.context(falling, now=et_ts(6, 0))
    assert down["agrees"] is False and not down["above_ema9"] and not down["macd_up"]
    assert five_minute.verdict(up) == "agrees" and five_minute.verdict(down) == "against"
    assert five_minute.verdict(None) == "unknown" and five_minute.verdict({"agrees": None}) == "unknown"


def test_a_setup_records_the_five_minute_read_when_it_arms_and_when_it_triggers(tmp_path):
    eng, _audits, journal, clock = make(tmp_path, armed_bars(), TemplateStore(tmp_path / "t.json"))
    run(eng, clock["t"])
    lane = eng.playing
    row = next(iter(lane.rows.values()))
    assert isinstance(row["tf5_armed"], dict) and isinstance(row["tf5_armed"]["agrees"], bool)
    armed = next(e for e in journal if e["event"] == "armed")
    assert armed["tf5"] == row["tf5_armed"]
    board = next(r for r in lane.board_rows(clock["t"]) if r["symbol"] == SYM)
    assert board["tf5"] == row["tf5_armed"] and board["tf5_at"] == "armed"

    trigger = float(row["trigger"])
    eng.on_l1_minute("last", SYM, {"price": trigger + 0.02, "ts": clock["t"] + 5, "bar_open": trigger - 0.02})
    run(eng, clock["t"] + 5)
    assert row["triggered_at"] and row["tf5_trigger"] == lane.tf5[SYM]
    fired = next(e for e in journal if e["event"] == "triggered")
    assert fired["tf5"] == row["tf5_trigger"]
    board = next(r for r in lane.board_rows(clock["t"] + 5) if r["symbol"] == SYM)
    assert board["tf5_at"] == "trigger" and board["tf5"] == row["tf5_trigger"]
    stored = next(r for r in eng.store.rows() if r["id"] == row["id"])
    assert stored["tf5_armed"] == row["tf5_armed"] and stored["tf5_trigger"] == row["tf5_trigger"]


def test_the_scoreboard_splits_by_the_five_minute_chart_at_the_trigger():
    rows = [{"armed_at": 1.0, "triggered_at": 2.0, "bar_r": 1.0, "risk": 0.1, "tf5_trigger": {"agrees": True}},
            {"armed_at": 1.0, "triggered_at": 2.0, "bar_r": -1.0, "risk": 0.1, "tf5_trigger": {"agrees": False}},
            {"armed_at": 1.0, "triggered_at": 2.0, "bar_r": -1.0, "risk": 0.1, "tf5_trigger": None}]
    by = summarize(rows)["by"]["tf5_at_trigger"]
    assert {k: v["avg_r"] for k, v in by.items()} == {"agrees": 1.0, "against": -1.0, "unknown": -1.0}


def test_a_schema_3_scoreboard_gains_the_five_minute_columns_and_its_rows_read_unknown(tmp_path):
    path = tmp_path / "setups.db"
    store = SetupStore(path)
    store.upsert({"id": "OLD", "session_date": "2026-09-29", "symbol": "OLD", "armed_at": 1.0})
    store.close()
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE s2 AS SELECT * FROM setups")
    con.execute("DROP TABLE setups")
    cols = ", ".join(c for c in (r[1] for r in con.execute("PRAGMA table_info(s2)")) if not c.startswith("tf5_"))
    con.execute(f"CREATE TABLE setups AS SELECT {cols} FROM s2")
    con.execute("DROP TABLE s2")
    con.execute("PRAGMA user_version = 3")
    con.commit()
    con.close()
    store = SetupStore(path)
    row = store.rows()[0]
    assert row["id"] == "OLD" and row["tf5_armed"] is None and row["tf5_trigger"] is None
    assert sqlite3.connect(path).execute("PRAGMA user_version").fetchone()[0] == SETUPS_DB_SCHEMA_VERSION


def test_the_plan_says_what_the_five_minute_chart_says_and_never_warns():
    from stock_read.plan import checks

    plan = {"entry": 4.40, "stop": 4.30, "risk": 0.10, "target": 4.60}
    against = {"agrees": False, "above_ema9": False, "macd_up": True, "ema9": 4.45}
    got = next(c for c in checks(plan, {"tf5": against}) if c["id"] == "tf5")
    assert got == {"id": "tf5", "state": "info", "text": "5m against: under its 9 EMA 4.45, MACD up (trial T8)"}
    agrees = {"agrees": True, "above_ema9": True, "macd_up": True, "ema9": 4.31}
    got = next(c for c in checks(plan, {"tf5": agrees}) if c["id"] == "tf5")
    assert got["state"] == "info" and got["text"].startswith("5m agrees: over its 9 EMA 4.31, MACD up")
    assert not any(c["id"] == "tf5" for c in checks(plan, {"tf5": None}))
