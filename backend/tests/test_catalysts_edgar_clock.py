"""EDGAR acceptance times on their own clock (ADR 024 amendment 2026-09-30).

SEC's bulk submissions JSON writes every ``acceptanceDateTime`` with a ``Z``, but some filers' JSON
holds Eastern wall time behind it. Read as UTC, an Eastern-clock filer's 16:05 ET results release
landed at 12:05 ET -- intraday, before it existed. These tests build a synthetic ``submissions.zip``
(temp files only -- never F:) with one Eastern-clock filer and one true-UTC filer and read it
through the research fetcher's own parser and its store repair.
"""
from __future__ import annotations

import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

RESEARCH = Path(__file__).resolve().parents[2] / "research" / "catalysts"
if str(RESEARCH) not in sys.path:
    sys.path.insert(0, str(RESEARCH))

import edgar_clock  # noqa: E402  (research/catalysts/edgar_clock.py)
import fetch_edgar  # noqa: E402
import store as research_store  # noqa: E402  (research/catalysts/store.py)

ET = ZoneInfo("America/New_York")


def et(y: int, mo: int, d: int, hh: int, mm: int = 0) -> float:
    return datetime(y, mo, d, hh, mm, tzinfo=ET).timestamp()


def utc(y: int, mo: int, d: int, hh: int, mm: int = 0) -> float:
    return datetime(y, mo, d, hh, mm, tzinfo=timezone.utc).timestamp()


def block(rows: list[tuple[str, str, str, str, str]]) -> dict:
    """A submissions column block from ``(accession, form, filing date, raw acceptance, items)`` rows."""
    return {"accessionNumber": [r[0] for r in rows], "form": [r[1] for r in rows],
            "filingDate": [r[2] for r in rows], "acceptanceDateTime": [r[3] for r in rows],
            "items": [r[4] for r in rows], "primaryDocument": ["doc.htm"] * len(rows)}


def write_zip(path: Path, filers: dict[str, list[list[tuple]]]) -> zipfile.ZipFile:
    """``{cik: [recent rows, overflow file rows, ...]}`` as SEC lays them out."""
    with zipfile.ZipFile(path, "w") as z:
        for cik, parts in filers.items():
            name = f"CIK{cik.zfill(10)}"
            files = [{"name": f"{name}-submissions-{n:03d}.json"} for n in range(1, len(parts))]
            z.writestr(f"{name}.json", json.dumps({"cik": cik, "filings": {"recent": block(parts[0]), "files": files}}))
            for f, rows in zip(files, parts[1:], strict=True):
                z.writestr(f["name"], json.dumps(block(rows)))
    return zipfile.ZipFile(path)


# EAST's JSON is on the Eastern clock: two rows say so on their own, and its results release at
# 16:05 ET reads "16:05Z". UTCO's JSON is true UTC: its own 16:05 ET release reads "20:05Z".
EAST_RELEASE = "0001001-24-000003"
UTCO_RELEASE = "0002002-24-000003"
FILERS = {
    "1001": [[
        ("0001001-24-000001", "10-Q", "2024-05-14", "2024-05-14T08:30:00.000Z", ""),           # 04:30 ET as UTC: Eastern
        ("0001001-24-000002", "8-K", "2024-02-28", "2024-02-27T18:10:00.000Z", "8.01"),        # dated the next day: Eastern
        (EAST_RELEASE, "8-K", "2024-03-26", "2024-03-26T16:05:00.000Z", "2.02,9.01"),          # either clock on its own
    ]],
    "2002": [[
        ("0002002-24-000001", "10-Q", "2024-05-14", "2024-05-14T23:40:00.000Z", ""),           # 23:40 ET as Eastern: UTC
        ("0002002-24-000002", "8-K", "2024-01-10", "2024-01-10T15:00:00.000Z", "7.01,9.01"),   # either clock on its own
        (UTCO_RELEASE, "8-K", "2024-03-26", "2024-03-26T20:05:00.000Z", "2.02,9.01"),          # dated that day: UTC
    ]],
}


@pytest.fixture
def zf(tmp_path: Path) -> zipfile.ZipFile:
    z = write_zip(tmp_path / "submissions.zip", FILERS)
    yield z
    z.close()


def by_acc(z: zipfile.ZipFile, cik: str) -> dict[str, dict]:
    return {f["acc"]: f for f in fetch_edgar.filings(z, cik)}


