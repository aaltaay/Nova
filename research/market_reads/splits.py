"""Splits for the market data front door: the list the board rebuild adjusts by, and the factor that turns a raw
price into another day's terms.

Nothing in the Massive files is split-adjusted, and IBKR's daily bars are: on 2026-07-15 GRML traded at $0.19, and
the desk's Full Day chart showed the same day near $9.25, after its 1-for-50 reverse split on 2026-08-24. The list
is the board rebuild's own (``research/leaderboard/lb_io.load_splits``): Massive's split table and its reference
archive, plus the splits SEC filings proved that Massive misses (#772). Reads stay raw; ``adjust`` is asked for.
"""
from __future__ import annotations

import sys
from datetime import date
from functools import lru_cache

import pandas as pd

from market_reads import REPO, tickers

if str(REPO / "research" / "leaderboard") not in sys.path:
    sys.path.insert(0, str(REPO / "research" / "leaderboard"))

import lb_io  # noqa: E402
from lb_config import CONFIRMED_SPLITS_PATH, DATA_ROOT, REFERENCE_SUBDIR, RESEARCH_DB  # noqa: E402

# Columns a split rescales: prices multiply by the factor, share counts divide by it.
PRICE_COLUMNS = ("price", "bid_price", "ask_price", "open", "high", "low", "close", "vwap")
SHARE_COLUMNS = ("size", "bid_size", "ask_size", "volume")


@lru_cache(maxsize=1)
def _all() -> tuple[pd.DataFrame, str]:
    research, note = lb_io.open_research_db(RESEARCH_DB)
    try:
        listed = lb_io.load_splits(research, DATA_ROOT / REFERENCE_SUBDIR, confirmed=None)
    finally:
        if research is not None:
            research.close()
    have = {(s.ticker, s.execution_date) for s in listed}
    confirmed = [s for s in lb_io.load_confirmed_splits(CONFIRMED_SPLITS_PATH) if (s.ticker, s.execution_date) not in have]
    rows = [(s.ticker, s.execution_date, s.split_from, s.split_to, "massive") for s in listed]
    rows += [(s.ticker, s.execution_date, s.split_from, s.split_to, "sec_confirmed") for s in confirmed]
    frame = pd.DataFrame(rows, columns=["ticker", "execution_date", "split_from", "split_to", "source"])
    frame["price_factor"] = frame["split_from"] / frame["split_to"]
    return frame.sort_values(["ticker", "execution_date"]).reset_index(drop=True), note


def table(symbol: str | None = None, day: str | None = None, cik: str | None = None) -> pd.DataFrame:
    """Every split (``symbol``'s only, when given), oldest first. ``price_factor`` multiplies a price from before the
    split into its terms: a 1-for-50 reverse split (``split_from`` 50, ``split_to`` 1) is 50.

    The list is keyed by ticker, and a ticker can have had two companies (``tickers.py``). With ``day`` (or
    ``cik``) only the splits executed while that day's company held the ticker are kept; without, a reused ticker's
    rows say which company held it (``holder_cik``, None when the windows overlap). ``attrs['ticker']`` says so."""
    frame, note = _all()
    held = None
    if symbol:
        frame = frame[frame["ticker"] == symbol.strip().upper()].reset_index(drop=True)
        held = tickers.resolve(symbol, day, cik)
        if held["ticker_reused"] and (day or cik):
            held = tickers.require(symbol, day, cik)
            mine = next(c for c in held["candidates"] if c["cik"] == held["cik"])
            frame = frame.loc[[tickers.holds(mine, d.isoformat()) for d in frame["execution_date"]]]
        elif held["ticker_reused"]:
            owners = [_holder(held["candidates"], d.isoformat()) for d in frame["execution_date"]]
            frame = frame.assign(holder_cik=pd.Series(owners, index=frame.index, dtype=object))
    frame = frame.reset_index(drop=True).copy()
    frame.attrs.update(symbol=symbol.upper() if symbol else None, reference=note, confirmed=str(CONFIRMED_SPLITS_PATH))
    if held is not None:
        frame.attrs["ticker"] = tickers.summary(held)
    return frame


def _holder(candidates: list[dict], day: str) -> str | None:
    holding = [c["cik"] for c in candidates if tickers.holds(c, day)]
    return holding[0] if len(holding) == 1 else None


def factor(symbol: str, day: str, as_of: str | None = None, cik: str | None = None) -> float:
    """What a raw price traded on ``day`` multiplies by to read in ``as_of``'s terms (default: after every split
    known); share counts divide by it. 1.0 when no split executes after ``day`` and by ``as_of``. Only the splits
    of the company that held the ticker on ``day``."""
    rows = table(symbol, day=day, cik=cik)
    through = date.fromisoformat(as_of) if as_of else date.max
    after = date.fromisoformat(day)
    picked = rows[(rows["execution_date"] > after) & (rows["execution_date"] <= through)]
    return float(picked["price_factor"].prod()) if len(picked) else 1.0


def adjust(frame: pd.DataFrame, symbol: str, day: str, as_of: str | None = None) -> pd.DataFrame:
    """A copy of one stock-day's read (``reads.trades / quotes / bars``) in ``as_of``'s terms: price columns times
    ``factor``, share columns divided by it. ``df.attrs`` gains ``split_factor`` and ``adjusted_to``."""
    k = factor(symbol, day, as_of)
    out = frame.copy()
    if k != 1.0:
        for column in PRICE_COLUMNS:
            if column in out:
                out[column] = out[column] * k
        for column in SHARE_COLUMNS:
            if column in out:
                out[column] = out[column] / k
    out.attrs.update(frame.attrs, split_factor=k, adjusted_to=as_of or "latest")
    return out
