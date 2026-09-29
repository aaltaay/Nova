"""Setups that ended (ADR 036 amendment, operator ask 2026-09-29): the eyes' journal folded into one
episode per setup's life on a symbol -- NCPL's bull flag, failed at 09:20 and gone at 09:21, is the case
the operator saw leave the chart -- and what price did after each one died."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from constants_bot import BOT_SCANNER_SETUPS
from eyes import aftermath
from eyes.episodes import closed_bar_t, fold, reason_key
from eyes.journal_day import JournalTail
from eyes.replay import EyesReplay
from setup_scanner.bars import Bar
from setup_templates.store import TemplateStore, default_template, set_store_for_tests
from tests.test_eyes import _pillars, recording

ET = ZoneInfo("America/New_York")
DAY = "2026-09-29"
POLE = {"t": 0.0, "high": 1.35, "low": 1.27, "pct": 0.063, "bars": 3}


def at(h: int, m: int, s: float = 0.0) -> float:
    return datetime(2026, 9, 29, h, m, tzinfo=ET).timestamp() + s


def line(event: str, ts: float, sym: str = "NCPL", lane: str = "bull_flag", **kw) -> dict:
    return {"schema_version": 1, "event": event, "ts": ts, "date": DAY, "source": "live", "symbol": sym,
            "setup_type": lane, "template": "default", "rev": 1, "playing": True, **kw}


def ncpl_lines() -> list[dict]:
    """NCPL's bull flag lines of 2026-09-29, as the lane wrote them."""
    pole = {**POLE, "t": at(9, 17)}
    return [
        line("leg", at(9, 18, 0.28), reason="pole: 3 green candles, +6.3% to 1.35 -- wait for the flag", leg=pole),
        line("state", at(9, 19, 0.3), state="leg", leg=pole,
             reason="pole +6.3% to 1.35; 1 red candle so far -- a flag needs 2 (one is a micro pullback)"),
        line("state", at(9, 20, 0.42), state="failed", leg=pole,
             reason="flag candle 2 made a higher high than the candle before it"),
        line("state", at(9, 21, 0.3), state="watching", reason="no pole", leg=None),
    ]


def test_a_failed_pole_is_one_episode_that_keeps_the_rule_it_broke_and_when():
    [ep] = fold(ncpl_lines()).episodes("NCPL")
    assert ep["end"] == "failed" and ep["reached"] == "leg"
    assert ep["died_at"] == at(9, 20, 0.42) and ep["died_bar_t"] == at(9, 19)   # the candle that broke it
    assert ep["ended_at"] == at(9, 21, 0.3) and ep["ended_by"] == "no pole"
    assert ep["reason"] == "flag candle 2 made a higher high than the candle before it"
    assert ep["reason_key"] == "flag candle # made a higher high than the candle before it"
    assert ep["leg"]["high"] == 1.35 and ep["setup"] is None


def test_a_failed_setup_is_past_from_the_moment_it_failed_and_keeps_its_first_rule():
    lines = ncpl_lines()[:3] + [line("state", at(9, 21, 0.3), state="failed", leg={**POLE, "t": at(9, 17)},
                                     reason="the flag gave back 61.9% of the pole -- more than 50%")]
    [ep] = fold(lines).episodes("NCPL")
    assert ep["end"] is None and ep["died_at"] == at(9, 20, 0.42) and ep["died_bar_t"] == at(9, 19)
    assert ep["reason"] == "flag candle 2 made a higher high than the candle before it"


def test_a_leg_that_extends_is_one_episode_and_a_lower_later_one_is_another():
    leg1 = {"t": at(9, 30), "high": 5.0, "low": 4.5, "pct": 0.11}
    leg2 = {"t": at(9, 31), "high": 5.2, "low": 4.5, "pct": 0.155}
    lower = {"t": at(9, 40), "high": 4.9, "low": 4.6, "pct": 0.065}
    setup = {"trigger": 5.1, "entry": 5.11, "stop": 4.95, "risk": 0.16, "target1": 5.43, "leg_t": at(9, 31)}
    f = fold([
        line("leg", at(9, 31, 0.2), lane="first_pullback", leg=leg1, reason="new high 5.00 on a 11% leg"),
        line("state", at(9, 32, 0.2), lane="first_pullback", state="leg", leg=leg2, reason="new high 5.20"),
        line("armed", at(9, 33, 0.2), lane="first_pullback", leg=leg2, setup_id="NCPL-2026-09-29-1",
             setup=setup, reason="trigger 5.10, stop 4.95, risk 0.16"),
        line("state", at(9, 41, 0.2), lane="first_pullback", state="leg", leg=lower, reason="new high 4.90"),
    ])
    first, second = f.episodes()
    assert first["leg"]["high"] == 5.2 and first["reached"] == "armed" and first["setup"]["trigger"] == 5.1
    assert first["end"] == "faded" and first["reason"] == "trigger 5.10, stop 4.95, risk 0.16"
    assert first["ended_by"] == "a new attempt began: new high 4.90"
    assert first["died_bar_t"] == at(9, 40)
    assert second["end"] is None and second["leg"]["high"] == 4.9


