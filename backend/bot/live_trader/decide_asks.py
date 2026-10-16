"""The Live Trader bot's asks: a step the operator approves (Entry: You, Exit: Bot) (ADR 055). Pure.

``decide_steps`` raises one (``ask``: the toast's words, ``LT_ASK_SEC`` to answer), follows it each pass (``follow``:
skipped, still waiting, or approved -- then the step meets every rule again before it is sent), withdraws it
(``drop``) and says one never answered as its skip (``expire``). ``run`` is the pass (``decide_steps._Pass``); the
asks live in its snapshot (``snap["asks"]``). Shapes: architecture/schema/bot.md ("The Live Trader bot").
"""
from __future__ import annotations

from typing import Any

from bot.live_trader import rules
from bot.live_trader.constants_live_trader import LT_ASK_EXPIRED, LT_ASK_SEC, LT_ASK_SKIPPED


def ask(run: Any, name, r, pid, step, plan, change, *, prev_price: float | None = None) -> str:
    """Raise an ask in the toast's words; its id."""
    run.snap["seq"] = int(run.snap.get("seq") or 0) + 1
    ask_id = f"{name.lower()}-{run.snap['seq']}"
    price, sym = rules.price_text(change["price"]), r["symbol"]
    lead = {"entry": f"{name} {rules.verb(r['side'], True)} {sym} at {price}",
            "already_open": f"{name} holds {sym} {r['side']} at {price} (already open)",
            "add": f"{name} added to {sym} (average {price})"}[step]
    stop = f", buy stop {rules.price_text(plan['stop'])}" if plan.get("stop") else ""
    more = " more" if step == "add" else ""
    ask = {"id": ask_id, "host": name, "row_id": r["id"], "pos_id": pid, "symbol": sym, "side": r["side"],
           "step": step, "their_price": change["price"], "qty": plan["qty"], "limit": plan["limit"],
           "stop": plan["stop"], "created_ts": run.now, "expires_ts": run.now + LT_ASK_SEC,
           "change": change, "approved": False, "prev_price": prev_price,
           "text": f"{lead}: {rules.verb(r['side'])} {plan['qty']}{more} at {rules.price_text(plan['limit'])}{stop}?"}
    run.snap["asks"][ask_id] = ask
    run.out["actions"].append({"kind": "ask", "ask": dict(ask)})
    return ask_id


def expire(run: Any) -> None:
    """Asks the operator has not answered in ``LT_ASK_SEC``, said as skips."""
    for ask_id, ask in list(run.snap["asks"].items()):
        if ask["approved"] or (run.ctx.get("answers") or {}).get(ask_id) is not None:
            continue
        if run.now >= ask["expires_ts"]:
            why = f"not approved in {LT_ASK_SEC:.0f} s"
            drop(run, ask_id, why)
            run.out["actions"].append({"kind": "skip", "host": ask["host"], "pos_id": ask["pos_id"],
                                       "row_id": ask["row_id"], "symbol": ask["symbol"], "side": ask["side"],
                                       "step": ask["step"], "code": LT_ASK_EXPIRED, "why": why,
                                       "change": ask["change"]})


def drop(run: Any, ask_id: str, why: str) -> None:
    ask = run.snap["asks"].pop(ask_id, None)
    if ask is not None:
        run.out["actions"].append({"kind": "drop_ask", "ask_id": ask_id, "host": ask["host"], "why": why})


def follow(run: Any, name, st, r, pid, ask_id, blocked, unread, *, entry: bool) -> str:
    """``taken`` | ``skipped`` | ``asked`` (still waiting on the operator, or approved and waiting)."""
    ask = run.snap["asks"].get(ask_id or "")
    if ask is None:
        return "skipped"
    change, step = ask["change"], ask["step"]
    answered = (run.ctx.get("answers") or {}).get(ask_id)
    if answered is False:
        drop(run, ask_id, "you skipped it")
        run.skip(name, r, pid, step, LT_ASK_SKIPPED, "you skipped it", change)
        return "skipped"
    if answered is True or ask["approved"]:
        ask["approved"] = True
        if blocked:
            drop(run, ask_id, blocked[1])
            run.skip(name, r, pid, step, blocked[0], blocked[1], change)
            return "skipped"
        v = run.read_doubt(name, r, ask.get("since"), unread, entry=entry)
        if v is None:
            v = run.check(name, st, r["side"], r["symbol"], change["price"], r.get("ticker") if entry else None,
                          ask.get("since"), entry=entry, prev_price=ask.get("prev_price"),
                          already_open=step == "already_open")
        if v["verdict"] == rules.WAIT:
            ask["since"] = ask.get("since") or run.now
            run.wait(pid, r, v)
            return "asked"
        drop(run, ask_id, "approved" if v["verdict"] == rules.GO else v["text"])
        if v["verdict"] == rules.SKIP:
            run.skip(name, r, pid, step, v["code"], v["text"], change)
            return "skipped"
        run.send(name, r, pid, step, v["plan"], change, approved=True)
        return "taken"
    if run.now >= ask["expires_ts"]:
        drop(run, ask_id, f"not approved in {LT_ASK_SEC:.0f} s")
        run.skip(name, r, pid, step, LT_ASK_EXPIRED, f"not approved in {LT_ASK_SEC:.0f} s", change)
        return "skipped"
    return "asked"
