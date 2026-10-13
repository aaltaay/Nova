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


# -- the band's steps, the 1-minute chart's line (ADR 047 amendment 2026-10-12) ---------------------------------------

def steps(tr: Tracker, at: str) -> list[tuple]:
    tr.view(t(at))
    return [(s["ts"], s["lower"], s["upper"], s["exact"]) for s in tr.trail()]


def test_the_trail_starts_with_the_open_and_steps_with_each_new_reference():
    tr = make()
    pr(tr, "09:15:00", 8.0)                       # premarket: no band, no step
    pr(tr, "09:30:01", 10.0, "O X")
    pr(tr, "09:30:10", 10.30)                     # the mean moves 1.5%: a new reference once the floor runs out
    assert steps(tr, "09:31:00") == [
        (t("09:30:01"), 9.0, 11.0, True),
        (t("09:30:31"), 9.14, 11.17, True),       # at the moment the 30 s floor ran out, mid-minute
    ]


def test_an_opening_print_a_moment_before_0930_starts_the_trail():
    tr = make()
    pr(tr, "09:29:59.8", 10.0, "O X")
    assert steps(tr, "09:30:05") == [(t("09:29:59.8"), 9.0, 11.0, True)]


def test_a_halt_ends_the_line_and_the_reopening_print_starts_it_again():
    tr = opened()
    tr.on_halt(t("09:40:00"), True)
    tr.on_halt(t("09:44:59"), False)              # the halt ended: still no band until the reopening print
    pr(tr, "09:45:00", 12.0, "5 X")
    assert steps(tr, "09:46:00") == [
        (t("09:30:01"), 9.0, 11.0, True),
        (t("09:40:00"), None, None, False),
        (t("09:45:00"), 10.8, 13.2, True),
    ]


def test_a_tape_gap_keeps_the_band_but_marks_it_approximate():
    tr = opened()
    tr.on_gap(t("09:40:00"), "the line was down")
    tr.on_gap(t("09:41:00"), "again")             # nothing changed: no step
    assert steps(tr, "09:42:00")[1:] == [(t("09:40:00"), 9.0, 11.0, False)]


def test_the_closing_doubling_and_the_close_are_steps():
    tr = make(prev=2.0, tier=None)
    pr(tr, "09:30:01", 2.0, "O")
    assert steps(tr, "16:00:01") == [
        (t("09:30:01"), 1.6, 2.4, True),
        (t("15:35:00"), 1.2, 2.8, True),
        (t("16:00:00"), None, None, False),
    ]


def test_no_previous_close_draws_nothing_until_it_arrives():
    tr = opened(prev=None)
    assert steps(tr, "09:31:00") == []
    tr.set_facts(Facts(prev_close=9.0, tier=2))
    assert steps(tr, "09:31:30") == [(t("09:31:00"), 9.0, 11.0, True)]


def test_two_changes_at_one_moment_keep_the_last():
    tr = opened()
    tr.on_halt(t("09:40:00"), True)
    tr.on_halt(t("09:40:00"), False)
    pr(tr, "09:40:00", 10.0, "5")                 # halted and reopened in the same instant: the reopen stands
    out = steps(tr, "09:41:00")
    assert out == [(t("09:30:01"), 9.0, 11.0, True)]   # the same band as before: no step at all


def test_a_new_day_starts_the_trail_over():
    tr = opened()
    assert steps(tr, "09:31:00") == [(t("09:30:01"), 9.0, 11.0, True)]
    tr.view(t("09:00:00", "2026-09-23"))
    assert tr.trail() == []


# -- a stock opened mid-session, rebuilt on IBKR's trades before it (ADR 047 amendment 2026-10-13) ------------------

def watching(start: str, prev: float = 3.5) -> Tracker:
    """A tracker that starts mid-session and keeps its inputs, as the live worker's do."""
    return Tracker("XYZ", started_at=t(start), facts=Facts(prev_close=prev, tier=2), journal=10_000)


def before(start: str, prices: list[float], every: float = 10.0, cond: str = "") -> list[tuple]:
    """IBKR's trades ``every`` seconds apart, the last one ``every`` seconds before ``start``."""
    end = t(start)
    return [(end - every * (len(prices) - k), p, True, cond, "NASDAQ") for k, p in enumerate(prices)]


