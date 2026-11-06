"""FINRA short interest from the Massive dump to the Sim's "Why it's moving" (ADR 028 amendment (2), 2026-10-12).

``massive_reference_dump.py`` writes one ``short_interest.jsonl``; ``research/orb/short_interest_months.py`` splits it
by settlement month, and ``move_reason/short_interest.py`` reads the split. The producer and the reader must agree.
"""
from __future__ import annotations

import importlib.util
import json
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from move_reason import short_interest

# Loaded by path: research/orb on sys.path would let its modules (common.py ...) shadow others for the session.
_SPEC = importlib.util.spec_from_file_location(
    "short_interest_months", Path(__file__).resolve().parents[2] / "research" / "orb" / "short_interest_months.py")
short_interest_months = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(short_interest_months)

ET = ZoneInfo("America/New_York")
ROWS = [
    {"settlement_date": "2026-08-31", "ticker": "SDEV", "short_interest": 1_177_802, "days_to_cover": 1.0},
    {"settlement_date": "2026-09-15", "ticker": "SDEV", "short_interest": 1_212_152, "days_to_cover": 4.4},
    {"settlement_date": "2026-09-15", "ticker": "PFAI", "short_interest": 9_077, "days_to_cover": 9.11},
    {"settlement_date": "2026-09-15", "ticker": "SDEVp", "short_interest": 4_000, "days_to_cover": 2.0},  # preferred
    {"settlement_date": "2026-09-30", "ticker": "SDEV", "short_interest": 3_436_239, "days_to_cover": 1.0},
    {"ticker": "BAD", "short_interest": 1},
]


def _dump(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    ref = tmp_path / "store" / "reference"
    ref.mkdir(parents=True)
    (ref / "short_interest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in ROWS), encoding="utf-8")
    return ref


def test_the_split_is_what_the_replay_read_opens(tmp_path, monkeypatch):
    ref = _dump(tmp_path, monkeypatch)
    oct2 = datetime(2026, 10, 2, 10, 31, tzinfo=ET).timestamp()
    assert short_interest.published_at("SDEV", oct2) == {
        "reason": "Massive's FINRA short interest is not split by month on this desk "
                  "(py -3 research/orb/short_interest_months.py)"}
    assert short_interest_months.needs_split(ref)

    counts = short_interest_months.split_by_month(ref)

    assert counts == {"skipped": 1, "2026-08": 1, "2026-09": 4}
    assert sorted(p.name for p in (ref / "short_interest").iterdir()) == ["2026-08.jsonl", "2026-09.jsonl"]
    assert not short_interest_months.needs_split(ref)
    found = short_interest.published_at("SDEV", oct2)
    assert found["row"]["short_interest"] == 1_212_152
    assert found["pending"] == {"settlement_date": date(2026, 9, 30), "counts_from": date(2026, 10, 12)}
    # a lowercase letter is another security (FINRA's SDEVp): read as written, never as SDEV's
    assert short_interest.published_at("SDEVp", oct2)["row"]["short_interest"] == 4_000
    assert short_interest.published_at("sdev", oct2)["row"]["short_interest"] == 1_212_152   # typed in lower case


def test_a_newer_dump_is_split_again(tmp_path, monkeypatch):
    ref = _dump(tmp_path, monkeypatch)
    short_interest_months.split_by_month(ref)
    newest = max(p.stat().st_mtime for p in (ref / "short_interest").iterdir())
    os.utime(ref / "short_interest.jsonl", (newest + 3600, newest + 3600))   # the dump fetched again
    assert short_interest_months.needs_split(ref)
