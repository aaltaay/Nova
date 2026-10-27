"""find_stock_days (``research/market_reads/stock_days.py``, ADR 059): movers rows joined with the shares known that
day (SEC outstanding by default, labelled; the desk's own float when asked), the catalyst verdict and the halts, a
float filter that says what it filtered on, and cursor pages that add up to the whole answer."""
from __future__ import annotations

import json
import sqlite3
import sys
import types
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

pd = pytest.importorskip("pandas")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

import market_reads  # noqa: E402
from day_movers import schema  # noqa: E402
from market_reads import roots, stock_days, tickers  # noqa: E402

ET = ZoneInfo("America/New_York")


def _ts(day: str, hhmm: str) -> int:
    return int(datetime.fromisoformat(f"{day}T{hhmm}").replace(tzinfo=ET).timestamp())


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVA_RVOL_DIR", str(tmp_path / "rvol"))       # no table: every rvol_daily unknown
    path = roots.movers_db()
    path.parent.mkdir(parents=True)
    db = sqlite3.connect(path)
    schema.initialize(db)
    day = "2025-03-03"
    rows = [(day, s, "CS", 4.0, 0.8, 0, 100_000, 2_000_000, _ts(day, "09:41"), 5.2, 300_000)
            for s in ("AAA", "BBB", "CCC", "DDD", "REUS")]
    db.executemany("INSERT INTO movers (session_date, symbol, kind, prev_close, high_pct, split_suspect, prev_volume,"
                   " volume, up20_ts, pm_high, pm_volume) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    db.executemany("INSERT INTO sec_shares VALUES (?, ?, ?, ?, ?, ?)", [
        ("AAA", "1", "2025-01-31", "2025-02-14", 5_000_000, "10-Q"),
        ("BBB", "2", "2025-01-31", "2025-02-14", 50_000_000, "10-Q"),
        ("DDD", "4", "2024-06-30", "2024-08-14", 1_000_000, "10-Q"),      # as of 246 days before: too old
        ("REUS", "99", "2025-01-31", "2025-02-14", 2_000_000, "10-Q")])   # the ticker's former company
    db.executemany("INSERT INTO ticker_holders VALUES (?, ?, ?, ?)", [
        ("REUS", "99", None, "2020-01-02"), ("REUS", "7", "2020-01-03", None)])
    db.commit()
    db.close()
    ref = tmp_path / "store" / "reference"
    ref.mkdir(parents=True)
    (ref / "tickers.json").write_text(json.dumps([
        {"ticker": "REUS", "cik": "7", "name": "Now", "active": True, "type": "CS"},
        {"ticker": "REUS", "cik": "99", "name": "Then", "active": False, "type": "CS",
         "delisted_utc": "2020-01-02T05:00:00Z"}]), encoding="utf-8")
    monkeypatch.setattr(tickers, "_list_date", lambda symbol, cik: None)
    tickers.clear()
    fake_cat = types.SimpleNamespace(for_pairs=lambda pairs: {
        (day, "AAA"): {"verdict": "catalyst", "category": "clinical_data", "strength": "strong", "title": "Data",
                       "cutoff_kind": "open"}})
    fake_halts = types.SimpleNamespace(for_pairs=lambda pairs: {
        **{p: {"halts": 0, "codes": [], "luld": 0} for p in pairs if p[1] != "DDD"},
        (day, "BBB"): {"halts": 2, "first_halt_et": "09:44:10", "codes": ["LUDP"], "luld": 2},
        (day, "DDD"): {"halts": None, "codes": [], "luld": None}})            # a day the log does not cover
    for name, module in (("catalysts", fake_cat), ("halts", fake_halts)):
        monkeypatch.setitem(sys.modules, f"market_reads.{name}", module)
        monkeypatch.setattr(market_reads, name, module, raising=False)
    yield day
    tickers.clear()


def test_rows_carry_shares_catalyst_halts_and_marks_each_labelled(store):
    frame = stock_days.find_stock_days(filters={"date_from": store}, float_unknown="include")
    rows = {r["symbol"]: r for r in frame.to_dict("records")}
    assert rows["AAA"]["outstanding_shares"] == 5_000_000 and rows["AAA"]["float_source"] == "sec_shares_outstanding"
    assert rows["AAA"]["catalyst_verdict"] == "catalyst" and rows["AAA"]["up20_et"] == "09:41"
    assert rows["BBB"]["halts"] == 2 and rows["BBB"]["halt_codes"] == "LUDP"
    assert pd.isna(rows["CCC"]["float_shares"]) and pd.isna(rows["CCC"]["catalyst_verdict"])
    assert pd.isna(rows["DDD"]["outstanding_shares"])                   # older than 120 days: not known
    assert pd.isna(rows["REUS"]["outstanding_shares"])                  # the count is the former company's
    assert rows["AAA"]["high_pct"] == pytest.approx(80.0) and rows["AAA"]["pm_volume"] == 300_000
    assert "not free float" in frame.attrs["float_rule"]


