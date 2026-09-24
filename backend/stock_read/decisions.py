"""One symbol's day, as the bot saw it (ADR 035): the eyes' journal lines of that symbol folded into
events, with the day's HOD Momo alerts, borrow changes, news, the open and the high of day, and the
bot's own audit lines. Read-only; the journal is never rewritten.

``fold_journal`` and ``summarize`` are pure; ``timeline`` reads the owners, each on its own -- one
that cannot be read is ``{ok: false, error}`` in ``sources`` and the others still answer.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, time as dtime
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from constants_stock_read import STOCK_READ_AUDIT_TAIL, STOCK_READ_DECISIONS_MAX_EVENTS

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
DEFAULT_LANE = "first_pullback"
TAPE_FOLD_SEC = 60.0
REFUSAL_STATES = ("pullback", "failed")


def _cap(text: str | None) -> str:
    text = (text or "").strip()
    return text[:1].upper() + text[1:] if text else ""


def _event(ts: float, lane: str, event: str, title: str, detail: str | None = None,
           levels: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ts": float(ts), "lane": lane, "event": event, "title": title, "detail": detail, "count": 1,
            "last_ts": None, "levels": levels}


def _journal_event(line: dict[str, Any]) -> dict[str, Any] | None:
    ev = line.get("event")
    lane = line.get("setup_type") or DEFAULT_LANE
    ts = float(line.get("ts") or line.get("wall_ts") or 0)
    reason = line.get("reason")
    if ev == "state":
        state = line.get("state") or ""
        if (reason or "").startswith("warming up"):
            return None
        lead = {"pullback": "Not armed", "failed": "Dropped", "watching": "Watching", "leg": "Forming"}.get(state,
                                                                                                          _cap(state))
        return _event(ts, lane, "state", f"{lead}: {reason}", None, {"leg": line.get("leg")} if line.get("leg") else None)
    if ev == "leg":
        return _event(ts, lane, "leg", _cap(reason), None, {"leg": line.get("leg")})
    if ev in ("armed", "rearmed"):
        grade = f" (grade {line['grade']})" if line.get("grade") else ""
        return _event(ts, lane, ev, f"{'Armed' if ev == 'armed' else 'Re-armed'}: {reason}{grade}", None,
                      {"setup": line.get("setup")})
    if ev == "filtered":
        return _event(ts, lane, ev, f"Kept out by the template's filter: {reason}")
    if ev == "near":
        verdict = ((line.get("tape") or {}).get("verdict") or "").upper()
        return _event(ts, lane, ev, f"Near: {reason}", f"tape {verdict}" if verdict else None)
    if ev == "tape":
        reasons = line.get("reasons") or []
        return _event(ts, lane, ev, f"Tape {str(line.get('verdict') or '?').upper()}", reasons[0] if reasons else None)
    if ev == "triggered":
        verdict = ((line.get("tape") or {}).get("verdict") or "").upper()
        return _event(ts, lane, ev, f"Triggered at {line.get('price')}", f"tape {verdict}" if verdict else None,
                      {"setup": line.get("setup")})
    if ev in ("failed", "disarmed"):
        return _event(ts, lane, ev, f"{'Failed' if ev == 'failed' else 'Disarmed'}: {reason}")
    if ev == "proposal":
        return _event(ts, lane, ev, f"Proposal {line.get('status')}", line.get("reason"))
    if ev == "scored":
        r = line.get("bar_r")
        return _event(ts, lane, ev, f"Scored: {str(line.get('outcome') or '').replace('_', ' ')}"
                      + (f" {float(r):+.1f}R" if r is not None else ""),
                      f"best {line.get('mfe')}, worst {line.get('mae')}" if line.get("mfe") is not None else None)
    if ev == "flow":
        return _event(ts, lane, ev, f"Tape turned {line.get('label')}", f"score {line.get('score')}")
    if ev == "flush":
        return _event(ts, lane, ev, f"Flush: {line.get('action')}", f"at {line.get('price')}")
    return None


def fold_journal(lines: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Events oldest first; a lane repeating the same line (a state and reason, or a tape verdict
    flipping inside a minute) is one event with a ``count`` and its ``last_ts``."""
    out: list[dict[str, Any]] = []
    last_by_lane: dict[str, dict[str, Any]] = {}
    for line in lines:
        e = _journal_event(line)
        if e is None:
            continue
        prev = last_by_lane.get(e["lane"])
        same_state = prev is not None and prev["event"] == "state" == e["event"] and prev["title"] == e["title"]
        tape_run = (prev is not None and prev["event"] == "tape" == e["event"]
                    and e["ts"] - (prev["last_ts"] or prev["ts"]) <= TAPE_FOLD_SEC)
        if same_state or tape_run:
            prev["count"] += 1
            prev["last_ts"] = e["ts"]
            if tape_run and e["title"] not in prev["title"]:
                prev["title"] = f"{prev['title']} / {e['title'].removeprefix('Tape ')}"
                prev["detail"] = e["detail"] or prev["detail"]
            continue
        out.append(e)
        last_by_lane[e["lane"]] = e
    return out


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    journal = [e for e in events if e["lane"] not in ("hod_momo", "market", "bot")]
    legs = sum(1 for e in journal if e["event"] == "leg")
    armed = sum(1 for e in journal if e["event"] == "armed")
    near = sum(1 for e in journal if e["event"] == "near")
    triggered = sum(1 for e in journal if e["event"] == "triggered")
    refusals: Counter[str] = Counter()
    for e in journal:
        if e["event"] == "state" and e["title"].split(":")[0] in ("Not armed", "Dropped"):
            refusals[e["title"].split(": ", 1)[-1]] += e["count"]
    trades = sum(1 for e in events if e["lane"] == "bot" and e["event"] == "filled")
    if armed or triggered:
        text = f"The scanners armed {armed} setup{'s' if armed != 1 else ''} and {triggered} triggered."
    elif legs:
        text = (f"The scanners saw {legs} leg{'s' if legs != 1 else ''} or pole{'s' if legs != 1 else ''} and armed "
                "nothing.")
    else:
        text = "No setup formed on it today." if journal else "The eyes' journal holds nothing for it today."
    if refusals:
        text += " Why: " + "; ".join(f"{r} (x{n})" if n > 1 else r for r, n in refusals.most_common(3)) + "."
    text += f" The bot traded it {trades} time{'s' if trades != 1 else ''}." if trades else " The bot did not trade it."
    return {"text": text, "legs": legs, "armed": armed, "near": near, "triggered": triggered, "trades": trades,
            "refusals": [{"reason": r, "count": n} for r, n in refusals.most_common()]}


