#!/usr/bin/env python3
"""Where each order's time went -- a read-only stage timeline (ADR 007).

Asks the backend that is answering (``/api/ibkr/executions`` and
``/api/ibkr/execution/{id}``), so it always reads the desk's own ledger, and
prints every order's stages on the backend's one clock (``perf_counter_ns``),
measured from the moment Nova received it:

    recorded in the ledger -> checks passed -> sent to the venue ->
    venue answered -> filled -> reply ready (the ticket unlocks on it)

"Venue answered" is IBKR's first status on Live -- a real round trip through
IB Gateway -- and the practice broker's answer on Paper and Sim, which runs
on this PC. The slowest step is marked. Browser stamps are the browser's own
clock and are never subtracted from the backend's; the reply's trip back to
the window and the ticket's repaint are the window's to measure (the desk's
Latency panel). Nothing here places, cancels or changes anything.

Usage (repo root, with the desk running):
  py -3 tools/order_timing.py                  # the last 5 orders
  py -3 tools/order_timing.py --last 10 --venue live
  py -3 tools/order_timing.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

DEFAULT_API = "http://127.0.0.1:8000"
_ET = ZoneInfo("America/New_York")
_ORDER_OPERATIONS = ("place", "bracket", "replace", "cancel")
_PRACTICE = ("paper", "sim")
_VENUE_SCAN = 1000  # rows asked for under --venue; the API caps it at its own query limit


def _ms(end_ns: Any, start_ns: Any) -> float | None:
    try:
        return (int(end_ns) - int(start_ns)) / 1_000_000
    except (TypeError, ValueError):
        return None


def timeline(row: dict[str, Any]) -> dict[str, Any]:
    """One execution row (``/api/ibkr/execution/{id}``) -> its stage timeline. Pure."""
    payload = row.get("payload") or {}
    measurement = payload.get("measurement") or {}
    backend = measurement.get("backend") or {}
    browser = measurement.get("browser") or {}
    received = row.get("received_ns")
    venue = str(row.get("mode") or "unknown")
    answer = row.get("broker_status")
    reply = _ms(backend.get("response_ready_perf_ns"), received)
    if reply is None:
        reply = backend.get("ingress_to_response_ready_ms")
    stages = [
        ("recorded in the ledger", _ms(row.get("persisted_ns"), received)),
        ("checks passed", _ms(row.get("validation_completed_ns"), received)),
        ("sent to the venue", _ms(row.get("broker_sent_ns"), received)),
        ("venue answered", _ms(row.get("broker_ack_ns"), received)),
        ("filled", _ms(row.get("filled_ns"), received)),
        ("reply ready (the ticket unlocks on it)", reply),
    ]
    shown = sorted(((name, at) for name, at in stages if at is not None), key=lambda s: s[1])
    steps, before = [], 0.0
    for name, at in shown:
        steps.append({"stage": name, "at_ms": round(at, 1), "step_ms": round(at - before, 1)})
        before = at
    slowest = max(steps, key=lambda s: s["step_ms"], default=None)
    fill = row.get("complete_fill") or row.get("first_fill") or {}
    return {
        "execution_id": row.get("id"),
        "created_et": _et(row.get("created_ts")),
        "venue": venue,
        "operation": row.get("operation"),
        "source": row.get("source"),
        "symbol": row.get("symbol"),
        "side": payload.get("side"),
        "qty": payload.get("sent_qty") if payload.get("sent_qty") is not None else payload.get("qty"),
        "order_type": payload.get("order_type"),
        "price": payload.get("requested_price"),
        "order_id": row.get("order_id"),
        "status": row.get("status"),
        "answer": answer,
        "error": row.get("error"),
        "steps": steps,
        "slowest": slowest["stage"] if slowest else None,
        "missing": [name for name, at in stages if at is None],
        "venue_leg_ms": _ms(row.get("broker_ack_ns"), row.get("broker_sent_ns")),
        "venue_is_local": venue in _PRACTICE,
        "browser_click_to_request_ms": browser.get("action_to_request_ms") if browser.get("valid") else None,
        "fill_price": fill.get("average_fill_price") or row.get("avg_fill_price"),
        "exchange_ts_utc": fill.get("exchange_ts_utc"),
        "exchange_to_callback_ms": fill.get("exchange_to_callback_ms"),
    }


def _et(ts: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(ts), _ET).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " ET"
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _num(value: Any) -> str:
    return "?" if value is None else f"{value:g}"


def render(tl: dict[str, Any]) -> str:
    """A timeline -> the lines the operator reads. Pure."""
    what = " ".join(
        str(part) for part in (tl["symbol"], tl["side"], _num(tl["qty"]) if tl["qty"] is not None else None,
                               tl["order_type"]) if part
    )
    if tl["price"] is not None:
        what += f" @ {tl['price']:g}"
    head = f"{what or tl['operation']}  {tl['venue']}  order {tl['order_id'] or '-'}  {tl['status']}  {tl['created_et'] or ''}"
    lines = [head.rstrip(), f"  ({tl['operation']}, source {tl['source']}, execution {tl['execution_id']})"]
    if tl["browser_click_to_request_ms"] is not None:
        lines.append(f"  click -> request left the window: {tl['browser_click_to_request_ms']:.1f} ms (browser clock)")
    lines.append("       at      step  stage (from the moment Nova received it)")
    for step in tl["steps"]:
        name = step["stage"]
        if name == "venue answered" and tl["answer"]:
            name += f": {tl['answer']}"
        mark = "   <- slowest step" if step["stage"] == tl["slowest"] and len(tl["steps"]) > 1 else ""
        lines.append(f"  {step['at_ms']:>9,.1f} {step['step_ms']:>9,.1f}  {name}{mark}")
    if tl["venue_leg_ms"] is not None:
        where = "the practice broker on this PC" if tl["venue_is_local"] else "IBKR round trip through IB Gateway"
        lines.append(f"  venue leg (sent -> answered): {tl['venue_leg_ms']:,.1f} ms -- {where}")
    if tl["fill_price"] is not None:
        lines.append(f"  fill price: {tl['fill_price']:g}")
    if tl["exchange_ts_utc"]:
        gap = tl["exchange_to_callback_ms"]
        heard = f", Nova heard it {gap:,.1f} ms later (IBKR's clock vs this PC's)" if gap is not None else ""
        lines.append(f"  IBKR execution time: {tl['exchange_ts_utc']}{heard}")
    missing = [name for name in tl["missing"] if name != "filled"]
    if missing:
        lines.append(f"  not recorded: {', '.join(missing)}")
    if tl["error"]:
        lines.append(f"  error: {tl['error']}")
    return "\n".join(lines)


def _get(api: str, path: str) -> Any:
    with urllib.request.urlopen(f"{api.rstrip('/')}{path}", timeout=10) as resp:  # noqa: S310 -- loopback API
        return json.loads(resp.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--last", type=int, default=5, help="how many orders (default 5)")
    parser.add_argument("--venue", choices=("live", "paper", "sim"), help="only this venue's orders")
    parser.add_argument("--api", default=DEFAULT_API, help=f"the backend to ask (default {DEFAULT_API})")
    parser.add_argument("--json", action="store_true", help="print the timelines as JSON")
    args = parser.parse_args(argv)
    try:
        # A venue filter reaches further back: the newest rows may all be another venue's.
        scan = _VENUE_SCAN if args.venue else max(args.last * 4, 20)
        rows = _get(args.api, f"/api/ibkr/executions?limit={scan}")
        picked = [
            r for r in rows
            if r.get("operation") in _ORDER_OPERATIONS and (args.venue is None or r.get("mode") == args.venue)
        ][: max(1, args.last)]
        timelines = [timeline(_get(args.api, f"/api/ibkr/execution/{r['id']}")) for r in picked]
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"Could not read the backend at {args.api}: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"schema_version": 1, "api": args.api, "orders": timelines}, indent=2))
        return 0
    if not timelines:
        venue = f"{args.venue} " if args.venue else ""
        print(f"No {venue}orders among the {len(rows)} most recent executions.")
        return 0
    print("\n\n".join(render(tl) for tl in timelines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
