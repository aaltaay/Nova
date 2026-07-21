"""Side-by-side Alpaca vs IBKR listing payloads — never merge into one Yes/No."""
from __future__ import annotations

from listing_compare import alpaca_listing_from_asset, build_listing_compare


def test_alpaca_listing_short_type_etb():
    out = alpaca_listing_from_asset(
        {"tradable": True, "shortable": True, "easy_to_borrow": True, "marginable": True}
    )
    assert out["source"] == "alpaca_assets"
    assert out["short_type"] == "easy_to_borrow"
    assert out["tradable"] is True
    assert "not IBKR" in (out["short_type_detail"] or "")


def test_alpaca_listing_htb():
    out = alpaca_listing_from_asset({"shortable": True, "easy_to_borrow": False})
    assert out["short_type"] == "hard_to_borrow"


def test_build_listing_compare_keeps_brokers_separate(monkeypatch):
    fake_ibkr = {
        "source": "ibkr",
        "connected": True,
        "qualified": True,
        "shortable_shares": 12_000,
        "short_type": "available",
        "tradable_hint": "qualified",
        "error": None,
    }
    monkeypatch.setattr(
        "ibkr.listing_flags.fetch_listing_flags_sync",
        lambda _sym: fake_ibkr,
    )
    payload = build_listing_compare(
        "aapl",
        {"tradable": True, "shortable": False, "easy_to_borrow": False},
    )
    assert payload["symbol"] == "AAPL"
    assert payload["alpaca"]["shortable"] is False
    assert payload["alpaca"]["short_type"] == "not_shortable"
    assert payload["ibkr"]["shortable_shares"] == 12_000
    # Must not collapse into a single merged boolean
    assert "tradable" not in payload or isinstance(payload["alpaca"], dict)
    assert payload["alpaca"]["tradable"] is True
    assert payload["ibkr"]["tradable_hint"] == "qualified"
