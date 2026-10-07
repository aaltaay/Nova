"""One stock's LULD state machine (ADR 047): the Plan's reference rules, applied to a tape and a quote."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from luld.tracker import Facts, Options, Tracker

ET = ZoneInfo("America/New_York")
DAY = "2026-09-22"   # a Tuesday


def t(hms: str, day: str = DAY) -> float:
    return datetime.fromisoformat(f"{day}T{hms}").replace(tzinfo=ET).timestamp()


def make(start: str = "09:00:00", prev: float | None = 9.0, tier: int | None = 2, **opts) -> Tracker:
    return Tracker("XYZ", started_at=t(start), facts=Facts(prev_close=prev, tier=tier),
                   options=Options(**opts) if opts else Options())


def pr(tr: Tracker, hms: str, price: float, cond: str = "", ex: str = "NASDAQ", eligible: bool = True) -> None:
    tr.on_print(t(hms), price, eligible=eligible, conditions=cond, exchange=ex)


def opened(**kw) -> Tracker:
    tr = make(**kw)
    pr(tr, "09:30:01", 10.0, "O X")
    return tr


def test_the_opening_print_is_the_first_reference_and_premarket_trades_never_count():
    tr = make()
    pr(tr, "09:15:00", 8.0)                       # premarket
    pr(tr, "09:30:01", 10.0, "O X")
    v = tr.view(t("09:30:02"))
    assert (v["reference"], v["reference_source"], v["exact"]) == (10.0, "open", True)
    assert (v["lower"], v["upper"]) == (9.0, 11.0)
    assert v["window_trades"] == 1
    assert v["anchor"] == {"kind": "open", "ts": t("09:30:01"), "price": 10.0}


def test_a_trade_report_facility_print_is_never_the_open():
    tr = make()
    pr(tr, "09:30:01", 9.5, "O", ex="FINRA")
    assert tr.view(t("09:30:02"))["reference"] is None


def test_a_new_reference_waits_out_the_30_second_floor():
    tr = opened()
    pr(tr, "09:30:10", 10.30)                     # the mean since the open: 10.15, 1.5% away
    assert tr.view(t("09:30:30"))["reference"] == 10.0
    v = tr.view(t("09:30:31.5"))
    assert v["reference"] == 10.15 and v["reference_source"] == "mean"
    assert v["reference_since"] == t("09:30:31")  # the moment the floor ran out, not the next trade


def test_a_move_under_one_percent_keeps_the_reference():
    tr = opened()
    pr(tr, "09:30:40", 10.05)
    assert tr.view(t("09:32:00"))["reference"] == 10.0


def test_a_trade_leaving_the_window_moves_the_reference_at_that_moment():
    tr = opened()
    pr(tr, "09:31:00", 10.10)                     # mean 10.05: 0.5%
    assert tr.view(t("09:35:00"))["reference"] == 10.0
    v = tr.view(t("09:35:02"))                    # 09:35:01 the opening print leaves: mean 10.10, exactly 1%
    assert v["reference"] == 10.10 and v["reference_since"] == t("09:35:01")


def test_five_minutes_without_a_trade_keep_the_reference():
    tr = opened()
    pr(tr, "09:31:00", 11.0)
    tr.advance(t("09:45:00"))
    v = tr.view(t("09:45:00"))
    assert v["window_trades"] == 0 and v["reference"] is not None


def test_a_limit_state_holds_the_reference_and_15_seconds_make_a_pause_due():
    tr = opened()
    tr.on_quote(t("09:31:00"), 8.95, 9.00)        # the best offer on the 9.00 lower band
    pr(tr, "09:31:02", 9.00)                      # the mean drops 5%: no new reference in a limit state
    v = tr.view(t("09:31:05"))
    assert v["limit"]["side"] == "down" and v["limit"]["band"] == 9.0 and not v["limit"]["overdue"]
    assert v["reference"] == 10.0 and v["limit"]["pause_at"] == t("09:31:15")
    assert tr.view(t("09:31:16"))["limit"]["overdue"]


def test_by_default_a_limit_state_ends_without_a_reference_of_its_own():
    tr = opened()
    tr.on_quote(t("09:31:00"), 8.95, 9.00)
    pr(tr, "09:31:02", 9.00)
    tr.on_quote(t("09:31:10"), 8.99, 9.02)        # off the band: out of the limit state
    v = tr.view(t("09:31:10"))
    assert v["limit"] is None
    # The continuous rule applies again at once (the 30 s floor ran out long ago): no "limit_exit".
    assert v["reference"] == 9.5 and v["reference_source"] == "mean"


def test_the_plans_literal_reading_makes_a_reference_at_the_limit_states_end():
    tr = opened(exit_updates_reference=True)
    tr.on_quote(t("09:31:00"), 8.95, 9.00)
    pr(tr, "09:31:02", 9.00)
    tr.on_quote(t("09:31:10"), 8.99, 9.02)
    v = tr.view(t("09:31:10"))
    assert v["reference"] == 9.5 and v["reference_source"] == "limit_exit"


def test_a_crossed_quote_is_no_limit_state():
    tr = opened()
    tr.on_quote(t("09:31:00"), 9.10, 9.00)
    assert tr.view(t("09:31:01"))["limit"] is None


def test_a_halt_shows_no_band_and_the_reopening_print_is_the_next_reference():
    tr = opened()
    tr.on_halt(t("09:40:00"), True)
    assert tr.view(t("09:41:00"))["halted_since"] == t("09:40:00")
    pr(tr, "09:45:00", 12.0, "5 X")
    v = tr.view(t("09:45:01"))
    assert v["halted_since"] is None and (v["reference"], v["reference_source"], v["exact"]) == (12.0, "reopen", True)
    assert (v["lower"], v["upper"]) == (10.8, 13.2)
    pr(tr, "09:45:20", 12.5, "5")                 # another reopening print within 5 minutes: not a new reopen
    v = tr.view(t("09:45:21"))
    assert (v["reference"], v["reference_source"], v["anchor"]["ts"]) == (12.0, "reopen", t("09:45:00"))


def test_trading_after_a_halt_without_a_reopening_print_is_approximate():
    tr = opened()
    tr.on_halt(t("09:40:00"), True)
    tr.on_halt(t("09:45:00"), False)
    pr(tr, "09:45:01", 12.0)
    v = tr.view(t("09:45:02"))
    assert v["reference_source"] == "first_trade_after_halt" and v["exact"] is False


def test_watching_from_mid_session_seeds_an_approximate_reference_after_five_minutes():
    tr = make(start="10:00:00")
    for sec in range(0, 300, 10):
        tr.on_print(t("10:00:00") + sec, 10.0, eligible=True, conditions="", exchange="NASDAQ")
    assert tr.view(t("10:04:59"))["reference"] is None
    v = tr.view(t("10:05:00.5"))
    assert (v["reference"], v["reference_source"], v["exact"]) == (10.0, "seeded", False)
    assert v["spread"] == 0.11                    # the band of a reference 1% away
    tr.on_quote(t("10:06:00"), 8.95, 9.00)        # an approximate band never claims a limit state
    assert tr.view(t("10:06:01"))["limit"] is None


def test_no_opening_print_by_0935_takes_the_0930_0935_mean():
    tr = make()
    pr(tr, "09:30:30", 10.0)
    pr(tr, "09:33:00", 10.4)
    v = tr.view(t("09:35:00.5"))
    assert v["reference"] == 10.2 and v["reference_source"] == "open_mean" and v["exact"] is False


def test_a_tape_gap_makes_the_band_approximate():
    tr = opened()
    tr.on_gap(t("09:40:00"), "the line was down")
    v = tr.view(t("09:40:01"))
    assert v["exact"] is False and v["gap"]["reason"] == "the line was down"


def test_the_closing_doubling_widens_a_20_percent_band_at_1535():
    tr = make(prev=2.0, tier=None)
    pr(tr, "09:30:01", 2.0, "O")
    assert (tr.view(t("15:34:59"))["lower"], tr.view(t("15:34:59"))["upper"]) == (1.6, 2.4)
    v = tr.view(t("15:35:01"))
    assert (v["lower"], v["upper"]) == (1.2, 2.8)
    assert tr.view(t("16:00:01"))["reference"] is None   # the bands end at the close


def test_a_new_day_starts_over():
    tr = opened()
    v = tr.view(t("09:00:00", "2026-09-23"))
    assert v["reference"] is None and v["anchor"] is None and v["day_open"] == t("09:30:00", "2026-09-23")


def test_unknown_previous_close_or_tier_draws_no_band_but_keeps_the_reference():
    tr = opened(prev=None)
    v = tr.view(t("09:31:00"))
    assert v["reference"] == 10.0 and v["upper"] is None
    tr = opened(prev=5.0, tier=None)
    assert tr.view(t("09:31:00"))["upper"] is None
