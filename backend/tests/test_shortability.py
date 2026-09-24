"""Phase K1 — shortability state mapping + fail-closed order gate."""
from __future__ import annotations

import time

import ibkr.shortability as shortability


def test_state_from_shares_matrix():
    assert shortability.state_from_shares(None) == "unknown"
    assert shortability.state_from_shares(-1) == "htb_likely"
    assert shortability.state_from_shares(0) == "htb_likely"
    assert shortability.state_from_shares(100) == "thin"
    assert shortability.state_from_shares(10_000) == "shortable_est"
    assert shortability.state_from_shares(250_000) == "shortable_est"


def test_enrich_marks_stale_and_orderable():
    raw = {
        "source": "ibkr",
        "connected": True,
        "qualified": True,
        "shortable_shares": 50_000,
        "error": None,
    }
    fresh = shortability.enrich_ibkr_listing(raw, fetched_at=time.time())
    assert fresh["state"] == "shortable_est"
    assert fresh["stale"] is False
    assert fresh["orderable"] is True

    stale = shortability.enrich_ibkr_listing(raw, fetched_at=time.time() - 10_000)
    assert stale["stale"] is True
    assert stale["orderable"] is False


def test_assert_shortable_reason_codes():
    ok, _, code = shortability.assert_shortable_for_order(None)
    assert ok is False and code == "SHORT_STALE_BORROW"

    snap = shortability.enrich_ibkr_listing(
        {"connected": True, "qualified": True, "shortable_shares": 50_000, "error": None},
        fetched_at=time.time(),
    )
    ok, _, code = shortability.assert_shortable_for_order(snap)
    assert ok is True and code is None

    thin = shortability.enrich_ibkr_listing(
        {"connected": True, "qualified": True, "shortable_shares": 100, "error": None},
        fetched_at=time.time(),
    )
    ok, _, code = shortability.assert_shortable_for_order(thin)
    assert ok is False and code == "SHORT_NOT_SHORTABLE"


def test_the_last_read_is_kept_and_aged_without_asking_ibkr_again(monkeypatch):
    # ADR 035: the stock read shows the last snapshot with its age; it never waits on IBKR.
    from ibkr import shortability as sh

    sh._last.clear()
    assert sh.cached("APUS") is None
    monkeypatch.setattr(sh._listing_flags, "fetch_listing_flags_sync",
                        lambda symbol: {"connected": True, "qualified": True, "shortable_shares": 0})
    snap = sh.fetch_shortability("apus")
    assert snap["state"] == "htb_likely"
    monkeypatch.setattr(sh._listing_flags, "fetch_listing_flags_sync",
                        lambda symbol: (_ for _ in ()).throw(AssertionError("cached() must not ask IBKR")))
    kept = sh.cached("APUS")
    assert kept["state"] == "htb_likely" and kept["fetched_at"] == snap["fetched_at"]


def test_an_unknown_state_is_asked_again_sooner_than_a_known_one():
    from ibkr import shortability as sh

    assert sh.refresh_due({"state": "unknown"}, 30.0) is True
    assert sh.refresh_due({"state": "htb_likely"}, 30.0) is False
    assert sh.refresh_due({"state": "htb_likely"}, 60.0) is True
    assert sh.refresh_due(None, 30.0) is True
