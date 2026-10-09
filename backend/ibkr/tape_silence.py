"""A live tape line gone silent, said in words: dead, quiet or halted (#722).

2026-10-05 09:35:42 ET: the AllLast lines of SAIQ (a Trader tab) and VEEA (a Session Record)
stopped at the same arrival instant while both books kept updating, with no IBKR error and no farm
notice. SAIQ's Time & Sales sat on its last print under a LIVE badge until 09:41:14, and the
operator traded it blind: "time and sale is fully frozen". The lines were dead, not quiet: in the
silence the same stocks' Level 1 lines counted 1,381 and 1,645 RTVolume updates, 2.5M and 1.05M
shares (``archive.db`` ``l1_ticks`` against ``tape_ibkr``).

A reading is ``{schema_version: 2, state: "halted" | "dead" | "silent" | "quiet", since,
last_print_ts, book_at, l1_trade_ts, halted, pipeline, notice, text}`` (epoch seconds; each
``null`` when not known), or ``None`` while the tape prints:

* ``halted`` -- the symbol is halted now (``halt_status.halted_now``): a halt prints nothing, so
  this is never a dead line;
* ``dead`` -- no print for TAPE_SILENT_SEC while the symbol's Level 1 line reported a trade at
  least TAPE_DEAD_L1_LEAD_SEC after the last print, by IBKR's own clock (Last Timestamp, tick 45,
  or RTVolume's trade time, 233; ib_async writes AllLast prints into ``ticker.last`` but never
  into these): the tape missed trades, so its line is down;
* ``quiet`` -- no print for TAPE_SILENT_SEC and the Level 1 line, updating, reports no trade since
  either; or, with no Level 1 trade clock, the book is quiet too or there is no Level 2 line;
* ``silent`` -- no print for TAPE_SILENT_SEC while the Level 2 line delivered a book within
  TAPE_SILENT_BOOK_FRESH_SEC and no Level 1 trade clock can tell: the line may be down.

``pipeline`` names the other live tape lines whose last print arrived within TAPE_PIPELINE_SAME_SEC
of this one's and that have printed nothing since (not halted): one tick-by-tick event, not this
line alone. ``notice`` is the newest farm or line notice that something stopped
(``ibkr.farm_notices``) from IBKR_NOTICE_NEAR_SILENCE_SEC before the silence began.

The silence counts from the newest of the last print, the line's opening and the last moment the
symbol was seen halted (the caller keeps that one), so a reopening is not read as a dead line. A
reading asks IBKR for nothing. Each line that turns dead or silent is logged once and written to
the perf day file (``kind: "tape_silence"``), so the next incident can be held up against the
farm notices beside it.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from constants_tape import (
    TAPE_DEAD_L1_LEAD_SEC,
    TAPE_PIPELINE_SAME_SEC,
    TAPE_SILENT_BOOK_FRESH_SEC,
    TAPE_SILENT_SEC,
)

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
SCHEMA_VERSION = 2

HALTED = "halted"
DEAD = "dead"
SILENT = "silent"
QUIET = "quiet"

# The (state, since) last written per symbol: one record per silence, however many sockets ping.
_noted: dict[str, tuple[str, float]] = {}


def reset_for_tests() -> None:
    _noted.clear()


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def _clock(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S ET")


def l1_shows_trade_after(
    *,
    l1_trade_at: float | None,
    last_print_exchange_ts: float | None,
    last_print_ts: float | None,
    line_since: float | None,
    halt_seen_at: float | None = None,
) -> bool:
    """Did the Level 1 line report a trade after the tape's last print, its opening or the reopening? (pure)

    The print is compared by IBKR's second (``exchange_ts``) when known, the same clock as the Level 1
    trade times; the opening and the reopening are the desk's clock, which runs later than IBKR's
    stamps on the same trade, so that comparison errs towards "not dead".
    """
    trade = _num(l1_trade_at)
    if trade is None:
        return False
    anchor = max(_num(last_print_exchange_ts) or _num(last_print_ts) or 0.0, _num(line_since) or 0.0,
                 _num(halt_seen_at) or 0.0)
    return bool(anchor) and trade >= anchor + TAPE_DEAD_L1_LEAD_SEC


def read(
    *,
    now: float,
    last_print_ts: float | None,
    line_since: float | None,
    book_at: float | None,
    halted: bool | None,
    halt_seen_at: float | None = None,
    last_print_exchange_ts: float | None = None,
    l1_trade_at: float | None = None,
    l1_fresh: bool | None = None,
    pipeline: list[str] | tuple[str, ...] = (),
    notice: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """The line's silence now, or None while it prints (pure)."""
    last = _num(last_print_ts)
    since = max(last or 0.0, _num(line_since) or 0.0, _num(halt_seen_at) or 0.0)
    if not since:
        return None
    book = _num(book_at)
    trade = _num(l1_trade_at)
    no_print = f"No prints since {_clock(last)}" if last else "No prints since the line opened"
    if halted is True:
        state = HALTED
        text = f"Halted: no prints until it reopens. {no_print}."
    elif now - since < TAPE_SILENT_SEC:
        return None
    elif l1_shows_trade_after(l1_trade_at=trade, last_print_exchange_ts=last_print_exchange_ts,
                              last_print_ts=last, line_since=line_since, halt_seen_at=halt_seen_at):
        state = DEAD
        text = (f"{no_print} while Level 1 shows trades up to {_clock(trade)}: "
                "IBKR's tape line is down, not quiet.")
    elif trade is not None and l1_fresh:
        state = QUIET
        text = f"{no_print}, and Level 1 shows no trade since either: a quiet name."
    elif book is not None and now - book <= TAPE_SILENT_BOOK_FRESH_SEC:
        state = SILENT
        text = (f"{no_print} while Level 2 kept updating: IBKR's tape line may be down. "
                "A quiet name looks the same; this clears on the next print.")
    elif book is not None:
        state = QUIET
        text = f"{no_print}; Level 2 is quiet too."
    else:
        state = QUIET
        text = f"{no_print}; no Level 2 line to compare with."
    peers = sorted(pipeline) if state in (DEAD, SILENT) else []
    said = notice if state in (DEAD, SILENT) else None
    if peers:
        text += (f" {', '.join(peers)} stopped printing in the same second: one IBKR tick-by-tick "
                 "event, not this line alone.")
    if said:
        what = said.get("farm") or said.get("symbol") or said.get("message") or ""
        text += f" IBKR said {said.get('code')} ({str(said.get('notice', '')).replace('_', ' ')}"
        text += f" {what})" if what else ")"
        text += f" at {_clock(said['ts'])}."
    return {
        "schema_version": SCHEMA_VERSION,
        "state": state,
        "since": since,
        "last_print_ts": last,
        "book_at": book,
        "l1_trade_ts": trade,
        "halted": halted,
        "pipeline": peers,
        "notice": said,
        "text": text,
    }