def test_float_max_filters_shares_outstanding_and_unknowns_are_left_out(store):
    frame = stock_days.find_stock_days(filters={"date_from": store}, float_max=10_000_000)
    assert list(frame["symbol"]) == ["AAA"]
    only = stock_days.find_stock_days(filters={"date_from": store}, float_max=10_000_000, float_unknown="only")
    assert list(only["symbol"]) == ["CCC", "DDD", "REUS"]


def test_the_desks_own_float_is_a_basis_when_asked(store):
    from paths import cache_root
    archive = cache_root() / "archive.db"
    archive.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(archive)
    db.execute("CREATE TABLE IF NOT EXISTS enrichment_snapshots (session_date TEXT, symbol TEXT, float_shares REAL)")
    db.execute("DELETE FROM enrichment_snapshots")
    db.execute("INSERT INTO enrichment_snapshots VALUES (?, 'BBB', 8000000)", (store,))
    db.commit()
    db.close()
    try:
        best = stock_days.find_stock_days(filters={"date_from": store}, float_max=10_000_000, float_basis="best")
        assert dict(zip(best["symbol"], best["float_source"], strict=True)) == {
            "AAA": "sec_shares_outstanding", "BBB": "enrichment_snapshot"}
    finally:
        archive.unlink()


def test_catalyst_and_halt_filters(store):
    assert list(stock_days.find_stock_days(filters={"date_from": store}, catalyst=["catalyst"],
                                           float_unknown="include")["symbol"]) == ["AAA"]
    assert list(stock_days.find_stock_days(filters={"date_from": store}, halted=True,
                                           float_unknown="include")["symbol"]) == ["BBB"]
    calm = stock_days.find_stock_days(filters={"date_from": store}, halted=False, float_unknown="include")
    assert list(calm["symbol"]) == ["AAA", "CCC", "REUS"]                 # DDD's day is not covered: unknown


def test_halt_codes_keep_a_day_with_that_halt_and_leave_uncovered_days_out_counted(store):
    def find(codes):
        return stock_days.find_stock_days(filters={"date_from": store}, halt_codes=codes, float_unknown="include")
    assert list(find(["ludp"])["symbol"]) == ["BBB"]                      # a code, any case
    assert list(find(["luld"])["symbol"]) == ["BBB"]                      # the group word
    paused = find(["news"])
    assert paused.empty and paused.attrs["left_out"] == {"halts_unknown": 1}   # DDD: unknown, never "no halt"
    assert paused.attrs["filters"]["halt_codes"] == ["news"]


def _news(monkeypatch, day: str) -> None:
    def verdict(category, title):
        return {"verdict": "catalyst", "category": category, "strength": "strong", "title": title,
                "cutoff_kind": "target"}
    fake = types.SimpleNamespace(for_pairs=lambda pairs: {
        (day, "AAA"): verdict("clinical_data", "Positive Phase 2 Data"),
        (day, "BBB"): verdict("fda_regulatory", "FDA Approves BBB's Drug"),
        (day, "CCC"): verdict("FDA_Regulatory", "FDA Grants Orphan Drug Designation")})
    monkeypatch.setitem(sys.modules, "market_reads.catalysts", fake)
    monkeypatch.setattr(market_reads, "catalysts", fake, raising=False)


def test_the_news_type_and_headline_words_filter_the_verdicts(store, monkeypatch):
    """#1100 follow-up: 'FDA approval news' is the category plus a headline word, not the bare verdict."""
    _news(monkeypatch, store)
    fda = stock_days.find_stock_days(filters={"date_from": store}, catalyst_category=["fda_regulatory"],
                                     float_unknown="include")
    assert _symbols(fda) == ["BBB", "CCC"]                               # the category's case is ignored
    approved = stock_days.find_stock_days(filters={"date_from": store}, catalyst_category=["fda_regulatory"],
                                          catalyst_words=["APPROV", "clear"], float_unknown="include")
    assert _symbols(approved) == ["BBB"]
    assert approved.attrs["filters"]["catalyst_words"] == ["approv", "clear"]
    either = stock_days.find_stock_days(filters={"date_from": store}, catalyst_words=["data", "approv"],
                                        float_unknown="include")
    assert _symbols(either) == ["AAA", "BBB"]                            # any word; no verdict, no headline


