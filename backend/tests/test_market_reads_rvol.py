"""The relative-volume table (#1100: ``research/rvol/build_rvol.py``, ``research/market_reads/rvol*.py``) on a tiny
fake Massive folder: its baselines are ``stock_day_stats``' own, a resumed build writes what a full build writes, a
listed split puts earlier volume on today's basis, a likely split or a new company starts the baseline again, only
common stocks are in it, triggers say when the stock was already over the line, outcomes read nothing before the
entry and never guess the order inside one bar, later sessions count, and the control is a same-minute stock."""
from __future__ import annotations

import contextlib
import json
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

pytest.importorskip("pandas")
pytest.importorskip("duckdb")
REPO = Path(__file__).resolve().parents[2]
for extra in (REPO / "research", REPO / "research" / "rvol", Path(__file__).resolve().parent):
    sys.path.insert(0, str(extra))

import build_rvol  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
from test_market_reads_daily import write_gz  # noqa: E402

from market_reads import daily, reads, rvol, rvol_outcomes, slots, splits, stats, tickers  # noqa: E402
from market_reads import rvol_store as rs  # noqa: E402

HEADER = "ticker,volume,open,close,high,low,window_start,transactions"


def _sessions(n: int = 24) -> list[str]:
    out, d = [], date(2026, 8, 3)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


DAYS = _sessions()
TODAY, D20, D21 = DAYS[-1], DAYS[20], DAYS[21]
SPLIT_DAY, LIKELY_DAY, NEW_OWNER_FROM = DAYS[15], DAYS[18], DAYS[10]
COMMON = ("ABC", "UPP", "DWN", "BTH", "NTH", "SRG", "FST", "LAT", "LBO", "SPL", "LKS")
SYMBOLS = (*COMMON, "HLD", "ETFX", "UNK")
TICKERS = [{"ticker": s, "cik": str(n), "name": s, "active": True, "type": "CS"} for n, s in enumerate(COMMON, 1)] + [
    {"ticker": "ETFX", "cik": "90", "name": "An ETF", "active": True, "type": "ETF"},
    {"ticker": "HLD", "cik": "71", "name": "Old Holder", "active": False, "delisted_utc": f"{DAYS[9]}T04:00:00Z",
     "type": "CS"},
    {"ticker": "HLD", "cik": "72", "name": "New Holder", "active": True, "type": "CS"}]
# (time, open, high, low, close, volume) added to a symbol's usual bars on one day.
EXTRA = {
    ("ABC", TODAY): [("07:00", 2.1, 2.2, 2.0, 2.1, 5000)],
    ("UPP", TODAY): [("09:45", 2.0, 3.05, 1.95, 3.0, 500)],        # +50% first, at 09:45
    ("DWN", TODAY): [("09:40", 2.0, 2.1, 0.99, 1.0, 500)],         # -50% first, at 09:40
    ("BTH", TODAY): [("09:35", 2.0, 3.1, 0.9, 2.0, 500)],          # both inside one bar
    ("SRG", TODAY): [("07:00", 2.0, 2.2, 2.0, 2.2, 1000)],         # 101x at 07:00
    ("FST", TODAY): [("05:00", 2.0, 2.0, 2.0, 2.0, 1000)],         # over the line before a 07:00 window
    ("LAT", D21): [("10:00", 2.0, 3.2, 2.0, 3.0, 500)],            # +50% the session after the entry
    ("LBO", D21): [("10:00", 2.0, 3.2, 0.9, 2.0, 500)],            # both inside that later session
}


def flat(price: float, *at_volume) -> list[tuple]:
    return [(t, price, price, price, price, v) for t, v in at_volume]


