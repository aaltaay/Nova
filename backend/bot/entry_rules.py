"""The rules a Nova automatic entry meets at Strategy (ADR 027, ADR 042): each setup's window,
the venue's daily cap, extended hours, and #564's commission hold.

Only entries (``BOT_ENTRY_KINDS``: a buy or a short) are gated; exits, cancels and protective sources never
are. The clock is the venue's (``execution.session_gate``: the replay playhead on Sim).

- **Windows.** Each setup at Strategy has its template in play's bot window
  (``bot_window_start`` / ``bot_window_end``; the template store clips it into the arming
  window and says so in ``Template.bot_window``). A template store that cannot be read keeps
  the material's 07:00-10:00, and the window says why.
- **One daily count** (ADR 042 E): Nova's automatic entries -- the bot's (and the localhost
  bot API's) buys and Auto-entry's -- share the venue sleeve's ``entries_per_day``. The count
  is folded from the persisted audit stream, so it survives a restart: an entry counts once
  it was sent, and a miss (``bot_trade`` / ``stock_mode`` ``missed``, nothing bought) gives
  the day back. Approve is the operator's own decision per trade: counted (``approved``) and
  shown, never capped. The day is the venue's ET date stamped on the line (``venue_day``),
  else the line's own ET date; a line written before the audit carried its venue counts on
  every venue. On a Sim replay the day is the replay's own run -- the entries sent before the
  playhead on it (``bot.replay_desk.today``, ADR 052) -- and a line written on a replay
  (``replay`` stamped) never counts anywhere else.
- **Extended hours**: with the sleeve's ``extended_hours`` off, entries wait for 09:30-16:00 ET.
- **#564**: every entry also passes ``bot.day_pnl.commission_hold`` (Live only).

Owner: this module (no state but a cache of the folded audit tail).
"""
from __future__ import annotations

import logging
from datetime import datetime, time as dtime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from bot.errors import BotError
from constants_bot import (
    BOT_AUDIT_ACTION_TRADE,
    BOT_ENTRY_KINDS,
    BOT_ENTRY_WINDOW_END_ET,
    BOT_ENTRY_WINDOW_START_ET,
    BOT_REASON_COMMISSIONS_UNKNOWN,
    BOT_REASON_DAY_TRADE_CAP,
    BOT_REASON_OUTSIDE_WINDOW,
    BOT_SKIP_EXTENDED_HOURS,
    BOT_TZ,
)

logger = logging.getLogger(__name__)
_ET = ZoneInfo(BOT_TZ)
_now_for_tests: Callable[[], datetime] | None = None
# The audit's tail as last folded: (signature, oldest timestamp read, whole file?, rows).
_tail: tuple[Any, float, bool, list[dict[str, Any]]] | None = None
_TAIL_BYTES = 256 * 1024
_STOCK_MODE = "stock_mode"


# -- the clock -------------------------------------------------------------------------
def venue_now() -> datetime:
    if _now_for_tests is not None:
        return _now_for_tests()
    from execution.session_gate import venue_now_et

    return venue_now_et()


def venue_day() -> str:
    return venue_now().date().isoformat()


def _hm(text: str) -> dtime:
    hour, minute = str(text).split(":")[:2]
    return dtime(int(hour), int(minute))


# -- windows ---------------------------------------------------------------------------
def window(setup: str, now: datetime | None = None) -> dict[str, Any]:
    """``{setup, start, end, open, clipped, template, error}`` -- the setup's template in play's bot window."""
    now = now or venue_now()
    out: dict[str, Any] = {"setup": setup, "start": BOT_ENTRY_WINDOW_START_ET, "end": BOT_ENTRY_WINDOW_END_ET,
                           "clipped": False, "template": None, "error": None}
    try:
        from setup_templates.store import get_store

        t = get_store().in_play(setup)
        v = t.values or {}
        bw = getattr(t, "bot_window", None)
        bw = bw if isinstance(bw, dict) else {}
        start = v.get("bot_window_start") or bw.get("start")
        end = v.get("bot_window_end") or bw.get("end")
        if start and end:
            out.update(start=str(start), end=str(end))
        out["clipped"] = bool(bw.get("clipped"))
        out["template"] = {"id": t.id, "rev": t.rev, "name": t.name}
    except Exception:
        logger.warning("bot entry rules: the %s template in play is unreadable -- keeping %s-%s", setup,
                       BOT_ENTRY_WINDOW_START_ET, BOT_ENTRY_WINDOW_END_ET, exc_info=True)
        out["error"] = "the template in play could not be read (the backend log has the error): the material's window applies"
    try:
        out["open"] = _hm(out["start"]) <= now.time() < _hm(out["end"])
    except (TypeError, ValueError):
        out["open"], out["error"] = False, f"the window {out['start']}-{out['end']} is unreadable"
    return out


