"""Each played-back mover's catalyst at the Sim playhead (#498; ADR 023, ADR 024).

The leaderboard store's schema 2 (a version-1 store migrates by gaining two tables), the research
export that fills them (temp stores only -- never F:), and the verdict a board read carries: only
items published by the playhead, unknown (null) when nothing was exported or no source looked.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from catalysts.classify import classify_item, verdict, verdict_from_labels
from catalysts.live import WIRE_KEYS
from constants_catalysts import CATALYST_RULES_VERSION
from constants_leaderboard import LEADERBOARD_HALT_SOURCE_NASDAQ, LEADERBOARD_SCHEMA_VERSION
from leaderboard import catalyst_verdicts, playback, schema, store
from leaderboard.halts import event

RESEARCH = Path(__file__).resolve().parents[2] / "research" / "catalysts"
if str(RESEARCH) not in sys.path:
    sys.path.insert(0, str(RESEARCH))

import export_leaderboard  # noqa: E402
import store as research_store  # noqa: E402  (research/catalysts/store.py)

ET = ZoneInfo("America/New_York")
DAY = "2026-09-18"  # a Friday; its window opens at Thursday's 16:00 ET close
LONG_AFTER = datetime(2026, 9, 19, 12, 0, tzinfo=ET).timestamp()
FDA = "Acme Receives FDA Approval for Its Lead Drug"
OFFERING = "Acme Announces $5 Million Registered Direct Offering"


def et(day: int, hh: int, mm: int = 0, ss: int = 0) -> float:
    return datetime(2026, 9, day, hh, mm, ss, tzinfo=ET).timestamp()


WINDOW = (et(17, 16), et(18, 20))


def rebuilt_board(minute_ts: float, symbols: list[str], db_path: Path | None = None) -> None:
    rows = [{"session_date": DAY, "minute_ts": int(minute_ts), "source": "reconstructed", "board": "market",
             "symbol": sym, "rank": i + 1, "price": 5.0, "prev_close": 2.5, "change_pct": 1.0, "volume": 5e5}
            for i, sym in enumerate(symbols)]
    coverage = [{"session_date": DAY, "minute_ts": int(minute_ts), "source": "reconstructed", "board": "market",
                 "state": "rebuilt", "row_count": len(rows), "run_id": None}]
    with store.connect(db_path) as db:
        store.write_batch(db, rows=rows, coverage=coverage)


def check(symbol: str, sources: str = "alpaca,edgar") -> dict:
    return {"session_date": DAY, "symbol": symbol, "window_start": WINDOW[0], "window_end": WINDOW[1],
            "sources_answered": sources, "rules_version": CATALYST_RULES_VERSION, "exported_ts": et(18, 21)}


def item(symbol: str, title: str, published: float, source: str = "alpaca", item_id: str | None = None) -> dict:
    label = classify_item(title, source=source)
    return {"session_date": DAY, "symbol": symbol, "item_id": item_id or f"{source}:{symbol}:{published}",
            "published_ts": published, "source": source, "publisher": "Wire", "title": title, "url": None,
            "kind": label.kind, "category": label.category, "strength": label.strength,
            "dilution": int(label.dilution), "rules_version": CATALYST_RULES_VERSION}


def put(checks: list[dict], items: list[dict] = ()) -> None:
    with store.connect() as db:
        store.replace_catalysts(db, checks, items)


def rows_by_symbol(answer: dict) -> dict[str, dict]:
    return {r["symbol"]: r for r in answer["boards"]["market"]["rows"]}


# ── Schema 2 ────────────────────────────────────────────────────────────────

def _tables(db_path: Path) -> set[str]:
    db = sqlite3.connect(db_path)
    try:
        return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        db.close()


def test_a_version_1_store_migrates_by_gaining_the_catalyst_tables_only(tmp_path):
    path = tmp_path / "leaderboard.sqlite3"
    db = sqlite3.connect(path)
    db.executescript(schema._DDL)
    db.execute("PRAGMA user_version=1")
    db.execute("INSERT INTO rows (session_date, minute_ts, source, board, symbol, rank, price) "
               "VALUES (?, ?, 'reconstructed', 'market', 'OLD', 1, 3.0)", (DAY, int(et(18, 7))))
    db.commit()
    db.close()
    assert "catalyst_checks" not in _tables(path)

    with store.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == LEADERBOARD_SCHEMA_VERSION == 2
        assert [dict(r)["symbol"] for r in store.rows_at(db, DAY, "reconstructed", int(et(18, 7)))] == ["OLD"]
        assert store.catalyst_checks(db, DAY) == []
    assert {"catalyst_checks", "catalyst_items"} <= _tables(path)
    with store.connect(path) as db:  # a second open is a no-op
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2


def test_a_new_store_is_created_at_version_2(tmp_path):
    with store.connect(tmp_path / "fresh.sqlite3") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert store.catalyst_checks(db, DAY) == []


@pytest.mark.parametrize("version", [3, 9])
def test_an_unknown_version_refuses_and_is_left_alone(tmp_path, version):
    path = tmp_path / "future.sqlite3"
    db = sqlite3.connect(path)
    db.execute(f"PRAGMA user_version={version}")
    db.close()
    with pytest.raises(schema.UnknownLeaderboardSchema):
        with store.connect(path):
            pass
    db = sqlite3.connect(path)
    assert db.execute("PRAGMA user_version").fetchone()[0] == version
    db.close()
    assert "catalyst_checks" not in _tables(path)


# ── One verdict function ────────────────────────────────────────────────────

def test_labels_give_the_same_verdict_as_the_live_classifier():
    raw = [{"title": t, "source": "alpaca", "published_ts": ts, "url": None}
           for t, ts in ((OFFERING, et(18, 6)), (FDA, et(18, 7)), ("Top Gainers Today: 12 Stocks Moving", et(18, 8)))]
    labelled = [{**it, **{k: getattr(classify_item(it["title"], source="alpaca"), k)
                          for k in ("kind", "category", "strength", "dilution")}} for it in raw]
    for cutoff in (et(18, 6, 30), et(18, 7, 30), et(18, 9)):
        live = verdict(raw, window_start=WINDOW[0], cutoff=cutoff, sources_answered=["alpaca"])
        played = verdict_from_labels(labelled, window_start=WINDOW[0], cutoff=cutoff, sources_answered=["alpaca"])
        assert played == live
    assert verdict_from_labels(labelled, window_start=WINDOW[0], cutoff=et(18, 9),
                               rules_version="catalyst-rules-v5")["rules_version"] == "catalyst-rules-v5"


# ── Playback ────────────────────────────────────────────────────────────────

def test_the_verdict_reads_only_items_published_by_the_playhead():
    rebuilt_board(et(18, 7, 0), ["ACME"])
    rebuilt_board(et(18, 7, 1), ["ACME"])
    put([check("ACME")], [item("ACME", FDA, et(18, 7, 0, 45))])

    # 07:00:30 reads the 07:00 board; the 07:00:45 release is not out yet.
    before = rows_by_symbol(playback.board_at(DAY, et(18, 7, 0, 30), now=LONG_AFTER))["ACME"]["catalyst"]
    assert before["verdict"] == "none_found" and before["title"] is None and before["n_items"] == 0

    at_it = rows_by_symbol(playback.board_at(DAY, et(18, 7, 0, 45), now=LONG_AFTER))["ACME"]["catalyst"]
    assert at_it["verdict"] == "catalyst" and at_it["title"] == FDA

    later = rows_by_symbol(playback.board_at(DAY, et(18, 7, 1, 30), now=LONG_AFTER))["ACME"]["catalyst"]
    assert later["verdict"] == "catalyst" and later["strength"] == "strong" and later["category"] == "fda_regulatory"
    assert later["sources_answered"] == ["alpaca", "edgar"] and later["rules_version"] == CATALYST_RULES_VERSION
    assert set(later) == set(WIRE_KEYS)


def test_an_item_from_before_the_window_never_counts():
    rebuilt_board(et(18, 7), ["ACME"])
    put([check("ACME")], [item("ACME", FDA, WINDOW[0] - 60)])
    row = rows_by_symbol(playback.board_at(DAY, et(18, 7, 0, 30), now=LONG_AFTER))["ACME"]
    assert row["catalyst"]["verdict"] == "none_found"


def test_unexported_and_unlooked_symbols_are_unknown_never_no_news():
    rebuilt_board(et(18, 7), ["ACME", "NONE", "BLIND", "LATE"])
    rebuilt_board(et(18, 7, 2), ["ACME", "NONE", "BLIND", "LATE"])
    put([check("ACME"), check("BLIND", sources=""), check("LATE", sources="")],
        [item("LATE", OFFERING, et(18, 7, 2))])
    answer = playback.board_at(DAY, et(18, 7, 0, 30), now=LONG_AFTER)
    rows = rows_by_symbol(answer)
    assert answer["catalyst_symbols"] == 3
    assert rows["NONE"]["catalyst"] is None     # no check row: nothing exported for it
    assert rows["BLIND"]["catalyst"] is None    # checked, but no source looked
    assert rows["LATE"]["catalyst"] is None     # no source looked, and its item is after the playhead
    assert rows["ACME"]["catalyst"]["verdict"] == "none_found"
    later = rows_by_symbol(playback.board_at(DAY, et(18, 7, 2, 30), now=LONG_AFTER))
    assert later["LATE"]["catalyst"]["verdict"] == "negative"   # an item counts even when no source is on record


def test_a_day_without_an_export_reads_zero_and_every_row_null():
    rebuilt_board(et(18, 7), ["ACME"])
    answer = playback.board_at(DAY, et(18, 7, 0, 30), now=LONG_AFTER)
    assert answer["catalyst_symbols"] == 0 and rows_by_symbol(answer)["ACME"]["catalyst"] is None
    gap = playback.board_at(DAY, et(18, 3), now=LONG_AFTER)
    assert gap["gap"]["reason"] == "outside_session" and gap["catalyst_symbols"] == 0


def test_a_news_halt_since_the_prior_close_is_news_pending_until_it_resumes():
    rebuilt_board(et(18, 7), ["HALT"])
    rebuilt_board(et(18, 9, 30), ["HALT"])
    put([check("HALT")])
    halted = event(symbol="HALT", ts=et(17, 17), kind="start", source=LEADERBOARD_HALT_SOURCE_NASDAQ,
                   halt_kind="T1", code="T1")
    resumed = event(symbol="HALT", ts=et(18, 9), kind="end", source=LEADERBOARD_HALT_SOURCE_NASDAQ,
                    halt_kind="T1", code="T1")
    with store.connect() as db:
        store.write_batch(db, halts=[halted, resumed])
    pending = rows_by_symbol(playback.board_at(DAY, et(18, 7, 0, 30), now=LONG_AFTER))["HALT"]["catalyst"]
    assert pending["news_pending"] is True and pending["halt_code"] == "T1"   # read from Thursday's log
    after = rows_by_symbol(playback.board_at(DAY, et(18, 9, 30, 30), now=LONG_AFTER))["HALT"]["catalyst"]
    assert after["news_pending"] is False and after["halt_code"] == "T1"


def test_verdicts_at_is_limited_to_the_symbols_asked():
    out = catalyst_verdicts.verdicts_at([check("A"), check("B")], [], [], at=et(18, 7), symbols=["b"])
    assert set(out) == {"B"} and out["B"]["verdict"] == "none_found"


# ── The research export ─────────────────────────────────────────────────────

def _research(tmp_path: Path) -> sqlite3.Connection:
    con = research_store.connect(tmp_path / "catalysts.sqlite3")
    con.executemany("INSERT INTO targets VALUES (?,?,?,?,?,?)", [
        ("ACME", DAY, WINDOW[0], et(18, 9, 30), WINDOW[1], "leaderboard"),
        ("QUIET", DAY, WINDOW[0], et(18, 9, 30), WINDOW[1], "pillars"),
        ("OLDER", "2026-09-10", et(9, 16), et(10, 9, 30), et(10, 20), "pillars"),
    ])
    research_store.put_items(con, [
        {"item_id": "alpaca:1", "source": "alpaca", "published_ts": et(18, 7), "title": FDA,
         "summary": "", "url": "https://example.test/1", "publisher": "Benzinga", "tickers": ["ACME"]},
        {"item_id": "finnhub:9", "source": "finnhub", "published_ts": et(18, 6), "title": OFFERING,
         "summary": "", "url": None, "publisher": "Benzinga", "tickers": ["ACME"]},  # a four-hours-early clock
        {"item_id": "alpaca:2", "source": "alpaca", "published_ts": et(17, 12), "title": OFFERING,
         "summary": "", "url": None, "publisher": "Benzinga", "tickers": ["ACME"]},  # before the window
    ])
    for ticker, day, source, status in (("ACME", DAY, "alpaca", "ok"), ("ACME", DAY, "edgar", "ok"),
                                        ("ACME", DAY, "finnhub", "error"), ("QUIET", DAY, "alpaca", "ok"),
                                        ("OLDER", "2026-09-10", "massive", "out_of_range")):
        research_store.put_check(con, ticker, day, source, status)
    con.commit()
    return con


def test_the_export_writes_checks_and_labelled_items_and_replaces_them(tmp_path):
    con = _research(tmp_path)
    lb_path = tmp_path / "lb" / "leaderboard.sqlite3"
    out = export_leaderboard.export(con, lb_path, now=123.0)
    assert (out["days"], out["symbol_days"], out["items"]) == (2, 3, 1)
    with store.connect(lb_path) as db:
        checks = {c["symbol"]: c for c in store.catalyst_checks(db, DAY)}
        items = store.catalyst_items(db, DAY, until=WINDOW[1])
        older = store.catalyst_checks(db, "2026-09-10")
    assert checks["ACME"]["sources_answered"] == "alpaca,edgar"      # an error row did not look
    assert checks["QUIET"]["sources_answered"] == "alpaca"
    assert older[0]["sources_answered"] == ""                         # out of range: nobody looked
    assert (checks["ACME"]["window_start"], checks["ACME"]["window_end"]) == WINDOW
    assert [(i["item_id"], i["kind"], i["category"], i["strength"], i["dilution"]) for i in items] == [
        ("alpaca:1", "catalyst", "fda_regulatory", "strong", 0)]     # no Benzinga-via-Finnhub, nothing early

    # The research store changes; the export replaces the symbol-day whole.
    con.execute("DELETE FROM item_tickers WHERE item_id = 'alpaca:1'")
    research_store.put_items(con, [{"item_id": "edgar:5", "source": "edgar", "published_ts": et(18, 8),
                                    "title": f"8-K: 3.02 | {OFFERING}", "summary": "", "url": None,
                                    "publisher": "SEC", "tickers": ["ACME"], "form": "8-K", "sec_items": "3.02"}])
    research_store.put_check(con, "QUIET", DAY, "edgar", "ok")
    con.commit()
    export_leaderboard.export(con, lb_path, now=456.0)
    with store.connect(lb_path) as db:
        checks = {c["symbol"]: c for c in store.catalyst_checks(db, DAY)}
        items = store.catalyst_items(db, DAY, until=WINDOW[1])
    assert [(i["item_id"], i["kind"]) for i in items] == [("edgar:5", "negative")]
    assert checks["QUIET"]["sources_answered"] == "alpaca,edgar" and checks["QUIET"]["exported_ts"] == 456.0
    con.close()


def test_the_export_since_leaves_earlier_days_alone(tmp_path):
    con = _research(tmp_path)
    lb_path = tmp_path / "lb.sqlite3"
    out = export_leaderboard.export(con, lb_path, since=DAY)
    assert (out["days"], out["symbol_days"]) == (1, 2)
    with store.connect(lb_path) as db:
        assert store.catalyst_checks(db, "2026-09-10") == []
    con.close()
