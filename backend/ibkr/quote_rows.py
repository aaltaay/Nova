"""A quote, and scanner rows repriced from it (split from ``ibkr/discovery.py``).

A quote (a ``discovery.snapshot_quotes`` entry, a ``brief_lines.stock_quotes`` one, or
an L1 tick in ``ibkr/l1_apply``) carries ``price`` and, when known, ``prev_close`` /
``open`` / ``volume``. ``quote_from_ticker`` builds one from an IBKR ticker (the
wall clock decides whether IBKR's open tick is today's). The rest are pure: they
rebuild a gapper or gainer/loser row's price and change fields from a quote,
always against the row's own prior close, so price and change never drift apart.
Whether a price is a trade or IBKR's prior close (``quote_quality``) is stamped by
the caller.
"""
from __future__ import annotations

import math

from constants_ibkr import IBKR_QUOTE_QUALITY_CLOSE_FALLBACK


def _clean(x: float | None) -> float | None:
    """IB leaves un-populated Ticker fields as NaN, not None."""
    if x is None:
        return None
    try:
        return None if math.isnan(x) else float(x)
    except TypeError:
        return None


def quote_from_ticker(t) -> dict | None:
    """``{price, quote_quality, prev_close, open, high, volume, exchange}`` from a stock's ticker; ``None`` with no
    price. A ``snapshot_quotes`` entry and a brief line's (``ibkr/brief_lines.stock_quotes``) are this shape.
    """
    from ibkr.open_tick import todays_open

    # Last preferred; close is a fallback print AND the usual prior close.
    # Do not require both — missing close used to drop the symbol entirely,
    # which blanked Stock View header price/change (symbol-only chip).
    last = _clean(t.last)
    price = last or _clean(t.close)
    if price is None:
        return None
    return {
        "price": price,
        # No trade yet: ``price`` is IBKR's prior close, never a print (#541).
        "quote_quality": None if last is not None else IBKR_QUOTE_QUALITY_CLOSE_FALLBACK,
        "prev_close": _clean(t.close),
        # IBKR's open tick is the previous session's until today opens.
        "open": todays_open(_clean(t.open)),
        "high": _clean(getattr(t, "high", None)),
        "volume": int(_clean(t.volume) or 0),
        "exchange": getattr(t.contract, "primaryExchange", None) or None,
    }


def reprice_gapper_row(g: dict, q: dict) -> dict:
    """Apply a fresh quote (a ``snapshot_quotes()`` entry or an L1 tick) to an existing
    gapper row, recomputing change fields from the row's own prev_close so price and
    change_pct/change_abs never drift apart."""
    prev_close = g.get("previous_close") or g.get("prev_close") or q.get("prev_close")
    price = q["price"]
    if not prev_close:
        return g
    gap_frac = (price - prev_close) / prev_close
    return {
        **g,
        "price": price,
        "current_price": price,
        "change_pct": gap_frac,
        "change_abs": price - prev_close,
        "gap_percent": gap_frac,
        "volume": q.get("volume", g.get("volume", 0)),
    }


def mover_row_from_quote(symbol: str, q: dict) -> dict:
    """A new gainer/loser row from a ``snapshot_quotes`` entry with a prior close.

    The arithmetic ``reprice_mover_row`` keeps up afterwards: the move against
    the prior close, and a gap only from the quote's open -- which the quote
    carries only once today's session has opened (``ibkr/open_tick.py``).
    """
    price, prev_close = q["price"], q["prev_close"]
    open_price = q.get("open")
    return {
        "symbol": symbol,
        "price": price,
        "change_pct": (price - prev_close) / prev_close,
        "change_abs": price - prev_close,
        "volume": q["volume"],
        "gap_percent": (open_price - prev_close) / prev_close if open_price else None,
        "prev_close": prev_close,
        "open": open_price,
        "exchange": q.get("exchange"),
    }


def reprice_mover_row(m: dict, q: dict) -> dict:
    """Gainer/loser counterpart to reprice_gapper_row.

    Also the fill path for a names-first stub row (ADR 010 decision 5): the
    resolved ``prev_close`` is written back so the row stops being a stub after
    the first L1 tick that carries a close. Without a close the price is still
    recorded, but no change is invented against an unknown baseline.

    ``gap_percent`` needs the session open (IB tick type 14), which arrives on
    the same streaming ticker. Before it lands the row keeps whatever gap it
    already had rather than reusing ``change_pct`` -- an intraday move is not a
    gap, and inventing one is what a null column is protecting against. The
    quote's open wins over the row's: a quote carries an open only once
    today's session has opened (``ibkr/open_tick.py``), so a stored open from
    before that can never outlive the real one.
    """
    prev_close = m.get("prev_close") or q.get("prev_close")
    price = q["price"]
    if not prev_close:
        return {**m, "price": price, "volume": q.get("volume", m.get("volume", 0))}
    change_pct = (price - prev_close) / prev_close
    open_price = q.get("open") or m.get("open")
    gap_percent = (
        (open_price - prev_close) / prev_close
        if open_price and prev_close else m.get("gap_percent")
    )
    return {
        **m,
        "price": price,
        "prev_close": prev_close,
        "open": open_price or m.get("open"),
        "change_pct": change_pct,
        "change_abs": price - prev_close,
        "gap_percent": gap_percent,
        "volume": q.get("volume", m.get("volume", 0)),
    }
