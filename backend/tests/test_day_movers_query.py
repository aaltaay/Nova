"""Searching the day movers index (ADR 050): numbers in, matches and their percentages out.

Percent arguments are percent points; "common" leaves warrants and type-less five-letter tickers out; a likely
split (a suspect that traded no more shares than the day before) is left out unless asked; the time of the high,
the close's place in the range and the give-back filter; the summary covers every match; a float passes only on
evidence -- the float Nova knew that day, or SEC shares outstanding under the limit -- else it is unknown.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from day_movers import floats, query, store
from day_movers.schema import UnknownDayMoversSchema

ET = ZoneInfo("America/New_York")


def ts(day: str, hh: int, mm: int) -> int:
    d = date.fromisoformat(day)
    return int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET).timestamp())


def mover(day: str, symbol: str, *, pc: float, o: float, hi: float, lo: float, c: float, kind: str | None = "CS",
          volume: float = 1_000_000, prev_volume: float = 100_000, suspect: int = 0, high_at=(10, 0), **extra):
    row = {
        "session_date": day, "symbol": symbol, "kind": kind, "prev_date": "x", "prev_close": pc,
        "prev_volume": prev_volume, "split_factor": 1.0, "split_listed": 0, "split_suspect": suspect,
        "open": o, "high": hi, "low": lo, "close": c, "volume": volume, "day_high": hi, "day_low": lo,
        "day_high_ts": ts(day, *high_at), "day_low_ts": ts(day, 9, 30), "dollar_volume": volume * c,
        "high_pct": hi / pc - 1, "low_pct": lo / pc - 1, "close_pct": c / pc - 1, "gap_pct": o / pc - 1,
        "up10_ts": ts(day, 7, 0), "up20_ts": ts(day, 8, 0),
    }
    row.update(extra)
    return row


@pytest.fixture
def db(tmp_path):
    target = tmp_path / "movers.sqlite3"
    sessions = {
        "2026-09-24": [
            mover("2026-09-24", "OLDR", pc=2.0, o=2.2, hi=9.0, lo=2.1, c=8.5, high_at=(15, 30)),    # +350%, held
        ],
        "2026-09-25": [
            mover("2026-09-25", "MSGY", pc=1.97, o=2.13, hi=12.73, lo=1.97, c=8.07, high_at=(17, 4)),  # +546%
            mover("2026-09-25", "FADE", pc=1.0, o=1.5, hi=4.5, lo=1.0, c=1.2, high_at=(9, 40)),        # +350%, faded
            mover("2026-09-25", "BIGP", pc=30.0, o=31, hi=130.0, lo=30.0, c=120.0),                     # $30 stock
            mover("2026-09-25", "WARRW", pc=0.1, o=0.1, hi=0.5, lo=0.1, c=0.4, kind="WARRANT"),
            mover("2026-09-25", "ABCDE", pc=1.0, o=1.0, hi=5.0, lo=1.0, c=4.0, kind=None),             # 5 letters, no type
            mover("2026-09-25", "XYZ", pc=1.0, o=1.0, hi=5.0, lo=1.0, c=4.0, kind=None),               # 3 letters, no type
            mover("2026-09-25", "RVSP", pc=0.9, o=14.0, hi=14.5, lo=12.5, c=13.0, suspect=1,
                  volume=15_812, prev_volume=412_227),                                                    # likely split
            mover("2026-09-25", "KITT", pc=0.49, o=3.2, hi=8.4, lo=2.2, c=2.3, suspect=1,
                  volume=11_784_145, prev_volume=748_821),                                                # suspect, traded more
            mover("2026-09-25", "DOWN", pc=10.0, o=9.0, hi=10.0, lo=5.0, c=5.5),                        # -45%
            mover("2026-09-25", "MIDS", pc=1.0, o=2.0, hi=2.5, lo=1.9, c=2.2, suspect=1,
                  volume=200_000, prev_volume=100_000),                                                   # 2x shares: a suspect
        ],
    }
    with store.connect(target) as conn:
        for day, rows in sessions.items():
            store.replace_session(conn, {"session_date": day, "prev_date": None, "tickers": 12_000,
                                         "rows": len(rows), "minute_bars": 1, "builder": 1, "built_ts": 0.0,
                                         "note": None}, rows)
    conn = store.read_only(target)
    yield conn
    conn.close()


def search(db, **params):
    return query.search(db, query.parse({k: str(v) for k, v in params.items()}))


def symbols(answer) -> list[str]:
    return [r["symbol"] for r in answer["rows"]]


def test_the_high_in_percent_points_and_the_default_common_kinds(db):
    answer = search(db, high_min=300, price_max=20)
    assert set(symbols(answer)) == {"OLDR", "MSGY", "FADE", "XYZ", "KITT"}     # no warrant, 5-letter or likely split
    assert answer["units"] == "percent" and answer["count"] == 5
    row = next(r for r in answer["rows"] if r["symbol"] == "MSGY")
    assert row["high_pct"] == pytest.approx(546.19, abs=0.01) and row["day_high_et"] == "17:04"
    assert row["first_et"]["up20"] == "08:00" and row["first_et"]["up300"] is None
    assert next(r for r in answer["rows"] if r["symbol"] == "KITT")["split"] is None     # 15.7x the shares: a real jump


def test_kinds_all_and_splits_include_bring_the_rest_back(db):
    answer = search(db, high_min=300, kinds="all", splits="include")
    assert {"WARRW", "ABCDE", "RVSP", "BIGP"} <= set(symbols(answer))
    assert next(r for r in answer["rows"] if r["symbol"] == "RVSP")["split"] == "likely_split"
    only = search(db, splits="only_suspects", kinds="all")
    assert set(symbols(only)) == {"RVSP", "KITT", "MIDS"}
    assert next(r for r in only["rows"] if r["symbol"] == "MIDS")["split"] == "suspect"


def test_the_shape_numbers_close_position_giveback_and_the_time_of_the_high(db):
    held = search(db, high_min=300, price_max=20, close_pos_min=0.67)
    assert set(symbols(held)) == {"OLDR", "XYZ"}                    # closed in the top third of the range
    faded = search(db, high_min=300, price_max=20, giveback_min=0.5)
    assert set(symbols(faded)) == {"FADE", "KITT"}                  # gave back half the run or more
    late = search(db, high_min=300, price_max=20, high_after="15:00")
    assert set(symbols(late)) == {"OLDR", "MSGY"} and late["excluded"]["high_time"] == 3
    down = search(db, close_max=-30)
    assert symbols(down) == ["DOWN"]


def test_the_summary_covers_every_match_and_the_sort_and_limit_apply_after(db):
    answer = search(db, high_min=300, price_max=20, sort="high", limit=2)
    assert answer["count"] == 5 and len(answer["rows"]) == 2
    assert symbols(answer) == ["KITT", "MSGY"]                       # biggest high first
    s = answer["summary"]
    assert s["matched"] == 5 and s["closed_above_prior_close"] == 100.0
    assert s["closed_top_third"] == 40.0 and s["median_high_pct"] is not None
    newest = search(db, high_min=300, date_from="2026-09-24", date_to="2026-09-24")
    assert symbols(newest) == ["OLDR"]


def test_a_search_too_broad_answers_the_count_only(db, monkeypatch):
    monkeypatch.setattr(query, "AGENT_MOVERS_MAX_SCAN", 3)
    answer = search(db, kinds="all", splits="include")
    assert answer["too_broad"] is True and answer["rows"] == [] and answer["count"] == 11


@pytest.mark.parametrize("params,field", [
    ({"high_min": "lots"}, "high_min"), ({"date_from": "26-09-25"}, "date_from"), ({"sort": "best"}, "sort"),
    ({"high_after": "3pm"}, "high_after"), ({"limit": "0"}, "limit"), ({"bogus": "1"}, "bogus"),
])
def test_a_bad_argument_names_its_field(params, field):
    with pytest.raises(query.QueryError) as caught:
        query.parse(params)
    assert caught.value.field == field


def test_replayable_keeps_the_days_whose_trades_are_on_disk(db):
    answer = query.search(db, query.parse({"high_min": "300", "price_max": "20", "replayable": "true"}), replayable={"2026-09-24"})
    assert symbols(answer) == ["OLDR"] and answer["excluded"]["not_replayable"] == 4
    assert answer["rows"][0]["replayable"] is True


def test_float_proofs_pass_on_evidence_and_leave_the_rest_unknown(db, tmp_path):
    archive = tmp_path / "archive.db"
    con = sqlite3.connect(archive)
    con.execute("CREATE TABLE enrichment_snapshots (symbol TEXT, session_date TEXT, float_shares REAL)")
    con.executemany("INSERT INTO enrichment_snapshots VALUES (?, ?, ?)",
                    [("MSGY", "2026-09-25", 4_500_000), ("FADE", "2026-09-25", 40_000_000)])
    con.commit()
    con.close()
    movers = tmp_path / "shares.sqlite3"
    with store.connect(movers) as conn:
        store.replace_sec_shares(conn, [
            {"symbol": "OLDR", "cik": "1", "as_of": "2026-08-01", "filed": "2026-08-10", "shares": 30_000_000},
            {"symbol": "OLDR", "cik": "1", "as_of": "2026-09-01", "filed": "2026-10-01", "shares": 1},  # filed after
            {"symbol": "XYZ", "cik": "2", "as_of": "2026-07-01", "filed": "2026-07-15", "shares": 8_000_000},
        ])
        store.replace_splits(conn, [{"symbol": "OLDR", "execution_date": "2026-09-10", "split_from": 10,
                                     "split_to": 1}])
        pairs = [("2026-09-25", "MSGY"), ("2026-09-25", "FADE"), ("2026-09-24", "OLDR"), ("2026-09-25", "XYZ"),
                 ("2026-09-25", "KITT")]
        proofs = floats.proofs(pairs, 5_000_000, db=conn, archive=archive)
    assert proofs[("2026-09-25", "MSGY")]["proof"] == "pass"                     # Nova's float that day
    assert proofs[("2026-09-25", "FADE")]["proof"] == "fail"                     # Nova's float, over the limit
    oldr = proofs[("2026-09-24", "OLDR")]                                        # 30M -> 3M through the split
    assert oldr["proof"] == "pass" and oldr["shares"] == 3_000_000 and oldr["source"] == "sec_shares_outstanding"
    assert proofs[("2026-09-25", "XYZ")]["proof"] == "unknown"                   # 8M shares out: proves nothing
    assert proofs[("2026-09-25", "KITT")] == {"shares": None, "source": None, "as_of": None, "proof": "unknown"}


def test_the_float_limit_in_a_search_lists_unknowns_only_when_asked(db):
    def evidence(pairs, limit):
        return {pair: {"shares": 1e6, "source": "enrichment", "as_of": pair[0], "proof": "pass"}
                for pair in pairs if pair[1] == "MSGY"}

    q = query.parse({"high_min": "300", "price_max": "20", "float_max": "10000000"})
    answer = query.search(db, q, floats=evidence)
    assert symbols(answer) == ["MSGY"] and answer["excluded"]["float_unknown"] == 4
    assert any("float unknown" in note for note in answer["notes"])
    both = query.search(db, query.parse({"high_min": "300", "price_max": "20", "float_max": "1e7", "float_unknown": "include"}),
                        floats=evidence)
    assert len(both["rows"]) == 5 and both["rows"][0]["float"]["proof"] in ("pass", "unknown")


def test_the_store_reads_none_before_it_is_built_and_refuses_another_version(tmp_path):
    assert store.read_only(tmp_path / "missing.sqlite3") is None
    target = tmp_path / "future.sqlite3"
    con = sqlite3.connect(target)
    con.execute("PRAGMA user_version = 99")
    con.close()
    with pytest.raises(UnknownDayMoversSchema):
        store.read_only(target)
