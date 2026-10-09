"""Nova's bot on a Sim replay (ADR 052): which replay, its clock, and how the bot goes back with it.

On the Sim desk off its live edge with a replay loaded (``sim.practice.loaded``: a Session Record
or a historical window), Nova's bot trades like on Paper -- the same rules, the same bracket --
on the Sim scratch account, from the Sim eyes' triggers (``eyes.sim_eyes``). What changes is time:

- **The clock is the playhead** (``venue_now``): a trigger's age, the entry's working TTL, the
  time stop and every exit wait run on the Sim clock, which stands still while it is paused.
- **The replay's own day.** The day's entries on a replay are this run's -- the entries sent
  before the playhead on this replay -- never the audit stream's, which keeps lines a rewind
  took back and lines from another play of the same day (``today``).
- **Back with the playhead.** The bot checkpoints what it remembers -- its trade, its working
  orders, the shares it holds, the replay's entries -- whenever that changes, stamped with the
  playhead. When the playhead goes back (the scratch account unwinds and says so through
  ``bot.rewind``, or the bot sees the playhead earlier than before), the bot takes back
  what it remembered as it stood at the new playhead (``follow``): a trade sent later never
  happened, a fill later is not filled. Only this replay's part goes back -- its trade, its
  orders, its shares; a trade made elsewhere (Paper, the live edge, another replay) shares the
  session's one trade slot and is never touched. An order of its own the ledger still holds but
  the restored trade does not know (sent between two checkpoints) is cancelled (``orphans``).
- **Another replay** starts the scratch account over: the bot retires its trade on the old one.
  A trade remembered from a replay this process did not run (a restart: the scratch account does
  not survive one) is retired with that reason.
- **A new run tag** after every rewind goes into the bot's idempotency keys (``run_tag``), so a
  setup the playhead plays across again is sent again instead of answered from the old receipt.

Owner: this module (process memory only, like the scratch account it follows; invalidation:
the loaded replay's key -- another replay, or none, starts it over -- and every rewind). Reads
the Sim's state; writes only the bot session row it is handed.
"""
from __future__ import annotations

import copy
import hashlib
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_EPS = 1e-6
_BACK_SEC = 0.5                 # the playhead earlier than this is a rewind the bot saw itself
_ROW_KEYS = ("trade", "working", "bot_qty")
_TRADE_ORDER_KEYS = ("entry_order_id", "target_order_id", "stop_order_id", "exit_order_id")
LIVE_STATES = frozenset({"entering", "open", "exiting"})
STATE_REWOUND = "rewound"


class _Run:
    """One replay's memory: what the bot remembered, by playhead."""

    def __init__(self, key: list, base: dict[str, Any]):
        self.key = key
        self.generation = 0
        self.base = base                                    # the bot's state when this replay began
        self.checkpoints: list[tuple[float, dict[str, Any]]] = []
        self.entries: list[dict[str, Any]] = []             # {ts, symbol, setup_type, setup_id, order_id, missed_ts}
        self.pending_low: float | None = None
        self.seen: float | None = None                      # the furthest playhead the bot has run at
        self.owned: set[int] = set()                        # order ids of this replay's trades


_lock = threading.Lock()
_run: _Run | None = None


# -- which replay, and its clock -------------------------------------------------------------
def desk() -> dict[str, Any] | None:
    """The replay the Sim desk trades now: ``{key, symbol, kind}``; None at the live edge, on another
    venue, or with nothing loaded. An unreadable desk is no replay (the venue gate refuses it)."""
    try:
        from sim.mode import is_replay_desk

        if not is_replay_desk():
            return None
        from sim import practice

        loaded = practice.loaded()
    except Exception:
        logger.warning("bot: the Sim replay could not be read", exc_info=True)
        return None
    if loaded is None:
        return None
    return {"key": list(loaded.key), "symbol": str(loaded.symbol).upper(), "kind": loaded.source}


def label(key: list | None) -> str:
    """``AMOD 2026-10-02`` for a replay key."""
    if not key:
        return "a replay"
    return " ".join(str(k) for k in key[1:3] if k)


