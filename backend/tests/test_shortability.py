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
