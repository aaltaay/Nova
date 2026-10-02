"""The squares, by ticker (ADR 043): ``GET /api/bot/triggers?date=YYYY-MM-DD``. Read-only.

One row per ticker -- every name on the day's hot list, then every name that triggered without being
on it (``listed: null``) -- saying now whether Nova would buy it if its setup triggered this minute
(``now``: today, listed names only, ``bot.trigger_now``), and under it every trigger of the day on it,
judged by the ten gates in the order Nova runs them (``bot.trigger_cells``). Under the table, what
each gate did (``impact``). ``judged_now`` names the gates judged with today's settings because
nothing recorded them at a trigger; ``sources`` says what could not be read.

Shape (schema 1): ``{schema_version, date, generated_at, gates: [{id, label}], tickers: [{symbol,
listed: {how, at} | null, now: {cells, answer, reasons} | null, triggers: [{ts, setup_id, setup_type,
kind, nth, grade, tape, outcome, r, cells, reasons}]}], impact: [{gate, blocked, target_first,
stop_first, r}], judged_now, sources: {journal, audit, hot_list: {ok, error}}}``.

Owner: this module (the answer; the reads are ``bot.trigger_inputs``', the cells ``bot.trigger_cells``'
and ``bot.trigger_now``'s; no state).
"""
from __future__ import annotations

import logging
from functools import partial
from typing import Any, Callable

from bot import trigger_cells
from bot.trigger_timeline import Timeline
from constants_bot import BOT_TRIGGER_GATES, BOT_TRIGGER_JUDGED_NOW, BOT_TRIGGERS_SCHEMA_VERSION

logger = logging.getLogger(__name__)
NowRow = Callable[[str, dict[str, Any], list[dict[str, Any]]], dict[str, Any]]


def build(day: str, *, lines: list[dict[str, Any]], ctx: trigger_cells.Context, sources: dict[str, Any],
          generated_at: float, now_row: NowRow | None = None) -> dict[str, Any]:
    """The answer from what was read (pure but for ``now_row``, which reads the desk)."""
    found = trigger_cells.triggers(lines)
    for t in found:
        t["cells"] = trigger_cells.judge(t, ctx)
    trigger_cells.take_cap(found, ctx)
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for t in found:
        by_symbol.setdefault(t["symbol"], []).append(t)
    order = list(ctx.listed) + [s for s in dict.fromkeys(t["symbol"] for t in found) if s not in ctx.listed]
    tickers = []
    for sym in order:
        entry = ctx.listed.get(sym)
        mine = by_symbol.get(sym, [])
        tickers.append({
            "symbol": sym,
            "listed": {"how": entry.get("how"), "at": entry.get("at")} if entry is not None else None,
            "now": now_row(sym, entry, found) if now_row is not None and entry is not None else None,
            "triggers": [trigger_cells.wire(t) for t in mine],
        })
    return {"schema_version": BOT_TRIGGERS_SCHEMA_VERSION, "date": day, "generated_at": generated_at,
            "gates": [{"id": gid, "label": label} for gid, label in BOT_TRIGGER_GATES],
            "tickers": tickers, "impact": trigger_cells.impact(found), "judged_now": list(BOT_TRIGGER_JUDGED_NOW),
            "sources": sources}


def answer(day: str, now: float, *, today: bool) -> dict[str, Any]:
    """Read the day's inputs and answer (``GET /api/bot/triggers``)."""
    from bot import trigger_inputs as inputs
    from bot import trigger_now

    lines, journal_src = inputs.journal(day, today=today)
    rows, audit_src = inputs.audit(day)
    listed, hot_src = inputs.hot_list(day)
    start = inputs.day_start(day)
    rules = inputs.rules()
    try:
        state: Any = inputs.Now()
    except Exception:
        logger.warning("triggers audit: the bot session could not be read -- the settings now are unknown",
                       exc_info=True)
        state = None
    ctx = trigger_cells.Context(
        timeline=Timeline(rows, restarts=trigger_cells.restarts(lines, start)), rules=rules, listed=listed,
        hot_error=None if hot_src["ok"] else hot_src["error"],
        audit_error=None if audit_src["ok"] else audit_src["error"])
    if state is not None:
        ctx.level_now, ctx.mode_now, ctx.cap_now = state.level, state.mode, state.cap
    now_row: NowRow | None = None
    if today:
        now_row = partial(trigger_now.row, trigger_now.desk(state, rules))
    return build(day, lines=lines, ctx=ctx, sources={"journal": journal_src, "audit": audit_src, "hot_list": hot_src},
                 generated_at=now, now_row=now_row)