def test_a_try_after_a_failure_is_a_new_episode_and_a_score_finds_its_trade_after_it_ended():
    leg = {"t": at(9, 30), "high": 5.0, "low": 4.5, "pct": 0.11}
    newer = {"t": at(9, 36), "high": 5.3, "low": 4.8, "pct": 0.1}
    trig = {"trigger": 5.3, "entry": 5.31, "stop": 5.2, "risk": 0.11, "target1": 5.53, "triggered_at": at(9, 38, 12)}
    f = fold([
        line("state", at(9, 31, 0.2), lane="first_pullback", state="failed", leg=leg, reason="gave back half the leg"),
        line("leg", at(9, 37, 0.2), lane="first_pullback", leg=newer, reason="new high 5.30"),
        line("triggered", at(9, 38, 12), lane="first_pullback", leg=newer, setup_id="S1", setup=trig, price=5.32,
             reason="traded 5.32 over the 5.30 trigger"),
        line("leg", at(9, 45, 0.2), lane="first_pullback", leg={**newer, "t": at(9, 44), "high": 5.5}, reason="x"),
        line("scored", at(9, 50), lane="first_pullback", setup_id="S1", outcome="target_first", bar_r=1.4,
             exit_reason="ema", mfe=0.25, mae=-0.02),
    ])
    failed, traded, newest = f.episodes()
    assert failed["end"] == "failed" and failed["ended_by"].startswith("a new attempt began")
    assert traded["end"] == "triggered" and traded["triggered_at"] == at(9, 38, 12) and traded["trigger_price"] == 5.32
    assert traded["score"] == {"outcome": "target_first", "bar_r": 1.4, "exit_reason": "ema", "mfe": 0.25,
                               "mae": -0.02}
    assert newest["end"] is None


def test_a_restart_cuts_a_setup_whose_end_was_open_and_keeps_one_that_had_failed():
    leg = {"t": at(9, 30), "high": 5.0, "low": 4.5, "pct": 0.11}
    f = fold([
        line("state", at(9, 31), lane="first_pullback", state="failed", leg=leg, reason="gave back half the leg"),
        line("leg", at(9, 31), sym="ABCD", lane="flat_top_breakout", leg=leg, reason="new high of day 5.00"),
        {"schema_version": 1, "event": "session", "ts": at(9, 35), "date": DAY, "source": "live", "symbol": None},
    ])
    ends = {e["symbol"]: (e["end"], e["ended_by"]) for e in f.episodes()}
    assert ends == {"NCPL": ("failed", "Nova restarted: the eyes began again"),
                    "ABCD": ("cut", "Nova restarted: the eyes began again")}


def test_only_the_template_in_play_counts_and_an_old_line_is_the_first_pullback():
    leg = {"t": at(9, 30), "high": 5.0, "low": 4.5, "pct": 0.11}
    other = line("state", at(9, 31), state="failed", leg=leg, reason="x")
    other["playing"] = False
    old = line("state", at(9, 31), state="failed", leg=leg, reason="gave back half the leg")
    del old["setup_type"]
    [ep] = fold([other, old]).episodes()
    assert ep["setup_type"] == "first_pullback"


def test_the_words_and_the_candle():
    assert reason_key("a base candle closed more than 2% under the 1.43 high") == \
        "a base candle closed more than #% under the # high"
    assert reason_key("the pole's volume fell (402,542 on its last candle, 624,545 on its first)") == \
        "the pole's volume fell (# on its last candle, # on its first)"
    assert closed_bar_t(at(9, 20, 0.4)) == at(9, 19)     # a bar close: the candle that just closed
    assert closed_bar_t(at(9, 17, 4.0)) == at(9, 17)     # between closes: the candle forming


def test_the_lanes_own_lines_fold_into_the_setup_they_traded(tmp_path):
    set_store_for_tests(TemplateStore(tmp_path / "t.json"))
    lines: list[dict] = []
    rep = EyesReplay(recording(), [default_template(s) for s in BOT_SCANNER_SETUPS], source="sim",
                     playing={s: "default" for s in BOT_SCANNER_SETUPS}, journal=lines.append, pillars=_pillars)
    rep.run_to_end()
    [trigger] = [e for e in lines if e["event"] == "triggered" and e["setup_type"] == "first_pullback"]
    eps = [e for e in fold(lines).episodes() if e["setup_type"] == "first_pullback"]
    [traded] = [e for e in eps if e["setup_id"] == trigger["setup_id"]]
    assert traded["reached"] == "triggered" and traded["setup"]["trigger"] == trigger["setup"]["trigger"]
    assert traded["started_at"] < trigger["ts"]


def test_the_tail_hands_each_line_out_once_and_never_a_half_written_one(tmp_path):
    path = tmp_path / f"{DAY}.jsonl"
    tail = JournalTail(path, DAY)
    assert tail.read() == [] and not tail.exists
    import json

    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(ncpl_lines()[0]) + "\n" + '{"schema_version": 1, "ev')
    assert [r["event"] for r in tail.read()] == ["leg"]
    with path.open("a", encoding="utf-8") as fh:
        fh.write('ent": "beat", "ts": 1, "date": "%s", "source": "live"}\n' % DAY)
    assert [r["event"] for r in tail.read()] == ["beat"] and tail.read() == []