def l1_trade_at(symbol: str) -> float | None:
    """IBKR's newest trade time on the symbol's Level 1 line (tick 45 or RTVolume), else None."""
    from ibkr import ticks
    from ibkr.l1_timestamp import epoch

    ticker = ticks.get_ticker(symbol)
    if ticker is None:
        return None
    stamps = [epoch(getattr(ticker, attr, None)) for attr in ("lastTimestamp", "rtTime")]
    stamps = [s for s in stamps if s is not None]
    return max(stamps) if stamps else None


def pipeline_peers(symbol: str, *, now: float | None = None) -> list[str]:
    """Other live tape lines silent since the same second as this one's last print, not halted."""
    from ibkr import halt_status, tape_stream
    from ibkr.tape_recording import producer_status

    sym = (symbol or "").strip().upper()
    mine = _num(producer_status(sym).get("last_print_ts"))
    if mine is None:
        return []
    peers = []
    for other in tape_stream.live_symbols():
        if other == sym:
            continue
        theirs = _num(producer_status(other).get("last_print_ts"))
        if theirs is not None and abs(theirs - mine) <= TAPE_PIPELINE_SAME_SEC:
            peers.append(other)
    if not peers:
        return []
    halted = halt_status.halted_now(peers, now=now)
    return sorted(p for p in peers if halted.get(p) is not True)


def witness(symbol: str, *, now: float, fresh_sec: float) -> dict[str, Any]:
    """``{trade_at, fresh, peers}`` for the recording keepalive (``capture.tape_watch``): the Level 1
    trade clock, whether that line updated within ``fresh_sec``, and the lines silent with this one."""
    from ibkr import ticks

    sym = (symbol or "").strip().upper()
    return {"trade_at": l1_trade_at(sym), "fresh": ticks.is_fresh(sym, fresh_sec),
            "peers": pipeline_peers(sym, now=now)}


def reading(symbol: str, *, now: float | None = None, halt_seen_at: float | None = None) -> dict[str, Any] | None:
    """``read`` for a live line from what Nova holds in memory: no IBKR request, no wait."""
    from constants_ibkr import IBKR_NOTICE_NEAR_SILENCE_SEC
    from ibkr import farm_notices, halt_status, ticks
    from ibkr.depth import state as depth_state
    from ibkr.tape_recording import producer_status

    sym = (symbol or "").strip().upper()
    ts = time.time() if now is None else float(now)
    producer = producer_status(sym)
    facts = {
        "now": ts,
        "last_print_ts": producer.get("last_print_ts"),
        "line_since": producer.get("line_since"),
        "last_print_exchange_ts": producer.get("last_print_exchange_ts"),
        "book_at": depth_state.last_book_at(sym),
        "halted": halt_status.halted_now([sym], now=ts).get(sym),
        "halt_seen_at": halt_seen_at,
        "l1_trade_at": l1_trade_at(sym),
        "l1_fresh": ticks.is_fresh(sym, TAPE_SILENT_BOOK_FRESH_SEC),
    }
    first = read(**facts)
    if first is None or first["state"] not in (DEAD, SILENT):
        return first
    out = read(**facts, pipeline=pipeline_peers(sym, now=ts),
               notice=farm_notices.trouble_since(first["since"], window=IBKR_NOTICE_NEAR_SILENCE_SEC))
    _note(sym, out, ts)
    return out


def _note(symbol: str, out: dict[str, Any], now: float) -> None:
    """Log and record a line that turned dead or silent, once per silence."""
    key = (out["state"], out["since"])
    if _noted.get(symbol) == key:
        return
    _noted[symbol] = key
    logger.warning("IBKR tape: %s's line reads %s -- %s", symbol, out["state"], out["text"])
    try:
        from constants_perf import PERF_SCHEMA_VERSION
        from perf import recorder

        recorder.persist({"schema_version": PERF_SCHEMA_VERSION, "kind": "tape_silence", "ts": round(now, 3),
                          "symbol": symbol, "reading": out})
    except Exception:
        logger.warning("IBKR tape: %s's silence not queued for the perf record", symbol, exc_info=True)