def bars_for(symbol: str, i: int) -> list[tuple]:
    day = DAYS[i]
    if symbol == "SPL":                         # 1-for-10 reverse split on SPLIT_DAY
        price, volume = (1.0, 10_000) if i < 15 else (10.0, 1_000)
        return flat(price, ("09:29", volume))
    bars = flat(2.0, ("04:30", 10), ("08:00", 100), ("09:29", 100 * (i + 1)), ("12:00", 300))
    if symbol == "NTH" and day == TODAY:        # a high before the entry: never an outcome
        bars = [b if b[0] != "09:29" else ("09:29", 2.0, 9.0, 2.0, 2.0, b[5]) for b in bars]
    return sorted(bars + EXTRA.get((symbol, day), []))


def write_folder(root: Path) -> None:
    for i, day in enumerate(DAYS):
        minute, day_rows = [], []
        for symbol in SYMBOLS:
            bars = bars_for(symbol, i)
            minute += [f"{symbol},{v},{o},{c},{h},{lo},{reads._ns(day, t)},1" for t, o, h, lo, c, v in bars]
            day_rows.append(f"{symbol},{sum(b[5] for b in bars)},{bars[0][1]},{bars[-1][4]},"
                            f"{max(b[2] for b in bars)},{min(b[3] for b in bars)},{reads._ns(day, '00:00')},1")
        write_gz(root, "minute_aggs_v1", day, HEADER, minute)
        write_gz(root, "day_aggs_v1", day, HEADER, sorted(day_rows))
    ref = root / "store" / "reference"
    ref.mkdir(parents=True, exist_ok=True)
    (ref / "tickers.json").write_text(json.dumps(TICKERS), encoding="utf-8")
    from day_movers import store
    with store.connect() as db:
        for i, day in enumerate(DAYS):
            db.execute("INSERT INTO sessions VALUES (?, ?, 0, 0, 0, 1, ?, NULL)",
                       (day, DAYS[i - 1] if i else None, 1000.0 + i))
        db.execute("INSERT INTO movers (session_date, symbol, split_listed, split_suspect, prev_volume, volume)"
                   " VALUES (?, 'LKS', 0, 1, 1000000, 1000)", (LIKELY_DAY,))
        db.commit()


def patch(mp, massive_root: Path, table_root: Path) -> None:
    mp.setenv("NOVA_MARKET_DATA_DIR", str(massive_root))
    mp.setenv("NOVA_RVOL_DIR", str(table_root))
    mp.setattr(slots, "heavy", lambda what, wait=0: contextlib.nullcontext())
    mp.setattr(tickers, "_list_date", lambda symbol, cik: NEW_OWNER_FROM if cik == "72" else None)
    frame = pd.DataFrame([{"ticker": "SPL", "execution_date": date.fromisoformat(SPLIT_DAY), "split_from": 10.0,
                           "split_to": 1.0, "source": "massive", "price_factor": 10.0}])
    mp.setattr(splits, "_all", lambda: (frame, "test"))
    tickers.clear()
    daily.clear()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    base = tmp_path_factory.mktemp("rvol")
    with pytest.MonkeyPatch.context() as mp:
        patch(mp, base / "massive", base / "rvol")
        write_folder(base / "massive")
        build_rvol.build(say=lambda *_: None, polite=False)
    return base


@pytest.fixture
def table(built, monkeypatch):
    patch(monkeypatch, built / "massive", built / "rvol")
    yield built
    tickers.clear()
    daily.clear()


def minutes(day: str) -> pd.DataFrame:
    return pq.read_table(rs.minutes_path(day)).to_pandas()


def days_rows(day: str) -> pd.DataFrame:
    return pq.read_table(rs.days_path(day)).to_pandas().set_index("symbol")


def test_the_baselines_are_stock_day_stats_own(table):
    want = stats.stock_day_stats("ABC", TODAY, rvol_days=20, spread=False)["rvol"]["by_minute"]
    bar = minutes(TODAY).query("symbol == 'ABC' and m == 569").iloc[0]          # the 09:29 bar
    assert bar.cum == want["09:35"]["cum_volume"]
    assert bar.base == pytest.approx(want["09:35"]["avg_cum_volume"], rel=1e-6)
    for clock in ("09:35", "12:00", "16:00"):                                   # no bar at 09:34 / 11:59 / 15:59
        row = rvol.scan(clock, filters={"symbol": "ABC", "date_from": TODAY, "date_to": TODAY}).iloc[0]
        assert row.volume == want[clock]["cum_volume"]
        assert row.base_volume == pytest.approx(want[clock]["avg_cum_volume"], rel=1e-9)
        assert row.rvol == pytest.approx(want[clock]["rvol"], rel=1e-9)
    assert days_rows(TODAY).loc["ABC", "base_sessions"] == 20


