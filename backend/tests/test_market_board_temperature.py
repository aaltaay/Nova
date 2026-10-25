"""The small-cap temperature (ADR 053 amendment 2026-10-25): the rules, the walk over a session's board rows, and the
climate fixes that came with it (an empty recorded board is no board; the 1 D baseline uses the session's clock)."""
from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market_board import climate, clock, industries, temperature
from market_board.temperature import Gauges

DAY = date(2026, 10, 13)


@pytest.fixture(autouse=True)
def _tmp_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("NOVA_LEADERBOARD_DIR", str(tmp_path / "lb"))
    climate.reset_for_tests()
    industries.reset_for_tests()
    yield
    climate.reset_for_tests()
    industries.reset_for_tests()


def test_day_label_needs_runners_and_money_for_hot_and_neither_for_cold():
    assert temperature.day_label(2, 101.0, 100.0) == "hot"
    assert temperature.day_label(2, 100.0, 100.0) == "warm"     # as many runners, no more money than usual
    assert temperature.day_label(1, 500.0, 100.0) == "warm"
    assert temperature.day_label(0, 100.0, 100.0) == "cold"
    assert temperature.day_label(0, 101.0, 100.0) == "warm"     # no runner, but more money than usual
    assert temperature.day_label(5, 500.0, None) is None        # no usual: no label


def _rows_db(rows: list[tuple]) -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE rows (session_date, minute_ts, source, board, symbol, rank, price, prev_close,"
               " change_pct, volume)")
    db.executemany("INSERT INTO rows VALUES (?,?,?,?,?,?,?,?,?,?)",
                   [("d", m, "recorded", "gainers", s, r, p, pc, c, v) for m, s, r, p, pc, c, v in rows])
    return db


def test_read_counts_runners_money_in_the_top_gainers_and_who_held():
    t1, t2 = 1000, 1060
    rows = [  # minute, symbol, rank, price, prev_close, change (fraction), volume
        (t1, "AAA", 1, 11.0, 5.0, 1.2, 1_000_000), (t1, "BBB", 2, 4.8, 3.0, 0.6, 2_000_000),
        (t1, "PNNY", 3, 4.0, 1.0, 3.0, 9_000_000),      # prior close under $2: not in the lens
        (t1, "BIGC", 4, 39.0, 30.0, 0.3, 9_000_000),    # over $20: not in the lens
        (t2, "AAA", 2, 10.0, 5.0, 1.0, 1_500_000), (t2, "BBB", 3, 3.6, 3.0, 0.2, 2_500_000),
        (t2, "EEE", 1, 25.0, 10.0, 1.5, 100_000),
    ]
    g = temperature.read(_rows_db(rows), "d", "recorded", "gainers", t2)
    assert g.minutes == [t1, t2]
    assert g.runners == [1, 2]                                  # AAA by t1; EEE joins at t2
    assert g.money[0] == pytest.approx(11.0e6 + 9.6e6)          # shares x last price of the top gainers in the lens
    assert g.money[1] == pytest.approx(15.0e6 + 9.0e6 + 2.5e6)
    assert (g.held, g.faded) == (2, 1)                          # AAA and EEE keep half their peak; BBB does not
    assert g.at(t1 - 1) is None                                 # before the recording: no observation, not zero
    assert g.at(t1 + 30) == (1, pytest.approx(20.6e6))
    assert g.at(t2 + 601) is None                               # past the gap after the last recorded minute
    assert temperature.read(_rows_db([]), "d", "recorded", "gainers", t2).minutes == []


