"""Nova's trading session ends at 20:00 ET (2026-10-01, "the entire market is closed, no?").

After the close IBKR keeps the same SMART Level 1 lines moving with its overnight session
(20:00-03:50 ET): the last price moves while IBKR's own day volume and day high stand still.
Nova turned those prints into one-minute candles and HOD Momo trades: the Bots page showed OM's
first pullback "new high 4.20 on a 12% leg" from one 200-share print at 20:48, and HOD Momo raised
78 alerts after 20:00. ``market.in_trading_session`` is the one rule; the bar builder and HOD Momo's
feed read it. The setup scanner's side is ``test_setup_scanner_session_close.py``.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import archive.db as archive_db
import archive.write_queue as wq
import bars_store
import ibkr.l1_minute as l1_minute
import market

ET = ZoneInfo("America/New_York")


def at(day: str, hh: int, mm: int, ss: int = 0) -> float:
    y, mo, d = (int(x) for x in day.split("-"))
    return datetime(y, mo, d, hh, mm, ss, tzinfo=ET).timestamp()


# -- the rule --------------------------------------------------------------------


def test_the_session_is_0400_to_2000_et_on_an_exchange_day():
    assert market.trading_session_bounds(at("2026-10-01", 12, 0)) == (at("2026-10-01", 4, 0),
                                                                       at("2026-10-01", 20, 0))
    assert market.in_trading_session(at("2026-10-01", 4, 0))
    assert market.in_trading_session(at("2026-10-01", 19, 59, 59))
    assert not market.in_trading_session(at("2026-10-01", 3, 59, 59))
    assert not market.in_trading_session(at("2026-10-01", 20, 0))


def test_ibkr_overnight_session_is_in_no_session():
    # The night the operator asked about: OM at 20:48, NAMM at 23:32, SDEV armed at 00:12, and
    # IBKR's overnight session runs to 03:50.
    for when in (at("2026-10-01", 20, 48), at("2026-10-01", 23, 32), at("2026-10-02", 0, 12),
                 at("2026-10-02", 3, 50)):
        assert not market.in_trading_session(when)


def test_no_session_on_a_weekend_or_an_nyse_holiday():
    assert market.trading_session_bounds(at("2026-10-03", 12, 0)) is None   # Saturday
    assert market.trading_session_bounds(at("2026-10-04", 21, 0)) is None   # Sunday: IBKR's overnight opens
    assert market.trading_session_bounds(at("2026-11-26", 12, 0)) is None   # Thanksgiving
    assert not market.in_trading_session(at("2026-12-25", 10, 0))
    assert market.in_trading_session(at("2026-10-02", 10, 0))                # and back on a Friday


def test_a_daylight_saving_week_keeps_the_eastern_clock():
    # The Mondays after the 2026 changes (Mar 8, Nov 1): still 04:00-20:00 on the Eastern clock.
    for day in ("2026-03-09", "2026-11-02"):
        start, end = market.trading_session_bounds(at(day, 12, 0))
        assert (datetime.fromtimestamp(start, ET).strftime("%H:%M"),
                datetime.fromtimestamp(end, ET).strftime("%H:%M")) == ("04:00", "20:00")
        assert end - start == 16 * 3600


# -- the bar builder ----------------------------------------------------------------


def _fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    l1_minute.reset_for_tests()


def test_an_overnight_print_makes_no_minute_and_reaches_no_listener(monkeypatch, tmp_path):
    """OM 2026-10-01: 3.79 at 19:59, then IBKR's overnight session printed 4.20 x 200 at 20:48 --
    a candle the setup scanner read as a 12% leg to a new high of day."""
    _fresh(monkeypatch, tmp_path)
    heard: list[tuple[str, str, dict]] = []
    listener = lambda kind, sym, payload: heard.append((kind, sym, payload))  # noqa: E731
    l1_minute.add_listener(listener)
    try:
        l1_minute.on_last("om", 3.79, at("2026-10-01", 19, 59, 12), size=100, cum_volume=983_761)
        l1_minute.on_last("om", 4.20, at("2026-10-01", 20, 48, 31), size=200, cum_volume=983_761)
        l1_minute.flush_elapsed(at("2026-10-01", 20, 50))
    finally:
        l1_minute.remove_listener(listener)
    wq.drain_once()

    bars = bars_store.read("OM", "1Min", 10)["bars"]
    assert [(b["c"], b["v"]) for b in bars] == [(3.79, 100)]      # the 19:59 minute; nothing at 20:48
    assert [p["price"] for kind, _, p in heard if kind == "last"] == [3.79]
    assert [p["c"] for kind, _, p in heard if kind == "bar"] == [3.79]


def test_the_overnight_volume_never_lands_on_the_next_morning(monkeypatch, tmp_path):
    """A line opened overnight counts IBKR's overnight volume (NAMM read 31,778 at 23:32): the
    morning's first print is a baseline again, not that counter's growth since the night."""
    _fresh(monkeypatch, tmp_path)
    l1_minute.on_last("namm", 1.36, at("2026-10-01", 19, 59, 49), size=100, cum_volume=27_206_968)
    l1_minute.on_last("namm", 1.36, at("2026-10-01", 23, 32, 22), size=1_006, cum_volume=31_778)
    l1_minute.on_last("namm", 1.32, at("2026-10-02", 4, 0, 5), size=300, cum_volume=40_000)
    l1_minute.on_last("namm", 1.33, at("2026-10-02", 4, 0, 20), size=100, cum_volume=40_100)
    l1_minute.flush_elapsed(at("2026-10-02", 4, 2))
    wq.drain_once()

    bars = bars_store.read("NAMM", "1Min", 10)["bars"]
    assert [(b["c"], b["v"]) for b in bars] == [(1.36, 100), (1.33, 400)]   # 300 (a baseline) + 100


def test_the_sessions_last_minute_still_closes_after_2000(monkeypatch, tmp_path):
    _fresh(monkeypatch, tmp_path)
    l1_minute.on_last("xrpn", 23.90, at("2026-10-01", 19, 59, 30))
    l1_minute.on_last("xrpn", 25.17, at("2026-10-01", 20, 21, 4))      # overnight: no new minute
    l1_minute.flush_elapsed(at("2026-10-01", 20, 22))
    wq.drain_once()
    assert [b["c"] for b in bars_store.read("XRPN", "1Min", 10)["bars"]] == [23.90]


# -- HOD Momo, its L1 tick archive and volume boost -----------------------------------------


def test_hod_momo_and_volume_boost_take_no_overnight_print(monkeypatch):
    import hod_tick_feed
    import volume_boost
    from ibkr import l1_apply

    fed: list = []
    boosted: list = []
    monkeypatch.setattr(hod_tick_feed, "feed_hod_on_tick", lambda *a: fed.append(a))
    monkeypatch.setattr(volume_boost, "observe_l1", lambda *a: boosted.append(a))
    state = SimpleNamespace(gainer_cache=[], loser_cache=[], gapper_cache=[], afterhours_cache=[],
                            large_cap_cache=[], current_mode="closed")
    # XRPN 2026-10-01: 27.49 at 20:31, over IBKR's own 23.99 day high, with the day's volume unchanged.
    patch = l1_apply.apply_l1_quote("XRPN", 27.49, 2_417_285, 21.0, at("2026-10-01", 20, 31, 19),
                                    get_state=lambda: state)
    assert fed == [] and boosted == []
    assert patch["price"] == 27.49            # the price itself is still shown as the line's last
    l1_apply.apply_l1_quote("XRPN", 23.50, 2_417_000, 21.0, at("2026-10-01", 19, 59, 1), get_state=lambda: state)
    assert len(fed) == 1 and fed[0][:2] == ("XRPN", 23.50) and len(boosted) == 1
