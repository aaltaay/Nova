"""Premarket Gappers as a projection of the live Gainers roster (ADR 008 amendment).

Why a projection and not its own IB lease: ``TOP_OPEN_PERC_GAIN`` measures
today's open against the prior close, and before 09:30 ET there is no open, so
IB answers with an empty list plus Warning 165 ("no items retrieved"). A
premarket gapper is simply a gainer whose move clears
``GAPPER_MIN_GAP_PCT`` -- exactly what the 2026-07-14 one-shot fallback did
before the authoritative cutover made that code path unreachable.

Ownership contract:

* Owner -- this module is the only writer of ``gapper_cache`` while
  ``discovery=ibkr``. Inputs are ``gainer_cache`` rows (names from the IB lease,
  prices from L1).
* Invalidation -- rebuilt on every Gainers roster commit and on every L1 quote
  that repriced a Gainers row. Frozen at 09:30 ET by ``scanner_session``, after
  which this module refuses to write.
* Freshness -- ``gapper_cache_ts`` is stamped only when the projection actually
  has rows. An empty projection resets the clock to 0 ("nothing qualifies yet")
  rather than advertising a fresh scan of nothing.
"""
from __future__ import annotations

import logging
import time

from constants import GAPPER_MIN_GAP_PCT, SCANNER_MIN_PRICE
from ibkr import scanner_session as _session
from market import session_key_et

logger = logging.getLogger(__name__)


def row_qualifies(row: dict | None) -> bool:
    """True when a gainer row clears the premarket gap floor."""
    if not row or not (row.get("symbol") or "").strip():
        return False
    price = row.get("price")
    prev_close = row.get("prev_close")
    change_pct = row.get("change_pct")
    if price is None or not prev_close or change_pct is None:
        return False
    if price < SCANNER_MIN_PRICE:
        return False
    return change_pct * 100 >= GAPPER_MIN_GAP_PCT


def derive_rows(gainer_rows: list[dict] | None) -> list[dict]:
    """Gapper-shaped rows for gainers whose move clears the gap floor.

    Unpriced stub rows are skipped: with no L1 tick yet the gap is unknown, and
    guessing would put a symbol on the desk's gap list without evidence.
    """
    out: list[dict] = []
    for row in gainer_rows or []:
        if not row_qualifies(row):
            continue
        prev_close = row.get("prev_close")
        price = row.get("price")
        change_pct = row.get("change_pct")
        out.append({
            **row,
            "previous_close": prev_close,
            "current_price": price,
            "gap_percent": change_pct,
        })
    out.sort(key=lambda r: r["gap_percent"], reverse=True)
    for rank, row in enumerate(out, start=1):
        row["rank"] = rank
    return out


def patch_for_table(table: str, row: dict) -> dict:
    """An L1 price patch as ``table`` reads it: on Gappers the gap is the move.

    A patch is built once per symbol from its Gainers row, whose
    ``gap_percent`` is today's open against the prior close (null before the
    open). A gapper's ``gap_percent`` is its ``change_pct`` (``derive_rows``),
    so a patch tagged ``gappers`` says the same -- it used to carry the Gainers
    gap, and the Gappers table and Focus rail flipped between the two numbers
    on every roster replace. Other tables' patches pass through unchanged.
    """
    if table != _session.TABLE_GAPPERS or "change_pct" not in row:
        return row
    return {**row, "gap_percent": row["change_pct"]}


def _publish(table: str, rows: list[dict], ts, wall: float) -> None:
    """Persist + push a roster replace, always on the HTTP loop.

    ``refresh`` is called from L1 quote handling, which runs on the IB
    connect-loop. Disk writes and WebSocket sends must not happen there (ADR
    010: no sync IO on the IB loop), so both hop across the seam.
    """
    import asyncio

    from ibkr.loop_supervisor import is_ib_loop, publish_to_http

    def _send() -> None:
        from ibkr.scanner_persist import persist_roster
        from scanner_push import broadcast_roster_replace

        try:
            # Empty projection is "nothing qualifies yet", not a completed
            # scan -- never persist it over a non-empty day's snapshot.
            if rows:
                persist_roster(table, rows, wall)
        except Exception:
            logger.debug("gapper_view: persist failed", exc_info=True)
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast_roster_replace(table, rows, ts))

    try:
        if is_ib_loop():
            publish_to_http(_send)
        else:
            _send()
    except RuntimeError:
        logger.debug("gapper_view: no running loop; roster push skipped")
    except Exception:
        logger.debug("gapper_view: roster publish failed", exc_info=True)


def refresh(state, *, source: str) -> bool:
    """Rebuild the Gappers projection. Returns True when membership changed.

    Price-only changes return False: the L1 ``price_patch`` already carries
    those to the UI, so there is no reason to replace the whole roster.
    """
    table = _session.TABLE_GAPPERS
    if _session.is_table_frozen(state, table):
        return False
    if not _session.table_is_live(table):
        return False
    rows = derive_rows(state.gainer_cache)
    prior = [(r.get("symbol") or "").upper() for r in (state.gapper_cache or [])]
    current = [(r.get("symbol") or "").upper() for r in rows]
    ts = _session.table_attr(state, table)
    wall = time.time()
    state.gapper_cache = rows
    # Empty projection means "no gainer clears the floor yet", which is not a
    # completed scan -- leave the clock unset so integrity reads it as warming
    # instead of a fresh empty market.
    state.gapper_cache_ts = wall if rows else 0.0
    if rows:
        _session.mark_live(ts, source=source, session_key=session_key_et())
    if prior == current:
        return False
    ts.roster_ts = wall if rows else 0.0
    ts.revision += 1
    logger.info(
        "gapper_view: %d gapper(s) from %d gainer row(s) (source=%s)",
        len(rows), len(state.gainer_cache or []), source,
    )
    _publish(table, rows, ts, wall)
    return True