def test_a_stock_opened_mid_session_is_banded_at_once_from_the_trades_before_it():
    tr = watching("09:43:06")
    pr(tr, "09:43:06", 4.20)
    assert tr.view(t("09:43:07"))["reference"] is None             # on its own: five minutes to wait
    trades = before("09:43:06", [4.00] * 29)                       # 09:38:16 .. 09:42:56
    new = tr.rebuilt(t("09:43:08"), trades, since=t("09:33:06"), complete=True)
    v = new.view(t("09:43:09"))
    # Five minutes into the ten it seeds itself (09:38:16, the first trade after 09:38:06), and the 4.20 Nova heard
    # moves the mean 0.2%: under 1%, so the reference stands.
    assert (v["reference"], v["reference_source"], v["exact"]) == (4.0, "backfill", False)
    assert v["reference_since"] == t("09:38:16") and v["window_trades"] == 30
    assert v["spread"] is not None and v["limit"] is None
    assert v["backfill"] == {"ts": t("09:43:08"), "since": t("09:33:06"), "trades": 29, "complete": True}
    assert steps(new, "09:43:09") == [(t("09:43:08"), v["lower"], v["upper"], False)]   # drawn from when Nova knew
    assert v["tape_since"] == t("09:43:06") and v["last"] == 4.20  # watching_since stays Nova's first print
    assert tr.view(t("09:43:09"))["reference"] is None             # the old tracker is left as it was


def test_rebuilt_is_a_tracker_that_heard_ibkrs_trades_and_then_its_own():
    trades = before("10:00:00", [4.00 + 0.004 * k for k in range(119)], every=5.0)   # 10:00 back to 09:50:05, rising
    live = [("10:00:00", 4.48), ("10:00:20", 4.52), ("10:00:40", 4.60)]
    tr = watching("10:00:00")
    for hms, price in live:
        pr(tr, hms, price)
    tr.on_quote(t("10:00:41"), 4.58, 4.61)
    new = tr.rebuilt(t("10:00:45"), trades, since=t("09:50:00"), complete=True)
    heard = Tracker("XYZ", started_at=t("09:50:00"), facts=Facts(prev_close=3.5, tier=2))
    for ts, price, eligible, cond, ex in trades:
        heard.on_print(ts, price, eligible=eligible, conditions=cond, exchange=ex)
    for hms, price in live:
        pr(heard, hms, price)
    a, b = new.view(t("10:01:00")), heard.view(t("10:01:00"))
    assert len([h for h in b["history"] if h["source"] == "mean"]) >= 3   # the rule moved it as the price rose
    assert (a["reference"], a["reference_since"], a["lower"], a["upper"]) ==         (b["reference"], b["reference_since"], b["lower"], b["upper"])
    assert (a["bid"], a["ask"], a["window_trades"]) == (4.58, 4.61, b["window_trades"])


def test_trades_nova_heard_itself_count_once():
    tr = watching("10:00:00")
    pr(tr, "10:00:00", 10.0)
    trades = [(t("09:58:00"), 10.0, True, "", "NASDAQ"),
              (t("10:00:00"), 50.0, True, "", "NASDAQ"), (t("10:00:01"), 50.0, True, "", "NASDAQ")]   # heard live
    new = tr.rebuilt(t("10:00:02"), trades, since=t("09:55:00"), complete=False)
    v = new.view(t("10:00:03"))
    assert (v["reference"], v["window_trades"], v["backfill"]["trades"]) == (10.0, 2, 1)


def test_pages_short_of_five_minutes_seed_when_they_land_and_say_so():
    tr = watching("11:00:00", prev=9.0)
    pr(tr, "11:00:00", 10.3)
    new = tr.rebuilt(t("11:00:02"), before("11:00:00", [10.0] * 30, every=1.0), since=t("10:59:30"), complete=False)
    v = new.view(t("11:00:03"))
    assert (v["reference"], v["reference_since"], v["reference_source"]) == (round((30 * 10 + 10.3) / 31, 4),
                                                                              t("11:00:02"), "backfill")
    assert v["backfill"]["complete"] is False


def test_ibkrs_reopening_print_sets_the_reference_but_only_novas_own_makes_it_exact():
    tr = watching("10:10:00", prev=4.0)
    pr(tr, "10:10:00", 4.62)
    trades = before("10:02:00", [4.10] * 6) + [(t("10:05:00"), 4.60, True, "5", "NASDAQ")]         + before("10:10:00", [4.61] * 20)
    new = tr.rebuilt(t("10:10:01"), trades, since=t("10:00:00"), complete=True)
    v = new.view(t("10:10:02"))
    assert (v["reference"], v["reference_source"], v["exact"]) == (4.60, "backfill", False)
    new.on_halt(t("10:12:00"), True)
    new.on_halt(t("10:17:00"), False)
    pr(new, "10:17:01", 4.20, "5")
    assert (new.view(t("10:17:02"))["reference_source"], new.view(t("10:17:02"))["exact"]) == ("reopen", True)


def test_a_tape_gap_while_ibkrs_trades_were_read_is_kept():
    tr = watching("10:00:00")
    pr(tr, "10:00:00", 4.0)
    tr.on_gap(t("10:00:01"), "IBKR's data stopped at 10:00:01 ET")
    pr(tr, "10:00:05", 4.0)
    new = tr.rebuilt(t("10:00:06"), before("10:00:00", [4.0] * 59), since=t("09:50:00"), complete=True)
    v = new.view(t("10:00:07"))
    assert v["tape_since"] == t("10:00:01") and v["reference_source"] == "backfill" and v["exact"] is False


