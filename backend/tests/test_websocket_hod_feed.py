"""Alpaca WS must not drive HOD when discovery=ibkr (single-feed rule)."""
from websocket import alpaca_trades_drive_hod


def test_alpaca_trades_drive_hod_when_alpaca():
    assert alpaca_trades_drive_hod("alpaca") is True


def test_alpaca_trades_do_not_drive_hod_when_ibkr():
    assert alpaca_trades_drive_hod("ibkr") is False
