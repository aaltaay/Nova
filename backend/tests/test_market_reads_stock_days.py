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