def test_nothing_rebuilds_a_tracker_with_its_own_reference_or_without_its_inputs():
    trades = before("09:43:06", [8.0] * 5)
    tr = opened()                                                  # it saw the open
    pr(tr, "09:43:06", 10.0)
    assert tr.rebuilt(t("09:43:08"), trades, since=t("09:33:06"), complete=True) is None
    tr = watching("09:43:06")
    pr(tr, "09:43:06", 10.0, "5")                                  # Nova's own reopening print
    assert tr.rebuilt(t("09:43:08"), trades, since=t("09:33:06"), complete=True) is None
    tr = make(start="09:43:06")                                    # keeps no inputs
    pr(tr, "09:43:06", 10.0)
    assert tr.rebuilt(t("09:43:08"), trades, since=t("09:33:06"), complete=True) is None
    tr = Tracker("XYZ", started_at=t("09:43:06"), facts=Facts(prev_close=9.0, tier=2), journal=3)
    for k in range(4):
        pr(tr, "09:43:06", 10.0 + k / 100)                         # a fourth input: past what it keeps
    assert not tr.keeps_journal
    assert tr.rebuilt(t("09:43:08"), trades, since=t("09:33:06"), complete=True) is None


def test_flye_the_reopening_print_replaces_a_reference_seeded_in_the_halt_and_is_exact():
    # FLYE 2026-10-13: Nova's first print 09:43:06, halted 09:46:37; five minutes after the first print, still
    # halted, the tracker seeded a reference (09:48:06). The reopening print must still make it exact.
    tr = make(start="09:43:06", prev=3.5)
    for sec in range(0, 211, 5):
        tr.on_print(t("09:43:06") + sec, 4.0 + sec / 1000, eligible=True, conditions="", exchange="NASDAQ")
    tr.on_halt(t("09:46:37"), True)
    v = tr.view(t("09:48:07"))
    assert v["history"][-1]["source"] == "seeded" and v["history"][-1]["ts"] == t("09:48:06")
    assert v["lower"] is not None and steps(tr, "09:48:07") == []   # computed, never drawn: the desk's steps: []
    tr.on_halt(t("09:51:37"), False)
    pr(tr, "09:51:38", 4.60, "5")
    v = tr.view(t("09:51:39"))
    assert (v["reference"], v["reference_source"], v["exact"]) == (4.60, "reopen", True)
    assert steps(tr, "09:51:39")[-1][0] == t("09:51:38") and steps(tr, "09:51:39")[-1][3] is True


def test_flye_with_the_backfill_the_band_shows_before_the_halt_and_the_reopen_is_exact():
    tr = watching("09:43:06")
    pr(tr, "09:43:06", 4.20)
    tr = tr.rebuilt(t("09:43:08"), before("09:43:06", [4.0] * 59), since=t("09:33:06"), complete=True)
    tr.on_halt(t("09:46:37"), True)
    tr.on_halt(t("09:51:37"), False)
    pr(tr, "09:51:38", 4.60, "5")
    drawn = steps(tr, "09:51:39")
    assert drawn[0][0] == t("09:43:08") and drawn[0][3] is False   # a band 3.5 minutes before the halt
    assert drawn[1][0] == t("09:46:37") and drawn[1][1:] == (None, None, False)
    assert drawn[-1][0] == t("09:51:38") and drawn[-1][3] is True


def test_a_reopening_print_that_a_trade_beat_to_novas_tape_is_still_the_exact_reference():
    tr = opened()
    tr.on_halt(t("09:40:00"), True)
    tr.on_halt(t("09:45:00"), False)
    pr(tr, "09:45:01", 12.0)                                       # another venue's trade arrived first
    assert tr.view(t("09:45:01"))["reference_source"] == "first_trade_after_halt"
    pr(tr, "09:45:01.4", 11.8, "5")
    v = tr.view(t("09:45:02"))
    assert (v["reference"], v["reference_source"], v["exact"], v["window_trades"]) == (11.8, "reopen", True, 1)


def test_flye_halted_before_ibkrs_trades_land_the_band_waits_for_the_reopen():
    tr = watching("09:43:06")
    pr(tr, "09:43:06", 4.20)
    tr.on_halt(t("09:43:07"), True)
    tr = tr.rebuilt(t("09:43:08"), before("09:43:06", [4.0] * 59), since=t("09:33:06"), complete=True)
    assert tr.view(t("09:43:09"))["halted_since"] == t("09:43:07") and steps(tr, "09:43:09") == []
    tr.on_halt(t("09:48:07"), False)
    pr(tr, "09:48:08", 4.60, "5")
    assert steps(tr, "09:48:09") == [(t("09:48:08"), 4.14, 5.06, True)]   # 10%: a $3.50 close, Tier 2