def test_a_runner_gone_from_a_full_board_counts_as_faded_only_when_the_board_shows_it():
    t1, t2 = 1000, 1060
    rows = [(t1, "GONE", 1, 9.0, 5.0, 0.8, 1000)]
    filler = [(t2, f"F{i}", i + 1, 1.1, 1.0, 0.1, 10) for i in range(50)]   # the 50th row is +10%
    assert temperature.read(_rows_db(rows + filler), "d", "recorded", "gainers", t2).faded == 1
    half = [(t2, f"F{i}", i + 1, 1.1, 1.0, 0.1, 10) for i in range(10)]       # not a full board: unknown
    g = temperature.read(_rows_db(rows + half), "d", "recorded", "gainers", t2)
    assert (g.held, g.faded) == (0, 0) and g.hold() is None


def _sessions(n: int) -> list[date]:
    return clock.sessions_back(DAY, n)


def _series(d: date, steps: list[tuple[int, int, float]], *, start: int = 4 * 60, end: int = 16 * 60,
            held: int = 1, faded: int = 1) -> Gauges:
    """A board recorded every 5 minutes from ``start`` to ``end`` (minutes after ET midnight); ``steps`` are
    (from minute, runners, money), the last one at or before each minute applying."""
    g = Gauges(held=held, faded=faded)
    for m in range(start, end + 1, 5):
        _, runners, money = [s for s in steps if s[0] <= m][-1] if any(s[0] <= m for s in steps) else (0, 0, 0.0)
        g.minutes.append(int(clock.at(d, m)))
        g.runners.append(runners)
        g.money.append(money)
    return g


def _flat(d: date, runners: int, money: float, *, held: int = 1, faded: int = 1) -> Gauges:
    return _series(d, [(0, runners, money)], held=held, faded=faded)


def test_each_day_is_weighed_against_the_median_of_the_sessions_before_it():
    days = _sessions(13)
    chain = [(d, _flat(d, 0, 100.0)) for d in days[:-2]]        # 11 ordinary sessions
    chain.append((days[-2], _flat(days[-2], 3, 250.0, held=3, faded=1)))
    chain.append((days[-1], None))                               # today: Nova recorded no board
    out = temperature.label_days(chain, clock.at(DAY, 15 * 60), 3)
    assert [r["label"] for r in out] == ["cold", "hot", None]
    assert out[1]["usual_money"] == 100 and out[1]["usual_days"] == 11 and out[1]["hold_pct"] == 75.0
    assert out[0]["usual_days"] == 10                            # the 11th session has 10 before it: enough
    short = temperature.label_days(chain[-5:], clock.at(DAY, 15 * 60), 2)
    assert short[0]["label"] is None and short[0]["usual_days"] == 3


def test_today_is_read_so_far_against_the_same_minute():
    days = _sessions(12)
    chain = [(d, _series(d, [(4 * 60, 0, 10.0), (11 * 60, 1, 1000.0)])) for d in days[:-1]]
    chain.append((DAY, _series(DAY, [(4 * 60, 2, 50.0)], end=8 * 60)))   # today, recorded until 08:00
    at_eight = temperature.label_days(chain, clock.at(DAY, 8 * 60), 1)[0]
    assert at_eight["usual_money"] == 10 and at_eight["label"] == "hot"    # hot by 08:00 against 08:00
    later = temperature.label_days(chain, clock.at(DAY, 11 * 60), 1)[0]
    assert later["usual_money"] == 1000 and later["runners_100"] is None and later["label"] is None
    assert temperature._rule("1D", [later])["why"] == "Nova's Gainers board has no recording near this time"


def test_a_session_recorded_later_in_the_day_is_left_out_of_the_usual_not_read_as_zero():
    days = _sessions(13)
    late_starts = [(d, _series(d, [(0, 0, 900.0)], start=9 * 60 + 45)) for d in days[:-1]]   # recorded from 09:45
    chain = late_starts + [(DAY, _series(DAY, [(0, 2, 100.0)], end=8 * 60))]
    at_eight = temperature.label_days(chain, clock.at(DAY, 8 * 60), 1)[0]
    assert at_eight["usual_days"] == 0 and at_eight["usual_money"] is None and at_eight["label"] is None
    early = [(d, _series(d, [(0, 0, 50.0)])) for d in days[:2]]
    mixed = temperature.label_days(early + late_starts[2:] + chain[-1:], clock.at(DAY, 8 * 60), 1)[0]
    assert mixed["usual_days"] == 2                              # only the sessions recorded at 08:00 count


