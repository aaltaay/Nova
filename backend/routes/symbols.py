"""Listed-symbol directory for the header ticker search. Read-only."""
from __future__ import annotations

from fastapi import APIRouter

import symbol_directory

router = APIRouter(tags=["symbols"])


@router.get("/api/symbols/directory")
def get_symbol_directory():
    # Sync route: FastAPI runs it on the threadpool, so the first (blocking)
    # Alpaca fetch never stalls the event loop.
    symbol_directory.refresh()
    return symbol_directory.snapshot()
