"""A Level 1 line IBKR refused: not open, said so, asked for again when there is room.

IBKR caps the market-data lines one login holds at once, and counts the login's other platforms
against the same cap (TWS and the API share it, per IBKR). A ``reqMktData`` past it is answered with Error 101 ("Max number of tickers has
been reached"). ib_async 2.1.0 logs the error but keeps the request registered, and its
``reqMktData`` is idempotent per contract, so a refused line stayed "subscribed" for good. After
the 2026-10-05 close IBKR refused 176 lines while Nova held 51-56 of its own; 17 of the 50 After
Hours rows never got a price (INBS for 53 minutes, until it left the list), and Nova still counted
76 of 100 lines open. A row came back only when a Trader tab happened to re-request its line (OLOX).

Every Level 1 request id is remembered with its symbol when the line opens. Error 101 on a line's
own id marks the line refused: it keeps its owners (a Trader tab, the scanner, HOD Momo) but no
longer counts as open, and the lines Nova held then become the cap it plans to (``ceiling``). The
scanner plans its displayed rows first and HOD Momo's other names into what is left, as it always
has, now within that cap; its reconcile asks for a refused line again (``due`` / ``rerequest``)
after ``IBKR_L1_REFUSED_RETRY_SEC`` and only while Nova holds fewer lines than the cap. The cap
rises by ``IBKR_L1_CAP_RELAX_STEP`` every ``IBKR_L1_CAP_RELAX_SEC`` without a refusal: another app
may have let lines go. The refusal is said in the scanner subscription's error (the header's
scanner hover), ``/api/ibkr/status`` and the ``market_data_lines`` diagnostics row.

Everything here runs on the IB loop (the error callback and the line changes in ``ibkr.ticks``).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from constants import (
    IBKR_L1_CAP_RELAX_SEC,
    IBKR_L1_CAP_RELAX_STEP,
    IBKR_L1_REFUSED_CODES,
    IBKR_L1_REFUSED_RESET_SEC,
    IBKR_L1_REFUSED_RETRY_SEC,
    IBKR_L1_REGISTRY_KIND,
    IBKR_L1_REQ_KEEP,
    IBKR_L1_STREAM_BUDGET,
)
from ibkr import line_session

logger = logging.getLogger(__name__)

# Every Level 1 request id Nova made -> (symbol, IBKR session generation), oldest first, bounded.
_req_symbol: dict[int, tuple[str, int]] = {}
# symbol -> request id of its current line.
_line_req: dict[str, int] = {}
# symbol -> (refusals in a row, when the last came): the backoff outlives the line's re-request.
_streak: dict[str, tuple[int, float]] = {}
# {"lines": the lines Nova held when IBKR last refused one, "at": when}; empty: no cap learned.
_cap: dict[str, float] = {}
# IB objects whose errorEvent is heard here.
_hooked_ib_ids: set[int] = set()
# Who waits least for a line again: a Trader tab, the displayed rows, then HOD Momo's names.
_OWNER_RANK = {"detail": 0, "depth": 0, "listing": 1, "scanner": 1, "hod": 2}


def reset_for_tests() -> None:
    _req_symbol.clear()
    _line_req.clear()
    _streak.clear()
    _cap.clear()
    _hooked_ib_ids.clear()


def _registered(ib: Any, contract: Any) -> Any | None:
    """ib_async's registered Level 1 request for the contract, else None."""
    registry = getattr(getattr(ib, "wrapper", None), "subscriptions", None)
    find = getattr(registry, "find_market_data", None)
    con_id = getattr(contract, "conId", None)
    if find is None or not con_id:
        return None
    try:
        return find(con_id, IBKR_L1_REGISTRY_KIND)
    except Exception:
        logger.warning("IBKR ticks: could not read ib_async's L1 request for conId %s", con_id, exc_info=True)
        return None


