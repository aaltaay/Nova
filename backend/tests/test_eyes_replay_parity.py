"""#966: the replayed eyes read a recording as the live eyes read the market.

The RVOL pillar live is HOD Momo's pace RVOL (today's volume over the average day's volume expected by
this clock time). A recorded leaderboard row holds the desk's daily-average RVOL, so a replay that graded
it raw read VEEA 0.99 at 07:06 on 2026-10-09 -- a 46% runner on 6.6M shares -- and failed a pillar the
live eyes passed.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from constants_leaderboard import LEADERBOARD_RVOL_BASIS_DAILY, LEADERBOARD_RVOL_BASIS_TOD
from constants_setups import SETUPS_PILLAR_MIN_RVOL
from leaderboard.rows import make_row
from market import volume_day_elapsed_fraction
from setup_scanner.grade import grade

ET = ZoneInfo("America/New_York")
MINUTE = int(datetime(2026, 10, 9, 7, 6, tzinfo=ET).timestamp())      # VEEA's trigger minute


@pytest.fixture(autouse=True)
def _no_catalyst(monkeypatch):
    import catalysts.live as catalyst_live

    monkeypatch.setattr(catalyst_live, "verdict_for", lambda *_a, **_k: None)


def _store(**kw) -> dict:
    from leaderboard import store as lb_store

    row = make_row(symbol="ZZVEEA", minute_ts=MINUTE, board="gainers", rank=1, price=5.65, prev_close=3.87,
                   volume=6_624_744, float_shares=1_576_258, **kw)
    with lb_store.connect() as db:
        lb_store.write_batch(db, rows=[row])
    return row


def _pillars(row: dict, at: float) -> dict:
    from eyes.recording import pillars_at

    return pillars_at("ZZVEEA", row["session_date"], at, last_price=5.67, prev_close=3.87)


def test_a_recorded_daily_average_rvol_is_read_as_the_live_pace_rvol():
    row = _store(source="recorded", rvol=0.99, rvol_basis=LEADERBOARD_RVOL_BASIS_DAILY)
    at = MINUTE + 8
    p = _pillars(row, at)
    share = volume_day_elapsed_fraction(datetime.fromtimestamp(at, ET))
    assert p["rvol"] == round(0.99 / share, 2)
    assert p["rvol"] >= SETUPS_PILLAR_MIN_RVOL
    assert grade(p)[1]["rvol"] is True


def test_a_rebuilt_time_of_day_rvol_is_a_pace_measure_already():
    row = _store(source="reconstructed", rvol=7.5, rvol_basis=LEADERBOARD_RVOL_BASIS_TOD)
    assert _pillars(row, MINUTE + 8)["rvol"] == 7.5


def test_an_after_hours_only_row_is_paced_already():
    """With the stock on no other board, the after-hours runners measured its RVOL paced (they never store a
    raw ratio) under the daily label; pacing it again inflated it."""
    from leaderboard import store as lb_store

    row = make_row(symbol="ZZVEEA", minute_ts=MINUTE + 9 * 3600, board="afterhours", rank=1, price=5.65,
                   prev_close=3.87, volume=9_000_000, source="recorded", rvol=6.2,
                   rvol_basis=LEADERBOARD_RVOL_BASIS_DAILY)
    with lb_store.connect() as db:
        lb_store.write_batch(db, rows=[row])
    assert _pillars(row, MINUTE + 9 * 3600 + 8)["rvol"] == 6.2


def test_a_stock_on_gainers_too_reads_the_gainers_daily_rvol_and_paces_it():
    """While the stock is on Gainers the After Hours row holds the Gainers row's daily RVOL copied over
    (``scanner_runners/afterhours.py``): the Gainers row is read, and paced."""
    from leaderboard import store as lb_store

    minute = MINUTE + 9 * 3600
    common = dict(symbol="ZZVEEA", minute_ts=minute, rank=1, price=5.65, prev_close=3.87, volume=9_000_000,
                  source="recorded", rvol=1.4, rvol_basis=LEADERBOARD_RVOL_BASIS_DAILY)
    rows = [make_row(board="afterhours", **common), make_row(board="gainers", **common)]
    with lb_store.connect() as db:
        lb_store.write_batch(db, rows=rows)
    at = minute + 8
    assert _pillars(rows[0], at)["rvol"] == round(1.4 / volume_day_elapsed_fraction(datetime.fromtimestamp(at, ET)), 2)


def test_a_replay_never_creates_the_leaderboard(monkeypatch, tmp_path):
    from leaderboard import store as lb_store

    missing = tmp_path / "nowhere" / "leaderboard.sqlite3"
    monkeypatch.setattr(lb_store, "path", lambda: missing)
    from eyes.recording import pillars_at

    p = pillars_at("ZZVEEA", "2026-10-09", MINUTE + 8, last_price=5.67, prev_close=3.87)
    assert p["rvol"] is None and p["source"] == "recording"
    assert not missing.parent.exists()


def test_the_replay_follows_the_live_switch_off_pace(monkeypatch):
    import constants_hod_momo

    monkeypatch.setattr(constants_hod_momo, "HOD_MOMO_RVOL_USE_PACE", False)
    row = _store(source="recorded", rvol=0.99, rvol_basis=LEADERBOARD_RVOL_BASIS_DAILY)
    assert _pillars(row, MINUTE + 8)["rvol"] == 0.99


def test_the_news_pillar_reads_the_recorded_feed_as_known_then(monkeypatch):
    """VEEA 2026-10-09: the live eyes' news pillar passed on a recorded release; the replay asked only this
    process's memory, which holds no past day, and read it unknown."""
    import catalysts.recorded as recorded

    seen: list[tuple[str, float]] = []

    def at(symbol: str, ts: float) -> dict:
        seen.append((symbol, ts))
        return {"verdict": "catalyst", "category": "listing_financing", "strength": "weak",
                "title": "Veea Regains Full Compliance with Nasdaq Continued Listing Requirements"}

    monkeypatch.setattr(recorded, "verdict_at", at)
    row = _store(source="recorded", rvol=0.99, rvol_basis=LEADERBOARD_RVOL_BASIS_DAILY)
    p = _pillars(row, MINUTE + 8)
    assert seen == [("ZZVEEA", MINUTE + 8)]
    assert p["news"] is True and p["headline"].startswith("Veea Regains")
    assert grade(p)[0] == "A"


def test_with_nothing_recorded_the_news_is_what_memory_holds(monkeypatch):
    import catalysts.live as catalyst_live
    import catalysts.recorded as recorded

    monkeypatch.setattr(recorded, "verdict_at", lambda *_a: None)
    monkeypatch.setattr(catalyst_live, "verdict_for", lambda *_a, **_k: {"verdict": "none_found"})
    row = _store(source="recorded", rvol=0.99, rvol_basis=LEADERBOARD_RVOL_BASIS_DAILY)
    assert _pillars(row, MINUTE + 8)["news"] is False


def test_no_rvol_stays_unknown():
    row = _store(source="recorded", rvol=None, rvol_basis=None)
    p = _pillars(row, MINUTE + 8)
    assert p["rvol"] is None and grade(p)[1]["rvol"] is None
