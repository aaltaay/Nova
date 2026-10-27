"""The relative-volume table (#1100: ``research/rvol/build_rvol.py``, ``research/market_reads/rvol*.py``) on a tiny
fake Massive folder: its baselines are ``stock_day_stats``' own, a resumed build writes what a full build writes, a
listed split puts earlier volume on today's basis, a likely split or a new company starts the baseline again, only
common stocks are in it, triggers say when the stock was already over the line, outcomes read nothing before the
entry and never guess the order inside one bar, later sessions count, and the control is a same-minute stock. The
day-fact filters (news, shares, halts: ``rvol_facts`` through ``day_facts``) join nothing unless asked, keep what
passes, count the unknowns they leave out, group the outcomes, and hold the control pool to the same universe."""
from __future__ import annotations

import contextlib
import json
import shutil
import sys
import types
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

import market_reads  # noqa: E402
from market_reads import daily, day_facts, reads, rvol, rvol_outcomes, slots, splits, stats, tickers  # noqa: E402
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
COMMON = ("ABC", "UPP", "DWN", "BTH", "NTH", "SRG", "FST", "PRE", "LAT", "LBO", "SPL", "LKS")
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
    ("PRE", TODAY): [("05:00", 2.0, 2.0, 2.0, 2.0, 200)],          # over it at 05:00, never again in the window
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


def test_a_stock_over_the_line_before_the_window_is_never_a_control(table):
    window = {"rvol_min": 10, "window_from": "07:00", "window_to": "09:30"}
    found = rvol.triggers(10, window_from="07:00", window_to="09:30", filters={"date_from": TODAY, "date_to": TODAY})
    assert "PRE" not in set(found["symbol"])             # no hit inside the window: not a trigger
    picked = set()
    for seed in range(1, 41):
        out = Path(rs.root()).parent / f"controls-{seed}.parquet"
        rvol_outcomes.outcomes(filters={"date_from": TODAY, "date_to": TODAY}, trigger=window, seed=seed, to_file=out)
        frame = pd.read_parquet(out)
        picked |= set(frame.loc[frame["is_control"], "symbol"])
        out.unlink()
    assert "PRE" not in picked and "FST" not in picked and len(picked) > 2


def test_a_horizon_past_the_last_session_is_open_and_left_out(table, tmp_path):
    done = rvol_outcomes.outcomes(filters={"date_from": D21, "date_to": D21}, at="09:30", horizon="days", days=2)
    assert done["entries"] and done["meta"]["left_out"]["horizon_open"] == 0      # D21 + 2 sessions = TODAY
    out = tmp_path / "open.parquet"
    late = rvol_outcomes.outcomes(filters={"date_from": DAYS[22], "date_to": DAYS[22]}, at="09:30", horizon="days",
                                  days=2, to_file=out)
    assert late["summary"] == [] and late["meta"]["left_out"]["horizon_open"] == late["entries"] > 0
    assert set(pd.read_parquet(out)["outcome"]) == {"horizon_open"}


def test_an_output_file_holds_this_answer_only(table, tmp_path):
    out = tmp_path / "t.csv"
    every = {"date_from": DAYS[0], "date_to": TODAY}
    rvol.triggers(10, window_from="07:00", window_to="09:30", filters=every, to_file=out)
    first = pd.read_csv(out)
    rvol.triggers(10, window_from="07:00", window_to="09:30", filters={**every, "symbol": "SRG"}, to_file=out)
    again = pd.read_csv(out)
    assert len(first) > len(again) and set(again["symbol"]) == {"SRG"}
    rvol.triggers(10_000_000, window_from="07:00", window_to="09:30", filters=every, to_file=out)
    assert len(pd.read_csv(out)) == 0 and "trigger_et" in pd.read_csv(out).columns


# --- day facts on the relative-volume reads (find_stock_days' filters through day_facts' join) --------------------
# TODAY's facts behind the join; every other stock-day is unknown (no verdict, no SEC count).
VERDICTS = {"UPP": ("catalyst", "fda_regulatory", "FDA Approves UPP's Drug"),
            "DWN": ("catalyst", "Clinical_Data", "Phase 2 Data Misses"),
            "SRG": ("catalyst", "fda_regulatory", "FDA Clears SRG's Device"),
            "BTH": ("none_found", None, None)}                          # judged: no news found -- not unknown
