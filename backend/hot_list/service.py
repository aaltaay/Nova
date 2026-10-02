"""Today's hot list, changed (ADR 043): every write goes through here, under one lock.

``today`` is the list a write starts from. When the file belongs to an earlier day it rolls over first:
the old day is kept as its day copy, its names become ``yesterday`` (``store.roll``), every Nova Buy left
from it is cleared (``nova_buys.clear_all``, at most once a day per process) with a ``hot_list`` audit
line ``{event: "rollover", cleared}``, and today's list is written. ``peek`` is the same list for a
reader, rolled in memory only. A file that cannot be read refuses every write (``HOT_LIST_UNREADABLE``),
and so does one that cannot be written.

Every change is a ``hot_list`` line on the bot's audit stream, ``inputs: {event, symbol?, ...}`` (events
in ``constants_hot_list``), so the triggers audit can tell what the list held at any moment.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from constants_hot_list import (
    HOT_LIST_AUDIT_ACTION,
    HOT_LIST_AUTO_N_CHOICES,
    HOT_LIST_BY_BRING_BACK,
    HOT_LIST_CAP,
    HOT_LIST_EVENT_AUTO,
    HOT_LIST_EVENT_REMOVE,
    HOT_LIST_EVENT_ROLLOVER,
    HOT_LIST_EVENT_SETTINGS,
    HOT_LIST_EVENT_STAR,
    HOT_LIST_FULL,
    HOT_LIST_HOW_STAR,
    HOT_LIST_INVALID,
    HOT_LIST_SIDES,
    HOT_LIST_UNREADABLE,
)
from hot_list import store
from hot_list.errors import HotListError

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_cleared_for: str | None = None      # the day whose rollover already cleared yesterday's Nova Buys


def listed(doc: dict[str, Any]) -> list[str]:
    return [str(e["symbol"]) for e in doc.get("entries") or []]


def peek(now: float | None = None) -> tuple[dict[str, Any], str | None]:
    """Today's list for a reader: the file, rolled over in memory when it is an earlier day's; never writes."""
    day = store.trading_day(now)
    doc, error = store.read_raw()
    if error is not None:
        return store.empty(day), error
    if doc is None or doc.get("date") == day:
        return doc or store.empty(day), None
    return store.roll(doc, day), None


def _save(doc: dict[str, Any]) -> None:
    try:
        store.save(doc)
    except OSError as exc:
        logger.exception("hot list: today's list could not be written")
        raise HotListError(HOT_LIST_UNREADABLE, f"today's hot list could not be written ({exc}): nothing changed")\
            from exc


def today(now: float | None = None) -> dict[str, Any]:
    """Today's list for a write: rolled over first when the file is an earlier day's (see the module)."""
    global _cleared_for
    ts = time.time() if now is None else float(now)
    day = store.trading_day(ts)
    with _lock:
        doc, error = store.read_raw()
        if error is not None:
            raise HotListError(HOT_LIST_UNREADABLE, f"today's hot list cannot be read ({error}): nothing changes "
                                                    "until the file is fixed or removed")
        if doc is not None and doc.get("date") == day:
            return doc
        fresh = store.roll(doc, day)
        cleared: list[dict[str, Any]] = []
        clear_error = archive_error = None
        if doc is not None:
            if str(doc["date"]) > day:
                logger.warning("hot list: the file is dated %s, after today (%s) -- the clock moved back; "
                               "nothing is cleared", doc["date"], day)
            elif _cleared_for != day:
                from hot_list import nova_buys

                cleared, clear_error = nova_buys.clear_all(ts)
                _cleared_for = day
            archive_error = store.archive(doc)
        _save(fresh)
    if doc is not None:
        _wake()
        _audit(HOT_LIST_EVENT_ROLLOVER,
               f"today's hot list started fresh ({day}); {len(cleared)} Nova Buy side(s) left from {doc['date']} "
               "cleared -- trades Nova holds keep their exits",
               {"from": doc["date"], "to": day, "cleared": cleared, "yesterday": fresh["yesterday"],
                "error": clear_error or archive_error})
    return fresh


def _wake() -> None:
    """The listed names changed: wake the L1 reconcile now, which rebuilds HOD Momo's active set from the list
    (``ibkr_bridge.refresh_hod_active_set``), so a listed name gets its line without waiting for a roster."""
    try:
        from ibkr import scanner_l1

        scanner_l1.request_reconcile()
    except Exception:
        logger.warning("hot list: the L1 reconcile was not woken -- its next pass follows the list", exc_info=True)


def _audit(event: str, reason: str, inputs: dict[str, Any]) -> None:
    try:
        from bot.audit import record

        record(action=HOT_LIST_AUDIT_ACTION, outcome=event, reason=reason, inputs={"event": event, **inputs})
    except Exception:
        logger.warning("hot list: the %s line was not written to the audit stream", event, exc_info=True)


def _entry(sym: str, how: str, now: float, *, board: str | None = None, rank: int | None = None,
           change_pct: float | None = None) -> dict[str, Any]:
    return {"symbol": sym, "how": how, "at": round(float(now), 3), "board": board, "rank": rank,
            "change_pct": change_pct}


def _full(sym: str) -> HotListError:
    return HotListError(HOT_LIST_FULL, f"today's hot list is full ({HOT_LIST_CAP} stocks): take one off before adding "
                                       f"{sym}", field="symbol")


def symbol(raw: Any) -> str:
    sym = store.valid_symbol(raw)
    if sym is None:
        raise HotListError(HOT_LIST_INVALID, "a ticker: a letter, then up to 11 letters, digits, '.', '/' or '-'",
                           status=400, field="symbol")
    return sym


def star(raw: Any, *, by: str, now: float | None = None) -> bool:
    """Star a stock onto today's list. True when it was added; False when it was listed already."""
    ts = time.time() if now is None else float(now)
    sym = symbol(raw)
    with _lock:
        doc = today(ts)
        if sym in listed(doc):
            return False
        if len(doc["entries"]) >= HOT_LIST_CAP:
            raise _full(sym)
        doc["entries"].append(_entry(sym, HOT_LIST_HOW_STAR, ts))
        _save(doc)
    _wake()
    _audit(HOT_LIST_EVENT_STAR, f"{sym} starred onto today's hot list", {"symbol": sym, "by": by})
    return True


