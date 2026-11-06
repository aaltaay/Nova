"""The agent search's news, halt and relative-volume filters (``day_movers.facts``, ADR 050 / ADR 059): the export
writes the day facts whole into the movers store, the search filters them by the same rule find_stock_days uses,
and an unknown -- a fact the export did not know, or no export at all -- is left out and counted, never read as
"no news", "no halt" or "low volume"."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from day_movers import facts, query, store

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research" / "movers"))

DAY = "2026-09-25"


def mover(symbol: str, hi: float) -> dict:
    return {"session_date": DAY, "symbol": symbol, "kind": "CS", "prev_close": 1.0, "open": 1.1, "high": hi,
            "low": 1.0, "close": hi * 0.9, "volume": 1_000_000, "dollar_volume": 2_000_000.0, "day_high": hi,
            "day_low": 1.0, "high_pct": hi - 1.0, "low_pct": 0.0, "close_pct": hi * 0.9 - 1.0, "gap_pct": 0.1}


FACTS = [  # symbol, verdict, category, title, halts, codes, luld, news, rvol
    ("FDAX", "catalyst", "fda_regulatory", "FDA Approves FDAX's Drug", 1, "T1", 0, 1, 12.5),
    ("PAUS", "none_found", None, None, 3, "LUDP", 3, 0, 4.0),
    ("CALM", "catalyst", "contract_partnership", "CALM wins a contract", 0, None, 0, 0, None),
    ("OLD", None, None, None, None, None, None, None, 7.0),            # halt log does not cover it; no verdict
]


@pytest.fixture
def db(tmp_path):
    target = tmp_path / "movers.sqlite3"
    rows = [mover(s, 2.0 + i) for i, s in enumerate(["FDAX", "PAUS", "CALM", "OLD", "NONE"])]
    with store.connect(target) as conn:
        store.replace_session(conn, {"session_date": DAY, "prev_date": None, "tickers": 5, "rows": len(rows),
                                     "minute_bars": 1, "builder": 1, "built_ts": 0.0, "note": None}, rows)
        written = store.replace_day_facts(conn, (
            {"session_date": DAY, "symbol": s, "catalyst_verdict": v, "catalyst_category": c, "catalyst_title": t,
             "halts": h, "halt_codes": codes, "luld_halts": luld, "news_halts": news, "rvol_daily": rvol}
            for s, v, c, t, h, codes, luld, news, rvol in FACTS))
        assert written == len(FACTS)
    conn = store.read_only(target)
    yield conn
    conn.close()


def search(db, **params):
    return query.search(db, query.parse({k: str(v) for k, v in params.items()}),
                        day_facts=lambda pairs: facts.read(db, pairs))


def symbols(answer) -> list[str]:
    return sorted(r["symbol"] for r in answer["rows"])


def test_news_filters_read_the_exported_verdicts(db):
    assert symbols(search(db, date_from=DAY, catalyst_category="fda_regulatory")) == ["FDAX"]
    assert symbols(search(db, date_from=DAY, catalyst="catalyst")) == ["CALM", "FDAX"]
    assert symbols(search(db, date_from=DAY, catalyst="unknown")) == ["NONE", "OLD"]    # never judged
    answer = search(db, date_from=DAY, catalyst_words="approv,clear")
    assert symbols(answer) == ["FDAX"] and answer["rows"][0]["day_facts"]["catalyst_title"].startswith("FDA")
    assert answer["excluded"]["day_facts"] == 4


def test_halt_filters_leave_an_uncovered_day_out_counted(db):
    halted = search(db, date_from=DAY, halted="true")
    assert symbols(halted) == ["FDAX", "PAUS"]
    assert halted["excluded"]["halts_unknown"] == 2                                     # OLD and NONE
    assert any("halt coverage unknown" in n for n in halted["notes"])
    assert symbols(search(db, date_from=DAY, halted="false")) == ["CALM"]
    assert symbols(search(db, date_from=DAY, halt_codes="news")) == ["FDAX"]
    assert symbols(search(db, date_from=DAY, halt_codes="ludp")) == ["PAUS"]


def test_rvol_daily_min_keeps_the_ratio_and_counts_unknowns(db):
    answer = search(db, date_from=DAY, rvol_daily_min=5)
    assert symbols(answer) == ["FDAX", "OLD"]
    assert answer["excluded"]["rvol_unknown"] == 2                                      # CALM and NONE


def test_a_search_without_fact_filters_keeps_its_shape(db):
    answer = search(db, date_from=DAY)
    assert len(answer["rows"]) == 5 and "day_facts" not in answer["rows"][0] and "day_facts" not in answer["excluded"]


def test_no_export_reads_every_fact_unknown(tmp_path):
    target = tmp_path / "bare.sqlite3"
    with store.connect(target) as conn:
        store.replace_session(conn, {"session_date": DAY, "prev_date": None, "tickers": 1, "rows": 1,
                                     "minute_bars": 1, "builder": 1, "built_ts": 0.0, "note": None},
                              [mover("FDAX", 3.0)])
        conn.execute("DROP TABLE day_facts")                       # an index built before day facts existed
    conn = store.read_only(target)
    try:
        assert facts.exported(conn) == {"exported": False, "first": None, "last": None}
        answer = search(conn, date_from=DAY, rvol_daily_min=2)
        assert answer["rows"] == [] and answer["excluded"]["rvol_unknown"] == 1
    finally:
        conn.close()


@pytest.mark.parametrize("params,field", [({"halted": "maybe"}, "halted"), ({"rvol_daily_min": "0"}, "rvol_daily_min"),
                                          ({"rvol_daily_min": "lots"}, "rvol_daily_min")])
def test_a_bad_fact_argument_names_its_field(params, field):
    with pytest.raises(query.QueryError) as caught:
        query.parse(params)
    assert caught.value.field == field


def test_keep_counts_every_unknown_it_drops_and_wanted_guards_its_arguments():
    left: dict[str, int] = {}
    news = facts.wanted(catalyst_category="fda_regulatory")              # one bare word, never its letters
    assert news.categories == frozenset({"fda_regulatory"})
    assert not facts.keep({"catalyst_verdict": None}, news, left)         # never judged
    assert not facts.keep({"catalyst_verdict": "none_found"}, news, left)  # judged: no news, not unknown
    shares = facts.wanted(float_max=10_000_000)
    assert not facts.keep({"float_shares": None}, shares, left)
    assert facts.keep({"float_shares": None}, facts.wanted(float_max=1, float_unknown="include"), left)
    assert left == {"catalyst_unknown": 1, "shares_unknown": 1}
    assert facts.keep({"catalyst_verdict": None}, facts.wanted(catalyst=["unknown"]), left)   # asked for: kept
    with pytest.raises(ValueError, match="halted is true"):
        facts.wanted(halted="false")                                      # a string would let every row through


def test_the_export_writes_only_rows_with_something_known(db, tmp_path, monkeypatch):
    import export_day_facts

    def for_pairs(pairs, parts):
        assert set(parts) == {"catalyst", "halts", "rvol"}
        return {p: ({"catalyst_verdict": "catalyst", "rvol_daily": 6.0} if p[1] == "FDAX" else {}) for p in pairs}
    monkeypatch.setitem(sys.modules, "market_reads.day_facts", types.SimpleNamespace(for_pairs=for_pairs))
    monkeypatch.setitem(sys.modules, "market_reads", types.SimpleNamespace(day_facts=sys.modules["market_reads.day_facts"]))
    target = Path(db.execute("PRAGMA database_list").fetchone()[2])
    lines: list[str] = []
    assert export_day_facts.export(target, say=lines.append) == 1
    assert lines and "1 of 1 sessions, 1 rows" in lines[-1]
    fresh = store.read_only(target)
    try:
        assert facts.read(fresh, [(DAY, "FDAX"), (DAY, "PAUS")]) == {
            (DAY, "FDAX"): {**dict.fromkeys(facts.FACT_KEYS), "catalyst_verdict": "catalyst", "rvol_daily": 6.0},
            (DAY, "PAUS"): dict.fromkeys(facts.FACT_KEYS)}                 # replaced whole: the old row is gone
    finally:
        fresh.close()
