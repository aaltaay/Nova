"""QA leftovers (2026-09-22): IB's unset price and the sticky recording dispatch error."""
from __future__ import annotations

import math


def test_unset_and_zero_prices_are_null_and_real_prices_pass():
    """C28: IB's UNSET_DOUBLE once rendered as a 400-character dollar figure."""
    from ibkr.order_rows import _nonzero_price

    assert _nonzero_price(1.7976931348623157e308) is None
    assert _nonzero_price(-1.7976931348623157e308) is None
    assert _nonzero_price(math.inf) is None
    assert _nonzero_price(math.nan) is None
    assert _nonzero_price(0.0) is None
    assert _nonzero_price(None) is None
    assert _nonzero_price("not a price") is None
    assert _nonzero_price(8.79) == 8.79
    assert _nonzero_price("12.5") == 12.5


def test_a_clean_dispatch_clears_the_sticky_recording_error(monkeypatch):
    """C55: one failed print used to mark every recording failed until restart."""
    import capture.bridge_ibkr as bridge
    from ibkr import tape_recording

    tape_recording.dispatch_errors.clear()
    calls = {"n": 0}

    def flaky_enqueue(_payload):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("queue full")

    monkeypatch.setattr(bridge, "enqueue_print", flaky_enqueue)
    monkeypatch.setattr(tape_recording, "_enqueue_l2", lambda _payload: None)

    tape_recording.dispatch({"symbol": "GRML", "receive_ts": 1.0})
    assert tape_recording.dispatch_errors.get("capture") == "capture recording dispatch failed"

    tape_recording.dispatch({"symbol": "GRML", "receive_ts": 2.0})
    assert "capture" not in tape_recording.dispatch_errors