def venue_now() -> float:
    """The bot's clock: the Sim playhead on the Sim venue (at its live edge it is the wall clock), else
    the wall clock. An unreadable venue is the wall clock."""
    try:
        from sim.mode import venue

        if venue() == "sim":
            from sim import session_clock

            return session_clock.now_et().timestamp()
    except Exception:
        logger.warning("bot: the venue clock could not be read -- the wall clock stands in", exc_info=True)
    return time.time()


def audit_stamp() -> dict[str, Any] | None:
    """``{key, playhead_ts}`` for a bot audit line written on a replay; None off one. Never raises."""
    here = desk()
    if here is None:
        return None
    return {"key": here["key"], "playhead_ts": venue_now()}


def run_tag() -> str:
    """The replay run's part of an idempotency key (``""`` off a replay): the replay and its rewinds."""
    with _lock:
        run = _run
        if run is None or desk() is None:
            return ""
        digest = hashlib.sha1(repr(run.key).encode("utf-8")).hexdigest()[:10]
        return f"{digest}.{run.generation}:"


# -- the run ---------------------------------------------------------------------------------
def _state(row: dict[str, Any], run: _Run | None) -> dict[str, Any]:
    out = {k: copy.deepcopy(row.get(k)) for k in _ROW_KEYS}
    out["entries"] = copy.deepcopy(run.entries) if run is not None else []
    return out


def _ours(trade: Any, run: _Run) -> bool:
    return isinstance(trade, dict) and bool(trade.get("replay_key")) and list(trade["replay_key"]) == run.key


def _live(trade: Any) -> bool:
    return isinstance(trade, dict) and trade.get("state") in LIVE_STATES


def _signed_held(trade: Any) -> float:
    """The shares a trade holds by the bot's count (``bot_qty``): long positive, short negative, 0 unless open."""
    if not isinstance(trade, dict) or trade.get("state") not in ("open", "exiting"):
        return 0.0
    qty = float(trade.get("qty") or 0)
    return -qty if trade.get("side") == "short" else qty


def _own(run: _Run, *trades: Any) -> None:
    for trade in trades:
        if _ours(trade, run):
            run.owned |= _trade_ids(trade)


def _put(row: dict[str, Any], state: dict[str, Any], run: _Run) -> None:
    """Take this replay's part of ``row`` back to ``state``: its trade, its working orders, its shares and its day.
    A live trade made elsewhere is never touched, and another venue's old trade is never brought back live."""
    cur, saved = row.get("trade"), state.get("trade")
    cur_ours, saved_ours = _ours(cur, run), _ours(saved, run)
    _own(run, cur, saved)
    if not (_live(cur) and not cur_ours):
        new = saved if saved_ours or not _live(saved) else (None if cur_ours else cur)
        if new is None:
            row.pop("trade", None)
        else:
            row["trade"] = copy.deepcopy(new)
    kept = [w for w in list(row.get("working") or []) if int(w.get("order_id") or 0) not in run.owned]
    back = [w for w in list(state.get("working") or []) if int(w.get("order_id") or 0) in run.owned]
    row["working"] = kept + copy.deepcopy(back)
    delta = (_signed_held(saved) if saved_ours else 0.0) - (_signed_held(cur) if cur_ours else 0.0)
    if abs(delta) > _EPS:
        sym = str(run.key[1]).upper()
        qty_map = dict(row.get("bot_qty") or {})
        qty_map[sym] = float(qty_map.get(sym) or 0) + delta
        if abs(qty_map[sym]) < _EPS:
            qty_map.pop(sym, None)
        row["bot_qty"] = qty_map
    run.entries = copy.deepcopy(state.get("entries") or [])


