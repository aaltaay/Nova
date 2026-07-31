"""TIF default + Warning 399 held-until parse + cancel verify."""
from __future__ import annotations

from ibkr.cancel_verify import cancel_order_verified
from ibkr.order_held_until import held_until_iso_from_message
from ibkr.orders import _build_order


def test_build_order_sets_tif_day():
    mkt = _build_order("BUY", 1.0, "MKT", None, None, True)
    assert getattr(mkt, "tif", None) == "DAY"
    lmt = _build_order("BUY", 1.0, "LMT", 2.5, None, True)
    assert getattr(lmt, "tif", None) == "DAY"
    stp = _build_order("SELL", 1.0, "STP", None, 2.0, False)
    assert getattr(stp, "tif", None) == "DAY"


def test_held_until_parse_warning_399():
    msg = (
        "Warning 399, reqId 95053: Order Message: BUY 1 CYCU NASDAQ.NMS "
        "Warning: Your order will not be placed at the exchange until "
        "2026-07-31 09:30:00 US/Eastern."
    )
    iso = held_until_iso_from_message(msg)
    assert iso == "2026-07-31T13:30:00Z"


def test_cancel_order_verified_gone(monkeypatch):
    calls = {"n": 0}

    def fake_cancel(oid):
        assert oid == 7
        return {"ok": True, "error": None}

    def fake_open():
        calls["n"] += 1
        if calls["n"] < 2:
            return [{"order_id": 7}]
        return []

    import ibkr.cancel_verify as cv
    import ibkr.orders as orders

    monkeypatch.setattr(orders, "cancel_order", fake_cancel)
    monkeypatch.setattr(orders, "open_orders", fake_open)
    monkeypatch.setattr(cv, "EXECUTION_CANCEL_VERIFY_POLL_SEC", 0.0)
    monkeypatch.setattr(cv, "EXECUTION_CANCEL_VERIFY_TIMEOUT_SEC", 2.0)

    out = cancel_order_verified(7)
    assert out["ok"] is True
    assert out["verified_gone"] is True
