"""The Forex page's IBKR reads (ADR 061), run from its reader thread on the IB loop (``run_coro``). Last in line:

- ``spot_quotes``: each pair's bid and ask from a line held for a moment (``ibkr.brief_lines``, ADR 054) -- refused
  (``NoHeadroom``) while fewer than ``IBKR_BRIEF_MIN_FREE_LINES`` lines are spare. Spot forex needs no extra IBKR
  market-data subscription.
- ``bars``: an instrument's bars through the paced historical service at background priority, under the pacing kind
  ``forex`` -- shed (``HistoricalShed``) while ``headroom()`` or fewer of the 10-minute 60 are left: the Market and
  Global pages' own 30, or 40 while one of them shows and this one does not.

An instrument IBKR refuses (no permission, unknown contract) raises ``Refused`` with IBKR's code and words; the caller
remembers it. Errors on forex and futures never touch the stock session's flags (``ibkr.reference_errors``, ADR 053
decision 3). Nothing here places anything.
"""
from __future__ import annotations

import math
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from constants_forex_board import (
    FOREX_HISTORY_HEADROOM,
    FOREX_HISTORY_TIMEOUT_SEC,
    FOREX_IBKR_TIMEOUT_SEC,
    FOREX_PACE_KIND,
    FOREX_YIELD_HEADROOM,
)
from constants_ibkr import IBKR_BRIEF_LINE_BATCH, IBKR_BRIEF_LINE_WAIT_SEC
from forex_board import contracts
from ibkr import brief_lines
from ibkr.brief_lines import NoHeadroom  # noqa: F401 -- refresh.py defers a read on it

DATA_TYPES = {1: "live", 2: "frozen", 3: "delayed", 4: "delayed_frozen"}
_SEC_TYPE = {"spot": "CASH", "future": "CONTFUT"}


class Stated(Exception):
    """A read failed for a known reason; its message is what the page shows (logged without a traceback)."""


class Refused(Stated):
    """IBKR refused this instrument: no market-data permission, or no such contract. Its message is IBKR's."""


def ready() -> bool:
    from ibkr import client

    return client.is_ready()


def history_left() -> int | None:
    from ibkr import historical_service

    try:
        snap = historical_service.pacing_snapshot()
        return int(snap["window_max"]) - int(snap["window_used"])
    except (KeyError, TypeError, ValueError):
        return None


def headroom(now: float | None = None) -> int:
    """How many of the 10-minute 60 Forex leaves: the Market and Global pages' own 30, so the three take turns --
    40 while one of them shows and this one does not, so the page on screen goes first."""
    from forex_board.state import store
    from global_board.state import store as global_store
    from market_board.state import store as market_store

    now = time.time() if now is None else now
    other = market_store().wanted(now) or global_store().wanted(now)
    return FOREX_YIELD_HEADROOM if other and not store().wanted(now) else FOREX_HISTORY_HEADROOM


def history_ok() -> bool:
    left = history_left()
    return left is not None and left > headroom()


def lines_ok() -> bool:
    return brief_lines.headroom_ok()