def _retire(row: dict[str, Any], why: str, now: float) -> dict[str, Any] | None:
    """A live trade from a replay this run did not make ends here: ``rewound``, its shares and working
    orders forgotten. Returns it (for the timeline), else None."""
    trade = row.get("trade")
    if not isinstance(trade, dict) or trade.get("state") not in LIVE_STATES or not trade.get("replay_key"):
        return None
    ids = {int(trade[k]) for k in _TRADE_ORDER_KEYS if trade.get(k)}
    row["working"] = [w for w in list(row.get("working") or []) if int(w.get("order_id") or 0) not in ids]
    if trade.get("state") in ("open", "exiting"):
        qty_map = dict(row.get("bot_qty") or {})
        sym = str(trade.get("symbol") or "").upper()
        held = float(trade.get("qty") or 0)
        qty_map[sym] = float(qty_map.get(sym) or 0) + (held if trade.get("side") == "short" else -held)
        if abs(qty_map[sym]) < _EPS:
            qty_map.pop(sym, None)
        row["bot_qty"] = qty_map
    trade = {**trade, "state": STATE_REWOUND, "closed_ts": now, "note": why}
    row["trade"] = trade
    return trade


def follow(row: dict[str, Any], now: float) -> dict[str, Any]:
    """Called first on each bot tick: keep the run on the replay the desk shows, and take back what a
    rewind undid. Returns ``{retired, restored_to, orphans}`` for the runner to say and to cancel.
    Changes ``row`` (the caller saves it) and never raises: time travel must not stop the bot's loop."""
    global _run
    out: dict[str, Any] = {"retired": None, "restored_to": None, "orphans": []}
    here = desk()
    if here is None:
        return out                       # the live edge or another venue: the run waits as it stood
    with _lock:
        run = _run
        if run is None or run.key != here["key"]:
            # Another replay started the scratch account over; with no run, the account this process had is gone.
            why = (f"another replay was loaded: the {label(run.key)} scratch account started over" if run is not None
                   else "the Sim scratch account this trade was on is gone (it does not survive a restart)")
            out["retired"] = _retire(row, why, now)
            run = _run = _Run(here["key"], _state(row, None))
            run.seen = now
            return out
        if run.seen is not None and now < run.seen - _BACK_SEC:
            run.pending_low = now if run.pending_low is None else min(run.pending_low, now)
        low, run.pending_low = run.pending_low, None
        if low is None:
            run.seen = now if run.seen is None else max(run.seen, now)
            return out
        before = _trade_ids(row.get("trade")) if _ours(row.get("trade"), run) else set()
        dropped = [s for t, s in run.checkpoints if t > low + _EPS]
        run.checkpoints = [(t, s) for t, s in run.checkpoints if t <= low + _EPS]
        state = run.checkpoints[-1][1] if run.checkpoints else run.base
        _put(row, state, run)
        run.generation += 1
        run.seen = now
        kept = _trade_ids(row.get("trade"))
        out["restored_to"] = low
        later = {i for s in dropped if _ours(s.get("trade"), run) for i in _trade_ids(s.get("trade"))}
        out["orphans"] = sorted((before | later) - kept)
        return out


def _trade_ids(trade: Any) -> set[int]:
    if not isinstance(trade, dict):
        return set()
    return {int(trade[k]) for k in _TRADE_ORDER_KEYS if trade.get(k)}


def rewound(playhead_ts: float) -> None:
    """The scratch account unwound to ``playhead_ts`` (``bot.rewind``): the next tick takes back what the bot
    remembered after it. Any thread; never raises."""
    with _lock:
        run = _run
        if run is None:
            return
        low = float(playhead_ts)
        run.pending_low = low if run.pending_low is None else min(run.pending_low, low)


def checkpoint(row: dict[str, Any], now: float) -> None:
    """Called last on each bot tick on a replay: remember the bot's state at the playhead when it changed.
    Skipped while a rewind waits to be taken back (this tick read a ledger that no longer stands)."""
    with _lock:
        run = _run
        here = desk()
        if run is None or here is None or run.key != here["key"] or run.pending_low is not None:
            return
        state = _state(row, run)
        last = run.checkpoints[-1][1] if run.checkpoints else run.base
        if state == last:
            return
        _own(run, state.get("trade"))
        run.checkpoints.append((float(now), state))


def on_replay(trade: dict[str, Any] | None) -> bool:
    """The trade was made on a replay (it waits whenever the desk is not on that replay)."""
    return bool(isinstance(trade, dict) and trade.get("replay_key"))