def windows(setups: list[str], now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or venue_now()
    return [window(s, now) for s in setups]


def window_text(w: dict[str, Any]) -> str:
    name = str(w.get("setup") or "setup").replace("_", " ")
    clipped = " (clipped into its arming window)" if w.get("clipped") else ""
    return f"the {name} trades {w.get('start')}-{w.get('end')} ET{clipped}"


# -- extended hours --------------------------------------------------------------------
def regular_hours() -> bool:
    from execution.session_gate import regular_hours_now

    return bool(regular_hours_now())


def extended_hours_block(caps: dict[str, Any]) -> str | None:
    """Why an entry waits now for regular hours, else None."""
    if bool(caps.get("extended_hours")) or regular_hours():
        return None
    return ("outside 09:30-16:00 ET and the sleeve does not allow extended hours -- turn on extended hours "
            "in the sleeve to trade the premarket")


# -- the daily count -------------------------------------------------------------------
def _row_day(row: dict[str, Any]) -> str | None:
    day = (row.get("inputs") or {}).get("venue_day")
    if day:
        return str(day)
    ts = row.get("timestamp")
    if not isinstance(ts, (int, float)):
        return None
    return datetime.fromtimestamp(float(ts), _ET).date().isoformat()


def _row_venue(row: dict[str, Any]) -> str | None:
    return row.get("venue") or (row.get("inputs") or {}).get("venue")


def _audit_rows(day: str) -> list[dict[str, Any]]:
    """Every audit line from the start of ``day`` (ET) on: the file's tail, read back far enough."""
    global _tail
    from bot.persist import audit_signature, read_audit_tail

    sig = audit_signature()
    if sig is None:
        return []
    start = datetime.combine(datetime.fromisoformat(day).date(), dtime.min, _ET).timestamp()
    cached = _tail                       # one read of the cache: another thread may replace it
    if cached is not None and cached[0] == sig and (cached[2] or cached[1] < start):
        return cached[3]
    size = _TAIL_BYTES
    while True:
        rows, whole = read_audit_tail(size)
        oldest = next((float(r["timestamp"]) for r in rows if isinstance(r.get("timestamp"), (int, float))), None)
        if whole or (oldest is not None and oldest < start):
            break
        size *= 4
    _tail = (sig, oldest if oldest is not None else float("inf"), whole, rows)
    return rows


def audit_rows(day: str) -> list[dict[str, Any]]:
    """Every audit line from the start of ``day`` (ET, ``YYYY-MM-DD``) to the end of the file, oldest first
    (the triggers audit, ADR 044). A line before the day's start may come with them."""
    return _audit_rows(day)


def _entry_of(row: dict[str, Any]) -> dict[str, Any] | None:
    """A line that sent a Nova automatic entry (or an approved bracket): what it was, else None."""
    action, outcome, inputs = row.get("action"), row.get("outcome"), row.get("inputs") or {}
    if action in BOT_ENTRY_KINDS and outcome == "ok":
        by = "bot"
    elif action == _STOCK_MODE and outcome == "sent" and inputs.get("kind") in ("auto_entry", "approve"):
        by = str(inputs["kind"])
    else:
        return None
    return {"symbol": inputs.get("symbol"), "setup_type": inputs.get("setup_type"), "by": by,
            "ts": row.get("timestamp"), "outcome": "sent", "order_id": row.get("order_id"),
            "setup_id": inputs.get("setup_id")}


def _resolves(row: dict[str, Any]) -> tuple[str, Any, Any] | None:
    """``(outcome, order_id, setup_id)`` for a line that says how an entry ended, else None."""
    action, outcome, inputs = row.get("action"), row.get("outcome"), row.get("inputs") or {}
    if action == BOT_AUDIT_ACTION_TRADE and outcome in ("missed", "filled"):
        return str(outcome), row.get("order_id"), inputs.get("setup_id")
    if action == _STOCK_MODE and outcome in ("missed", "filled"):
        return str(outcome), row.get("order_id") or inputs.get("entry_order_id"), inputs.get("setup_id")
    return None


def fold(rows: list[dict[str, Any]], venue: str | None, day: str) -> dict[str, Any]:
    """``{count, entries, approved}`` from the audit lines of ``venue``'s ``day``."""
    sent: list[dict[str, Any]] = []
    approved = 0
    for row in rows:
        if _row_day(row) != day or _row_venue(row) not in (None, venue) or row.get("replay"):
            continue                # a replay's entries are its own run's (``bot.replay_desk.today``, ADR 052)
        entry = _entry_of(row)
        if entry is not None:
            if entry["by"] == "approve":
                approved += 1
            else:
                sent.append(entry)
            continue
        ended = _resolves(row)
        if ended is None:
            continue
        outcome, order_id, setup_id = ended
        for e in sent:
            same = (order_id is not None and e["order_id"] is not None and int(e["order_id"]) == int(order_id)) or \
                (order_id is None and setup_id and e["setup_id"] == setup_id)
            if same and e["outcome"] != "missed":
                e["outcome"] = "missed" if outcome == "missed" else "filled"
                break
        else:
            if outcome == "missed" and order_id is None and not setup_id:
                # A miss that names no order (written before misses carried it) gives one day back.
                for e in sent:
                    if e["outcome"] == "sent":
                        e["outcome"] = "missed"
                        break
    count = sum(1 for e in sent if e["outcome"] != "missed")
    entries = [{k: e[k] for k in ("symbol", "setup_type", "by", "ts", "outcome")} for e in sent]
    return {"count": count, "entries": entries, "approved": approved}


def today(venue: str | None = None, now: datetime | None = None, *, cap: int | None = None,
          rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """``{count, cap, venue_day, entries, approved}`` -- the venue's Nova automatic entries today."""
    from bot.gates import current_venue
    from bot.replay_desk import desk as replay_desk, today as replay_today

    at = now or venue_now()
    day = at.date().isoformat()
    here = current_venue() if venue is None else venue
    if rows is None and here == "sim" and replay_desk() is not None:
        folded = {**replay_today(at.timestamp()), "approved": 0}      # the replay's own run (ADR 052)
    else:
        folded = fold(_audit_rows(day) if rows is None else rows, here, day)
    if cap is None:
        cap = _cap()
    return {"count": folded["count"], "cap": int(cap), "venue_day": day, "entries": folded["entries"],
            "approved": folded["approved"]}


def entries_today(now: datetime | None = None, *, rows: list[dict[str, Any]] | None = None) -> int:
    """This venue's Nova automatic entries today (the bot and Auto-entry)."""
    return int(today(None, now, cap=0, rows=rows)["count"])


def _cap() -> int:
    from bot.persist import load_session
    from bot.sleeve import of

    return int(of(load_session())["entries_per_day"])


def cap_text(count: int, cap: int) -> str:
    return (f"{cap} Nova automatic entr{'y' if cap == 1 else 'ies'} a day on this venue (the bot and "
            f"Auto-entry together) -- {count} already sent today")


# -- the gate a fire meets ---------------------------------------------------------------
def assert_entry_allowed(kind: str, setup: str | None = None) -> None:
    """Refuse an entry while Live commissions are unknown, outside its window (``setup``'s, else
    any Strategy setup's), outside regular hours without extended hours, or past the day's cap.

    Anything that is not an entry passes."""
    if kind not in BOT_ENTRY_KINDS:
        return
    from bot.day_pnl import commission_hold
    from bot.persist import load_session
    from bot.setup_levels import at_strategy
    from bot.sleeve import of

    hold = commission_hold()
    if hold is not None:
        raise BotError(
            f"the session's commissions are unreadable ({hold['error']}) -- the day P&L is unknown, "
            "so no new bot entry until they read again",
            409,
            BOT_REASON_COMMISSIONS_UNKNOWN,
        )
    row = load_session()
    now = venue_now()
    wins = [window(setup, now)] if setup else windows(at_strategy(row), now)
    if not any(w.get("open") for w in wins):
        said = "; ".join(window_text(w) for w in wins) or "no setup is at Strategy"
        raise BotError(f"outside the bot's window: {said} (venue clock {now.strftime('%H:%M')})", 409,
                       BOT_REASON_OUTSIDE_WINDOW)
    caps = of(row)
    late = extended_hours_block(caps)
    if late is not None:
        raise BotError(late, 409, BOT_SKIP_EXTENDED_HOURS)
    cap = int(caps["entries_per_day"])
    count = int(today(None, now, cap=cap)["count"])
    if count >= cap:
        raise BotError(cap_text(count, cap), 409, BOT_REASON_DAY_TRADE_CAP)


def set_clock_for_tests(fn: Callable[[], datetime] | None) -> None:
    global _now_for_tests, _tail
    _now_for_tests = fn
    _tail = None