SHARES = {"SRG": 2_000_000, "UPP": 3_000_000, "DWN": 8_000_000, "NTH": 12_000_000, "BTH": 30_000_000,
          "ABC": 60_000_000}
HALTS = {"UPP": {"halts": 1, "first_halt_et": "09:50:00", "codes": ["T1"], "luld": 0, "news": 1},
         "DWN": {"halts": 1, "first_halt_et": "09:41:00", "codes": ["LUDP"], "luld": 1, "news": 0},
         "NTH": {"halts": None, "codes": [], "luld": None, "news": None}}   # a day the halt log does not cover
TODAY_ONLY = {"date_from": TODAY, "date_to": TODAY}
WINDOW = {"window_from": "07:00", "window_to": "09:30"}


@pytest.fixture
def facts(table, monkeypatch):
    """Fake stores behind ``day_facts.for_pairs``; the answer is every pair each part was asked for."""
    asked = {"catalyst": [], "halts": [], "shares": []}

    def verdicts(pairs):
        asked["catalyst"] += pairs
        return {p: {"verdict": VERDICTS[p[1]][0], "category": VERDICTS[p[1]][1], "title": VERDICTS[p[1]][2],
                    "strength": "strong", "cutoff_kind": "target"} for p in pairs if p[0] == TODAY and p[1] in VERDICTS}

    def stops(pairs):
        asked["halts"] += pairs
        return {p: HALTS.get(p[1], {"halts": 0, "codes": [], "luld": 0, "news": 0}) for p in pairs}

    def counts(pairs):
        asked["shares"] += pairs
        return {p: {"shares": SHARES[p[1]], "as_of": "2026-06-30", "filed": "2026-08-01", "age_days": 70}
                for p in pairs if p[0] == TODAY and p[1] in SHARES}
    for name, fake in (("catalysts", types.SimpleNamespace(for_pairs=verdicts)),
                       ("halts", types.SimpleNamespace(for_pairs=stops))):
        monkeypatch.setitem(sys.modules, f"market_reads.{name}", fake)
        monkeypatch.setattr(market_reads, name, fake, raising=False)
    monkeypatch.setattr(day_facts, "_outstanding", counts)
    return asked


def _symbols(frame) -> set[str]:
    return set(frame["symbol"])


def test_without_a_day_fact_filter_nothing_is_joined_and_the_answer_is_as_before(facts):
    scan = rvol.scan("09:30", filters=TODAY_ONLY, float_basis="best")       # a basis alone filters nothing
    found = rvol.triggers(10, filters=TODAY_ONLY, **WINDOW)
    after = rvol_outcomes.outcomes(filters=TODAY_ONLY, trigger={"rvol_min": 10, **WINDOW})
    assert facts == {"catalyst": [], "halts": [], "shares": []}
    for frame in (scan, found):
        assert not {*day_facts.SHARES, *day_facts.CATALYST, *day_facts.HALTS} & set(frame.columns)
        assert "day_facts" not in frame.attrs and "left_out" not in frame.attrs
    assert "day_facts" not in after["meta"] and "float_buckets" not in after["meta"]
    assert set(after["meta"]["left_out"]) == {"no_price", "split", "base_sessions", "horizon_reset", "horizon_open"}


