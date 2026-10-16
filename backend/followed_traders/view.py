"""``GET /api/followed-traders/day``'s answer, put together from the feed's day and the prices. Pure.

The price now, the exit and the ticker check come in as callables (``lines.quotes``, ``exits.view`` and
``tickers.check`` over ``exits.view`` in the route; fakes in tests), so nothing here touches IBKR or the clock. A trade
whose ticker or averages may be glued to a price is shown as the check says (``tickers.shown``), and never priced
while it is not settled; a position the feed read two ways in turn is one trade (``joined``). Shapes:
architecture/schema/followed-traders.md.
"""
from __future__ import annotations

from typing import Any, Callable

from followed_traders import pricing, scoring, tickers
from followed_traders.constants_followed import FOLLOWED_SCHEMA_VERSION
from followed_traders.exits import stated as exit_stated
from followed_traders.feed import evidence_name
from followed_traders.lines import now_state

NowFor = Callable[[dict[str, Any]], dict[str, Any]]
ExitFor = Callable[[dict[str, Any]], dict[str, Any]]
TickerFor = Callable[[dict[str, Any]], dict[str, Any] | None]
EVIDENCE_PATH = "/api/followed-traders/evidence/{date}/frames/{name}.jpg"
LIVE_PATH = "/api/followed-traders/live/{name}.jpg"
FACE_PATH = "/api/followed-traders/faces/{date}/{name}.jpg"


def feed_down(state: str, error: str, date: str | None, now: float) -> dict[str, Any]:
    """The feed did not answer, or answered something Nova cannot read: said, with nothing else."""
    return {"schema_version": FOLLOWED_SCHEMA_VERSION, "generated_at": round(now, 3),
            "feed": {"state": state, "error": error}, "date": date, "today": None, "resets_at": None, "dates": [],
            "capture": None, "prices": None, "overall": None, "traders": []}


def compose(day: dict[str, Any], *, now: float, prices: dict[str, Any], now_for: NowFor,
            exit_for: ExitFor, resets_at: float | None = None,
            seen: dict[str, dict[str, Any]] | None = None, ticker_for: TickerFor | None = None) -> dict[str, Any]:
    """``day["today"]`` is the desk's trading day and ``resets_at`` the epoch second it ends (the route's
    ``desk_day``); ``seen`` each trader's sighting on the bar (``sightings.sightings``), None when not read: a
    trader who left the bar has closed every trade (``closed_on_leaving``)."""
    seen = seen or {}
    traders: dict[str, dict[str, list]] = {}
    trades = [closed_on_leaving(t, left_bar(seen, t["trader"])) for t in day["trades"]]
    for trade, shown, ticker in joined(trades, ticker_for):
        row = row_of(trade, shown, ticker, day["date"], now=now, prices=prices, now_for=now_for, exit_for=exit_for)
        group = traders.setdefault(trade["trader"], {"open": [], "closed": []})
        group["open" if shown["status"] == "open" else "closed"].append(row)
    out = []
    for name, group in traders.items():
        group["open"].sort(key=lambda r: r["entry"]["ts"], reverse=True)
        group["closed"].sort(key=_closed_order, reverse=True)
        face = FACE_PATH.format(date=day["date"], name=name) if name in day.get("faces", ()) else None
        out.append({"name": name, "face": face, "record": scoring.record(group["open"] + group["closed"]),
                    "seen": seen.get(name), "open": group["open"], "closed": group["closed"]})
    every = [r for t in out for r in t["open"] + t["closed"]]
    return {"schema_version": FOLLOWED_SCHEMA_VERSION, "generated_at": round(now, 3),
            "feed": {"state": "ok", "error": None}, "date": day["date"], "today": day["today"],
            "resets_at": None if resets_at is None else round(resets_at, 3), "dates": list(day["dates"]), "capture": capture(day.get("status"), now, faces=_faces_now(day)), "prices": prices,
            "overall": scoring.record(every), "traders": out}


