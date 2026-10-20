"""The Global page's IBKR reads (ADR 060), run from its reader thread on the IB loop (``run_coro``). Last in line:

- ``index_quotes``: each market's index from a line held for a moment (``ibkr.brief_lines``, ADR 054) -- refused
  (``NoHeadroom``) while fewer than ``IBKR_BRIEF_MIN_FREE_LINES`` lines are spare.
- ``bars``: an instrument's bars through the paced historical service at background priority, under the pacing kind
  ``global`` -- shed (``HistoricalShed``) while ``headroom()`` or fewer of the 10-minute 60 are left: the Market
  page's own 30, or 40 while the Market page shows and this one does not.
- ``fx_close``: a currency's US dollars per unit, IBKR's last daily midpoint close of its pair.

An instrument IBKR refuses (no permission, unknown contract) raises ``Refused`` with IBKR's code and words; the caller
remembers it and reads the market's ETF instead. Errors on futures, indexes and forex never touch the stock session's
flags (``ibkr.reference_errors``, ADR 053 decision 3). Nothing here places anything.
"""
from __future__ import annotations

import math
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from constants_global_board import (
    GLOBAL_FX_DURATION,
    GLOBAL_FX_PAIRS,
    GLOBAL_HISTORY_HEADROOM,
    GLOBAL_HISTORY_TIMEOUT_SEC,
    GLOBAL_IBKR_TIMEOUT_SEC,
    GLOBAL_PACE_KIND,
    GLOBAL_YIELD_HEADROOM,
)
from constants_ibkr import IBKR_BRIEF_LINE_BATCH, IBKR_BRIEF_LINE_WAIT_SEC
from global_board import contracts
from ibkr import brief_lines
from ibkr.brief_lines import NoHeadroom  # noqa: F401 -- refresh.py defers a read on it

SOURCE = "ibkr"
DATA_TYPES = {1: "live", 2: "frozen", 3: "delayed", 4: "delayed_frozen"}


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
    """How many of the 10-minute 60 Global leaves: the Market page's own 30, so the two take turns -- 40 while the
    Market page shows and Global does not, so the page on screen goes first."""
    from global_board.state import store
    from market_board.state import store as market_store

    now = time.time() if now is None else now
    return GLOBAL_YIELD_HEADROOM if market_store().wanted(now) and not store().wanted(now) else GLOBAL_HISTORY_HEADROOM


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
    from ibkr import reference_errors

    sec = {"index": "IND", "future": "CONTFUT", "fx": "CASH"}.get(kind)
    entry = None
    if contract is not None and getattr(contract, "conId", 0):
        entry = reference_errors.last_error(con_id=contract.conId, since=since)
    if entry is None and sec:
        entry = reference_errors.last_error(sec_type=sec, symbol=spec["symbol"], since=since)
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
            f"Global reads last: fewer than {limit + 1} of IBKR's historical requests are left")
    return await coro


def index_quotes(markets: list[Mapping], trading_date: str) -> dict[str, dict]:
    """``{market id: quote}`` for every market with an index; a refused index carries ``error`` and no numbers."""
    brief_lines.guard()
    wanted = [m for m in markets if m.get("index")]

    async def _ask() -> dict[str, dict]:
        from ibkr import client

        ib = client.get_ib()
        if ib is None:
            raise Stated("IBKR is not connected")
        out: dict[str, dict] = {}
        pairs: list[tuple[Mapping, Any]] = []
        for m in wanted:
            started = time.time()
            contract = await contracts.resolve(ib, "index", m["index"], trading_date)
            if contract is None:
                why = _refusal(None, "index", m["index"], started - 1)
                out[m["id"]] = _quote(m, None, why or "IBKR does not know this index")
                continue
            pairs.append((m, contract))
        started = time.time()
        tickers = await brief_lines.read(ib, [c for _, c in pairs])
        for m, contract in pairs:
            ticker = tickers.get(contract.conId)
            why = _refusal(contract, "index", m["index"], started - 1)
            out[m["id"]] = _quote(m, ticker, why if ticker is None or _num(getattr(ticker, "last", None)) is None
                                  else None)
        return out

    batches = max(1, -(-len(wanted) // IBKR_BRIEF_LINE_BATCH))
    budget = GLOBAL_IBKR_TIMEOUT_SEC * (1 + len(wanted)) + batches * (IBKR_BRIEF_LINE_WAIT_SEC + 1.0) + 5.0
    return _run(_ask(), budget, "global_board.index_quotes") or {}


def _quote(m: Mapping, ticker: Any, error: str | None) -> dict:
    last = _num(getattr(ticker, "last", None)) if ticker is not None else None
    close = _num(getattr(ticker, "close", None)) if ticker is not None else None
    pct = round((last / close - 1.0) * 100.0, 3) if last is not None and close else None
    return {"id": m["id"], "last": last, "prev_close": close, "pct": pct,
            "data_type": DATA_TYPES.get(int(getattr(ticker, "marketDataType", 0) or 0)) if ticker else None,
            "at": time.time(), "error": None if pct is not None else (error or "IBKR gave no index price yet")}


def bars(kind: str, spec: Mapping, trading_date: str, *, duration: str, bar_size: str, use_rth: bool,
         what: str = "TRADES") -> dict:
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
            f"{GLOBAL_PACE_KIND}:{contracts.key(kind, spec)}", contract, duration=duration, bar_size=bar_size,
            what_to_show=what, use_rth=use_rth, pace_kind=GLOBAL_PACE_KIND))
        if not rows:
            why = _refusal(contract, kind, spec, started - 1)
            if why:
                raise Refused(why)
            raise Stated(f"IBKR gave no bars for {spec['symbol']}")
        return {"bars": rows, "instrument": contracts.instrument(kind, spec, contract)}

    return _run(_ask(), GLOBAL_HISTORY_TIMEOUT_SEC, f"global_board.bars.{kind}")


def daily_rows(got: dict) -> list[dict]:
    """Daily bars as ``[{date, close, volume, average}]`` (a daily bar's ``t`` is its date's midnight UTC)."""
    return [{"date": datetime.fromtimestamp(b["t"], timezone.utc).date().isoformat(), "close": b.get("close"),
             "volume": b.get("volume"), "average": b.get("average")} for b in got.get("bars") or []]


def fx_close(currency: str, trading_date: str) -> dict:
    """``{currency, usd_per_unit, date}`` from the pair's last daily midpoint close."""
    _pair, usd_per_unit = GLOBAL_FX_PAIRS[currency]
    got = bars("fx", contracts.fx_spec(currency), trading_date, duration=GLOBAL_FX_DURATION, bar_size="1 day",
               use_rth=False, what="MIDPOINT")
    rows = [r for r in daily_rows(got) if r.get("close")]
    if not rows:
        raise Stated(f"IBKR gave no {currency} rate")
    price = float(rows[-1]["close"])
    return {"currency": currency, "usd_per_unit": round(price if usd_per_unit else 1.0 / price, 8),
            "date": rows[-1]["date"]}