def waits(trade: dict[str, Any]) -> str | None:
    """Why the bot does not manage ``trade`` now: it was made on another replay, or on a replay while the desk
    is at the live edge, or at the live edge while the desk replays. None: manage it."""
    here = desk()
    made = trade.get("replay_key")
    if here is None and made:
        return f"the trade is on the {label(made)} replay: it waits until the desk is back on that replay"
    if here is not None and not made:
        return "the trade is on Sim's live edge: it waits until the desk follows the wall clock again"
    if here is not None and made and list(made) != here["key"]:
        return f"the trade is on the {label(made)} replay, not the one loaded"
    return None


# -- the replay's day -------------------------------------------------------------------------
def note_entry(trade: dict[str, Any], ts: float) -> None:
    with _lock:
        if _run is not None:
            _run.entries.append({"ts": float(ts), "symbol": trade.get("symbol"), "setup_type": trade.get("setup_type"),
                                 "setup_id": trade.get("setup_id"), "order_id": trade.get("entry_order_id"),
                                 "missed_ts": None})


def note_missed(trade: dict[str, Any], ts: float) -> None:
    """A miss gives the day back, as on Paper."""
    with _lock:
        if _run is None:
            return
        for e in reversed(_run.entries):
            if e["order_id"] == trade.get("entry_order_id") and e["missed_ts"] is None:
                e["missed_ts"] = float(ts)
                return


def today(now: float) -> dict[str, Any]:
    """``{count, entries}``: the bot's entries on this replay before ``now`` (the playhead), a miss given back."""
    with _lock:
        rows = list(_run.entries) if _run is not None else []
    out = []
    for e in rows:
        if e["ts"] > now + _EPS:
            continue
        missed = e["missed_ts"] is not None and e["missed_ts"] <= now + _EPS
        out.append({"symbol": e["symbol"], "setup_type": e["setup_type"], "by": "bot", "ts": e["ts"],
                    "outcome": "missed" if missed else "sent"})
    return {"count": sum(1 for e in out if e["outcome"] != "missed"), "entries": out}


# -- what the replay shows the bot ----------------------------------------------------------
def holds_book(symbol: str) -> bool:
    """On a replay the depth-line rule is met by the replay's own book: the loaded symbol, with recorded
    Level 2, a window's NBBO, or a book Nova recorded that day (``sim.history_depth``). An IBKR download
    has no bid or ask of its own."""
    here = desk()
    if here is None or here["symbol"] != (symbol or "").strip().upper():
        return False
    try:
        from sim import session_clock

        at = session_clock.now_et().timestamp()
        if here["kind"] == "capture":
            from sim import capture_player

            return capture_player.book_at(at) is not None
        from sim import history_depth, history_playback

        selected = history_playback.selected()
        if selected is not None and selected.quotes is not None and len(selected.quotes) > 0:
            return True
        return history_depth.book_at(here["symbol"], at) is not None
    except Exception:
        logger.warning("bot: the replay's book could not be read for %s -- it counts as none", symbol, exc_info=True)
        return False


def book_missing(symbol: str) -> str | None:
    """On a replay, why ``symbol`` has no book there (None off a replay: the live hint stands)."""
    here = desk()
    if here is None:
        return None
    sym = (symbol or "").strip().upper()
    if here["symbol"] != sym:
        return f"the Sim replay is {here['symbol']}: the bot trades only the loaded replay"
    if here["kind"] == "capture":
        return "the Session Record holds no Level 2 at the playhead"
    return "an IBKR download has no bid or ask: load the day from the Massive files for its NBBO"


def quote(symbol: str) -> dict[str, Any] | None:
    """``{last, bid, ask}`` of the loaded replay at the playhead -- what its practice orders fill against."""
    if desk() is None:
        return None
    from sim import practice

    ref = practice.reference((symbol or "").strip().upper())
    return {"last": ref.last, "bid": ref.bid, "ask": ref.ask}


def reset_for_tests() -> None:
    global _run
    with _lock:
        _run = None
