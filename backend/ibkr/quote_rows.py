"""Scanner rows repriced from a quote -- pure (split from ``ibkr/discovery.py``).

A quote (a ``discovery.snapshot_quotes`` entry, or an L1 tick in ``ibkr/l1_apply``)
carries ``price`` and, when known, ``prev_close`` / ``open`` / ``volume``. These
functions rebuild a gapper or gainer/loser row's price and change fields from it,
always against the row's own prior close, so price and change never drift apart.
Whether a price is a trade or IBKR's prior close (``quote_quality``) is stamped by
the caller.
"""
from __future__ import annotations


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


def reprice_mover_row(m: dict, q: dict) -> dict:
    """Gainer/loser counterpart to reprice_gapper_row.

    Also the fill path for a names-first stub row (ADR 010 decision 5): the
    resolved ``prev_close`` is written back so the row stops being a stub after
    the first L1 tick that carries a close. Without a close the price is still
    recorded, but no change is invented against an unknown baseline.

    ``gap_percent`` needs the session open (IB tick type 14), which arrives on
    the same streaming ticker. Before it lands the row keeps whatever gap it
    already had rather than reusing ``change_pct`` -- an intraday move is not a
    gap, and inventing one is what a null column is protecting against.
    """
    prev_close = m.get("prev_close") or q.get("prev_close")
    price = q["price"]
    if not prev_close:
        return {**m, "price": price, "volume": q.get("volume", m.get("volume", 0))}
    change_pct = (price - prev_close) / prev_close
    open_price = m.get("open") or q.get("open")
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