def test_a_session_has_one_label_on_every_card_and_in_the_day_read(tmp_path):
    """Recorded sessions with gaps: the 1 D card once read a shorter history than the Day Read, so the same day
    could be warm on the card and hot in the Day Read."""
    from leaderboard import store

    days = _sessions(81)
    with store.connect(Path(tmp_path / "lb") / "leaderboard.sqlite3") as db:
        for i, d in enumerate(days):
            if i % 3 == 1:
                continue                                         # sessions Nova did not record
            iso = d.isoformat()
            volume = 1_000_000 if i < 40 else 100_000 * (1 + i % 7)  # older sessions carry more money
            for minute in (9 * 60 + 45, 15 * 60 + 59):
                m = int(clock.at(d, minute))
                db.execute("INSERT INTO coverage VALUES (?,?,?,?,?,?,?)", (iso, m, "recorded", "gainers", "live", 2, "r"))
                for sym in ("RUNA", "RUNB"):
                    db.execute("INSERT INTO rows (session_date, minute_ts, source, board, symbol, rank, price,"
                               " prev_close, change_pct, gap_pct, volume) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                               (iso, m, "recorded", "gainers", sym, 1, 6.0, 3.0, 1.0, 0.0, volume))
        db.commit()
    now = clock.at(DAY, 17 * 60)
    climate.refresh(now, sessions_needed=81)
    cards = {p: climate.compose(p, now)["heat"] for p in ("1D", "7D", "30D")}
    words = climate.today_numbers(now)["temperature"]
    assert cards["1D"]["label"] == words["day"] and cards["1D"]["label"] is not None
    assert cards["7D"]["label"] == words["week"] and cards["30D"]["label"] == words["month"]
    by_date = {d["date"]: d for d in cards["30D"]["days"]}
    for d in cards["1D"]["days"] + cards["7D"]["days"]:
        assert d == by_date[d["date"]]                           # the same usual and label wherever it shows
    agents = temperature.report(climate.heat_chain_for(DAY, now), now)   # and what agents read
    assert (agents["day_detail"], agents["week"], agents["month"]) == (cards["1D"], cards["7D"], cards["30D"])
    assert agents["labels"] == words and agents["final"] is True


def test_agents_read_the_temperature_without_the_page_having_run(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from agent_desk import routes as agent_routes
    from main import app

    client = TestClient(app)
    url = "/api/agent/market-temperature"
    assert client.get(url).status_code == 503                    # no leaderboard store yet
    _seed(tmp_path, _sessions(3))
    climate.reset_for_tests()                                    # the Market page's refresher never ran
    monkeypatch.setattr(agent_routes, "time", SimpleNamespace(time=lambda: clock.at(DAY, 9 * 60 + 50)))
    got = client.get(url).json()
    assert got["schema_version"] == 1 and got["day"] == DAY.isoformat() and got["final"] is False
    assert set(got["labels"]) == {"day", "week", "month"} and got["day_detail"]["days"][-1]["runners_100"] == 1
    assert got["day_detail"]["why"].startswith("the usual money needs 10 recorded sessions")
    assert got["rules"] and "never a trade signal" in got["rules"][-1]
    past = client.get(url, params={"day": "2026-10-10"}).json()  # a Saturday: the session before it
    assert past["day"] == "2026-10-09" and past["final"] is True
    assert client.get(url, params={"day": "2026-10-14"}).json()["detail"]["reason"] == "AGENT_INVALID"
    assert client.get(url, params={"day": "13-10-2026"}).status_code == 400


def _day(label, hold=None):
    return {"date": "x", "label": label, "runners_100": 0, "money": 0, "usual_money": 0, "usual_days": 10,
            "hold_pct": hold}


def test_week_rules():
    rule = temperature._rule
    assert rule("7D", [_day("cold")] * 3 + [_day("hot", 90.0)] * 2)["label"] == "cold"
    assert rule("7D", [_day("hot", 50.0)] * 2 + [_day("warm", 45.0)] * 3)["label"] == "good"
    assert rule("7D", [_day("hot", 20.0)] * 2 + [_day("warm", 30.0)] * 3)["label"] == "choppy"
    assert rule("7D", [_day("hot", 40.0)] * 2 + [_day("warm", 40.0)] * 3)["label"] == "ok"
    assert rule("7D", [_day("warm")] * 5)["label"] == "ok"                 # no hold measured: neither good nor choppy
    few = rule("7D", [_day(None)] * 3 + [_day("hot")] * 2)
    assert few["label"] is None and few["why"] == "2 of its 5 sessions have a label; it needs 3"


def test_month_rules():
    rule = temperature._rule
    just_under = rule("30D", [_day("hot")] * 6 + [_day("warm")] * 12 + [_day("cold")] * 3)
    assert just_under["score_pct"] == 14.3 and just_under["label"] == "warm"
    hot = rule("30D", [_day("hot")] * 7 + [_day("warm")] * 11 + [_day("cold")] * 3)
    assert hot["score_pct"] == 19.0 and hot["label"] == "hot" and (hot["hot"], hot["cold"]) == (7, 3)
    assert rule("30D", [_day("cold")] * 5 + [_day("warm")] * 16)["label"] == "cold"
    assert rule("30D", [_day("hot")] * 2 + [_day("warm")] * 19)["label"] == "warm"
    assert rule("30D", [_day("hot")] * 9 + [_day(None)] * 12)["label"] is None


def _seed(tmp_path: Path, days: list[date], *, empty: set[date] = frozenset()) -> None:
    from leaderboard import store

    with store.connect(Path(tmp_path / "lb") / "leaderboard.sqlite3") as db:
        for d in days:
            iso, m = d.isoformat(), int(clock.at(d, 9 * 60 + 45))
            db.execute("INSERT INTO coverage VALUES (?,?,?,?,?,?,?)",
                       (iso, m, "recorded", "gainers", "live", 0 if d in empty else 1, "r"))
            if d in empty:
                continue
            db.execute("INSERT INTO rows (session_date, minute_ts, source, board, symbol, rank, price, prev_close,"
                       " change_pct, gap_pct, volume) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (iso, m, "recorded", "gainers", "RUNR", 1, 6.0, 3.0, 1.0, 0.0, 1_000_000))
        db.commit()


def test_a_board_that_kept_no_row_is_no_board(tmp_path):
    days = _sessions(3)
    _seed(tmp_path, days, empty={DAY})
    now = clock.at(DAY, 11 * 60)
    climate.refresh(now, sessions_needed=3)
    block = climate.compose("1D", now)
    assert block["covered"] == 0 and block["counts"]["up20"] is None
    assert block["heat"]["why"] == "Nova recorded no Gainers board this session"
    assert climate.today_numbers(now)["runners_why"] == "Nova recorded no Gainers board this session"


def test_after_the_session_the_one_day_baseline_is_taken_at_its_close(tmp_path):
    days = _sessions(3)
    _seed(tmp_path, days)
    overnight = clock.at(date(2026, 10, 14), 90)                # 01:30 ET the next day: still the 13th's page
    assert clock.trading_date(overnight) == DAY
    climate.refresh(overnight, sessions_needed=3)
    block = climate.compose("1D", overnight)
    assert block["baseline"]["up20"] == 1.0                     # not 0 "by 01:30"
    words = climate.today_numbers(overnight)["temperature"]
    assert set(words) == {"day", "week", "month"} and words["day"] is None   # 2 sessions before: no usual yet