def test_rvol_daily_joins_every_row_and_its_minimum_leaves_unknowns_out_counted(store, monkeypatch):
    known = {"AAA": (12.5, 50), "BBB": (3.0, 50), "CCC": (None, 7)}      # CCC: too few earlier sessions
    monkeypatch.setattr(stock_days.rvol_days, "for_pairs", lambda pairs: {
        p: ({"rvol_daily": known[p[1]][0], "rvol_volume": 1e6, "rvol_day_avg_volume": 8e4,
             "rvol_day_avg_sessions": known[p[1]][1]} if p[1] in known else None) for p in pairs})
    rows = {r["symbol"]: r for r in stock_days.find_stock_days(filters={"date_from": store},
                                                               float_unknown="include").to_dict("records")}
    assert rows["AAA"]["rvol_daily"] == 12.5 and rows["AAA"]["rvol_day_avg_sessions"] == 50
    assert pd.isna(rows["DDD"]["rvol_daily"])                            # not in the table: unknown
    hot = stock_days.find_stock_days(filters={"date_from": store}, rvol_daily_min=5, float_unknown="include")
    assert _symbols(hot) == ["AAA"]
    assert hot.attrs["left_out"] == {"rvol_unknown": 3}                  # CCC, DDD, REUS -- never read as low
    assert hot.attrs["note_rvol"].startswith("3 stock-days") and "day_avg_volume" in hot.attrs["rvol_rule"]
    with pytest.raises(ValueError, match="rvol_daily_min"):
        stock_days.find_stock_days(filters={"date_from": store}, rvol_daily_min=0)


def test_rvol_days_reads_the_tables_day_rows(tmp_path, monkeypatch):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    from market_reads import rvol_days, rvol_store
    monkeypatch.setenv("NOVA_RVOL_DIR", str(tmp_path))
    manifest = rvol_store.new_manifest()
    manifest["days"]["2025-03-03"] = {}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    path = rvol_store.days_path("2025-03-03")
    path.parent.mkdir(parents=True)
    pq.write_table(pa.table({"symbol": ["AAA", "NEW", "ZERO"], "volume": [1_000_000.0, 50_000.0, 10.0],
                             "day_avg_volume": [80_000.0, 1_000.0, 0.0], "day_avg_sessions": [50, 3, 40]}), path)
    got = rvol_days.for_pairs([("2025-03-03", "aaa"), ("2025-03-03", "NEW"), ("2025-03-03", "ZERO"),
                               ("2025-03-03", "GONE"), ("2025-03-04", "AAA")])
    assert got[("2025-03-03", "AAA")]["rvol_daily"] == 12.5
    assert got[("2025-03-03", "NEW")]["rvol_daily"] is None              # 3 earlier sessions: too little history
    assert got[("2025-03-03", "ZERO")]["rvol_daily"] is None             # a zero average is no ratio
    assert got[("2025-03-03", "GONE")] is None and got[("2025-03-04", "AAA")] is None   # not held / not built


def test_cursor_pages_add_up_to_the_whole_answer(store):
    seen, cursor = [], None
    for _ in range(5):
        page = stock_days.find_stock_days(filters={"date_from": store}, float_unknown="include", page_size=2,
                                          cursor=cursor)
        seen += list(page["symbol"])
        cursor = page.attrs["next_cursor"]
        if cursor is None:
            break
    assert seen == ["AAA", "BBB", "CCC", "DDD", "REUS"]


def test_a_broad_or_malformed_ask_is_refused(store):
    with pytest.raises(ValueError, match="date_from / date_to or a symbol"):
        stock_days.find_stock_days(filters={"high_min": 50})
    with pytest.raises(ValueError, match="cursor"):
        stock_days.find_stock_days(filters={"date_from": store}, cursor="junk")
    with pytest.raises(ValueError, match="float_basis"):
        stock_days.find_stock_days(filters={"date_from": store}, float_basis="yahoo")
    with pytest.raises(ValueError, match="page_size"):
        stock_days.find_stock_days(filters={"date_from": store}, page_size=stock_days.PAGE_MAX + 1)


