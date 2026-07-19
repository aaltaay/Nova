"""Classify IBKR managed account ids (paper pin)."""
from ibkr.account_kind import (
    classify_managed_accounts,
    is_live_account_id,
    is_paper_account_id,
    paper_mode_accounts_ok,
)


def test_paper_prefixes():
    assert is_paper_account_id("DU1234567")
    assert is_paper_account_id("df123")
    assert not is_paper_account_id("U1234567")
    assert not is_paper_account_id("")


def test_live_prefixes():
    assert is_live_account_id("U1234567")
    assert is_live_account_id("F123")
    assert not is_live_account_id("DU123")


def test_classify():
    assert classify_managed_accounts(["DU111"]) == "paper"
    assert classify_managed_accounts(["U111"]) == "live"
    assert classify_managed_accounts(["DU111", "U111"]) == "mixed"
    assert classify_managed_accounts([]) == "unknown"
    assert classify_managed_accounts(["XYZ"]) == "unknown"


def test_paper_mode_accounts_ok():
    assert paper_mode_accounts_ok("paper") == (True, "")
    ok, reason = paper_mode_accounts_ok("live")
    assert ok is False
    assert "LIVE" in reason or "live" in reason.lower()
    ok2, _ = paper_mode_accounts_ok("unknown")
    assert ok2 is False