def note_opened(symbol: str, ib: Any, contract: Any) -> None:
    """A line was requested: remember its request id, so an error on that id names it."""
    req_id = getattr(_registered(ib, contract), "reqId", None)
    if not isinstance(req_id, int):
        _line_req.pop(symbol, None)
        return
    _line_req[symbol] = req_id
    _req_symbol.pop(req_id, None)  # re-inserted last: the bound drops the oldest
    _req_symbol[req_id] = (symbol, line_session.generation())
    while len(_req_symbol) > IBKR_L1_REQ_KEEP:
        _req_symbol.pop(next(iter(_req_symbol)))


def note_closed(symbol: str) -> None:
    _line_req.pop(symbol, None)


def forget_request(ib: Any, contract: Any) -> bool:
    """Unregister a refused line in ib_async without a cancel: IBKR never opened it (it answers 300)."""
    sub = _registered(ib, contract)
    if sub is None:
        return False
    sub.close(send_cancel=False)
    return True


def open_count(subs: dict[str, dict[str, Any]]) -> int:
    """Lines IBKR holds for Nova: every entry but the refused ones."""
    return sum(1 for sub in list(subs.values()) if not sub.get("refused"))


def ceiling(now: float | None = None) -> int | None:
    """The line cap Nova plans to: the lines held at the last refusal, risen since. None: none learned."""
    lines = _cap.get("lines")
    if lines is None:
        return None
    now = time.time() if now is None else now
    risen = int(lines) + int(max(0.0, now - _cap["at"]) // IBKR_L1_CAP_RELAX_SEC) * IBKR_L1_CAP_RELAX_STEP
    if risen >= IBKR_L1_STREAM_BUDGET:
        _cap.clear()
        return None
    return risen


def on_ib_error(
    subs: dict[str, dict[str, Any]], req_id: int, code: int, message: str, now: float | None = None,
) -> str | None:
    """errorEvent hook: Error 101 on a live line's own request id marks it refused. The symbol, else None."""
    if int(code) not in IBKR_L1_REFUSED_CODES:
        return None
    hit = _req_symbol.get(req_id)
    if hit is None:
        return None
    symbol, generation = hit
    sub = subs.get(symbol)
    if generation != line_session.generation() or _line_req.get(symbol) != req_id or sub is None:
        return None  # an earlier request of the symbol, or one of an ended session
    if sub.get("refused"):
        return None
    now = time.time() if now is None else now
    count, last = _streak.get(symbol, (0, 0.0))
    count = count + 1 if now - last <= IBKR_L1_REFUSED_RESET_SEC else 1
    _streak[symbol] = (count, now)
    wait = IBKR_L1_REFUSED_RETRY_SEC[min(count, len(IBKR_L1_REFUSED_RETRY_SEC)) - 1]
    sub["refused"] = {
        "at": now, "code": int(code), "message": (message or "").strip() or f"IB error {code}",
        "req_id": req_id, "refusals": count, "retry_at": now + wait,
    }
    held = open_count(subs)
    # Requests sent together are answered together: within a burst the cap is the fewest held.
    prior = _cap.get("lines")
    burst = prior is not None and now - _cap["at"] < IBKR_L1_CAP_RELAX_SEC
    _cap["lines"] = float(min(held, int(prior)) if burst and prior is not None else held)
    _cap["at"] = now
    logger.warning(
        "IBKR ticks: IBKR refused %s's L1 line (reqId %s, Error %s: %s) with %d of Nova's lines open "
        "-- not counted as open; asking again in %.0fs (refused %d time(s) in a row)",
        symbol, req_id, code, sub["refused"]["message"], held, wait, count,
    )
    return symbol


def install_error_hook(ib: Any, subs: Callable[[], dict[str, dict[str, Any]]]) -> None:
    """Hear ``ib``'s errors once per IB object; ``subs`` reads the Level 1 lines (``ibkr.ticks._subs``)."""
    if id(ib) in _hooked_ib_ids or not hasattr(ib, "errorEvent"):
        return

    def _on_error(reqId: int, errorCode: int, errorString: str, contract: Any = None) -> None:
        on_ib_error(subs(), reqId, errorCode, errorString)

    ib.errorEvent += _on_error
    _hooked_ib_ids.add(id(ib))


def _owner_rank(sub: dict[str, Any]) -> int:
    return min((_OWNER_RANK.get(str(o), 2) for o in (sub.get("owners") or ())), default=2)


def due(subs: dict[str, dict[str, Any]], now: float | None = None) -> list[str]:
    """Refused lines to ask for again now: their wait is over and Nova holds fewer lines than the cap."""
    now = time.time() if now is None else now
    ready = [
        (_owner_rank(sub), sub["refused"]["at"], sym)
        for sym, sub in list(subs.items())
        if sub.get("refused") and sub["refused"]["retry_at"] <= now
    ]
    cap = ceiling(now)
    room = len(ready) if cap is None else max(0, cap - open_count(subs))
    return [sym for _rank, _at, sym in sorted(ready)[:room]]


def plan_budget(subs: dict[str, dict[str, Any]], planned_owners: set[str], now: float | None = None) -> int:
    """The scanner planner's budget: within the learned cap, less the open lines no planned owner holds."""
    from ibkr.scanner_l1_plan import budget_for_streams

    others = sum(
        1 for sub in list(subs.values())
        if not sub.get("refused") and not (set(sub.get("owners") or ()) & planned_owners)
    )
    return budget_for_streams(ceiling(now), others)


def rerequest(ib: Any, symbol: str, sub: dict[str, Any], now: float | None = None) -> bool:
    """Ask IBKR again for a refused line, in place: its owners and handler stay."""
    from ibkr.ticks_generic import reattach_handler

    contract = sub.get("contract")
    if ib is None or contract is None:
        return False
    forget_request(ib, contract)
    try:
        ticker = ib.reqMktData(contract, sub.get("generic_ticks") or "", False, False)
    except Exception as exc:
        now = time.time() if now is None else now
        sub["refused"]["retry_at"] = now + IBKR_L1_REFUSED_RETRY_SEC[-1]
        logger.warning("IBKR ticks: asking again for %s's refused L1 line failed: %s", symbol, exc)
        return False
    reattach_handler(symbol, sub, ticker)
    sub["ticker"] = ticker
    refusals = sub.pop("refused", {}).get("refusals")
    note_opened(symbol, ib, contract)
    logger.info("IBKR ticks: asked IBKR again for %s's L1 line (refused %s time(s) in a row)", symbol, refusals)
    return True


def view(subs: dict[str, dict[str, Any]], now: float | None = None) -> dict[str, Any]:
    """The refused lines (oldest first), the cap Nova plans to and the lines it holds."""
    now = time.time() if now is None else now
    refused = sorted(
        (
            {
                "symbol": sym, "at": sub["refused"]["at"], "code": sub["refused"]["code"],
                "message": sub["refused"]["message"], "retry_at": sub["refused"]["retry_at"],
                "refusals": sub["refused"]["refusals"], "owners": sorted(sub.get("owners") or ()),
            }
            for sym, sub in list(subs.items())
            if sub.get("refused")
        ),
        key=lambda row: row["at"],
    )
    return {"refused": refused, "cap": ceiling(now), "open": open_count(subs)}


def error_text(state: dict[str, Any]) -> str | None:
    """The refusal in words for the scanner subscription's error, else None."""
    refused = state.get("refused") or []
    if not refused:
        return None
    cap = state.get("cap")
    names = ", ".join(row["symbol"] for row in refused[:8]) + (" ..." if len(refused) > 8 else "")
    return (
        f"IBKR refused {len(refused)} Level 1 line(s) at its line cap (Error 101: {names}); the cap counts "
        f"this login's other IBKR platforms too. Nova holds {state.get('open')}"
        + (f" and plans to {cap}" if cap is not None else "")
        + " and asks again as lines free up"
    )
