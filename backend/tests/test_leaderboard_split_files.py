"""The confirmed-splits file (#772): the rebuild reads it beside Massive's list, a run replaces only
its own span, an unknown version refuses, and the days a split touches can be rebuilt by name."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from tests.test_leaderboard_reconstruct_helpers import (  # noqa: F401  (puts research/leaderboard on sys.path)
    build,
    rows_at,
    session,
    write_closes,
    write_minutes,
)

import build_leaderboard  # noqa: E402
import confirm_splits  # noqa: E402
import lb_io  # noqa: E402
import split_confirm  # noqa: E402


def confirmed_file(path, splits, version=1):
    path.write_text(json.dumps({"schema_version": version, "updated_at": None, "spans": [], "splits": splits,
                                "refused": []}), encoding="utf-8")
    return path


def entry(ticker, day, split_from, split_to, **extra):
    return {"ticker": ticker, "execution_date": day, "split_from": split_from, "split_to": split_to, **extra}


def test_load_splits_adds_the_confirmed_ones_and_massive_wins_a_tie(tmp_path):
    ref = tmp_path / "reference"
    ref.mkdir()
    (ref / "splits.json").write_text(json.dumps([entry("AAA", "2026-09-09", 23, 1)]), encoding="utf-8")
    confirmed = confirmed_file(tmp_path / "splits_confirmed.json",
                               [entry("AAA", "2026-09-09", 10, 1), entry("PHGE", "2026-09-09", 10, 1)])

    got = {(s.ticker, s.execution_date): (s.split_from, s.split_to) for s in lb_io.load_splits(None, ref, confirmed)}
    assert got == {("AAA", date(2026, 9, 9)): (23.0, 1.0), ("PHGE", date(2026, 9, 9)): (10.0, 1.0)}
    assert len(lb_io.load_splits(None, ref, None)) == 1                      # Massive's own list only
    assert lb_io.load_splits(None, ref, tmp_path / "absent.json")[0].ticker == "AAA"


def test_an_unknown_version_refuses(tmp_path):
    path = confirmed_file(tmp_path / "splits_confirmed.json", [], version=2)
    with pytest.raises(ValueError, match="schema_version"):
        lb_io.load_confirmed_splits(path)
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        confirm_splits.read_confirmed(path)


def test_a_run_replaces_its_span_and_keeps_every_other():
    existing = {
        "schema_version": 1, "updated_at": None,
        "spans": [{"start": "2026-01-01", "end": "2026-03-31"}, {"start": "2026-06-16", "end": "2026-09-21"}],
        "splits": [entry("OLD", "2026-02-02", 5, 1), entry("STALE", "2026-07-01", 4, 1)],
        "refused": [{"ticker": "R", "execution_date": "2026-07-02", "accession": None, "reason": "x"}],
    }
    span = {"start": "2026-06-16", "end": "2026-09-21", "confirmed": 1}
    out = confirm_splits.merge(existing, start=date(2026, 6, 16), end=date(2026, 9, 21), span=span,
                               splits=[entry("PHGE", "2026-09-09", 10, 1)], refused=[],
                               now=datetime(2026, 10, 6, 23, 0, tzinfo=timezone.utc))
    assert [s["ticker"] for s in out["splits"]] == ["OLD", "PHGE"]
    assert out["refused"] == []
    assert out["spans"] == [{"start": "2026-01-01", "end": "2026-03-31"}, span]
    assert out["schema_version"] == 1 and out["updated_at"] == "2026-10-06T23:00:00+00:00"


def test_only_charter_and_foreign_filings_near_the_session_are_read():
    day = date(2026, 9, 9)
    filings = [
        {"acc": "a", "form": "8-K", "items": "5.03,9.01", "filed": date(2026, 9, 9)},
        {"acc": "b", "form": "8-K", "items": "8.01,9.01", "filed": date(2026, 9, 1)},      # not a charter item
        {"acc": "c", "form": "6-K", "items": "", "filed": date(2026, 8, 1)},
        {"acc": "d", "form": "8-K", "items": "3.03", "filed": date(2026, 6, 1)},          # too early
        {"acc": "e", "form": "8-K/A", "items": "5.03", "filed": date(2026, 9, 13)},       # too late
        {"acc": "f", "form": "10-Q", "items": "", "filed": date(2026, 9, 8)},
    ]
    assert [f["acc"] for f in confirm_splits.split_filings(filings, day)] == ["a", "c"]


def test_decide_takes_the_dated_confirmation_and_reports_a_refusal():
    suspect = split_confirm.Suspect("PHGE", date(2026, 9, 8), date(2026, 9, 9), 0.155, 1.60, 10.3226, 0.1146)
    good = ("Reverse Stock Split. The Split Amendment effected a one-for-ten reverse stock split, which became "
            "effective on September 9, 2026.")
    other = "The board may effect a reverse stock split of up to 1-for-20 at its discretion."
    filing = {"acc": "0001213900-26-098212", "form": "8-K", "items": "5.03,9.01", "filed": date(2026, 9, 9)}
    split, refusal = confirm_splits.decide(suspect, [(filing, good)])
    assert refusal is None and (split["split_from"], split["split_to"], split["date_match"]) == (10, 1, True)
    assert split["execution_date"] == "2026-09-09" and split["prev_session"] == "2026-09-08"
    split, refusal = confirm_splits.decide(suspect, [(filing, other)])
    assert split is None and refusal["reason"].startswith("names a split but states no ratio")
    assert confirm_splits.decide(suspect, [(filing, "Item 5.03 Bylaws amended.")]) == (None, None)


def test_dates_rebuilds_the_named_sessions_only(tmp_path):
    minute = {session(i): tmp_path / f"{i}.csv.gz" for i in range(4)}
    args = SimpleNamespace(date=None, dates=f"{session(1).isoformat()}, {session(3).isoformat()},2030-01-01",
                           start=None, end=None)
    assert build_leaderboard._dates(args, minute) == [session(1), session(3)]


def test_a_confirmed_split_moves_the_prior_close_on_its_day(tmp_path):
    root, db = tmp_path / "massive", tmp_path / "lb.sqlite3"
    prev, day = session(0), session(1)
    write_minutes(root, prev, [("PHGE", 9, 30, 0.155, 1000)])
    write_closes(root, prev, {"PHGE": 0.155})
    write_minutes(root, day, [("PHGE", 9, 30, 1.60, 1000)])
    build(root, day, {"PHGE": "CS"}, db=db, splits=[lb_io.Split("PHGE", day, 10.0, 1.0)])

    row = rows_at(db, day, 9, 31)["PHGE"]
    assert row["prev_close"] == pytest.approx(1.55)
    assert row["change_pct"] == pytest.approx(1.60 / 1.55 - 1)   # +3.2%, not +932%
