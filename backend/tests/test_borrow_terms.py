"""Borrow terms (ETB / HTB / LOCATE / NSS) from IBKR's live read and its short-stock list."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ibkr import borrow_terms, shortability

ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 7, 11, 35, tzinfo=ET).timestamp()
LIVE = {"connected": True, "qualified": True, "error": None}


def _list(**kw):
    base = {"listed": True, "fee_rate": 0.41, "available": 50_000, "capped": False,
            "as_of": NOW - 300, "polled_at": NOW - 300, "changed_at": None, "was": None}
    return {**base, **kw}


def test_biya_dropped_from_the_list_reads_nss_with_when_and_what_it_was():
    dropped = datetime(2026, 10, 7, 4, 28, tzinfo=ET).timestamp()
    lst = _list(listed=False, fee_rate=None, available=None, changed_at=dropped,
                was={"listed": True, "fee_rate": 181.0464, "available": 10_000, "since": dropped - 1800})
    t = borrow_terms.describe({**LIVE, "shortable_shares": None}, lst, symbol="biya", now=NOW)
    assert (t["term"], t["chip"], t["tone"], t["source"]) == ("NSS", "NSS", "bad", "list")
    assert "dropped BIYA at 04:28 ET; was 10K @ 181%" in t["text"]


def test_the_live_level_says_nss_or_locate_without_a_count():
    nss = borrow_terms.describe({**LIVE, "shortable_level": 1.0}, None, symbol="BIYA", now=NOW)
    assert (nss["term"], nss["source"]) == ("NSS", "live")
    loc = borrow_terms.describe({**LIVE, "shortable_level": 2.0}, None, symbol="X", now=NOW)
    assert loc["term"] == "LOCATE" and loc["tone"] == "warn"
    easy = borrow_terms.describe({**LIVE, "shortable_level": 3.0}, _list(), symbol="X", now=NOW)
    assert easy["term"] == "SHORTABLE" and "no share count" in easy["text"]


def test_etb_and_htb_split_on_the_fee():
    etb = borrow_terms.describe({**LIVE, "shortable_shares": 50_000}, _list(fee_rate=0.41), symbol="X", now=NOW)
    assert (etb["term"], etb["chip"]) == ("ETB", "ETB 50K · 0.4%")
    htb = borrow_terms.describe({**LIVE, "shortable_shares": 50_000}, _list(fee_rate=181.05), symbol="X", now=NOW)
    assert (htb["term"], htb["chip"]) == ("HTB", "HTB 50K · 181%")
    thin = borrow_terms.describe({**LIVE, "shortable_shares": 400}, _list(fee_rate=378.8, available=400),
                                 symbol="SXTC", now=NOW)
    assert (thin["term"], thin["chip"]) == ("HTB", "HTB 400 · 379%")


def test_a_live_count_wins_over_the_list_and_no_fee_is_never_guessed():
    t = borrow_terms.describe({**LIVE, "shortable_shares": 50_000}, _list(listed=False), symbol="X", now=NOW)
    assert (t["term"], t["chip"], t["fee_rate"]) == ("SHORTABLE", "SHORT 50K", None)


def test_the_list_never_passes_a_short_and_an_old_list_is_not_read():
    listed = borrow_terms.describe({**LIVE}, _list(), symbol="X", now=NOW)
    assert listed["term"] == "UNKNOWN" and "live count only" in listed["text"]
    old = borrow_terms.describe({**LIVE}, _list(listed=False, polled_at=NOW - 7200), symbol="X", now=NOW)
    assert old["term"] == "UNKNOWN" and old["list"] is None
    aged = borrow_terms.describe({**LIVE, "shortable_shares": 50_000}, _list(polled_at=NOW - 2400),
                                 symbol="X", now=NOW)
    assert aged["list_note"] == "IBKR's short-stock list is 40 min old"


def test_disconnected_is_unknown():
    t = borrow_terms.describe({"connected": False, "error": "IB Gateway not connected"}, None, symbol="X", now=NOW)
    assert t["term"] == "UNKNOWN" and "not connected" in t["text"]


def test_the_door_refuses_in_the_terms_words():
    snap = shortability.enrich_ibkr_listing({**LIVE, "shortable_shares": None, "shortable_level": 1.0})
    snap["borrow"] = borrow_terms.describe(snap, None, symbol="BIYA", now=NOW)
    ok, detail, code = shortability.assert_shortable_for_order(snap)
    assert (ok, code) == (False, "SHORT_NOT_SHORTABLE")
    assert detail.startswith("NSS: IBKR marks BIYA not available to short")