def test_the_news_filters_keep_what_passes_join_only_their_part_and_count_the_unknowns(facts):
    total = len(rvol.scan("09:30", filters=TODAY_ONLY))
    news = rvol.scan("09:30", filters=TODAY_ONLY, catalyst=["catalyst"])
    assert _symbols(news) == {"UPP", "DWN", "SRG"} and news.attrs["rows"] == 3
    assert news.attrs["left_out"] == {"catalyst_unknown": total - 4}       # BTH was judged none_found: not unknown
    upp = news.set_index("symbol").loc["UPP"]
    assert (upp["catalyst_verdict"], upp["catalyst_category"], upp["catalyst_title"]) == (
        "catalyst", "fda_regulatory", "FDA Approves UPP's Drug")
    assert "float_shares" not in news.columns and "halts" not in news.columns
    assert facts["shares"] == facts["halts"] == [] and len(facts["catalyst"]) == total
    assert news.attrs["day_facts"]["joined"] == ["catalyst"] and news.attrs["day_facts"]["examined"] == total
    assert news.attrs["day_facts"]["filters"]["catalyst"] == ["catalyst"]
    assert _symbols(rvol.scan("09:30", filters=TODAY_ONLY, catalyst="catalyst")) == _symbols(news)   # one bare word
    assert _symbols(rvol.scan("09:30", filters=TODAY_ONLY, catalyst=["unknown"])) == _symbols(
        rvol.scan("09:30", filters=TODAY_ONLY)) - {"UPP", "DWN", "SRG", "BTH"}
    approved = rvol.scan("09:30", filters=TODAY_ONLY, catalyst_category=["FDA_Regulatory"], catalyst_words=["approv"])
    assert _symbols(approved) == {"UPP"}
    assert _symbols(rvol.scan("09:30", filters=TODAY_ONLY, catalyst_words=["approv", "clear"])) == {"UPP", "SRG"}


def test_the_share_filter_reads_its_basis_and_never_reads_an_unknown_as_small(facts):
    total = len(rvol.scan("09:30", filters=TODAY_ONLY))
    small = rvol.scan("09:30", filters=TODAY_ONLY, float_max=10_000_000)
    assert _symbols(small) == {"SRG", "UPP", "DWN"}
    assert small.attrs["left_out"] == {"shares_unknown": total - len(SHARES)}
    srg = small.set_index("symbol").loc["SRG"]
    assert (srg["float_shares"], srg["float_source"], srg["outstanding_as_of"]) == (
        2_000_000, "sec_shares_outstanding", "2026-06-30")
    unknown = _symbols(rvol.scan("09:30", filters=TODAY_ONLY)) - set(SHARES)
    included = rvol.scan("09:30", filters=TODAY_ONLY, float_max=10_000_000, float_unknown="include")
    assert _symbols(included) == {"SRG", "UPP", "DWN"} | unknown and included.attrs["left_out"] == {}
    assert _symbols(rvol.scan("09:30", filters=TODAY_ONLY, float_unknown="only")) == unknown


def test_the_halt_filters_name_codes_or_groups_and_leave_an_uncovered_day_out(facts):
    total = len(rvol.scan("09:30", filters=TODAY_ONLY))
    news = rvol.scan("09:30", filters=TODAY_ONLY, halt_codes=["news"])
    assert _symbols(news) == {"UPP"} and news.attrs["left_out"] == {"halts_unknown": 1}     # NTH: not covered
    assert news.set_index("symbol").loc["UPP", "halt_codes"] == "T1"
    assert _symbols(rvol.scan("09:30", filters=TODAY_ONLY, halt_codes=["ludp"])) == {"DWN"}
    assert _symbols(rvol.scan("09:30", filters=TODAY_ONLY, halt_codes=["luld"])) == {"DWN"}
    calm = rvol.scan("09:30", filters=TODAY_ONLY, halted=False)
    assert len(calm) == total - 3 and not {"UPP", "DWN", "NTH"} & _symbols(calm)


def test_triggers_take_the_filters_and_their_file_holds_the_fact_columns(facts, tmp_path):
    plain = rvol.triggers(10, filters=TODAY_ONLY, **WINDOW)
    assert _symbols(plain) == {"ABC", "SRG", "FST"}
    out = tmp_path / "fda.parquet"
    fda = rvol.triggers(10, filters=TODAY_ONLY, catalyst_category=["fda_regulatory"], to_file=out, **WINDOW)
    assert list(fda["symbol"]) == ["SRG"] and fda.attrs["rows"] == 1
    assert {p[1] for p in facts["catalyst"]} == {"ABC", "SRG", "FST"}       # only the triggers were looked up
    assert fda.attrs["left_out"] == {"catalyst_unknown": 2}
    written = pd.read_parquet(out)
    assert list(written["symbol"]) == ["SRG"] and written.loc[0, "catalyst_title"] == "FDA Clears SRG's Device"
    none = tmp_path / "none.csv"
    rvol.triggers(10, filters=TODAY_ONLY, catalyst=["negative"], float_max=1e9, to_file=none, **WINDOW)
    empty = pd.read_csv(none)
    assert len(empty) == 0 and {"trigger_et", "catalyst_verdict", "float_shares"} <= set(empty.columns)