def test_a_resumed_build_writes_what_a_build_from_the_start_wrote(table, tmp_path):
    before = (minutes(TODAY), days_rows(TODAY))
    out = build_rvol.build(rebuild_from=D20, say=lambda *_: None, polite=False)
    assert out["built"] == len(DAYS) - 20
    pd.testing.assert_frame_equal(before[0], minutes(TODAY))
    pd.testing.assert_frame_equal(before[1], days_rows(TODAY))
    assert build_rvol.build(say=lambda *_: None, polite=False)["built"] == 0      # up to date


def test_a_changed_minute_file_rebuilds_that_day_and_every_later_one(table, tmp_path, monkeypatch):
    copy = tmp_path / "copy"
    shutil.copytree(table, copy)
    patch(monkeypatch, copy / "massive", copy / "rvol")
    path = copy / "massive" / "minute_aggs_v1" / D21[:4] / D21[5:7] / f"{D21}.csv.gz"
    path.write_bytes(path.read_bytes())                                          # a re-downloaded file
    import os
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 10**9))
    assert build_rvol.build(say=lambda *_: None, polite=False)["built"] == len(DAYS) - 21


def test_a_listed_split_puts_the_earlier_volume_on_todays_basis(table):
    split = days_rows(SPLIT_DAY).loc["SPL"]
    assert split["split"] == "listed" and split["prev_close"] == pytest.approx(10.0)       # $1.00 x 10
    after = minutes(DAYS[16]).query("symbol == 'SPL'").iloc[0]
    assert after.base == pytest.approx(1000.0)            # 10,000 old shares are 1,000 new ones: rvol 1, not 0.1
    assert after.cum / after.base == pytest.approx(1.0)


def test_a_likely_split_and_a_new_company_start_the_baseline_again(table):
    lks = days_rows(LIKELY_DAY).loc["LKS"]
    assert (lks["reset"], lks["split"], lks["base_sessions"], lks["epoch"]) == (
        "likely_split", "likely_split", 0, rs.ordinal(LIKELY_DAY))
    assert days_rows(DAYS[19]).loc["LKS", "base_sessions"] == 1
    scan = rvol.scan("09:30", filters={"date_from": LIKELY_DAY, "date_to": LIKELY_DAY}, min_base_sessions=0)
    assert "LKS" not in set(scan["symbol"])                                    # left out unless splits=include
    hld = days_rows(NEW_OWNER_FROM).loc["HLD"]
    assert hld["reset"] == "holder_changed" and hld["base_sessions"] == 0


def test_only_common_stocks_are_in_the_table_and_unknowns_wait_to_be_asked(table):
    rows = days_rows(TODAY)
    assert "ETFX" not in rows.index and rows.loc["UNK", "kind"] == "unknown"
    scan = rvol.scan("09:30", filters={"date_from": TODAY, "date_to": TODAY})
    assert "UNK" not in set(scan["symbol"])
    asked = rvol.scan("09:30", filters={"date_from": TODAY, "date_to": TODAY}, kinds=["unknown"])
    assert set(asked["symbol"]) == {"UNK"}