# -- what price did next -------------------------------------------------------------------------------

def bars(*rows: tuple[int, int, float, float, float, float]) -> list[Bar]:
    return [Bar(at(h, m), o, hi, lo, c, 1000.0) for h, m, o, hi, lo, c in rows]


NCPL_BARS = bars(
    (9, 15, 1.27, 1.30, 1.27, 1.30), (9, 16, 1.30, 1.33, 1.29, 1.33), (9, 17, 1.33, 1.35, 1.32, 1.35),
    (9, 18, 1.35, 1.35, 1.31, 1.32), (9, 19, 1.32, 1.39, 1.32, 1.33),          # the flag: 1.39 over 1.35
    (9, 20, 1.33, 1.38, 1.33, 1.37), (9, 21, 1.37, 1.43, 1.36, 1.42),
)


def ncpl_episode() -> dict:
    return fold(ncpl_lines()).episodes("NCPL")[0]


def test_after_a_failed_pole_price_went_over_its_high_first_and_the_refused_trade_is_scored():
    a = aftermath.after(ncpl_episode(), NCPL_BARS, now=at(9, 22))
    assert (a["level"], a["entry"], a["floor"], a["price"]) == (1.35, 1.36, 1.31, 1.33)
    assert a["first"] == "high" and a["crossed_at"] == at(9, 20) and not a["complete"]
    t = a["trade"]
    assert (t["entry"], t["stop"], t["risk"], t["target"]) == (1.36, 1.31, 0.05, 1.46)
    assert t["outcome"] == "open" and t["mfe_r"] == 1.4 and t["mae_r"] == 0.0


def test_a_candle_that_broke_both_ways_counts_the_low_and_a_quiet_window_is_neither():
    both = NCPL_BARS[:5] + bars((9, 20, 1.33, 1.40, 1.30, 1.34))
    assert aftermath.after(ncpl_episode(), both, now=at(10, 0))["first"] == "low"
    quiet = NCPL_BARS[:5] + bars((9, 20, 1.33, 1.34, 1.32, 1.33))
    assert aftermath.after(ncpl_episode(), quiet, now=at(10, 0))["first"] == "neither"
    assert aftermath.after(ncpl_episode(), quiet, now=at(9, 21))["first"] == "pending"
    assert aftermath.after(ncpl_episode(), NCPL_BARS[:5], now=at(10, 0))["first"] == "unknown"


def test_a_gap_over_the_level_buys_the_open_and_the_first_touch_is_the_target_or_the_stop():
    gap = NCPL_BARS[:5] + bars((9, 20, 1.38, 1.40, 1.37, 1.39), (9, 21, 1.39, 1.52, 1.39, 1.50))
    t = aftermath.after(ncpl_episode(), gap, now=at(10, 0))["trade"]
    assert t["entry"] == 1.38 and t["target"] == 1.52 and t["outcome"] == "target_first"
    # The crossing candle counts its stop only on a close under it (the scoreboard's entry bar) ...
    dip = NCPL_BARS[:5] + bars((9, 20, 1.33, 1.37, 1.33, 1.36), (9, 21, 1.36, 1.36, 1.30, 1.31))
    assert aftermath.after(ncpl_episode(), dip, now=at(10, 0))["trade"]["outcome"] == "stop_first"
    # ... and a later candle that touches both counts the stop.
    whip = NCPL_BARS[:5] + bars((9, 20, 1.33, 1.37, 1.33, 1.36), (9, 21, 1.36, 1.47, 1.30, 1.40))
    assert aftermath.after(ncpl_episode(), whip, now=at(10, 0))["trade"]["outcome"] == "stop_first"


def test_an_armed_setup_is_measured_on_its_own_levels_and_red_to_green_on_its_open():
    ep = {**ncpl_episode(), "setup": {"trigger": 1.34, "entry": 1.35, "stop": 1.3, "risk": 0.05, "target1": 1.5}}
    a = aftermath.after(ep, NCPL_BARS, now=at(10, 0))
    assert (a["level"], a["entry"], a["floor"]) == (1.34, 1.35, 1.3) and a["trade"]["target"] == 1.5
    r2g = {**ncpl_episode(), "setup_type": "red_to_green", "leg": {"t": at(9, 30), "high": 2.17, "low": 2.05}}
    a = aftermath.after(r2g, NCPL_BARS, now=at(10, 0))
    assert (a["level"], a["floor"]) == (2.17, 2.05)


def test_nothing_is_measured_for_a_setup_that_did_not_die():
    traded = {**ncpl_episode(), "end": "triggered", "died_at": None}
    assert aftermath.after(traded, NCPL_BARS, now=at(10, 0)) is None
    alive = {**ncpl_episode(), "end": None, "died_at": None}
    assert aftermath.after(alive, NCPL_BARS, now=at(10, 0)) is None
