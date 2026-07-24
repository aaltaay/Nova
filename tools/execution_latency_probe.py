#!/usr/bin/env python3
"""Paper-only execution latency probe (ADR 007).

Guards:
  - Requires --confirm-paper-orders
  - Aborts unless IBKR spend_status is paper_armed and live confirmation is off
  - Cancels benchmark orders and finishes flat when possible

Usage (from repo root, with Gateway paper logged in):
  py -3 tools/execution_latency_probe.py --confirm-paper-orders --synthetic
  py -3 tools/execution_latency_probe.py --confirm-paper-orders --samples 50
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def _abort(msg: str) -> int:
    print(f"ABORT: {msg}", file=sys.stderr)
    return 2


async def _synthetic(samples: int, *, run_id: str | None = None) -> dict:
    """In-process fake broker — isolates validation + SQLite overhead."""
    import execution.service as exec_svc
    import execution.store as store
    import execution.telemetry as telemetry
    import ibkr.account as account_mod
    import ibkr.client as client_mod
    import ibkr.orders as orders_mod
    import ibkr.safety as safety_mod
    from execution.models import ExecutionCommand

    store.init_db()
    telemetry.reset_for_tests()
    client_mod.is_enabled = lambda: True  # type: ignore[method-assign]
    client_mod.is_connected = lambda: True  # type: ignore[method-assign]
    client_mod.account_mode = lambda: "paper"  # type: ignore[method-assign]
    client_mod.broker_account_kind = lambda: "paper"  # type: ignore[method-assign]
    client_mod.get_ib = lambda: None  # type: ignore[method-assign]
    safety_mod.orders_enabled = lambda: True  # type: ignore[method-assign]
    safety_mod.gateway_mode = lambda: "paper"  # type: ignore[method-assign]
    safety_mod.live_trading_confirmed = lambda: False  # type: ignore[method-assign]
    account_mod.get_account_summary = lambda: {  # type: ignore[method-assign]
        "connected": True, "BuyingPower": 1_000_000.0, "pending": False,
    }
    account_mod.get_positions = lambda: []  # type: ignore[method-assign]

    next_id = 1000

    def place(**kw):
        nonlocal next_id
        next_id += 1
        oid = next_id
        # Simulate near-instant broker ack on the watch created after return.
        return {"ok": True, "order_id": oid, "error": None, "mode": "paper"}

    orders_mod.place_order = place  # type: ignore[method-assign]
    orders_mod.cancel_order = lambda oid: {"ok": True}  # type: ignore[method-assign]

    marker = run_id or uuid.uuid4().hex
    prefix = f"bench:synth:{marker}:"
    for i in range(samples):
        key = f"{prefix}place:{i}:{uuid.uuid4()}"
        r = await exec_svc.execute(
            ExecutionCommand(
                operation="place",
                idempotency_key=key,
                source="benchmark",
                symbol="AAPL",
                side="BUY",
                qty=1,
                order_type="LMT",
                limit_price=0.01,
                skip_risk=True,
                skip_concurrency=True,
            ),
            wait_ack=False,
        )
        if r.order_id:
            watch = telemetry.watch_order(int(r.order_id))
            watch.note_status("Submitted")
            watch.note_execution(
                avg_price=0.01,
                price=0.01,
                shares=1.0,
                cumulative_shares=1.0,
                remaining=0.0,
                complete=True,
            )
            watch.note_filled()
            await exec_svc.execute(
                ExecutionCommand(
                    operation="cancel",
                    idempotency_key=f"{prefix}cancel:{r.order_id}:{uuid.uuid4()}",
                    source="benchmark",
                    order_id=int(r.order_id),
                    skip_risk=True,
                    skip_concurrency=True,
                ),
                wait_ack=False,
            )

    summary = exec_svc.latency_summary(
        limit=samples * 2,
        idempotency_prefix=prefix,
    )
    summary["mode"] = "synthetic"
    summary["run_id"] = marker
    return summary


async def _paper_gateway(
    samples: int,
    symbol: str,
    *,
    run_id: str | None = None,
) -> dict:
    from ibkr import client as client_mod
    from ibkr import safety as safety_mod
    import execution.service as exec_svc
    from execution.models import ExecutionCommand

    snap = safety_mod.status_snapshot()
    if snap.get("spend_status") != "paper_armed":
        raise RuntimeError(
            f"spend_status={snap.get('spend_status')!r} — need paper_armed"
        )
    if snap.get("live_trading_confirmed"):
        raise RuntimeError("IBKR_LIVE_TRADING_CONFIRMED is set — refuse probe")
    if client_mod.account_mode() != "paper":
        raise RuntimeError(f"account_mode={client_mod.account_mode()!r} — paper only")
    if not client_mod.is_connected():
        raise RuntimeError("IBKR not connected")

    placed: list[int] = []
    marker = run_id or uuid.uuid4().hex
    prefix = f"bench:paper:{marker}:"
    for index in range(samples):
        key = f"{prefix}place:{index}:{uuid.uuid4()}"
        r = await exec_svc.execute(
            ExecutionCommand(
                operation="place",
                idempotency_key=key,
                source="benchmark",
                symbol=symbol,
                side="BUY",
                qty=1,
                order_type="LMT",
                limit_price=0.01,  # intentionally non-marketable
                skip_risk=True,
                skip_concurrency=True,
            ),
            wait_ack=True,
        )
        if r.order_id:
            placed.append(int(r.order_id))
            await exec_svc.execute(
                ExecutionCommand(
                    operation="cancel",
                    idempotency_key=f"{prefix}cancel:{r.order_id}:{uuid.uuid4()}",
                    source="benchmark",
                    order_id=int(r.order_id),
                    skip_risk=True,
                    skip_concurrency=True,
                ),
                wait_ack=False,
            )
        await asyncio.sleep(0.05)

    summary = exec_svc.latency_summary(
        limit=samples * 2,
        idempotency_prefix=prefix,
    )
    summary["mode"] = "paper_gateway"
    summary["run_id"] = marker
    summary["placed_order_ids"] = placed
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--confirm-paper-orders",
        action="store_true",
        required=True,
        help="Required acknowledgement that this may send paper orders",
    )
    p.add_argument("--synthetic", action="store_true", help="Fake broker only")
    p.add_argument("--samples", type=int, default=50)
    p.add_argument("--symbol", default="AAPL")
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args()

    if not args.confirm_paper_orders:
        return _abort("pass --confirm-paper-orders")

    t0 = time.perf_counter()
    try:
        if args.synthetic:
            summary = asyncio.run(_synthetic(args.samples))
        else:
            summary = asyncio.run(_paper_gateway(args.samples, args.symbol.upper()))
    except Exception as exc:
        return _abort(str(exc))

    summary["wall_sec"] = round(time.perf_counter() - t0, 3)
    print(json.dumps(summary, indent=2))
    if args.json_out:
        args.json_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    ack = (summary.get("broker_ack_ms") or {}).get("p95")
    if ack is None:
        print("NOTE: no ack samples recorded — check telemetry wiring", file=sys.stderr)
        return 1
    if ack > 250.0:
        print(f"SLA MISS: p95 ack {ack:.1f} ms > 250 ms", file=sys.stderr)
        return 1
    print(f"SLA PASS: p95 ack {ack:.1f} ms <= 250 ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
