"""A switched-off trader's positions, handed to you (ADR 072 decisions 5-6, ``traders.md`` "Handed to you").

Turning Claude's or the brain's switch Off hands every position it holds then. A handed position stays handed until
that trader is flat in the stock on that venue, whatever the switch does after (the operator, 2026-11-13): you may
close it, never add to it, and the trader may not open, add or close there (its own resting exits still fill).

The marks live in ``trader-handed.json`` in the operator cache, rewritten whole and atomically: ``{schema_version: 1,
handed: [{venue: "paper" | "sim", trader, symbol, at}]}``. Owner: this module. An entry ends when the trader's shares
there are flat on that venue; a Sim entry also ends when the Sim account resets (its shares are gone) or a rewind
goes back before ``at``. A missing or unreadable file reads empty and is logged; it is never guessed from the
switches. A retired bot's shares still open read as handed from Earlier bots without a mark (``earlier``).
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from constants_owners import AI_TRADERS, OWNER_EARLIER_BOTS
from constants_practice import PRACTICE_VENUE_PAPER, PRACTICE_VENUE_SIM
from constants_traders import TRADER_HANDED_FILE, TRADER_HANDED_SCHEMA_VERSION

logger = logging.getLogger(__name__)

_EPS = 1e-9
_lock = threading.Lock()
PRACTICE_VENUES = (PRACTICE_VENUE_PAPER, PRACTICE_VENUE_SIM)


def path() -> Path:
    from paths import cache_dir

    return cache_dir() / TRADER_HANDED_FILE


def _read() -> list[dict[str, Any]]:
    try:
        doc = json.loads(path().read_text(encoding="utf-8"))
    except FileNotFoundError:  # maintainer: allow-swallow no file means nothing was handed today
        return []
    except (OSError, ValueError):  # maintainer: allow-swallow logged; an unreadable file hands nothing
        logger.warning("TRADERS: %s is unreadable -- nothing reads as handed", path(), exc_info=True)
        return []
    if not isinstance(doc, dict) or doc.get("schema_version") != TRADER_HANDED_SCHEMA_VERSION:
        logger.warning("TRADERS: %s is not version %s -- nothing reads as handed", path(), TRADER_HANDED_SCHEMA_VERSION)
        return []
    rows = doc.get("handed") if isinstance(doc.get("handed"), list) else []
    return [r for r in rows if isinstance(r, dict) and r.get("trader") in AI_TRADERS and r.get("symbol")]


def _write(rows: list[dict[str, Any]]) -> None:
    from capture.manifest_io import write_json_atomic

    write_json_atomic(path(), {"schema_version": TRADER_HANDED_SCHEMA_VERSION, "handed": rows})


def entries() -> list[dict[str, Any]]:
    with _lock:
        return [dict(r) for r in _read()]


def hand(venue: str, trader: str, symbols: list[str], at: float) -> list[str]:
    """Mark ``trader``'s positions in ``symbols`` on ``venue`` handed to you; returns the symbols newly handed."""
    with _lock:
        rows = _read()
        have = {(r["venue"], r["trader"], r["symbol"]) for r in rows}
        new = [s.upper() for s in symbols if (venue, trader, s.upper()) not in have]
        if new:
            rows.extend({"venue": venue, "trader": trader, "symbol": s, "at": float(at)} for s in new)
            _write(rows)
    return new


def _live(row: dict[str, Any], owners: Any, now_ts: float | None) -> bool:
    """The entry still stands: its trader holds shares there, and on Sim the playhead is not back before it."""
    if owners is None or abs(owners.qty_of(row["symbol"], row["trader"])) < _EPS:
        return False
    return not (row["venue"] == PRACTICE_VENUE_SIM and now_ts is not None and now_ts < float(row.get("at") or 0.0))


def active(venue: str | None, ledger: Any, now_ts: float | None = None) -> dict[str, str]:
    """``{symbol: trader}`` handed to you on ``venue`` now -- each switched-off trader's position still held, and
    each stock a retired bot still holds (``earlier_bots``). Entries whose trader is flat there are dropped."""
    owners = getattr(ledger, "owners", None)
    if owners is None or venue is None:
        return {}
    out: dict[str, str] = {}
    from owners.whose import book_of

    for symbol, lots in owners.lots.items():
        if any(book_of(h) == OWNER_EARLIER_BOTS and abs(lot.qty) > _EPS for h, lot in lots.items()):
            out[symbol] = OWNER_EARLIER_BOTS
    with _lock:
        rows = _read()
        mine = [r for r in rows if r.get("venue") == venue]
        keep = [r for r in mine if _live(r, owners, now_ts)]
        flat = [r for r in mine if abs(owners.qty_of(r["symbol"], r["trader"])) < _EPS]
        if flat:
            # Flat ends the entry for good (a rewind before ``at`` only hides it while the playhead is there).
            _write([r for r in rows if r not in flat])
    for row in keep:
        out[str(row["symbol"]).upper()] = str(row["trader"])
    return out


def drop_venue(venue: str) -> None:
    """Every mark on ``venue`` ends (its account reset)."""
    with _lock:
        rows = _read()
        left = [r for r in rows if r.get("venue") != venue]
        if len(left) != len(rows):
            _write(left)


def held_by(ledger: Any, trader: str) -> list[str]:
    """The stocks ``trader`` holds shares in on ``ledger``."""
    owners = getattr(ledger, "owners", None)
    if owners is None:
        return []
    return sorted(sym for sym, lots in owners.lots.items()
                  if trader in lots and abs(lots[trader].qty) > _EPS)


def hand_held(trader: str, now: float | None = None) -> dict[str, list[str]]:
    """Hand every position ``trader`` holds on Paper and Sim to you, each marked at its venue's own clock (Sim's
    playhead, so a rewind before it ends the mark); returns ``{venue: symbols newly handed}``. Paper's account is
    loaded to look (it persists); a Sim this process has not loaded holds nothing to hand."""
    from practice.broker import for_venue, loaded

    out: dict[str, list[str]] = {}
    for venue in PRACTICE_VENUES:
        broker = for_venue(venue) if venue == PRACTICE_VENUE_PAPER else loaded(venue)
        if broker is None:
            continue
        symbols = held_by(broker.ledger, trader)
        if symbols:
            at = float(broker.reference.now_ts()) if now is None or venue == PRACTICE_VENUE_SIM else float(now)
            out[venue] = hand(venue, trader, symbols, at)
    return out