def test_an_eastern_clock_release_lands_after_the_close(zf):
    f = by_acc(zf, "1001")[EAST_RELEASE]
    assert (f["clock"], f["clock_how"]) == ("et", "near_180d")
    assert f["ts"] == et(2024, 3, 26, 16, 5)          # after the close: it can move only 03-27
    assert f["ts"] != utc(2024, 3, 26, 16, 5)         # the old reading: 12:05 ET, intraday


def test_a_true_utc_release_is_unchanged(zf):
    f = by_acc(zf, "2002")
    assert (f[UTCO_RELEASE]["clock"], f[UTCO_RELEASE]["clock_how"]) == ("utc", "filing_date")
    assert f[UTCO_RELEASE]["ts"] == utc(2024, 3, 26, 20, 5) == et(2024, 3, 26, 16, 5)
    assert f["0002002-24-000002"]["ts"] == et(2024, 1, 10, 10, 0)   # placed by its UTC neighbours


def test_every_eastern_row_moves_by_the_day_offset(zf):
    f = by_acc(zf, "1001")
    assert f["0001001-24-000001"]["ts"] == et(2024, 5, 14, 8, 30)    # EDT: 4 hours later than UTC
    assert f["0001001-24-000002"]["ts"] == et(2024, 2, 27, 18, 10)   # EST: 5 hours
    assert [f[a]["clock_how"] for a in ("0001001-24-000001", "0001001-24-000002")] == ["hours", "filing_date"]


@pytest.mark.parametrize(("form", "raw", "filed", "want"), [
    ("8-K", "2024-07-15T08:12:00.000Z", "2024-07-15", ("et", "hours")),         # EDT: 04:12 ET if UTC
    ("8-K", "2024-01-16T10:30:00.000Z", "2024-01-16", ("et", "hours")),         # EST: 05:30 ET if UTC
    ("8-K", "2024-07-15T10:30:00.000Z", "2024-07-15", ("", "")),                # EDT 10:30: 06:30 ET if UTC
    ("8-K", "2024-07-15T23:10:00.000Z", "2024-07-16", ("utc", "hours")),        # 23:10 ET if Eastern
    ("8-K", "2024-01-16T02:40:00.000Z", "2024-01-16", ("utc", "hours")),        # EST: 02:40 ET if Eastern
    ("10-K", "2024-03-26T19:00:00.000Z", "2024-03-26", ("utc", "filing_date")),  # 15:00 ET, dated that day
    ("10-K", "2024-03-26T19:00:00.000Z", "2024-03-27", ("et", "filing_date")),   # 19:00 ET, dated the next day
    ("8-K", "2024-03-22T18:00:00.000Z", "2024-03-25", ("et", "filing_date")),    # a Friday evening, dated Monday
    ("4", "2024-03-26T19:00:00.000Z", "2024-03-26", ("", "")),                  # Form 4: dated that day until 22:00
    ("8-K", "2024-03-26T17:30:00.000Z", "2024-03-26", ("", "")),                # the cutoff minute itself
    ("8-K", "", "2024-03-26", ("", "")),
])
def test_own_clock(form, raw, filed, want):
    assert edgar_clock.own_clock(form, raw, filed) == want


def test_the_clock_belongs_to_each_filers_json(tmp_path):
    """One filing listed by two co-registrants: UTC in one JSON, Eastern in the other -- one instant."""
    acc = "0000092122-19-000006"
    z = write_zip(tmp_path / "submissions.zip", {
        "3001": [[(acc, "10-K", "2019-02-20", "2019-02-20T21:15:00.000Z", "")]],
        "3002": [[("0000003002-19-000001", "8-K", "2019-03-05", "2019-03-05T07:45:00.000Z", "8.01"),
                  (acc, "10-K", "2019-02-20", "2019-02-20T16:15:00.000Z", "")]],
    })
    a, b = by_acc(z, "3001")[acc], by_acc(z, "3002")[acc]
    assert a["clock"] == "utc" and b["clock"] == "et"
    assert a["ts"] == b["ts"] == et(2019, 2, 20, 16, 15)
    z.close()