# --- ranking, kinds and the outstanding_max alias (#1086) --------------------------------------------------------
# (day, symbol, kind, high_pct as the store keeps it -- a fraction -- and the volume)
RANKED = [
    ("2025-03-03", "AAA", "CS", 0.5, 900), ("2025-03-03", "BBB", "CS", 2.0, 800),
    ("2025-03-03", "ABCDW", "WARRANT", 9.0, 700), ("2025-03-03", "ETFX", "ETF", 0.9, 600),
    ("2025-03-03", "NULB", "CS", None, 250),
    ("2025-03-04", "CCC", "CS", 0.5, 500), ("2025-03-04", "DDD", "ADRC", 2.0, 400),
    ("2025-03-04", "NONE", "CS", None, 300), ("2025-03-04", "UNLB", None, 1.0, 200),
    ("2025-03-04", "LONGSYM", None, 3.0, 100), ("2025-03-05", "EEE", "CS", 0.7, 1000),
]
COMMON = ["AAA", "BBB", "NULB", "CCC", "DDD", "NONE", "UNLB", "EEE"]
BY_HIGH = ["DDD", "BBB", "UNLB", "EEE", "CCC", "AAA", "NONE", "NULB"]   # ties newest day first; no figure last, same


@pytest.fixture
def ranked(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVA_RVOL_DIR", str(tmp_path / "rvol"))
    path = roots.movers_db()
    path.parent.mkdir(parents=True)
    db = sqlite3.connect(path)
    schema.initialize(db)
    db.executemany("INSERT INTO movers (session_date, symbol, kind, prev_close, high_pct, split_suspect, prev_volume,"
                   " volume) VALUES (?, ?, ?, 4.0, ?, 0, 100000, ?)", RANKED)
    db.executemany("INSERT INTO sec_shares VALUES (?, ?, '2025-01-31', '2025-02-14', ?, '10-Q')", [
        ("AAA", "1", 5_000_000), ("BBB", "2", 50_000_000), ("DDD", "4", 8_000_000), ("UNLB", "5", 3_000_000),
        ("EEE", "6", 5_000_000), ("ABCDW", "7", 1_000_000)])
    db.commit()
    db.close()
    tickers.clear()
    fake_cat = types.SimpleNamespace(for_pairs=lambda pairs: {})
    fake_halts = types.SimpleNamespace(for_pairs=lambda pairs: {p: {"halts": 0, "codes": [], "luld": 0} for p in pairs})
    for name, module in (("catalysts", fake_cat), ("halts", fake_halts)):
        monkeypatch.setitem(sys.modules, f"market_reads.{name}", module)
        monkeypatch.setattr(market_reads, name, module, raising=False)
    yield {"date_from": "2025-03-03"}
    tickers.clear()


def _symbols(frame) -> list[str]:
    return list(frame["symbol"])


def test_kinds_default_to_common_stock_like_the_movers_search(ranked):
    frame = stock_days.find_stock_days(filters=ranked, float_unknown="include")
    assert _symbols(frame) == COMMON                                  # no warrant, ETF or long unlabelled symbol
    assert frame.attrs["filters"]["kinds"] == "common" and "common stock" in frame.attrs["kinds_rule"]
    everything = stock_days.find_stock_days(filters=ranked, kinds=["all"], float_unknown="include")
    assert len(everything) == len(RANKED) and everything.attrs["filters"]["kinds"] == "all"
    etf = stock_days.find_stock_days(filters=ranked, kinds=["etf", "warrant"], float_unknown="include")
    assert _symbols(etf) == ["ABCDW", "ETFX"] and etf.attrs["filters"]["kinds"] == ["ETF", "WARRANT"]
    both = stock_days.find_stock_days(filters=ranked, kinds="ETF,ADRC", float_unknown="include")
    assert _symbols(both) == ["ETFX", "DDD"]
    with pytest.raises(ValueError, match="stands alone"):
        stock_days.find_stock_days(filters=ranked, kinds=["all", "ETF"])


def test_a_named_symbol_is_not_filtered_by_kind_unless_asked(ranked):
    named = stock_days.find_stock_days(filters=ranked, symbol="ABCDW", float_unknown="include")
    assert _symbols(named) == ["ABCDW"] and "named symbol" in named.attrs["kinds_rule"]
    assert named.attrs["filters"]["kinds"] == "all"
    assert len(stock_days.find_stock_days(filters=ranked, symbol="ABCDW", kinds=["common"],
                                          float_unknown="include")) == 0


@pytest.mark.parametrize("sort,expected", [
    ("high", BY_HIGH),
    ("newest", ["EEE", "CCC", "DDD", "NONE", "UNLB", "AAA", "BBB", "NULB"]),
    ("oldest", ["AAA", "BBB", "NULB", "CCC", "DDD", "NONE", "UNLB", "EEE"]),
    ("volume", ["EEE", "AAA", "BBB", "CCC", "DDD", "NONE", "NULB", "UNLB"])])
def test_sort_ranks_like_the_movers_search(ranked, sort, expected):
    frame = stock_days.find_stock_days(filters=ranked, sort=sort, float_unknown="include")
    assert _symbols(frame) == expected
    assert frame.attrs["filters"]["sort"] == sort


@pytest.mark.parametrize("sort", ["newest", "oldest", "high", "low", "close", "gap", "volume", "dollar_volume"])
def test_the_ranking_matches_the_movers_search_answer(ranked, sort):
    """The same filters through the capped search (``reads.movers``) and ``find_stock_days`` rank alike, including
    the rows without the figure (two of them here, on different days)."""
    from market_reads import reads
    ours = stock_days.find_stock_days(filters=ranked, sort=sort, float_unknown="include")
    theirs = reads.movers(date_from="2025-03-03", sort=sort, limit=50)
    assert [(r["date"], r["symbol"]) for r in theirs["rows"]] == list(zip(ours["date"], ours["symbol"], strict=True))


@pytest.mark.parametrize("sort", ["high", "low", "newest", "oldest", "volume", "close", "gap", "dollar_volume"])
@pytest.mark.parametrize("size", [1, 2, 3])
def test_ranked_pages_resume_exactly_where_they_stopped(ranked, sort, size):
    """Every page resumes strictly after the last row examined in the same order: no repeat, no hole, null last."""
    whole = stock_days.find_stock_days(filters=ranked, sort=sort, float_unknown="include")
    seen, cursor = [], None
    for _ in range(12):
        page = stock_days.find_stock_days(filters=ranked, sort=sort, float_unknown="include", limit=size,
                                          cursor=cursor)
        seen += list(zip(page["date"], page["symbol"], strict=True)) if len(page) else []
        cursor = page.attrs["next_cursor"]
        if cursor is None:
            break
    assert seen == list(zip(whole["date"], whole["symbol"], strict=True)) and len(seen) == len(COMMON)


def test_the_float_filter_picks_from_the_ranking(ranked):
    best = stock_days.find_stock_days(filters=ranked, sort="high", outstanding_max=10_000_000, limit=2)
    assert _symbols(best) == ["DDD", "UNLB"]                    # BBB (50M) is over the limit, NONE has no count
    rest = stock_days.find_stock_days(filters=ranked, sort="high", outstanding_max=10_000_000, limit=9,
                                      cursor=best.attrs["next_cursor"])
    assert _symbols(rest) == ["EEE", "AAA"]


def test_a_cursor_outside_the_search_is_refused_for_a_ranking(ranked):
    with pytest.raises(ValueError, match="not a row of the movers index"):
        stock_days.find_stock_days(filters=ranked, sort="high", cursor="2025-03-03|ZZZZ")
    with pytest.raises(ValueError, match="sort must be one of"):
        stock_days.find_stock_days(filters=ranked, sort="biggest")


def test_outstanding_max_is_the_float_max_limit_named_for_what_it_filters(ranked):
    named = stock_days.find_stock_days(filters=ranked, outstanding_max=10_000_000)
    plain = stock_days.find_stock_days(filters=ranked, float_max=10_000_000)
    assert _symbols(named) == _symbols(plain) == ["AAA", "DDD", "UNLB", "EEE"]
    assert named.attrs["filters"]["outstanding_max"] == 10_000_000 and named.attrs["filters"]["float_max"] is None
    with pytest.raises(ValueError, match="not both"):
        stock_days.find_stock_days(filters=ranked, float_max=1, outstanding_max=1)
    with pytest.raises(ValueError, match="sec_outstanding"):
        stock_days.find_stock_days(filters=ranked, outstanding_max=1, float_basis="best")


def test_limit_is_page_size_under_the_movers_searchs_name(ranked):
    assert len(stock_days.find_stock_days(filters=ranked, limit=2, float_unknown="include")) == 2
    assert len(stock_days.find_stock_days(filters=ranked, limit=2, page_size=2, float_unknown="include")) == 2
    with pytest.raises(ValueError, match="page_size"):
        stock_days.find_stock_days(filters=ranked, limit=2, page_size=3)
    with pytest.raises(ValueError, match="page_size / limit must be"):
        stock_days.find_stock_days(filters=ranked, limit=stock_days.PAGE_MAX + 1)
