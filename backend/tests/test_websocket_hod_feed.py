"""Alpaca WS must not drive HOD when discovery=ibkr (single-feed rule)."""
from websocket import alpaca_trades_drive_hod


def test_alpaca_trades_drive_hod_when_alpaca():
    assert alpaca_trades_drive_hod("alpaca") is True


def test_alpaca_trades_do_not_drive_hod_when_ibkr():
    assert alpaca_trades_drive_hod("ibkr") is False


def test_stream_loop_idles_under_ibkr(monkeypatch):
    """stream_loop must not open Alpaca's socket when discovery=ibkr."""
    import asyncio
    import websocket as ws_mod

    slept: list[float] = []

    async def fake_sleep(sec):
        slept.append(sec)
        if len(slept) >= 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(ws_mod, "alpaca_trades_drive_hod", lambda provider=None: False)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def run():
        try:
            await ws_mod.stream_loop()
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
    assert slept, "expected idle sleeps under ibkr"
    assert all(s > 0 for s in slept)
