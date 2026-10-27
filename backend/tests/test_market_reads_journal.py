"""The operator's journal through the front door (``research/market_reads/journal.py``, ADR 059): the desk's own
filter rule (``journal.store.get_trades``) on a read-only connection -- the journal is found where the desk keeps it,
never created or changed, mock rows only when asked, and an empty answer says what the file holds."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("pandas")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from market_reads import journal  # noqa: E402

ET = ZoneInfo("America/New_York")


def ts(stamp: str) -> float:
    return datetime.fromisoformat(stamp).replace(tzinfo=ET).timestamp()


@pytest.fixture
def cache(tmp_path, monkeypatch):
    import journal.db as db
    from journal.store import record_trade
    monkeypatch.setattr(db, "cache_dir", lambda: tmp_path)
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    db.init_db()
    for symbol, setup, adherent, opened, pnl, tags, mock in (
            ("AAA", "gap_and_go", True, "2026-10-01 09:35", 40.0, ["gap", "Morning"], False),
            ("BBB", "bull_flag", False, "2026-10-01 23:30", -25.5, ["flag"], False),
            ("CCC", "abcd", True, "2026-10-03 11:00", None, [], False),
            ("FAKE", "gap_and_go", True, "2026-10-02 10:00", 999.0, [], True)):
        record_trade(symbol, setup, "long", 100, 10.0, 9.8, 10.4, 10.4, pnl, adherent, opened_ts=ts(opened),
                     closed_ts=None if pnl is None else ts(opened) + 60, tags=tags, is_mock=mock)
    return tmp_path


def test_the_desks_filter_rule_reads_the_journal_with_et_times(cache):
    frame = journal.trades(setup="GAP_AND_GO")
    assert list(frame["symbol"]) == ["AAA"]                                  # the mock row left out
    assert frame.iloc[0]["opened_et"] == "2026-10-01 09:35:00" and frame.iloc[0]["tags"] == "gap, Morning"
    assert list(journal.trades(date_from="2026-10-01", date_to="2026-10-01")["symbol"]) == ["BBB", "AAA"]
    assert list(journal.trades(adherent=False)["symbol"]) == ["BBB"]
    assert list(journal.trades(tag="morning")["symbol"]) == ["AAA"]
    assert set(journal.trades(include_mock=True)["symbol"]) == {"AAA", "BBB", "CCC", "FAKE"}


def test_the_summary_sums_the_rows_and_the_file_counts_real_and_mock(cache):
    frame = journal.trades()
    assert frame.attrs["summary"] == {"trades": 3, "closed": 2, "pnl": 14.5, "wins": 1, "losses": 1,
                                      "commission": None}
    assert frame.attrs["journal_rows"] == {"real": 3, "mock": 1}
    assert frame.attrs["source"] == str(cache / "journal.db") and frame.attrs["filters"] == {}


def test_the_journal_is_read_only_and_a_missing_one_says_where_it_looked(cache, tmp_path, monkeypatch):
    path = cache / "journal.db"
    stamp = path.stat().st_mtime_ns
    journal.trades(symbol="aaa")
    assert path.stat().st_mtime_ns == stamp
    with pytest.raises(ValueError, match="limit"):
        journal.trades(limit=0)
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("NOVA_CACHE_DIR", str(empty))
    with pytest.raises(LookupError, match="journal.db is not on disk"):
        journal.trades()
    assert list(empty.iterdir()) == []                                        # never created
