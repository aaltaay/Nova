"""The book watcher's HTTP reads (ADR 033). Read-only: nothing here places, gates or cancels an order.

  GET /api/book-watch/{symbol}/big-sellers   the big sellers on the ask and big buyers on the bid of the held
                                             Level 2 line (#846; ``big_read``) -- the live line's, or on a Sim
                                             replay the loaded Session Record's at the playhead. The held-trade
                                             card polls it every second while you hold.

Sync route: FastAPI runs it on a worker thread, off the event loop (a replay may feed minutes of a
recording on its first read). Memory reads only: no network, no IBKR request.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from book_watch import big_read
from scanner_wire import wire_safe

router = APIRouter(prefix="/api/book-watch", tags=["book_watch"])


def _symbol(raw: str) -> str:
    sym = (raw or "").strip().upper()
    if not sym or len(sym) > 12:
        raise HTTPException(400, "a symbol, up to 12 characters")
    return sym


@router.get("/{symbol}/big-sellers")
def big_sellers(symbol: str):
    return wire_safe(big_read.reading(_symbol(symbol)))