def test_outcomes_group_by_the_verdict_its_category_and_the_float_bucket(facts):
    def groups(answer):
        return {g["group"]: g["entries"] for g in answer["summary"]}
    verdict = rvol_outcomes.outcomes(filters=TODAY_ONLY, at="09:30", group_by="catalyst")
    total = verdict["entries"]
    assert [g["group"] for g in verdict["summary"]] == ["catalyst", "none_found", "unknown", "all"]
    assert groups(verdict) == {"catalyst": 3, "none_found": 1, "unknown": total - 4, "all": total}
    category = rvol_outcomes.outcomes(filters=TODAY_ONLY, at="09:30", group_by="catalyst_category")
    assert groups(category) == {"clinical_data": 1, "fda_regulatory": 2, "no category": 1, "unknown": total - 4,
                                "all": total}
    size = rvol_outcomes.outcomes(filters=TODAY_ONLY, at="09:30", group_by="float")
    assert [g["group"] for g in size["summary"]] == ["<5M", "5-10M", "10-20M", "20-50M", "50M+", "unknown", "all"]
    assert groups(size)["<5M"] == 2 and groups(size)["unknown"] == total - len(SHARES)
    assert size["meta"]["float_buckets"]["edges"] == [5_000_000, 10_000_000, 20_000_000, 50_000_000]
    assert size["meta"]["day_facts"]["joined"] == ["shares"] and facts["halts"] == []
    assert "catalyst_unknown" not in size["meta"]["left_out"]               # a group leaves nothing out


def test_outcome_filters_narrow_the_entries_and_the_control_pool_alike(facts, tmp_path):
    trigger = {"rvol_min": 10, **WINDOW}

    def controls(seeds, **facts_asked):
        picked, answer = set(), None
        for seed in seeds:
            out = tmp_path / f"c{seed}-{len(facts_asked)}.parquet"
            answer = rvol_outcomes.outcomes(filters=TODAY_ONLY, trigger=trigger, seed=seed, to_file=out,
                                            **facts_asked)
            rows = pd.read_parquet(out)
            picked |= set(rows.loc[rows["is_control"], "symbol"])
        return picked, answer, rows
    anyone, _answer, _rows = controls(range(1, 13))
    assert anyone - set(SHARES)                       # unfiltered, a control can be a stock with no SEC count
    picked, answer, rows = controls(range(1, 13), float_max=100_000_000, group_by="float")
    assert set(rows.loc[~rows["is_control"], "symbol"]) == {"ABC", "SRG"}      # FST's count is unknown
    assert picked and picked <= set(SHARES) - {"ABC", "SRG"}                   # the same universe
    assert answer["meta"]["left_out"]["shares_unknown"] == 1
    assert {g["group"]: g["entries"] for g in answer["control"]} == {"<5M": 1, "50M+": 1, "all": 2}
    assert "control" in answer["meta"]["day_facts"]["rules"] and "group" in answer["meta"]["day_facts"]["rules"]


def test_a_bad_day_fact_ask_is_refused_with_its_reason(facts):
    with pytest.raises(ValueError, match="float_basis"):
        rvol.scan("09:30", filters=TODAY_ONLY, float_basis="yahoo")
    with pytest.raises(ValueError, match="float_unknown"):
        rvol.triggers(10, filters=TODAY_ONLY, float_unknown="maybe", **WINDOW)
    with pytest.raises(ValueError, match="halted"):
        rvol.scan("09:30", filters=TODAY_ONLY, halted="no")
    with pytest.raises(TypeError):
        rvol.scan("09:30", filters=TODAY_ONLY, float_min=1)
    with pytest.raises(ValueError, match="group_by"):
        rvol_outcomes.outcomes(filters=TODAY_ONLY, at="09:30", group_by="sector")
