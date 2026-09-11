#!/usr/bin/env python3
"""Broker-free probe of the spend gates that decide whether money can move.

Drives the real FastAPI app (`main:app`) over `TestClient` with the broker
adapter stubbed at `ibkr.orders` only, so every assertion runs through the
production `execution.service.execute` + `ibkr.safety` code paths. No IB
Gateway, no network, no order ever reaches a broker.

Covers the three gates that let money out:
  - D-038 / ADR 013 -- a live place needs `broker_account_kind == "live"`;
    `unknown` and `paper` behind a live door must refuse, and `spend_status`
    must never read `live_armed` over a non-live account.
  - D-037 -- a tripped kill switch refuses every place from every source
    (including `skip_risk=True` manual / hotkey routes), survives a restart,
    and still lets the operator cancel.
  - ADR 007 -- every refusal leaves a persisted `rejected` ledger row.

Usage (from repo root):
  py -3 tools/execution_safety_probe.py

Exit code 0 = every gate held. Non-zero = a gate that guards spending failed;
do not trade until it is understood.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

RULE = "-" * 74


def _pin_isolated_env() -> Path:
    """Never touch the operator cache or read their real .env gates."""
    cache = Path(tempfile.mkdtemp(prefix="nova_safety_probe_"))
    os.environ["NOVA_CACHE_DIR"] = str(cache)
    # This harness serves requests in-process via TestClient and never binds
    # the API port, which is exactly the shape `api_process_guard` exists to
    # kill (D-005 dark-port orphan). Opt out of the instance lock so the probe
    # is not shot mid-run, and so it never claims a real operator's lock.
    os.environ["NOVA_SKIP_INSTANCE_LOCK"] = "1"
    os.environ["IBKR_ENABLED"] = "true"
    os.environ["IBKR_ORDERS_ENABLED"] = "true"
    os.environ["IBKR_GATEWAY_MODE"] = "live"
    os.environ["IBKR_LIVE_TRADING_CONFIRMED"] = "true"
    return cache


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def section(self, title: str) -> None:
        print(RULE)
        print(title)
        print(RULE)

    def fact(self, label: str, value: object) -> None:
        print(f"  {label:<30} {value}")

    def check(self, name: str, ok: bool) -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            self.failures.append(name)


def _place(client, key: str) -> dict:
    return client.post(
        "/api/ibkr/order",
        json={
            "symbol": "AAPL", "side": "BUY", "qty": 1,
            "order_type": "LMT", "limit_price": 1.0,
            "idempotency_key": key,
        },
    ).json()


def _probe_account_pin(client, rep: Report, client_mod, sent: list) -> None:
    """D-038 -- the IB account class decides live spend, not the env door."""
    for kind, expect_armed in (("unknown", False), ("paper", False), ("live", True)):
        rep.section(f"D-038  live door + broker_account_kind={kind}")
        client_mod.broker_account_kind = staticmethod(lambda k=kind: k)
        sent.clear()
        status = client.get("/api/ibkr/status").json()
        rep.fact("spend_status", status["spend_status"])
        rep.fact("armed_for_account_kind", status["armed_for_account_kind"])
        rep.fact("spend_locked_reason", status["spend_locked_reason"])
        result = _place(client, f"probe-{kind}")
        rep.fact("place ok", result["ok"])
        rep.fact("place reason_code", result["reason_code"])
        rep.fact("place error", result["error"])
        rep.fact("broker place calls", len(sent))

        if expect_armed:
            rep.check(
                "a genuinely live account still reaches the broker",
                status["spend_status"] == "live_armed"
                and status["armed_for_account_kind"] == "live"
                and result["ok"] is True
                and len(sent) == 1,
            )
        else:
            rep.check(
                f"{kind!r} account never reads live_armed",
                status["spend_status"] == "locked_account_unconfirmed"
                and status["armed_for_account_kind"] is None,
            )
            rep.check(
                f"{kind!r} account cannot place, with zero broker calls",
                result["ok"] is False and sent == [],
            )


def _probe_kill_latch(client, rep: Report, cache: Path, sent: list) -> None:
    """D-037 -- kill is a spend latch across every source and a restart."""
    import strategy.executor as executor

    rep.section("D-037  manual place under a tripped kill (skip_risk=True route)")
    sent.clear()
    kill = client.post("/api/strategy/executor/kill-switch").json()
    rep.fact("kill_switch_tripped", kill["kill_switch_tripped"])
    result = _place(client, "probe-kill-manual")
    rep.fact("place reason_code", result["reason_code"])
    rep.fact("place error", result["error"])
    rep.fact("broker place calls", len(sent))
    rep.check(
        "manual / hotkey place refused while killed",
        result["ok"] is False
        and result["reason_code"] == "KILL_SWITCH"
        and sent == [],
    )

    row = client.get(f"/api/ibkr/execution/{result['execution_id']}").json()
    rep.fact("ledger status", row["status"])
    rep.fact("ledger reason_code", row["reason_code"])
    rep.check(
        "the refusal is persisted in the ledger (ADR 007)",
        row["status"] == "rejected" and row["reason_code"] == "KILL_SWITCH",
    )

    rep.section("D-037  cancel is never blocked by a kill")
    sent.clear()
    cancel = client.delete("/api/ibkr/order/4242").json()
    rep.fact("cancel ok", cancel["ok"])
    rep.fact("cancel error", cancel["error"])
    rep.fact("broker cancel calls", len(sent))
    rep.check(
        "the operator can still get flat after a kill",
        cancel["ok"] is True and len(sent) == 1,
    )

    rep.section("D-037  the latch survives an API restart")
    latch = json.loads(
        (cache / "kill_switch_state.json").read_text(encoding="utf-8")
    )
    rep.fact("latch file", json.dumps(latch))
    executor._kill_switch_tripped = None  # what a fresh process sees
    rep.fact("is_kill_switch_tripped()", executor.is_kill_switch_tripped())
    sent.clear()
    result = _place(client, "probe-kill-after-restart")
    rep.fact("place reason_code after restart", result["reason_code"])
    rep.check(
        "a restart does not silently re-arm the desk",
        latch["schema_version"] == 1
        and latch["tripped"] is True
        and executor.is_kill_switch_tripped() is True
        and result["reason_code"] == "KILL_SWITCH",
    )

    rep.section("D-037  an explicit reset is the only way back")
    reset = client.post("/api/strategy/executor/reset-kill-switch").json()
    rep.fact("kill_switch_tripped", reset["kill_switch_tripped"])
    sent.clear()
    result = _place(client, "probe-after-reset")
    rep.fact("place ok", result["ok"])
    rep.fact("broker place calls", len(sent))
    rep.check("reset re-allows places", result["ok"] is True and len(sent) == 1)


def main() -> int:
    cache = _pin_isolated_env()

    from fastapi.testclient import TestClient

    import app_lifespan
    import execution.store as exec_store
    import ibkr.account as account_mod
    import ibkr.client as client_mod
    import ibkr.orders as orders_mod
    import journal.db as journal_db
    import nova_os.events_db as events_db
    import strategy.executor as executor
    from main import app

    exec_store.init_db()
    journal_db.init_db()
    events_db.init_db()

    rep = Report()
    sent: list[dict] = []

    # The real lifespan schedules an IBKR ping + journal replay; neither has
    # anything to do here and the replay would read operator history.
    with patch.object(app_lifespan, "_bootstrap_runtime", AsyncMock()), \
            patch.object(client_mod, "is_enabled", lambda: True), \
            patch.object(client_mod, "is_connected", lambda: True), \
            patch.object(client_mod, "is_ready", lambda: True), \
            patch.object(client_mod, "account_mode", lambda: "live"), \
            patch.object(client_mod, "get_ib", lambda: None), \
            patch.object(orders_mod, "open_orders", lambda: []), \
            patch.object(
                orders_mod, "place_order",
                lambda **kw: sent.append(kw) or {"ok": True, "order_id": 101},
            ), \
            patch.object(
                orders_mod, "cancel_order",
                lambda oid: sent.append({"cancel": oid}) or {"ok": True},
            ), \
            patch.object(
                account_mod, "get_account_summary",
                lambda: {
                    "connected": True, "BuyingPower": 1_000_000.0, "pending": False,
                },
            ), \
            patch.object(account_mod, "get_positions", lambda: []), \
            TestClient(app) as client:
        client_mod._enabled = True
        executor._kill_switch_tripped = False
        _probe_account_pin(client, rep, client_mod, sent)
        client_mod.broker_account_kind = staticmethod(lambda: "live")
        _probe_kill_latch(client, rep, cache, sent)

    print(RULE)
    if rep.failures:
        print(f"RESULT: {len(rep.failures)} SPEND GATE(S) FAILED -> {rep.failures}")
        return 1
    print("RESULT: every spend gate held")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
