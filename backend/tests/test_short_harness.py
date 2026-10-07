"""The five-year test harness (ADR 049 step 4, ``research/shorts/``) on synthetic data: the universe without
hindsight, the walk with the scanner's own detectors and scoring, gate 1's account, the kill criteria, and the
result file the setup's card reads."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RESEARCH = Path(__file__).resolve().parents[2] / "research"
for folder in (RESEARCH / "shorts", RESEARCH / "orb"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import select_shorts as sel  # noqa: E402
import short_sim as sim  # noqa: E402
import shorts_config as cfg  # noqa: E402
import test_shorts as runner  # noqa: E402

from setup_scanner import short_tests  # noqa: E402
from setup_scanner.bars import Bar  # noqa: E402
from setup_scanner.lane_params import lane_params  # noqa: E402
from setup_templates.store import default_template  # noqa: E402
from tests.test_short_detectors import _backside_day, add  # noqa: E402

TODAY, YESTERDAY = "2026-10-07", "2026-10-06"


def mover(sym, **over):
    row = {"symbol": sym, "kind": "CS", "prev_close": 4.0, "prev_volume": 900_000, "volume": 500_000,
           "split_suspect": 0, "split_listed": 0, "up10_ts": 1_000, "low_pct": -0.02, "close": 4.4}
    row.update(over)
    return row


# -- the universe ------------------------------------------------------------------------------------------
def test_the_universe_follows_common_movers_at_1_to_20_dollars_with_volume_and_no_likely_split():
    today = [mover("AAA"), mover("BIG", prev_close=25.0), mover("WRNT", kind="WARRANT"),
             mover("ABCDE", kind=None), mover("THIN", volume=50_000), mover("NUL", kind=None),
             mover("SPLT", split_suspect=1, prev_volume=900_000, volume=500_000)]
    yesterday = [mover("AAA", low_pct=-0.12, prev_close=3.6), mover("OLD", close=5.0, low_pct=-0.05)]
    picked = sel.select({TODAY: today, YESTERDAY: yesterday}, {TODAY: YESTERDAY, YESTERDAY: None})
    mine = [p for p in picked if p[0] == TODAY]
    assert mine == [(TODAY, "AAA", 4.0, 1_000, True, True, True),        # yesterday's low -12%: SSR carries
                    (TODAY, "NUL", 4.0, 1_000, True, False, False),      # a 3-letter ticker with no type is common
                    (TODAY, "OLD", 5.0, None, False, True, False)]       # Former Momo: yesterday's close
    assert sel.ssr_from(None, True) is False and sel.ssr_from(None, False) is None
    assert sel.ssr_from(mover("X", low_pct=None), True) is None


def test_a_stock_is_followed_the_minute_after_it_met_both_conditions():
    t0 = 1_791_400_000 // 60 * 60
    bars = [Bar(t0 + 60 * i, 4.0, 4.1, 3.9, 4.0, 30_000) for i in range(8)]
    assert runner.follow_from(bars, t0 + 120 + 17, False) == t0 + 240     # +10% at minute 2, 100k by minute 3
    assert runner.follow_from(bars, t0 + 360, False) == t0 + 420          # the volume was there: the +10% decides
    assert runner.follow_from(bars, None, False) is None
    assert runner.follow_from(bars, None, True) == t0                     # Former Momo: from 04:00


# -- the walk: the scanner's own detector and scoring ------------------------------------------------------
def _breakdown_day() -> list[Bar]:
    bars = _backside_day()                                           # armed at 10:22: trigger 5.47, stop 5.56
    add(bars, 5.48, 5.49, 5.40, 5.41, 30_000)                        # 10:23: under the 5.46 entry
    add(bars, 5.41, 5.42, 5.25, 5.27, 30_000)                        # 10:24: target 1 (5.26), half covered
    add(bars, 5.27, 5.30, 5.20, 5.22, 20_000)
    add(bars, 5.22, 5.25, 5.18, 5.20, 20_000)
    return bars


def test_the_walk_takes_the_detectors_trigger_and_scores_it_the_scanners_way():
    params = lane_params(default_template("backside_lower_high"))
    bars = _breakdown_day()
    day = sim.StockDay("FADE", TODAY, 4.0, bars[0].t, False, tuple(bars))
    [trade] = sim.walk(day, params)
    assert (trade.entry, trade.stop, trade.risk) == (5.46, 5.56, pytest.approx(0.10))
    assert trade.target1 == pytest.approx(5.26) and trade.ssr == "off" and trade.kind == "backside_lower_high"
    assert trade.half_px == pytest.approx(5.26) and trade.exit_px == 5.20 and trade.exit_reason == "close"
    assert trade.gross_r == pytest.approx(0.5 * 2.0 + 0.5 * 2.6)
    later = sim.StockDay("FADE", TODAY, 4.0, bars[-3].t, False, tuple(bars))   # followed from 10:24
    taken = sim.walk(later, params)
    assert taken and all(t.triggered_at >= bars[-3].t for t in taken)   # never the 10:23 trigger it did not see
    assert [t.entry for t in taken] == [5.39]                          # the setup re-read at 10:23's bounce low
    assert sim.walk(sim.StockDay("FADE", TODAY, 4.0, bars[-1].t + 60, False, tuple(bars)), params) == []


def test_a_template_that_skips_ssr_takes_no_trade_armed_under_ssr():
    from setup_scanner.lane_params import LaneParams  # noqa: F401  -- the params are the lane's own
    import dataclasses

    params = dataclasses.replace(lane_params(default_template("backside_lower_high")), ssr="skip")
    bars = _breakdown_day()
    on = sim.StockDay("FADE", TODAY, 4.0, bars[0].t, True, tuple(bars))     # yesterday's SSR carries
    assert sim.walk(on, params) == []
    off = sim.StockDay("FADE", TODAY, 4.0, bars[0].t, False, tuple(bars))
    assert len(sim.walk(off, params)) == 1


# -- gate 1's account ----------------------------------------------------------------------------------------
def _won(d=TODAY, ts=1.0, exit_px=5.30) -> sim.Trade:
    return sim.Trade("FADE", d, "backside_lower_high", "off", ts, 5.46, 5.56, 5.26, 0.10, half_px=5.26,
                     exit_px=exit_px, exit_reason="ema", gross_r=1.8)


def test_a_short_is_sized_by_risk_capped_by_notional_and_pays_slippage_and_commission():
    t = sim.cost_trade(_won(), 25_000.0, sim.BASE)
    assert t.shares == 1144                                    # 25% of $25,000 at 5.46, under 1% risk's 2,500
    # 572 x 0.20 + 572 x 0.16 = 205.92 gross; 2 x 1144 x $0.01 slippage; $5.72 + $2.86 + $2.86 commission
    assert t.net_usd == pytest.approx(205.92 - 22.88 - 11.44) and t.net_r == pytest.approx(1.5)
    small = sim.cost_trade(sim.Trade("X", TODAY, None, "off", 1.0, 0.50, 0.90, 0.10, 0.40, exit_px=0.40), 25_000.0,
                           sim.BASE)
    assert small.skipped and small.net_usd is None             # 625 shares at $0.50: under the $500 minimum


def test_the_account_compounds_daily_and_the_best_year_is_taken_out():
    trades = [_won("2024-03-01"), _won("2025-03-01"), _won("2025-03-02", exit_px=5.60)]
    costed = sim.account(trades)
    assert costed[1].shares > costed[0].shares                 # the second day sized on the first day's gain
    s = sim.stats(costed)
    assert s["trades"] == 3 and set(s["by_year"]) == {"2024", "2025"}
    best = sim.best_year_removed(costed)
    assert best["year"] in ("2024", "2025") and best["ok"] == (best["exp_r"] > 0)


def test_a_run_with_no_losing_trade_writes_no_infinity():
    costed = sim.account([_won("2025-03-01"), _won("2025-03-02")])
    s = sim.stats(costed)
    assert s["pf"] is None and s["no_losses"] is True             # JSON has no infinity; the API could not serve it
    assert sim.stats([])["no_losses"] is False and sim.stats([])["pf"] is None


def test_the_permutation_moves_each_trade_to_a_random_minute_of_its_own_day():
    params = lane_params(default_template("backside_lower_high"))
    t0 = 1_791_389_700                                          # 2026-10-07 09:35 ET
    rising = tuple(Bar(t0 + 60 * i, 5.0 + 0.01 * i, 5.0 + 0.01 * i + 0.02, 5.0 + 0.01 * i - 0.005,
                       5.0 + 0.01 * i + 0.015, 10_000) for i in range(150))
    day = sim.StockDay("UP", TODAY, 4.0, rising[0].t, False, rising)
    won = sim.Trade("UP", TODAY, "backside_lower_high", "off", rising[5].t + 1, 5.05, 5.15, 4.85, 0.10,
                    half_px=4.85, exit_px=4.90, exit_reason="ema", gross_r=1.75)
    got = sim.shuffle([won], {("UP", TODAY): day}, params, shuffles=30, seed=1)
    assert got["shuffles"] == 30 and got["p"] == pytest.approx(1 / 31, abs=1e-4) and got["ok"] is True
    assert sim.shuffle([won], {("UP", TODAY): day}, params, shuffles=30, seed=1) == got   # seeded


# -- the rules under test and the result file -----------------------------------------------------------------
def test_neighbours_resolve_from_the_template_and_say_what_a_setup_lacks():
    assert runner.resolve({"stop_cap": "x0.75", "entry_cutoff": "-30", "target_r": 1.5},
                          {"stop_cap": 0.20, "entry_cutoff": "11:30", "target_r": 2.0}) == {
        "stop_cap": 0.15, "entry_cutoff": "11:00", "target_r": 1.5}
    rules, left_out = runner.variants(default_template("backside_lower_high"))
    names = [n for n, _ in rules]
    assert names[0] == "base" and "target 1.5R" in names and "fade 6%" in names and "no MACD rule" in names
    by = dict(rules)
    assert by["target 1.5R"].pattern.target_r == 1.5 and by["base"].pattern.target_r == 2.0
    assert by["window 30 min shorter"].pattern.entry_cutoff == "11:00"
    assert all("has no" in x for x in left_out)
    assert len(names) + len(left_out) == 1 + len(cfg.COMMON_NEIGHBOURS) + len(cfg.NEIGHBOURS["backside_lower_high"])


def test_the_result_file_is_what_the_setups_card_and_lock_read():
    template = default_template("bear_flag")
    result = runner.Result("bear_flag", template, "py -3 research/shorts/test_shorts.py --setup bear_flag", False)
    result.write(progress={"done": 3, "total": 10, "unit": "days"})
    short_tests.reset_for_tests()
    got = short_tests.test("bear_flag", template.fingerprint)
    assert got["state"] == "running" and got["text"] == "five-year test running: 3 of 10 days"
    assert got["rules_hash"] == template.fingerprint and got["matches"] is True
    result.write(progress={"done": 50, "total": 1000, "unit": "shuffles"})
    short_tests.reset_for_tests()
    assert short_tests.test("bear_flag", template.fingerprint)["text"] == "five-year test running: 50 of 1000 shuffles"
    result.write(state="passed", passed=True, progress=None, main={"trades": 412, "pf": 1.3, "exp_r": 0.11},
                 criteria={"costs_2x": {"pf": 1.1, "ok": True}, "permutation": {"p": 0.02, "ok": True}})
    short_tests.reset_for_tests()
    got = short_tests.test("bear_flag", template.fingerprint)
    assert got["state"] == "passed" and got["summary"]["trades"] == 412 and got["summary"]["p"] == 0.02
    assert short_tests.lock("bear_flag", template.fingerprint) is None
    assert not list(short_tests.folder().glob("*.tmp"))           # written through a rename


def test_the_criteria_judge_the_ssr_off_trades_and_count_the_neighbourhood(monkeypatch):
    monkeypatch.setattr(sim, "shuffle", lambda trades, days, params, progress=None: {
        "p": 0.01, "shuffles": 1000, "actual_exp_r": 1.0, "seed": 49, "ok": True})
    base = [_won(f"2025-01-{i + 1:02d}") for i in range(4)]
    under_ssr = sim.Trade("FADE", "2025-02-01", "backside_lower_high", "on", 1.0, 5.46, 5.56, 5.26, 0.10,
                          exit_px=5.56, exit_reason="stop", gross_r=-1.0)
    rules = [("base", None), ("n1", None), ("n2", None), ("n3", None)]
    by_variant = {"base": [*base, under_ssr], "n1": base, "n2": base, "n3": [under_ssr]}
    main, ssr_days, crit = runner.criteria("backside_lower_high", by_variant, lambda keys: {}, rules, None)
    assert main["trades"] == 4 and ssr_days["trades"] == 1
    assert crit["trades"] == {"value": 4, "need": cfg.MIN_TRADES, "ok": False}
    assert crit["neighbourhood"]["positive"] == 2 and crit["neighbourhood"]["total"] == 3
    assert crit["neighbourhood"]["ok"] is True and crit["costs_2x"]["ok"] is True
    main, ssr_days, _ = runner.criteria("ssr_bounce", {**by_variant}, lambda keys: {}, rules, None)
    assert main["trades"] == 5 and ssr_days is None                # the SSR bounce: one pool