def _day_bounds(date: str) -> tuple[float, float]:
    d = datetime.strptime(date, "%Y-%m-%d").date()
    return (datetime.combine(d, dtime(0, 0), ET).timestamp(), datetime.combine(d, dtime(23, 59, 59), ET).timestamp())


def _read(sources: dict[str, dict], name: str, fn) -> list[dict[str, Any]]:
    try:
        out = fn()
        sources[name] = {"ok": True, "error": None}
        return out
    except Exception as exc:
        logger.warning("stock read decisions: %s failed", name, exc_info=True)
        sources[name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
        return []


def _journal(sym: str, date: str) -> list[dict[str, Any]]:
    from eyes import journal, reader

    return fold_journal(reader.lines(journal.journal_dir() / f"{date}.jsonl", source="live", symbol=sym))


def _hod(sym: str, date: str) -> list[dict[str, Any]]:
    import hod_momo

    alerts = [a for a in hod_momo.get_history_alerts(date) or [] if str(a.get("ticker") or "").upper() == sym]
    alerts.sort(key=lambda a: float(a.get("created_ts") or 0))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in alerts:
        name = str(a.get("strategy_name") or a.get("strategy_id"))
        if name in seen:
            continue
        seen.add(name)
        n = sum(1 for x in alerts if str(x.get("strategy_name") or x.get("strategy_id")) == name)
        e = _event(float(a.get("created_ts") or 0), "hod_momo", "alert", f"HOD Momo: {name} at {a.get('price')}",
                   f"{n} of these today" if n > 1 else None)
        out.append(e)
    return out


def _borrow(sym: str, date: str) -> list[dict[str, Any]]:
    from move_reason import borrow_store

    start, end = _day_bounds(date)
    db = borrow_store.connect()
    try:
        rows = borrow_store.changes_between(db, sym, start, end)
    finally:
        db.close()
    out = []
    for r in rows:
        if not r["listed"] or not r.get("available"):
            title = "Borrow: nothing to lend"
        else:
            title = f"Borrow: fee {r['fee_rate']:.1f}%/yr, {int(r['available']):,} shares to lend"
        out.append(_event(r["ts"], "market", "borrow", title))
    return out


def _news(sym: str, date: str, now: float) -> list[dict[str, Any]]:
    from catalysts import live as catalyst_live

    if datetime.fromtimestamp(now, ET).date().isoformat() != date:
        return []                          # the panel holds today's window only
    panel = catalyst_live.panel(sym, now)
    out = []
    for it in panel.get("items") or []:
        if it.get("kind") not in ("catalyst", "negative"):
            continue
        out.append(_event(float(it.get("published_ts") or 0), "market", "news",
                          f"News ({it.get('kind')}, {str(it.get('category') or '').replace('_', ' ')}): {it.get('title')}",
                          f"{it.get('source')}"))
    return out


def _bot(sym: str, date: str) -> list[dict[str, Any]]:
    from bot.persist import read_audit_lines

    start, end = _day_bounds(date)
    out = []
    for r in read_audit_lines(limit=STOCK_READ_AUDIT_TAIL):
        ts = float(r.get("timestamp") or 0)
        inputs = r.get("inputs") or {}
        if not start <= ts <= end or str(inputs.get("symbol") or "").upper() != sym:
            continue
        if r.get("action") not in ("bot_trade", "setup_proposal"):
            continue
        what = "Bot trade" if r["action"] == "bot_trade" else "Proposal"
        out.append(_event(ts, "bot", str(r.get("outcome") or ""), f"{what} {r.get('outcome')}", r.get("reason")))
    return out


def _market(sym: str, date: str) -> list[dict[str, Any]]:
    from sensors.feeds import get_bars
    from stock_read.indicators import levels

    bars, _src = get_bars(sym, "1Min", 1000)
    start, end = _day_bounds(date)
    day = [b for b in bars if start <= float(b["t"]) <= end]
    if not day:
        return []
    lv = levels(day, price=None, prev_close=None)
    out = []
    if lv.get("open") is not None:
        open_t = next(float(b["t"]) for b in day if datetime.fromtimestamp(float(b["t"]), ET).time() >= dtime(9, 30))
        out.append(_event(open_t, "market", "open", f"Open {lv['open']:.2f}"))
    if lv.get("hod"):
        out.append(_event(lv["hod"]["ts"], "market", "hod", f"High of day {lv['hod']['price']:.2f}"))
    return out


def timeline(symbol: str, date: str, now: float) -> dict[str, Any]:
    sym = (symbol or "").strip().upper()
    sources: dict[str, dict] = {}
    events = (_read(sources, "journal", lambda: _journal(sym, date)) + _read(sources, "hod_momo", lambda: _hod(sym, date))
              + _read(sources, "borrow", lambda: _borrow(sym, date)) + _read(sources, "catalysts", lambda: _news(sym, date, now))
              + _read(sources, "bot", lambda: _bot(sym, date)) + _read(sources, "market", lambda: _market(sym, date)))
    events.sort(key=lambda e: e["ts"])
    cut = len(events) > STOCK_READ_DECISIONS_MAX_EVENTS
    events = events[:STOCK_READ_DECISIONS_MAX_EVENTS]
    summary = summarize(events)
    if cut:
        summary["text"] += f" (The timeline stops at {STOCK_READ_DECISIONS_MAX_EVENTS} events.)"
    return {"symbol": sym, "date": date, "generated_at": now, "summary": summary, "events": events,
            "sources": sources}
