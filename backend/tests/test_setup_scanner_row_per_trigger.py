"""One setups.db row per trigger (ADR 022 amendment, 2026-10-02).

AMOD 2026-10-02: the first pullback triggered at 08:48:04 and was stopped at 08:48:13. At 08:49 a
candle tied the leg's high and the detector armed the same leg again as the second pullback. The lane
named rows by the leg, so the trade's row became ``second_pullback`` with the new levels, and the
read-out (first of the day) lost the trigger; LITS 2026-09-24 then triggered again on that id and the
first trade's score was gone. GOW 2026-09-30 triggered red to green twice on one id after its detector
was made again mid-day. These tests drive a real detector through each path.
"""
from __future__ import annotations

import asyncio

from bot.trigger_cells import triggers
from eyes.episodes import fold
from setup_scanner.engine import SetupEngine
from setup_scanner.pullback import PullbackDetector
from setup_scanner.red_to_green import RedToGreenDetector, RedToGreenParams
from setup_scanner.store import SetupStore
from tests.setup_scanner_fixtures import add, base_morning, leg_up
from tests.test_setup_scanner_detectors import morning_to_open
from tests.test_setup_scanner_engine import EYES, FP_ONLY, SYM, FakeTape, bar_msg


def armed_bars():
    """A leg to 4.39 and one pullback candle: armed on a 4.37 trigger, stop 4.30."""
    return add(leg_up(base_morning(), [4.08, 4.18, 4.28, 4.38]), 4.38, 4.37, 4.30, 4.32, 30_000)


def make(path, bars, journal=None):
    clock = {"t": bars[-1].t + 30}
    eng = SetupEngine(store=SetupStore(path), tape=FakeTape(), universe=lambda: [SYM],
                      seed=lambda sym, since: list(bars), replay_desk=lambda: False, audit=lambda **kw: None,
                      clock=lambda: clock["t"], journal=(journal if journal is not None else []).append,
                      bot_state=lambda: {"level": 1, "active": True, "venue": "paper"}, levels=EYES, setups=FP_ONLY)
    return eng, clock


def run(eng, now):
    asyncio.run(eng.tick(now))


def price(eng, clock, px, bar_open, dt=0.0):
    clock["t"] += dt
    eng.on_l1_minute("last", SYM, {"price": px, "ts": clock["t"], "bar_open": bar_open})
    run(eng, clock["t"])


def stored(eng) -> dict[str, dict]:
    return {r["id"]: r for r in eng.store.rows(template_id="default")}


def first_trade(eng, clock):
    """Near at 4.35, the trigger at 4.38, the stop at 4.30: stop first."""
    run(eng, clock["t"])
    price(eng, clock, 4.35, 4.32)
    price(eng, clock, 4.38, 4.32, dt=2)
    price(eng, clock, 4.30, 4.32, dt=5)


def test_a_trigger_then_a_rearm_on_the_same_leg_then_a_second_trigger_keeps_both_rows(tmp_path):
    bars = armed_bars()
    journal: list[dict] = []
    eng, clock = make(tmp_path / "setups.db", bars, journal)
    first_trade(eng, clock)
    det = eng.det[SYM]
    assert det.state == "triggered" and det.nth == 1
    leg_t = int(det.triggered["leg_t"])
    base = f"{SYM}-{eng.session}-{leg_t}"
    assert stored(eng)[base]["outcome"] == "stop_first"

    # The minute the trade ran in closes with a high that ties the leg's 4.39: the same leg arms again.
    tie = add(list(bars), 4.32, 4.39, 4.30, 4.37, 40_000)[-1]
    eng.on_l1_minute("bar", SYM, bar_msg(tie))
    clock["t"] = tie.t + 61
    run(eng, clock["t"])
    assert det.state == "armed" and int(det.armed["leg_t"]) == leg_t and det.armed["kind"] == "second_pullback"
    again = f"{SYM}-{eng.session}-{leg_t}#2"
    assert eng.active_id[SYM] == again

    rows = stored(eng)
    assert set(rows) == {base, again}
    first = rows[base]
    assert (first["kind"], first["state"], first["nth"]) == ("first_pullback", "triggered", 1)
    assert (first["trigger"], first["entry"], first["stop"]) == (4.37, 4.38, 4.30)
    assert first["outcome"] == "stop_first"
    assert (rows[again]["kind"], rows[again]["state"], rows[again]["trigger"]) == ("second_pullback", "armed", 4.39)
    assert rows[again]["triggered_at"] is None

    # The second setup comes near and triggers, then runs to its target.
    price(eng, clock, 4.37, 4.37)
    price(eng, clock, 4.40, 4.37, dt=2)
    assert det.state == "triggered" and det.nth == 2
    price(eng, clock, 4.65, 4.37, dt=5)

    rows = stored(eng)
    first, second = rows[base], rows[again]
    assert (first["kind"], first["nth"], first["entry"], first["outcome"]) == ("first_pullback", 1, 4.38, "stop_first")
    assert first["triggered_at"] < second["triggered_at"]
    assert (second["kind"], second["nth"], second["entry"], second["stop"]) == ("second_pullback", 2, 4.40, 4.30)
    assert second["outcome"] == "target_first"
    assert set(eng.trackers) == {base, again}                     # both trades are still scored

    # The journal names each trigger and each score by its own row.
    said = [(e["event"], e["setup_id"]) for e in journal if e.get("template") == "default"
            and e["event"] in ("triggered", "scored")]
    assert [s for e, s in said if e == "triggered"] == [base, again]
    scored = {e["setup_id"]: e["outcome"] for e in journal if e.get("event") == "scored"
              and e.get("template") == "default"}
    assert scored == {base: "stop_first", again: "target_first"}

    # The past setups and the triggers audit read two trades, each with its own score.
    eps = [e for e in fold(journal).episodes(SYM) if e["setup_id"]]
    assert [(e["setup_id"], (e["score"] or {}).get("outcome")) for e in eps] == [
        (base, "stop_first"), (again, "target_first")]
    got = triggers(journal)
    assert [(t["setup_id"], t["kind"], t["nth"], t["outcome"]) for t in got] == [
        (base, "first_pullback", 1, "stop_first"), (again, "second_pullback", 2, "target_first")]


