"""IBKR's prior close is never a trade (#541): candles, HOD Momo, the chart tip and Paper fills."""
from __future__ import annotations

from types import SimpleNamespace

from ibkr import ticks

CLOSE_FALLBACK = "close_fallback"


def _line(symbol: str, owners=None) -> None:
    ticks._subs.clear()
    ticks._subs[symbol] = {"owners": set(owners or {ticks.OWNER_SCANNER}), "last_price": None,
                           "last_update_ts": None}


def _ticker(**kw):
    base = dict(last=None, close=None, volume=None, high=None, lastTimestamp=None, rtTime=None,
                time=None, lastSize=None, rtVolume=None, ticks=[])
    return SimpleNamespace(**{**base, **kw})


def test_the_line_says_its_price_is_the_prior_close_and_when_it_last_traded(monkeypatch):
    _line("APLX")
    monkeypatch.setattr(ticks, "_broadcast", None)
    ticks._on_ticker_update(_ticker(close=9.52), "APLX")
    row = ticks.last_quotes(["APLX"])["APLX"]
    assert (row["price"], row["quote_quality"], row["last_trade_ts"]) == (9.52, CLOSE_FALLBACK, None)
    ticks._on_ticker_update(_ticker(last=8.60, close=9.52, lastTimestamp=1_790_193_683), "APLX")
    row = ticks.last_quotes(["APLX"])["APLX"]
    assert (row["price"], row["quote_quality"], row["last_trade_ts"]) == (8.60, None, 1_790_193_683.0)
    ticks._subs.clear()


def test_the_prior_close_is_never_broadcast_as_a_trade_update(monkeypatch):
    _line("APLX", owners={ticks.OWNER_SCANNER, ticks.OWNER_DETAIL})
    sent: list = []

    async def broadcast(*args):
        sent.append(args)

    monkeypatch.setattr(ticks, "_broadcast", broadcast)
    scheduled: list = []
    import ibkr.loop_supervisor as sup

    monkeypatch.setattr(sup, "is_ib_loop", lambda: True)
    monkeypatch.setattr(sup, "publish_to_http", lambda fn: scheduled.append(fn))
    ticks._on_ticker_update(_ticker(close=9.52), "APLX")
    assert scheduled == []  # nothing traded: no chart tip at the prior close
    ticks._on_ticker_update(_ticker(last=8.60, close=9.52), "APLX")
    assert len(scheduled) == 1
    ticks._subs.clear()


def test_no_live_minute_candle_from_the_prior_close(monkeypatch):
    from ibkr import scanner_l1, scanner_l1_apply

    stamped: list = []
    monkeypatch.setattr(scanner_l1_apply._l1_minute, "on_last", lambda *a, **k: stamped.append(a))
    monkeypatch.setattr(scanner_l1, "_apply_quote", None)
    scanner_l1.on_l1_quote("APLX", 9.52, None, 9.52, 1_790_193_658.0, quote_quality=CLOSE_FALLBACK)
    assert stamped == []
    scanner_l1.on_l1_quote("APLX", 8.60, 100, 9.52, 1_790_193_683.0)
    assert stamped == [("APLX", 8.60, 1_790_193_683.0)]
    scanner_l1._pending.clear()


def test_hod_momo_and_its_tick_archive_take_trades_only(monkeypatch):
    import hod_tick_feed
    from ibkr import l1_apply

    fed: list = []
    monkeypatch.setattr(hod_tick_feed, "feed_hod_on_tick", lambda *a: fed.append(a))
    state = SimpleNamespace(gainer_cache=[], loser_cache=[], gapper_cache=[], afterhours_cache=[],
                            large_cap_cache=[], current_mode="premarket")
    l1_apply.apply_l1_quote("APLX", 9.52, None, 9.52, 1.0, quote_quality=CLOSE_FALLBACK, get_state=lambda: state)
    assert fed == []
    l1_apply.apply_l1_quote("APLX", 8.60, 100, 9.52, 2.0, get_state=lambda: state)
    assert len(fed) == 1 and fed[0][:2] == ("APLX", 8.60)
