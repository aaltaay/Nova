"""``GET /api/followed-traders/day``'s answer, put together from the feed's day and the prices. Pure.

The price now and the exit come in as callables (``lines.quotes``, ``exits.view`` in the route; fakes in tests),
so nothing here touches IBKR or the clock. Shapes: architecture/schema/followed-traders.md.
"""
from __future__ import annotations

from typing import Any, Callable

from followed_traders import pricing, scoring
from followed_traders.constants_followed import FOLLOWED_SCHEMA_VERSION
from followed_traders.exits import stated as exit_stated
from followed_traders.feed import evidence_name
from followed_traders.lines import now_state

NowFor = Callable[[dict[str, Any]], dict[str, Any]]
ExitFor = Callable[[dict[str, Any]], dict[str, Any]]
EVIDENCE_PATH = "/api/followed-traders/evidence/{date}/frames/{name}.jpg"
LIVE_PATH = "/api/followed-traders/live/{name}.jpg"
FACE_PATH = "/api/followed-traders/faces/{date}/{name}.jpg"


def feed_down(state: str, error: str, date: str | None, now: float) -> dict[str, Any]:
    """The feed did not answer, or answered something Nova cannot read: said, with nothing else."""
    return {"schema_version": FOLLOWED_SCHEMA_VERSION, "generated_at": round(now, 3),
            "feed": {"state": state, "error": error}, "date": date, "today": None, "dates": [], "capture": None,
            "prices": None, "overall": None, "traders": []}


def compose(day: dict[str, Any], *, now: float, prices: dict[str, Any], now_for: NowFor,
            exit_for: ExitFor) -> dict[str, Any]:
    traders: dict[str, dict[str, list]] = {}
    for trade in day["trades"]:
        row = trade_row(trade, day["date"], now=now, prices=prices, now_for=now_for, exit_for=exit_for)
        group = traders.setdefault(trade["trader"], {"open": [], "closed": []})
        group["open" if trade["status"] == "open" else "closed"].append(row)
    out = []
    for name, group in traders.items():
        group["open"].sort(key=lambda r: r["entry"]["ts"], reverse=True)
        group["closed"].sort(key=_closed_order, reverse=True)
        face = FACE_PATH.format(date=day["date"], name=name) if name in day.get("faces", ()) else None
        out.append({"name": name, "face": face, "record": scoring.record(group["open"] + group["closed"]),
                    "open": group["open"], "closed": group["closed"]})
    every = [r for t in out for r in t["open"] + t["closed"]]
    return {"schema_version": FOLLOWED_SCHEMA_VERSION, "generated_at": round(now, 3),
            "feed": {"state": "ok", "error": None}, "date": day["date"], "today": day["today"],
            "dates": list(day["dates"]), "capture": capture(day.get("status"), now, faces=_faces_now(day)), "prices": prices,
            "overall": scoring.record(every), "traders": out}


def records(got: dict[str, Any], *, span: str, now: float, exit_for: ExitFor) -> dict[str, Any]:
    """``GET /api/followed-traders/record``: each trader's record over the feed's trades from ``got["from"]`` to
    ``got["to"]``, and everyone's. Open trades are not priced here; ``pending`` counts exits not read yet."""
    rows: dict[str, list[dict[str, Any]]] = {}
    for trade in got["trades"]:
        row = trade_row(trade, trade["date"], now=now, prices={"state": "off", "why": None},
                        now_for=lambda t: now_state("off"), exit_for=exit_for)
        rows.setdefault(trade["trader"], []).append(row)
    every = [r for group in rows.values() for r in group]
    return {"schema_version": FOLLOWED_SCHEMA_VERSION, "generated_at": round(now, 3),
            "feed": {"state": "ok", "error": None}, "range": span, "from": got["from"], "to": got["to"],
            "dates": list(got["dates"]),
            "pending": sum(1 for r in every if (r["exit"] or {}).get("state") == "pending"),
            "overall": scoring.record(every),
            "traders": [{"name": name, "record": scoring.record(group)} for name, group in rows.items()]}