def test_a_trigger_is_the_first_bar_over_the_line_and_says_when_it_was_over_already(table):
    found = rvol.triggers(10, window_from="07:00", window_to="09:30", filters={"date_from": TODAY,
                                                                                "date_to": TODAY})
    by = found.set_index("symbol")
    assert (by.loc["SRG", "trigger_et"], by.loc["SRG", "entry_et"], bool(by.loc["SRG", "above_before"])) == (
        "07:00", "07:01", False)
    assert by.loc["SRG", "rvol"] == pytest.approx(1010 / 10)
    assert by.loc["FST", "trigger_et"] == "08:00" and bool(by.loc["FST", "above_before"]) is True
    fresh = rvol.triggers(10, window_from="07:00", window_to="09:30", fresh=True,
                          filters={"date_from": TODAY, "date_to": TODAY})
    assert "FST" not in set(fresh["symbol"]) and "SRG" in set(fresh["symbol"])
    assert found.attrs["rows"] == len(found)


def test_outcomes_read_nothing_before_the_entry_and_never_guess_inside_one_bar(table, tmp_path):
    out = tmp_path / "rows.parquet"
    answer = rvol_outcomes.outcomes(filters={"date_from": TODAY, "date_to": TODAY}, at="09:30", up_pct=50,
                                    down_pct=50, group_by="none", to_file=out)
    rows = pd.read_parquet(out).set_index("symbol")
    assert rows.loc["UPP", "outcome"] == "up" and rows.loc["UPP", "up_et"] == "09:45"
    assert rows.loc["DWN", "outcome"] == "down" and rows.loc["DWN", "down_et"] == "09:40"
    assert rows.loc["BTH", "outcome"] == "same_bar"
    assert rows.loc["NTH", "outcome"] == "neither" and rows.loc["NTH", "price"] == 2.0    # its 9.00 high was before
    assert rows.loc["NTH", "max_up_pct"] == pytest.approx(0.0)
    total = answer["summary"][-1]
    assert total["group"] == "all" and total["same_bar"] >= 1 and answer["control"] is None


def test_later_sessions_count_on_the_entry_days_basis(table, tmp_path):
    out = tmp_path / "rows.parquet"
    rvol_outcomes.outcomes(filters={"date_from": D20, "date_to": D20}, at="09:30", up_pct=50, down_pct=50,
                           horizon="days", days=2, to_file=out)
    rows = pd.read_parquet(out).set_index("symbol")
    assert rows.loc["LAT", "outcome"] == "up" and rows.loc["LBO", "outcome"] == "same_day"
    assert rows.loc["ABC", "outcome"] == "neither"


def test_the_control_is_a_same_minute_stock_that_had_not_crossed(table, tmp_path):
    out = tmp_path / "rows.parquet"
    trigger = {"rvol_min": 10, "window_from": "07:00", "window_to": "09:30"}
    answer = rvol_outcomes.outcomes(filters={"date_from": TODAY, "date_to": TODAY}, trigger=trigger,
                                    up_pct=50, down_pct=50, to_file=out)
    rows = pd.read_parquet(out)
    control = rows[rows["is_control"]]
    assert len(control) == len(rows[~rows["is_control"]]) == answer["entries"]
    picked = set(control["symbol"])
    assert picked.isdisjoint({"ABC", "SRG", "FST"})      # crossed by then, or already over the line
    assert set(control["entry_et"]) <= set(rows.loc[~rows["is_control"], "entry_et"])
    again = rvol_outcomes.outcomes(filters={"date_from": TODAY, "date_to": TODAY}, trigger=trigger,
                                   up_pct=50, down_pct=50)
    assert again["control"] == answer["control"]          # seeded: the same pick every time


def test_a_bad_ask_is_refused_with_its_reason(table):
    with pytest.raises(ValueError, match="date_from and date_to"):
        rvol.scan("09:30", filters={"date_from": TODAY})
    with pytest.raises(ValueError, match="outside the table's session"):
        rvol.scan("21:00", filters={"date_from": TODAY, "date_to": TODAY})
    with pytest.raises(ValueError, match="not both"):
        rvol_outcomes.outcomes(filters={"date_from": TODAY, "date_to": TODAY}, at="09:30", trigger={"rvol_min": 5})
    with pytest.raises(ValueError, match="no bar inside horizon"):
        rvol_outcomes.outcomes(filters={"date_from": TODAY, "date_to": TODAY}, at="16:00")