def test_neighbours_follow_a_clock_change_inside_one_part():
    """A JSON can switch clocks: each ambiguous row takes the majority near it, not the part's."""
    part = [("8-K", "2015-06-01T07:10:00.000Z", "2015-06-01"),    # Eastern on its own
            ("8-K", "2015-07-01T07:20:00.000Z", "2015-07-01"),    # Eastern on its own
            ("8-K", "2015-06-15T14:00:00.000Z", "2015-06-15"),    # ambiguous, among Eastern rows
            ("8-K", "2024-06-03T23:30:00.000Z", "2024-06-03"),    # UTC on its own
            ("8-K", "2024-06-10T14:00:00.000Z", "2024-06-10")]    # ambiguous, beside a UTC row
    marks = edgar_clock.clocks([part])[0]
    assert marks[2] == ("et", "near_180d")
    assert marks[4] == ("utc", "near_180d")


def test_a_part_without_evidence_takes_the_filers_other_parts_else_utc():
    recent = [("8-K", "2024-03-26T14:00:00.000Z", "2024-03-26")]        # ambiguous, nothing near
    older = [("8-K", "2012-05-01T07:00:00.000Z", "2012-05-01"),         # Eastern on its own
             ("8-K", "2012-06-01T08:00:00.000Z", "2012-06-01")]
    assert edgar_clock.clocks([recent, older])[0] == [("et", "filer")]
    assert edgar_clock.clocks([recent])[0] == [("utc", "default")]


def test_reclock_moves_only_eastern_items_and_their_ticker_rows(zf, tmp_path):
    con = research_store.connect(tmp_path / "catalysts.sqlite3")
    old = {f"edgar:{EAST_RELEASE}": utc(2024, 3, 26, 16, 5), f"edgar:{UTCO_RELEASE}": utc(2024, 3, 26, 20, 5)}
    with con:
        research_store.put_items(con, [
            {"item_id": item_id, "source": "edgar", "published_ts": ts, "title": "8-K", "tickers": [ticker]}
            for (item_id, ts), ticker in zip(old.items(), ("EAST", "UTCO"), strict=True)])
    out = fetch_edgar.reclock(con, zf, {"EAST": "1001", "UTCO": "2002"})
    assert out == {"stored": 2, "retimed": 1, "not_in_zip": 0}
    rows = dict(con.execute("SELECT item_id, published_ts FROM items"))
    links = dict(con.execute("SELECT item_id, published_ts FROM item_tickers"))
    assert rows == links == {f"edgar:{EAST_RELEASE}": et(2024, 3, 26, 16, 5), f"edgar:{UTCO_RELEASE}": old[f"edgar:{UTCO_RELEASE}"]}
    # Idempotent: a second pass finds nothing to move.
    assert fetch_edgar.reclock(con, zf, {"EAST": "1001", "UTCO": "2002"})["retimed"] == 0
    con.close()


def test_reclock_fixes_a_ticker_row_its_item_row_hides(tmp_path):
    """A filing two filers list was stored once per ticker: the item row from the acquirer's UTC JSON
    (right), the target's ticker row from its Eastern JSON read as UTC (four hours early). The
    verdicts read the ticker rows, so the item row being right is not enough."""
    acc = "0001193125-22-221876"
    z = write_zip(tmp_path / "submissions.zip", {
        "4001": [[(acc, "425", "2022-08-16", "2022-08-16T13:06:00.000Z", "")]],
        "4002": [[("0004002-22-000001", "8-K", "2022-08-10", "2022-08-10T07:30:00.000Z", "8.01"),   # Eastern on its own
                  (acc, "425", "2022-08-16", "2022-08-16T09:06:00.000Z", "")]],
    })
    con = research_store.connect(tmp_path / "catalysts.sqlite3")
    item_id = f"edgar:{acc}"
    with con:   # what the fetcher did: the acquirer's ticker first, then the target's (first fetch wins)
        research_store.put_items(con, [{"item_id": item_id, "source": "edgar", "published_ts": et(2022, 8, 16, 9, 6),
                                        "title": "425", "tickers": ["BUYR"]}])
        research_store.put_items(con, [{"item_id": item_id, "source": "edgar", "published_ts": utc(2022, 8, 16, 9, 6),
                                        "title": "425", "tickers": ["TRGT"]}])
    assert fetch_edgar.reclock(con, z, {"BUYR": "4001", "TRGT": "4002"}) == {"stored": 1, "retimed": 1, "not_in_zip": 0}
    times = {t for (t,) in con.execute("SELECT published_ts FROM item_tickers UNION SELECT published_ts FROM items")}
    assert times == {et(2022, 8, 16, 9, 6)}
    con.close()
    z.close()