def add_auto(entries: list[dict[str, Any]], *, now: float | None = None) -> list[str]:
    """The auto feed's picks (``auto.pick``): each name not listed yet, never past the cap. The names added."""
    ts = time.time() if now is None else float(now)
    added: list[dict[str, Any]] = []
    with _lock:
        doc = today(ts)
        have = set(listed(doc))
        for entry in entries:
            if len(doc["entries"]) >= HOT_LIST_CAP:
                break
            if entry["symbol"] in have:
                continue
            doc["entries"].append(entry)
            have.add(entry["symbol"])
            added.append(entry)
        if added:
            _save(doc)
    if added:
        _wake()
    for entry in added:
        _audit(HOT_LIST_EVENT_AUTO, f"{entry['symbol']} led the Gainers board (rank {entry.get('rank')}): on today's "
               "hot list for the day", {k: entry.get(k) for k in ("symbol", "rank", "change_pct", "board")})
    return [e["symbol"] for e in added]


def remove(sym: str, *, now: float | None = None) -> bool:
    """Take a stock off today's list (its Who trades side is the caller's). True when it was listed."""
    ts = time.time() if now is None else float(now)
    with _lock:
        doc = today(ts)
        kept = [e for e in doc["entries"] if e["symbol"] != sym]
        if len(kept) == len(doc["entries"]):
            return False
        doc["entries"] = kept
        _save(doc)
    _wake()
    _audit(HOT_LIST_EVENT_REMOVE, f"{sym} taken off today's hot list", {"symbol": sym})
    return True


def settings(*, auto_n: Any = None, default_buy: Any = None, default_sell: Any = None,
             now: float | None = None) -> dict[str, Any]:
    """Change how many leaders the auto feed takes and the side a new name starts on."""
    if auto_n is not None and (isinstance(auto_n, bool) or auto_n not in HOT_LIST_AUTO_N_CHOICES):
        raise HotListError(HOT_LIST_INVALID, f"auto_n is one of {', '.join(map(str, HOT_LIST_AUTO_N_CHOICES))} "
                                             "(0 is off)", status=400, field="auto_n")
    for field, value in (("default_buy", default_buy), ("default_sell", default_sell)):
        if value is not None and value not in HOT_LIST_SIDES:
            raise HotListError(HOT_LIST_INVALID, f"{field} is 'you' or 'nova'", status=400, field=field)
    with _lock:
        doc = today(now)
        if auto_n is not None:
            doc["auto_n"] = int(auto_n)
        doc["default"] = {"buy": default_buy or doc["default"]["buy"], "sell": default_sell or doc["default"]["sell"]}
        _save(doc)
    _audit(HOT_LIST_EVENT_SETTINGS, f"auto top {doc['auto_n'] or 'off'}; new names start Buy {doc['default']['buy']} "
           f"· Sell {doc['default']['sell']}", {"auto_n": doc["auto_n"], "default": dict(doc["default"])})
    return doc


def bring_back(*, now: float | None = None) -> list[str]:
    """Star yesterday's names again -- those not listed, up to the cap. The names added; a list with no room
    for any of them refuses (``HOT_LIST_FULL``)."""
    ts = time.time() if now is None else float(now)
    with _lock:
        doc = today(ts)
        have = set(listed(doc))
        wanted = [s for s in doc.get("yesterday") or [] if s not in have]
        room = HOT_LIST_CAP - len(doc["entries"])
        if wanted and room <= 0:
            raise _full(wanted[0])
        added = wanted[:max(0, room)]
        if added:
            doc["entries"] += [_entry(sym, HOT_LIST_HOW_STAR, ts) for sym in added]
            _save(doc)
    if added:
        _wake()
    for sym in added:
        _audit(HOT_LIST_EVENT_STAR, f"{sym} brought back from yesterday's hot list",
               {"symbol": sym, "by": HOT_LIST_BY_BRING_BACK})
    return added


def reset_for_tests() -> None:
    global _cleared_for
    _cleared_for = None
    store.forget_cache_for_tests()
