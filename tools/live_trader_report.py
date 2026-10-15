#!/usr/bin/env python3
"""The Live Trader bot's day, order by order (ADR 055) -- a read-only report.

Asks the backend that is answering for the bot's audit stream (``GET /api/bot/audit``) and prints, for every order
the Live Trader bot sent on the day asked (the desk's day, ET):

    when it was sent -> the host -> what changed on their bar (open, add, close, off air, the bar hidden, the
    sell-all time, a key or the Bot switch turned off) and when the stream showed it -> how many seconds after that
    the order went -> the order -> its fill and how Paper filled it -> IBKR's last print and quote when the fill was
    read -> the fill against that print

and then every skip, by its reason. Nothing here places, cancels or changes anything.

Usage (repo root, with the desk running):
  py -3 tools/live_trader_report.py                     # today
  py -3 tools/live_trader_report.py --date 2026-10-15 --md report.md
  py -3 tools/live_trader_report.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

DEFAULT_API = "http://127.0.0.1:8000"
ACTION = "live_trader"
AUDIT_LINES = 20_000
ET = ZoneInfo("America/New_York")
DAY_START_HOUR_ET = 4           # the desk's day turns at 04:00 ET


def desk_day(ts: float) -> str:
    et = datetime.fromtimestamp(ts, ET)
    return (et - timedelta(hours=DAY_START_HOUR_ET)).date().isoformat()


def hms(ts: Any) -> str:
    try:
        return datetime.fromtimestamp(float(ts), ET).strftime("%H:%M:%S")
    except (TypeError, ValueError, OverflowError, OSError):
        return "—"


def px(v: Any) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{f:.4f}" if abs(f) < 1 else f"{f:.2f}"


def orders(lines: list[dict[str, Any]], date: str) -> list[dict[str, Any]]:
    """Each order the bot sent on ``date`` (an ``order`` or ``closed`` line) with its fill (the ``filled`` line of
    the same order id), oldest first. Pure."""
    mine = [r for r in lines if r.get("action") == ACTION and desk_day(float(r.get("timestamp") or 0)) == date]
    fills = {(r.get("inputs") or {}).get("order_id") or r.get("order_id"): r for r in mine if r.get("outcome") == "filled"}
    out = []
    for r in mine:
        if r.get("outcome") not in ("order", "closed"):
            continue
        inp = r.get("inputs") or {}
        oid = r.get("order_id") or inp.get("order_id")
        fill = fills.get(oid) or {}
        fin = fill.get("inputs") or {}
        ibkr = fin.get("ibkr") or {}
        change = inp.get("change") or {}
        fill_price = fin.get("fill_price")
        last = ibkr.get("last")
        try:
            vs = round(float(fill_price) - float(last), 4)
        except (TypeError, ValueError):
            vs = None
        out.append({
            "sent_ts": r.get("timestamp"), "host": inp.get("host"), "symbol": inp.get("symbol"), "side": inp.get("side"),
            "step": inp.get("step") or ("close" if r.get("outcome") == "closed" else None),
            "change": change.get("kind"), "change_ts": change.get("ts"), "their_price": change.get("price"),
            "late_sec": inp.get("late_sec"), "qty": inp.get("qty"), "limit": inp.get("limit"), "order_id": oid,
            "fill_price": fill_price, "fill_basis": fin.get("fill_basis"), "fill_ts": fin.get("fill_ts"),
            "ibkr_last": last, "ibkr_last_ts": ibkr.get("last_ts"), "ibkr_bid": ibkr.get("bid"),
            "ibkr_ask": ibkr.get("ask"), "fill_minus_last": vs, "filled": bool(fill), "why": r.get("reason"),
        })
    return out


def skips(lines: list[dict[str, Any]], date: str) -> list[dict[str, Any]]:
    """Every skip of the day, oldest first. Pure."""
    return [{"ts": r.get("timestamp"), "host": (r.get("inputs") or {}).get("host"),
             "symbol": (r.get("inputs") or {}).get("symbol"), "code": (r.get("inputs") or {}).get("code"),
             "why": r.get("reason")}
            for r in lines if r.get("action") == ACTION and r.get("outcome") == "skipped"
            and desk_day(float(r.get("timestamp") or 0)) == date]


def markdown(date: str, rows: list[dict[str, Any]], skipped: list[dict[str, Any]]) -> str:
    head = [f"# Live Trader bot -- {date}", "",
            f"{len(rows)} orders sent, {sum(1 for r in rows if r['filled'])} filled; {len(skipped)} skips.", "",
            "| Sent (ET) | Host | Step | Stock | Their change | Shown (ET) | Late (s) | Order | Fill | Basis "
            "| IBKR last | Bid x ask | Fill − last |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    body = []
    for r in rows:
        order = f"{r['qty'] or '—'} @ {px(r['limit'])}" if r["limit"] is not None else f"{r['qty'] or '—'} @ mkt"
        cells = [
            hms(r["sent_ts"]), str(r["host"]), str(r["step"]), f"{r['symbol']} {r['side'] or ''}".strip(),
            f"{r['change']} {px(r['their_price'])}" if r["their_price"] is not None else str(r["change"]),
            hms(r["change_ts"]), "—" if r["late_sec"] is None else f"{r['late_sec']:.1f}", order,
            px(r["fill_price"]) if r["filled"] else "not filled", str(r["fill_basis"] or "—"), px(r["ibkr_last"]),
            f"{px(r['ibkr_bid'])} x {px(r['ibkr_ask'])}",
            "—" if r["fill_minus_last"] is None else f"{r['fill_minus_last']:+.4f}"]
        body.append("| " + " | ".join(cells) + " |")
    counts = Counter(s["code"] for s in skipped)
    tail = ["", "## Skips", ""] + [f"- {code}: {n}" for code, n in counts.most_common()]
    tail += ["", "| Time (ET) | Host | Stock | Reason |", "|---|---|---|---|"]
    tail += [f"| {hms(s['ts'])} | {s['host']} | {s['symbol']} | {s['why']} |" for s in skipped]
    return "\n".join(head + body + tail) + "\n"


def _fetch(api: str) -> list[dict[str, Any]]:
    with urllib.request.urlopen(f"{api}/api/bot/audit?limit={AUDIT_LINES}", timeout=30) as resp:  # noqa: S310 -- localhost
        return list(json.loads(resp.read().decode("utf-8")).get("entries") or [])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", help="the desk's day, YYYY-MM-DD (default: today)")
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--md", help="also write the report to this Markdown file")
    args = ap.parse_args(argv)
    try:
        lines = _fetch(args.api)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"the backend at {args.api} did not answer: {exc}", file=sys.stderr)
        return 1
    date = args.date or desk_day(datetime.now(ET).timestamp())
    rows, skipped = orders(lines, date), skips(lines, date)
    if args.json:
        print(json.dumps({"date": date, "orders": rows, "skips": skipped}, indent=1))
        return 0
    text = markdown(date, rows, skipped)
    print(text)
    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