def records(got: dict[str, Any], *, span: str, now: float, exit_for: ExitFor,
            seen_by_date: dict[str, dict[str, dict[str, Any]]] | None = None,
            ticker_for: TickerFor | None = None) -> dict[str, Any]:
    """``GET /api/followed-traders/record``: each trader's record and scored trades (``scoring.scored``) over the
    feed's trades from ``got["from"]`` to ``got["to"]``, and everyone's record. Open trades are not priced here;
    ``pending`` counts exits not read yet. A trader who left the bar on a day (``seen_by_date``) closed that day's
    trades when they left, as on the day."""
    seen_by_date = seen_by_date or {}
    rows: dict[str, list[dict[str, Any]]] = {}
    days: dict[str, list[str]] = {}
    trades = [closed_on_leaving(t, left_bar(seen_by_date.get(t["date"]), t["trader"])) for t in got["trades"]]
    for trade, shown, ticker in joined(trades, ticker_for):
        row = row_of(trade, shown, ticker, trade["date"], now=now, prices={"state": "off", "why": None},
                     now_for=lambda t: now_state("off"), exit_for=exit_for)
        rows.setdefault(trade["trader"], []).append(row)
        days.setdefault(trade["trader"], []).append(trade["date"])
    every = [r for group in rows.values() for r in group]
    return {"schema_version": FOLLOWED_SCHEMA_VERSION, "generated_at": round(now, 3),
            "feed": {"state": "ok", "error": None}, "range": span, "from": got["from"], "to": got["to"],
            "dates": list(got["dates"]),
            "pending": sum(1 for r in every if (r["exit"] or {}).get("state") == "pending"),
            "overall": scoring.record(every),
            "traders": [{"name": name, "record": scoring.record(group), "scored": scoring.scored(group, days[name])}
                        for name, group in rows.items()]}


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


def left_bar(seen: dict[str, dict[str, Any]] | None, trader: str) -> dict[str, Any] | None:
    """The trader's sighting when they left the bar (``left_ts`` set), else None."""
    got = (seen or {}).get(trader)
    return got if got and got.get("left_ts") is not None else None


def closed_on_leaving(t: dict[str, Any], gone: dict[str, Any] | None) -> dict[str, Any]:
    """An open trade of a trader who left the bar, closed when they left (operator rule 2026-10-14: "if they are off
    air then all trades are closed"). The exit is at ``left_ts``, or somewhere in ``last_ts``..``left_ts`` when the bar
    was not read between; there is no exit image, since no close was seen. Any other trade as the feed has it."""
    if gone is None or t["status"] != "open":
        return t
    last, left = gone["last_ts"], gone["left_ts"]
    return {**t, "status": "closed", "exit_ts": left, "exit_since_ts": last if last < left else None,
            "exit_evidence": None, "left_bar": True}


def joined(trades: list[dict[str, Any]],
           ticker_for: TickerFor | None) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]]:
    """``(trade, shown, ticker)`` for each of the feed's trades in its order: the trade as the feed has it (its id),
    as Nova shows it (``tickers.shown``) and its check. A position the feed closed and opened again in the same
    second, for the same trader, side and stock as shown, never left the bar -- the feed read it two ways
    (2026-10-15: RGTI 12.08 read RGTI 112.08 and RGT 112.08 in turn made one trade ten) -- and is joined back into
    the trade it was (``_joins``, ``_join``)."""
    out: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]] = []
    for t in trades:
        ticker = ticker_for(t) if ticker_for else None
        part = (t, tickers.shown(t, ticker), ticker)
        at = next((i for i in range(len(out) - 1, -1, -1) if _joins(out[i], part)), None)
        if at is None:
            out.append(part)
        else:
            out[at] = _join(out[at], part)
    return out


def _joins(first: tuple, then: tuple) -> bool:
    (a, shown_a, ticker_a), (b, shown_b, ticker_b) = first, then
    return (a["trader"] == b["trader"] and shown_a["side"] == shown_b["side"]
            and shown_a["symbol"] == shown_b["symbol"] and tickers.settled(ticker_a) and tickers.settled(ticker_b)
            and shown_a["status"] == "closed" and not shown_a.get("left_bar") and shown_a["exit_since_ts"] is None
            and shown_a["exit_ts"] is not None and shown_b["entry_since_ts"] is None and shown_b["entry_known"]
            and int(shown_a["exit_ts"]) == int(shown_b["entry_ts"]))


