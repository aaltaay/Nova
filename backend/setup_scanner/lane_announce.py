"""What a lane tells the rest of Nova (ADR 022, ADR 030, ADR 042 H): its proposals and its triggers.

Moved out of ``lane.py`` so the lane keeps one concern -- turning detector events into rows
and tape reads. Both carry what a consumer needs to judge the setup without asking again:
the grade and the pillars' count, whether the template's stock filter kept the name out, and
the book's spread at the moment. A proposal also says whether it is a trade at all
(``not_a_trade``, ``setup_scanner.trade_verdict``) and who will take it by itself
(``taken_by``: Nova's bot or Auto-entry, the live host's ``taker``); it is still raised, so
the desk can say "the bot is taking this -- nothing to do" or "not a trade: ...". Nothing
here places an order.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from setup_scanner.grade import pillar_count
from setup_scanner.trade_verdict import verdict

logger = logging.getLogger(__name__)


def _spread(res: dict | None) -> float | None:
    value = ((res or {}).get("metrics") or {}).get("spread")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _count(row: dict) -> dict | None:
    return pillar_count(((row.get("pillars") or {}).get("checks")))


def _taker(lane: Any, sym: str) -> str | None:
    """Who takes this setup by itself (the live host knows; a replay host has no ``taker``)."""
    ask = getattr(lane.host, "taker", None)
    if ask is None:
        return None
    try:
        return ask(sym, lane.p.setup)
    except Exception:
        logger.warning("setup scanner: who takes %s's %s could not be read", sym, lane.p.setup, exc_info=True)
        return None


def propose(lane: Any, sym: str, sid: str, res: dict, now: float) -> dict:
    """Raise a proposal: the setup is near its trigger and the tape says go."""
    row = lane.rows.get(sid) or {}
    spread = _spread(res)
    judged = verdict(grade=row.get("grade"), pillars=_count(row), spread=spread, risk=row.get("risk"))
    not_a_trade = None if judged["ok"] else {"reasons": judged["reasons"]}
    prop = {"id": str(uuid.uuid4()), "setup_id": sid, "symbol": sym, "kind": row.get("kind"),
            "trigger": row.get("trigger"), "entry": row.get("entry_planned"), "stop": row.get("stop"),
            "target1": row.get("target1"), "risk": row.get("risk"), "grade": row.get("grade"),
            "pillars": _count(row), "spread": spread, "reasons": res.get("reasons"), "created_at": now,
            "status": "open", "tape_now": res["verdict"], "template_id": lane.p.template_id,
            "template_name": lane.p.name, "source": lane.host.source, "setup_type": lane.p.setup,
            "not_a_trade": not_a_trade, "taken_by": None if not_a_trade else _taker(lane, sym)}
    lane.proposals[sid] = prop
    lane.alerts.append(prop)
    row["proposal_id"] = prop["id"]
    lane.host.save(row)
    lane.journal("proposal", sym, setup_id=sid, status="proposed", proposal=prop)
    said = {"bot": " -- the bot is taking it", "auto_entry": " -- Auto-entry is taking it"}.get(prop["taken_by"] or "")
    lane.host.audit(action="setup_proposal", outcome="proposed",
                    reason=(f"{str(prop['kind'] or 'setup').replace('_', ' ')} on {sym}: trigger "
                            f"{prop['trigger']}, stop {prop['stop']} -- tape go"
                            + (f"; not a trade: {'; '.join(not_a_trade['reasons'])}" if not_a_trade else said or "")),
                    inputs=prop)
    return prop


def trigger(lane: Any, sym: str, sid: str, setup: dict, tape: dict | None, ts: float, *,
            filtered: str | None = None) -> None:
    """The playing lane tells its host a setup triggered (ADR 030); a replay host has no ear for it.

    A setup the template's filter kept out is announced too, marked ``filtered``: Nova's bot
    and Auto-entry say they skipped it, and why, instead of saying nothing."""
    notify = getattr(lane.host, "on_trigger", None)
    if not lane.playing or notify is None:
        return
    from setup_scanner.lane import slim

    row = lane.rows.get(sid) or {}
    notify({"symbol": sym, "setup_id": sid, "setup": dict(setup), "tape": slim(tape) if tape else None, "ts": ts,
            "template_id": lane.p.template_id, "template_rev": lane.p.template_rev,
            "template_name": lane.p.name, "setup_type": lane.p.setup, "grade": row.get("grade"),
            "pillars": _count(row), "filtered": filtered, "spread": _spread(tape)})
