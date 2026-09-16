"""Advise application API: book lookup, start/cancel/retry, estimates.

Never calls the order SSOT or IBKR client modules.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any

from advise import book, pool
from advise.estimate import clamp_depth, estimate as build_estimate
from advise.llm import openrouter_key
from constants_advise import (
    ADVISE_DISCLAIMER,
    ADVISE_GRAPH_VERSION,
    ADVISE_STALE_SEC,
    advise_model_id,
)
from market import session_key_et

_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,11}$")


class AdviseError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def normalize_symbol(symbol: str) -> str:
    value = (symbol or "").strip().upper()
    if not _SYMBOL_RE.match(value):
        raise AdviseError("Enter a ticker like AAPL before running Advise")
    return value


def _decorate(run: dict[str, Any], *, from_book: bool = False) -> dict[str, Any]:
    finished = run.get("finished_ts")
    stale = False
    if run.get("status") == "complete" and finished:
        stale = (time.time() - float(finished)) >= ADVISE_STALE_SEC
    return {
        **run,
        "from_book": from_book,
        "stale": stale,
        "stale_nudge": "This run is over ~2 hours old. Refresh?" if stale else None,
        "disclaimer": ADVISE_DISCLAIMER,
        "places": False,
    }


def latest(symbol: str, depth: int | None = None) -> dict[str, Any] | None:
    sym = normalize_symbol(symbol)
    clamp_depth(depth)
    row = book.find_latest(sym)
    return _decorate(row, from_book=True) if row else None


def history(symbol: str) -> list[dict[str, Any]]:
    return [_decorate(row, from_book=True) for row in book.list_history(normalize_symbol(symbol))]


def get_run(run_id: int) -> dict[str, Any]:
    run = book.get_run(int(run_id))
    if run is None:
        raise AdviseError("Advise run not found", 404)
    return _decorate(run, from_book=run["status"] == "complete")


def estimate(symbol: str, depth: int | None = None) -> dict[str, Any]:
    return build_estimate(normalize_symbol(symbol), depth)


def _require_key_for_spend() -> None:
    if (os.environ.get("ADVISE_STUB") or "").strip().lower() in ("1", "true", "yes"):
        return
    if not openrouter_key():
        raise AdviseError(
            "OPENROUTER_API_KEY is not set in local .env -- required to run a debate"
        )


async def start_run(symbol: str, depth: int | None, force_refresh: bool) -> dict[str, Any]:
    sym = normalize_symbol(symbol)
    rounds = clamp_depth(depth)
    if not force_refresh:
        cached = book.find_complete_cached(
            symbol=sym,
            session_date=session_key_et(),
            model=advise_model_id(),
            graph_version=ADVISE_GRAPH_VERSION,
            depth=rounds,
        )
        if cached:
            return _decorate(cached, from_book=True)
    active_id = pool.active_run_for(sym)
    if active_id is not None:
        return get_run(active_id)
    _require_key_for_spend()
    run = book.create_run(
        symbol=sym,
        model=advise_model_id(),
        graph_version=ADVISE_GRAPH_VERSION,
        depth=rounds,
    )
    await pool.enqueue(run["id"])
    return _decorate(book.get_run(run["id"]) or run)


async def cancel_run(run_id: int) -> dict[str, Any]:
    run = book.get_run(int(run_id))
    if run is None:
        raise AdviseError("Advise run not found", 404)
    if run["status"] in ("complete", "failed", "cancelled"):
        return _decorate(run)
    await pool.cancel(int(run_id))
    return _decorate(book.get_run(int(run_id)) or run)


async def retry_run(run_id: int) -> dict[str, Any]:
    run = book.get_run(int(run_id))
    if run is None:
        raise AdviseError("Advise run not found", 404)
    return await start_run(run["symbol"], int(run["depth"]), force_refresh=True)
