"""Borrow, recorded for good, so a past-day replay knows what IBKR said then (ADR 048 decision 4)."""
from __future__ import annotations

import sqlite3

import pytest

from short_sale import borrow_log


@pytest.fixture
def log(monkeypatch, tmp_path):
    monkeypatch.setenv("NOVA_BORROW_LOG", "1")
    monkeypatch.setenv("NOVA_BORROW_DIR", str(tmp_path / "borrow"))
    monkeypatch.setattr(borrow_log, "_ensure_thread", lambda: None)  # write in-line
    borrow_log.reset_for_tests()
    yield borrow_log
    borrow_log.reset_for_tests()


def test_reads_are_kept_and_read_back_at_or_before_a_moment(log):
    log.note("rdyn", {"fetched_at": 1000.0, "shortable_shares": 50_000.0, "state": "shortable_est"})
    log.note("RDYN", {"fetched_at": 1030.0, "shortable_shares": 0.0, "state": "htb_likely"})
    assert log.write_pending() == 2
    assert log.at("RDYN", 999.0) is None
    assert log.at("RDYN", 1010.0) == {"ts": 1000.0, "shares": 50_000.0, "state": "shortable_est"}
    assert log.at("RDYN", 5000.0)["state"] == "htb_likely"
    with sqlite3.connect(log.path()) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1


def test_an_unknown_store_version_refuses_to_be_read_or_written(log):
    log.path().parent.mkdir(parents=True)
    with sqlite3.connect(log.path()) as db:
        db.execute("PRAGMA user_version = 9")
    with pytest.raises(log.UnknownBorrowSchema):
        log.at("RDYN", 1.0)
    log.note("RDYN", {"fetched_at": 1.0, "shortable_shares": 1.0, "state": "thin"})
    assert log.write_pending() == 0 and log.counts["failed"] == 1 and "version 9" in log.last_error


def test_off_records_nothing(log, monkeypatch):
    monkeypatch.setenv("NOVA_BORROW_LOG", "0")
    assert log.note("RDYN", {"fetched_at": 1.0, "state": "thin"}) is False