def records_down(state: str, error: str, span: str, now: float) -> dict[str, Any]:
    return {"schema_version": FOLLOWED_SCHEMA_VERSION, "generated_at": round(now, 3),
            "feed": {"state": state, "error": error}, "range": span, "from": None, "to": None, "dates": [],
            "pending": 0, "overall": None, "traders": []}


def _faces_now(day: dict[str, Any]) -> dict[str, str]:
    """This API's path to each photo the feed has on its today, when the day answered is today: the bar is the
    feed's now, so a past day's photos never stand in for it."""
    if day["date"] is None or day["date"] != day["today"]:
        return {}
    return {name: FACE_PATH.format(date=day["date"], name=name) for name in day.get("faces", ())}


def capture(status: dict[str, Any] | None, now: float, *, faces: dict[str, str] | None = None) -> dict[str, Any] | None:
    if status is None:
        return None
    updated = status["updated_at"]
    return {"live": status["live"], "clock": status["clock"], "updated_at": updated,
            "age_sec": None if updated is None else round(max(0.0, now - updated), 1),
            "bar_visible": status["bar_visible"], "title": status["title"], "video_id": status.get("video_id"),
            "traders": list(status["traders"]),
            "problem": status.get("problem"), "problem_at": status.get("problem_at"), "bar": bar(status, faces or {})}


def bar(status: dict[str, Any], faces: dict[str, str] | None = None) -> list[dict[str, Any]] | None:
    """Each trader's bar as the feed last confirmed it, with this API's path to their slot image and to their photo
    that day when the feed has them."""
    held = status.get("positions")
    if held is None:
        return None
    slots, faces = status.get("slots", ()), faces or {}
    return [{"trader": t["trader"], "positions": [dict(p) for p in t["positions"]],
             "image": LIVE_PATH.format(name=t["trader"]) if t["trader"] in slots else None,
             "face": faces.get(t["trader"])} for t in held]


def trade_row(t: dict[str, Any], date: str, *, now: float, prices: dict[str, Any], now_for: NowFor,
              exit_for: ExitFor) -> dict[str, Any]:
    side, avg = t["side"], t["price"]
    row: dict[str, Any] = {
        "id": f"{t['trader']}|{side}|{t['symbol']}|{t['entry_ts']:.0f}",
        "trader": t["trader"], "side": side, "symbol": t["symbol"], "status": t["status"],
        "entry": {"first_price": t["entry_price"], "avg_price": avg, "ts": t["entry_ts"],
                  "since_ts": t["entry_since_ts"], "known": t["entry_known"]},
        "adds": [dict(a) for a in t["adds"]],
        "now": None, "exit": None, "pl": None,
        "evidence": {"entry": evidence_path(date, t["entry_evidence"]),
                     "exit": evidence_path(date, t["exit_evidence"])},
    }
    if t["status"] == "open":
        current = now_for(t) if prices["state"] == "live" else now_state("off", why=prices.get("why"))
        row["now"] = current
        if current["state"] == "live":
            row["pl"] = pricing.pl_point(side, avg, current["price"])
        row["held"] = pricing.held(t["entry_ts"], t["entry_since_ts"], t["entry_known"], now)
        row["result"] = None
        return row
    if t["status"] == "closed" and t["exit_ts"] is not None:
        out = exit_for(t)
        row["held"] = pricing.held(t["entry_ts"], t["entry_since_ts"], t["entry_known"], t["exit_ts"],
                                   t["exit_since_ts"])
    else:
        out = exit_stated("unavailable", why="the feed never saw it close")
        row["held"] = {"min_sec": None, "max_sec": None}
    row["exit"] = out
    if out["state"] == "at":
        row["pl"] = pricing.pl_point(side, avg, out["price"])
    elif out["state"] == "range":
        row["pl"] = pricing.pl_range(side, avg, out["low"], out["high"])
    row["result"] = scoring.result(row)
    return row


def evidence_path(date: str, path: str | None) -> str | None:
    name = evidence_name(path)
    return None if name is None else EVIDENCE_PATH.format(date=date, name=name)


def _closed_order(row: dict[str, Any]) -> float:
    exit_ = row["exit"] or {}
    return exit_.get("to_ts") or row["entry"]["ts"]