def _num(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _run(coro, timeout: float, label: str):
    from ibkr.client_bridge import run_coro

    return run_coro(coro, timeout, label=label)


def _refusal(contract: Any, kind: str, spec: Mapping, since: float) -> str | None:
    """IBKR's words for this instrument since ``since``: by its conId when qualified, else by its secType and symbol
    (a pair's symbol is its first currency, ``EURUSD`` -> ``EUR``)."""
    from ibkr import reference_errors

    entry = None
    if contract is not None and getattr(contract, "conId", 0):
        entry = reference_errors.last_error(con_id=contract.conId, since=since)
    if entry is None:
        symbol = spec["symbol"][:3] if kind == "spot" else spec["symbol"]
        entry = reference_errors.last_error(sec_type=_SEC_TYPE[kind], symbol=symbol, since=since)
    return reference_errors.describe(entry)


async def _paced(coro):
    """``coro``, a historical request -- or ``HistoricalShed`` while the page's headroom is not there. Checked on the
    IB loop, where the budget is kept."""
    from ibkr import historical_service

    snap = historical_service.pacing_snapshot()
    limit = headroom()
    if snap["window_max"] - snap["window_used"] <= limit:
        coro.close()
        raise historical_service.HistoricalShed(
            f"Forex reads last: fewer than {limit + 1} of IBKR's historical requests are left")
    return await coro


def spot_quotes(currencies: list[Mapping], trading_date: str) -> dict[str, dict]:
    """``{code: quote}`` for every currency with a pair; a pair IBKR refused carries ``error`` and no numbers."""
    brief_lines.guard()

    async def _ask() -> dict[str, dict]:
        from ibkr import client

        ib = client.get_ib()
        if ib is None:
            raise Stated("IBKR is not connected")
        out: dict[str, dict] = {}
        pairs: list[tuple[Mapping, Mapping, Any]] = []
        for cur in currencies:
            spec = contracts.spot_spec(cur)
            started = time.time()
            contract = await contracts.resolve(ib, "spot", spec, trading_date)
            if contract is None:
                out[cur["code"]] = _quote(None, _refusal(None, "spot", spec, started - 1)
                                          or "IBKR does not know this pair")
                continue
            pairs.append((cur, spec, contract))
        started = time.time()
        tickers = await brief_lines.read(ib, [c for _cur, _spec, c in pairs])
        for cur, spec, contract in pairs:
            ticker = tickers.get(contract.conId)
            out[cur["code"]] = _quote(ticker, _refusal(contract, "spot", spec, started - 1))
        return out

    batches = max(1, -(-len(currencies) // IBKR_BRIEF_LINE_BATCH))
    budget = FOREX_IBKR_TIMEOUT_SEC * (1 + len(currencies)) + batches * (IBKR_BRIEF_LINE_WAIT_SEC + 1.0) + 5.0
    return _run(_ask(), budget, "forex_board.spot_quotes") or {}


def _quote(ticker: Any, error: str | None) -> dict:
    bid = _num(getattr(ticker, "bid", None)) if ticker is not None else None
    ask = _num(getattr(ticker, "ask", None)) if ticker is not None else None
    mid = (bid + ask) / 2.0 if bid and ask and bid > 0 and ask > 0 else None
    return {"bid": bid, "ask": ask, "mid": mid,
            "data_type": DATA_TYPES.get(int(getattr(ticker, "marketDataType", 0) or 0)) if ticker else None,
            "at": time.time(), "error": None if mid is not None else (error or "IBKR gave no quote yet")}


def bars(kind: str, spec: Mapping, trading_date: str, *, duration: str, bar_size: str, what: str,
         use_rth: bool = False) -> dict:
    """``{bars, instrument}`` -- IBKR's bars oldest first (``[{t, open, high, low, close, volume, average}]``)."""
    from ibkr import historical_service

    async def _ask() -> dict:
        from ibkr import client

        ib = client.get_ib()
        if ib is None:
            raise Stated("IBKR is not connected")
        started = time.time()
        contract = await contracts.resolve(ib, kind, spec, trading_date)
        if contract is None:
            raise Refused(_refusal(None, kind, spec, started - 1) or f"IBKR does not know {spec['symbol']}")
        started = time.time()
        rows = await _paced(historical_service.request_reference_bars(
            f"{FOREX_PACE_KIND}:{contracts.key(kind, spec)}", contract, duration=duration, bar_size=bar_size,
            what_to_show=what, use_rth=use_rth, pace_kind=FOREX_PACE_KIND))
        if not rows:
            why = _refusal(contract, kind, spec, started - 1)
            if why:
                raise Refused(why)
            raise Stated(f"IBKR gave no bars for {spec['symbol']}")
        return {"bars": rows, "instrument": contracts.instrument(kind, spec, contract)}

    return _run(_ask(), FOREX_HISTORY_TIMEOUT_SEC, f"forex_board.bars.{kind}")


def daily_rows(got: dict) -> list[dict]:
    """Daily bars as ``[{date, high, low, close, volume, average}]`` (a daily bar's ``t`` is its date's midnight UTC:
    for forex and CME futures, the FX day it ends)."""
    return [{"date": datetime.fromtimestamp(b["t"], timezone.utc).date().isoformat(), "high": b.get("high"),
             "low": b.get("low"), "close": b.get("close"), "volume": b.get("volume"), "average": b.get("average")}
            for b in got.get("bars") or []]