def _join(first: tuple, then: tuple) -> tuple:
    """One trade from two parts: the first's id, entry and entry image, the last's exit and exit image, and an add
    where the average shown changed between them. A corrected ticker of either part names what was read."""
    (a, shown_a, ticker_a), (_b, shown_b, ticker_b) = first, then
    adds = [dict(x) for x in shown_a["adds"]]
    if tickers.price_text(shown_b["entry_price"]) != tickers.price_text(shown_a["price"]):
        adds.append({"ts": shown_b["entry_ts"], "price": shown_b["entry_price"], "prev_price": shown_a["price"]})
    adds += [dict(x) for x in shown_b["adds"]]
    shown = {**shown_a, "price": shown_b["price"], "adds": adds, "status": shown_b["status"],
             "exit_ts": shown_b["exit_ts"], "exit_since_ts": shown_b["exit_since_ts"],
             "exit_evidence": shown_b["exit_evidence"], "left_bar": bool(shown_b.get("left_bar"))}
    fixed = next((t for t in (ticker_a, ticker_b) if t and t["state"] == "corrected"), None)
    return a, shown, fixed or ticker_a


def trade_row(t: dict[str, Any], date: str, *, now: float, prices: dict[str, Any], now_for: NowFor,
              exit_for: ExitFor, ticker_for: TickerFor | None = None) -> dict[str, Any]:
    ticker = ticker_for(t) if ticker_for else None
    return row_of(t, tickers.shown(t, ticker), ticker, date, now=now, prices=prices, now_for=now_for,
                  exit_for=exit_for)


def row_of(t: dict[str, Any], shown: dict[str, Any], ticker: dict[str, Any] | None, date: str, *, now: float,
           prices: dict[str, Any], now_for: NowFor, exit_for: ExitFor) -> dict[str, Any]:
    """A trade's row: ``t`` as the feed has it gives the id, ``shown`` (``tickers.shown``, or a joined trade)
    everything else."""
    # The ticker as first read keeps the id: neither the feed's correction nor Nova's check makes a trade new.
    row_id = f"{t['trader']}|{t['side']}|{t.get('read_as') or t['symbol']}|{t['entry_ts']:.0f}"
    t = shown
    settled = tickers.settled(ticker)
    side, avg = t["side"], t["price"]
    row: dict[str, Any] = {
        "id": row_id,
        "trader": t["trader"], "side": side, "symbol": t["symbol"], "status": t["status"],
        "entry": {"first_price": t["entry_price"], "avg_price": avg, "ts": t["entry_ts"],
                  "since_ts": t["entry_since_ts"], "known": t["entry_known"]},
        "adds": [dict(a) for a in t["adds"]],
        "left_bar": bool(t.get("left_bar")),
        "ticker": ticker,
        "now": None, "exit": None, "pl": None,
        "evidence": {"entry": evidence_path(date, t["entry_evidence"]),
                     "exit": evidence_path(date, t["exit_evidence"])},
    }
    if t["status"] == "open":
        if not settled:  # no line and no P/L from a ticker that may be wrong
            current = now_state("no_line", why=ticker["why"])
        elif prices["state"] == "live":
            current = now_for(t)
        else:
            current = now_state("off", why=prices.get("why"))
        row["now"] = current
        if current["state"] == "live":
            row["pl"] = pricing.pl_point(side, avg, current["price"])
        row["held"] = pricing.held(t["entry_ts"], t["entry_since_ts"], t["entry_known"], now)
        row["result"] = None
        return row
    if t["status"] == "closed" and t["exit_ts"] is not None:
        out = exit_for(t) if settled else exit_stated(
            "pending" if ticker["state"] == "checking" else "unavailable", from_ts=t["exit_since_ts"],
            to_ts=t["exit_ts"], why=ticker["why"])
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
