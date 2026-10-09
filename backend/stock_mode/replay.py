"""Stock mode on a Sim replay (ADR 052 amendment, #815): Auto-entry, Approve and "Nova takes the exit" go back with
the playhead, as Nova's bot does (``bot.replay_desk``).

On the Sim desk off its live edge with a replay loaded, the stock-mode runner hears the Sim eyes' triggers and
runs on the playhead's clock. What it sends there is the replay's:

- **The replay's rows.** A trade or approval made on a replay carries its key (``replay_key``) and is kept apart
  from the live edge's, in memory only (``stock_mode.store``): the scratch account it trades on does not survive
  a restart either. It is acted on only while the desk shows that replay; one made at the live edge waits while
  the desk replays (``waits``).
- **Back with the playhead.** The runner checkpoints the replay's trades, approvals and entries whenever they
  change, stamped with the playhead -- at the end of each tick and after each of the operator's acts. When the
  playhead goes back (the scratch account unwinds and says so through ``bot.rewind``, or the runner sees the
  playhead earlier than before), they return to what they were at the new playhead (``follow``): a trade sent
  later never happened, an approval made later was never made, a fill later is not filled. An order of a
  replay trade the ledger still holds but the restored trades do not know is cancelled (``orphans``). The
  switch is the operator's setting, like Activate: it does not go back. A trade made at the live edge is never
  touched.
- **Another replay** starts the scratch account over: the old replay's trades and approvals go with it.
- **The replay's day.** Auto-entry's and Approve's entries on a replay are this run's -- sent before the
  playhead, a miss given back (``today``) -- and ``bot.entry_rules.today`` adds them to the bot's.
- **A new run tag** after every rewind goes into the stock-mode idempotency keys (``run_tag``), so an approved
  setup the playhead plays across again is sent again instead of answered from the old receipt.

Owner: this module (process memory only; invalidation: the loaded replay's key -- another replay starts it over
-- and every rewind). Reads the Sim's state through ``bot.replay_desk``; writes only the store's replay rows.
"""
from __future__ import annotations

import copy
import hashlib
import logging
import threading
from typing import Any

from stock_mode import store

logger = logging.getLogger(__name__)

_EPS = 1e-6
_BACK_SEC = 0.5                  # the playhead earlier than this is a rewind the runner saw itself
_ORDER_KEYS = ("entry_order_id", "target_order_id", "stop_order_id")


class _Run:
    """One replay's memory: the stock-mode rows by playhead."""

    def __init__(self, key: list) -> None:
        self.key = list(key)
        self.generation = 0
        self.entries: list[dict[str, Any]] = []        # {ts, symbol, setup_type, setup_id, order_id, by, missed_ts}
        self.base: dict[str, Any] = {}
        self.checkpoints: list[tuple[float, dict[str, Any]]] = []
        self.pending_low: float | None = None
        self.seen: float | None = None


_lock = threading.Lock()
_run: _Run | None = None


def here() -> list | None:
    """The loaded replay the desk shows (its key), else None."""
    from bot.replay_desk import desk

    got = desk()
    return list(got["key"]) if got is not None else None


def label(key: Any) -> str:
    from bot.replay_desk import label as replay_label

    return replay_label(list(key) if key else None)


def _state(run: _Run) -> dict[str, Any]:
    return {"trades": store.replay_trades(run.key), "approvals": store.replay_approvals(run.key),
            "entries": copy.deepcopy(run.entries)}


