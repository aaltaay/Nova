"""A board row's frozen price gives way to the L1 line's last trade (XRPN 2026-09-30: the Gainers row
held 16.40 from the close while the stock traded 17.11 after hours, so every level was judged against
the close)."""
from move_reason.facts import with_live_trade

ROW = {"symbol": "XRPN", "price": 16.40, "prev_close": 12.90, "change_pct": 16.40 / 12.90 - 1, "volume": 900_000}


def test_a_live_trade_reprices_the_row():
    out = with_live_trade(ROW, {"price": 17.11, "last_trade_ts": 1.0, "volume": 1_200_000})
    assert out["price"] == 17.11
    assert abs(out["change_pct"] - (17.11 / 12.90 - 1)) < 1e-9
    assert out["volume"] == 1_200_000
    assert ROW["price"] == 16.40


def test_the_prior_close_is_not_a_trade():
    assert with_live_trade(ROW, {"price": 12.90, "last_trade_ts": None, "quote_quality": "close_fallback"}) is ROW


def test_no_line_or_no_trade_time_keeps_the_row():
    assert with_live_trade(ROW, None) is ROW
    assert with_live_trade(ROW, {"price": 17.11, "last_trade_ts": None}) is ROW


def test_a_smaller_volume_keeps_the_rows():
    assert with_live_trade(ROW, {"price": 17.11, "last_trade_ts": 1.0, "volume": 5})["volume"] == 900_000


def test_without_a_prior_close_the_rows_change_stays():
    row = {**ROW, "prev_close": None}
    assert with_live_trade(row, {"price": 17.11, "last_trade_ts": 1.0})["change_pct"] == ROW["change_pct"]