def test_a_restart_never_writes_a_setup_over_a_stored_trade(tmp_path):
    bars = armed_bars()
    eng, clock = make(tmp_path / "setups.db", bars)
    first_trade(eng, clock)
    leg_t = int(eng.det[SYM].triggered["leg_t"])
    base = f"{SYM}-{eng.session}-{leg_t}"
    before = stored(eng)[base]

    # Nova restarts: a new engine on the same store seeds the same bars and the same leg arms.
    after, clock2 = make(tmp_path / "setups.db", bars)
    clock2["t"] = clock["t"]
    run(after, clock2["t"])
    det = after.det[SYM]
    assert det.nth == 1 and det.state == "armed" and det.armed["kind"] == "second_pullback"
    rows = stored(after)
    assert set(rows) == {base, f"{base}#2"}
    kept = rows[base]
    for col in ("kind", "state", "nth", "trigger", "entry", "stop", "triggered_at", "outcome", "outcome_at"):
        assert kept[col] == before[col], col
    assert rows[f"{base}#2"]["kind"] == "second_pullback"


def test_a_cold_start_reads_the_days_stored_triggers_once(tmp_path):
    """2026-10-07 13:12:27: a restart followed 101 symbols on 11 lanes and asked setups.db for each pair's
    stored triggers -- 1,111 queries at 1.9 ms, the HTTP loop held 2.3 s. The day is read once now."""
    bars = armed_bars()
    store = SetupStore(tmp_path / "setups.db")
    asked: list[str] = []
    store._conn.set_trace_callback(lambda sql: asked.append(sql) if "triggered_at IS NOT NULL" in sql else None)
    syms = [f"{SYM}{i}" for i in range(6)]
    clock = {"t": bars[-1].t + 30}
    eng = SetupEngine(store=store, tape=FakeTape(), universe=lambda: syms, seed=lambda sym, since: list(bars),
                      replay_desk=lambda: False, audit=lambda **kw: None, clock=lambda: clock["t"],
                      journal=[].append, bot_state=lambda: {"level": 1, "active": True, "venue": "paper"},
                      levels=EYES)
    run(eng, clock["t"])
    assert len(eng.lanes) > 1 and set(eng.bars) == set(syms)
    assert len(asked) == 1


def test_a_trigger_saved_after_the_days_read_is_still_a_stored_trade(tmp_path):
    bars = armed_bars()
    eng, clock = make(tmp_path / "setups.db", bars)
    run(eng, clock["t"])
    assert eng.stored_triggers(SYM, "default", "first_pullback") == []
    first_trade(eng, clock)
    base = f"{SYM}-{eng.session}-{int(eng.det[SYM].triggered['leg_t'])}"
    assert eng.stored_triggers(SYM, "default", "first_pullback") == [base]
    assert eng.stored_triggers(SYM, "other", "first_pullback") == []


def test_a_symbol_back_in_the_universe_starts_from_the_days_triggers(tmp_path):
    bars = armed_bars()
    eng, clock = make(tmp_path / "setups.db", bars)
    first_trade(eng, clock)
    lane = eng.playing
    base = lane.active_id[SYM]
    lane.drop(SYM)                                   # the symbol left the universe ...
    lane.on_bars(SYM, list(bars), clock["t"])        # ... and came back: a new detector, the same leg
    det = lane.det[SYM]
    assert det.nth == 1 and det.armed["kind"] == "second_pullback"
    assert lane.active_id[SYM] == f"{base}#2"
    assert stored(eng)[base]["kind"] == "first_pullback" and stored(eng)[base]["outcome"] == "stop_first"


def test_a_detector_made_mid_day_keeps_the_days_cap():
    bars = armed_bars()
    d = PullbackDetector(SYM)
    d.restore(1)
    assert [name for name, _ in d.on_bars(bars)] == ["armed"] and d.armed["kind"] == "second_pullback"
    used = PullbackDetector(SYM)
    used.restore(2)                                   # the first and the second already triggered today
    assert used.on_bars(bars) == [] and used.state == "watching" and "used" in used.reason
    assert used.on_price(4.50, bars[-1].t + 70) == []


def test_red_to_green_made_mid_day_after_its_trigger_has_no_try_left():
    bars = morning_to_open()
    open_px = bars[-1].c + 0.02
    add(bars, open_px, open_px + 0.01, open_px - 0.06, open_px - 0.04, 60_000)
    fresh = RedToGreenDetector("TEST", RedToGreenParams(macd_positive=False))
    assert [name for name, _ in fresh.on_bars(bars)] == ["armed"]       # a new detector would try again
    again = RedToGreenDetector("TEST", RedToGreenParams(macd_positive=False))
    again.restore(1)
    assert again.spent and again.on_bars(bars) == [] and again.state == "watching"
    assert again.on_price(open_px + 0.02, bars[-1].t + 70) == []