def _ids(trades: dict[str, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Every order id the trades hold, with the trade that holds it."""
    out: dict[int, dict[str, Any]] = {}
    for trade in trades.values():
        for k in _ORDER_KEYS:
            if trade.get(k):
                out[int(trade[k])] = trade
    return out


def follow(now: float) -> dict[str, Any]:
    """Called first on each runner tick: keep the run on the replay the desk shows, and take back what a rewind
    undid. Returns ``{retired, restored_to, changed, orphans: [(order_id, trade)]}`` for the runner to say and to
    cancel. Never raises past a logged warning: time travel must not stop the runner's loop."""
    global _run
    out: dict[str, Any] = {"retired": [], "restored_to": None, "changed": [], "orphans": [], "key": None}
    key = here()
    if key is None:
        return out                       # the live edge or another venue: the run waits as it stood
    with _lock:
        run = _run
        if run is None or run.key != key:
            out["retired"] = store.drop_replays(keep=key)
            out["key"] = run.key if run is not None else None
            run = _run = _Run(key)
            run.base = _state(run)
            run.seen = now
            return out
        if run.seen is not None and now < run.seen - _BACK_SEC:
            run.pending_low = now if run.pending_low is None else min(run.pending_low, now)
        low, run.pending_low = run.pending_low, None
        if low is None:
            run.seen = now if run.seen is None else max(run.seen, now)
            return out
        before = _state(run)
        dropped = [s for t, s in run.checkpoints if t > low + _EPS]
        run.checkpoints = [(t, s) for t, s in run.checkpoints if t <= low + _EPS]
        state = run.checkpoints[-1][1] if run.checkpoints else run.base
        store.restore_replay(run.key, state["trades"], state["approvals"])
        run.entries = copy.deepcopy(state["entries"])
        run.generation += 1
        run.seen = now
        held = _ids(state["trades"])
        later: dict[int, dict[str, Any]] = {}
        for s in [before, *dropped]:
            later.update(_ids(s["trades"]))
        out["restored_to"] = low
        out["orphans"] = sorted(((oid, t) for oid, t in later.items() if oid not in held), key=lambda x: x[0])
        syms = set(before["trades"]) | set(before["approvals"]) | set(state["trades"]) | set(state["approvals"])
        out["changed"] = sorted(s for s in syms if before["trades"].get(s) != state["trades"].get(s)
                                or before["approvals"].get(s) != state["approvals"].get(s))
        return out


def rewound(playhead_ts: float) -> None:
    """The scratch account unwound to ``playhead_ts`` (``bot.rewind``): the next tick takes back what stock mode
    remembered after it. Any thread; never raises."""
    with _lock:
        run = _run
        if run is None:
            return
        low = float(playhead_ts)
        run.pending_low = low if run.pending_low is None else min(run.pending_low, low)


def checkpoint(now: float) -> None:
    """Remember the replay's rows at the playhead when they changed: at the end of each tick on a replay, and
    after each of the operator's acts there. Skipped while a rewind waits to be taken back."""
    with _lock:
        run = _run
        if run is None or run.pending_low is not None or here() != run.key:
            return
        state = _state(run)
        last = run.checkpoints[-1][1] if run.checkpoints else run.base
        if state != last:
            run.checkpoints.append((float(now), state))


def run_tag() -> str:
    """The replay run's part of a stock-mode idempotency key (``""`` off a replay): the replay and its rewinds."""
    with _lock:
        run = _run
        if run is None or here() != run.key:
            return ""
        digest = hashlib.sha1(repr(run.key).encode("utf-8")).hexdigest()[:10]
        return f"{digest}.{run.generation}:"


def waits(trade: dict[str, Any], replay_desk: bool) -> str | None:
    """Why the runner does not manage a Sim ``trade`` now (None: manage it): it was made on a replay the desk does
    not show, or at the live edge while the desk replays (``replay_desk``)."""
    made = trade.get("replay_key")
    key = here() if replay_desk else None
    if made and key is None:
        return f"the trade is on the {label(made)} replay: it waits until the desk is back on that replay"
    if made and list(made) != key:
        return f"the trade is on the {label(made)} replay, not the one loaded"
    if not made and replay_desk:
        return "the trade is on Sim's live edge: it waits until the desk follows the wall clock again"
    return None


# -- the replay's day ------------------------------------------------------------------
def note_entry(trade: dict[str, Any], ts: float) -> None:
    """An Auto-entry or an approved bracket sent on the replay (``by``: the trade's kind)."""
    with _lock:
        if _run is not None and list(trade.get("replay_key") or []) == _run.key:
            _run.entries.append({"ts": float(ts), "symbol": trade.get("symbol"), "setup_type": trade.get("setup_type"),
                                 "setup_id": trade.get("setup_id"), "order_id": trade.get("entry_order_id"),
                                 "by": trade.get("kind"), "missed_ts": None})


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
    """``{count, entries, approved}``: Auto-entry's entries on the loaded replay before ``now`` (the playhead), a
    miss given back, and the approved brackets sent (counted, never capped)."""
    with _lock:
        rows = list(_run.entries) if _run is not None and here() == _run.key else []
    out, approved = [], 0
    for e in rows:
        if e["ts"] > now + _EPS:
            continue
        if e["by"] == "approve":
            approved += 1
            continue
        missed = e["missed_ts"] is not None and e["missed_ts"] <= now + _EPS
        out.append({"symbol": e["symbol"], "setup_type": e["setup_type"], "by": e["by"], "ts": e["ts"],
                    "outcome": "missed" if missed else "sent"})
    return {"count": sum(1 for e in out if e["outcome"] != "missed"), "entries": out, "approved": approved}


def reset_for_tests() -> None:
    global _run
    with _lock:
        _run = None
