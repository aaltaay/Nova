"""The first order after a backend start loads nothing (operator report 2026-10-14, GLND order 247).

Order 247 was the first after a restart: it loaded the order path's lazy imports on the way, reached Paper
97 ms after the click instead of the usual 6 to 8, and found the $4.00 offer gone. A fresh interpreter is the
only place a first order is first, so the probe runs in one: it loads the order path the way startup does
(``execution.warm``), then places an order that rests, one that fills and cancels the first, and reports every
module each one loaded.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI

import app_lifespan
from execution import warm
from practice import broker as practice_broker

BACKEND = Path(__file__).resolve().parents[1]

PROBE = r"""
import asyncio, json, os, sys, tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="nova_warm_probe_"))
os.environ.update({"NOVA_CACHE_DIR": str(tmp), "NOVA_LOG_DIR": str(tmp / "logs"),
                   "NOVA_ENV_PATH": str(tmp / "never-written.env"), "IBKR_GATEWAY_MODE": "paper",
                   "IBKR_ENABLED": "true", "IBKR_ORDERS_ENABLED": "true", "NOVA_BROKER": "paper"})
for env in ("NOVA_SIM_CAPTURE_DIR", "NOVA_SIM_HISTORY_DIR", "NOVA_MARKET_DATA_DIR", "NOVA_SHORT_TESTS_DIR"):
    os.environ[env] = str(tmp / env.lower())
os.environ.pop("NOVA_API_KEY", None)

import sim.mode as mode
from execution import service
from execution.models import ExecutionCommand
from execution.warm import warm_order_path
from ibkr import client, safety
from sim.fill_model import Reference

failed = warm_order_path()
from practice import broker as practice_broker

paper = practice_broker.loaded("paper")   # the warm-up opened it; the probe never does
mode.set_venue("paper", persist=False)
client.is_enabled = lambda: True
client.is_connected = lambda: True
book = {"ask": 4.02}
reference = paper.reference if paper is not None else practice_broker.for_venue("paper").reference
reference.reference = lambda symbol: Reference(4.0, 3.99, book["ask"], live=True)
reference.admission = lambda symbol: (True, "OK", None)
safety.arm(True, actor="operator")


def place(key):
    return ExecutionCommand(operation="place", idempotency_key=key, source="manual", symbol="GLND",
                            side="BUY", qty=100.0, order_type="LMT", limit_price=4.0, skip_risk=True)


async def run():
    out, resting = [], None
    for op in ("rests", "fills", "cancel"):
        if op == "fills":
            book["ask"] = 4.0
        cmd = (ExecutionCommand(operation="cancel", idempotency_key="cancel", source="manual", order_id=resting)
               if op == "cancel" else place(op))
        before = set(sys.modules)
        receipt = await service.execute(cmd)
        if op == "rests":
            resting = receipt.order_id
        out.append({"op": op, "ok": receipt.ok, "broker_status": receipt.broker_status, "error": receipt.error,
                    "loaded": sorted(set(sys.modules) - before)})
    return out

print("PROBE " + json.dumps({"failed": failed, "paper_open": paper is not None, "orders": asyncio.run(run())}))
"""


def _probe() -> dict:
    done = subprocess.run([sys.executable, "-c", PROBE], cwd=str(BACKEND), capture_output=True, text=True,
                          timeout=180)
    line = next((ln for ln in done.stdout.splitlines() if ln.startswith("PROBE ")), None)
    assert line is not None, f"probe printed no result (exit {done.returncode}):\n{done.stderr[-4000:]}"
    return json.loads(line[len("PROBE "):])


def test_the_first_order_after_a_start_loads_no_module():
    got = _probe()
    assert got["failed"] == []
    assert got["paper_open"] is True, "the warm-up did not open the Paper account; the first order would"
    rests, fills, cancel = got["orders"]
    assert (rests["ok"], rests["broker_status"]) == (True, "Submitted"), rests
    assert (fills["ok"], fills["broker_status"]) == (True, "Filled"), fills
    assert (cancel["ok"], cancel["broker_status"]) == (True, "Cancelled"), cancel
    for order in got["orders"]:
        # A module named here is imported inside the order path: add it to execution.warm.ORDER_PATH_MODULES.
        assert order["loaded"] == [], f"the first {order['op']} loaded {order['loaded']}"


def test_a_module_that_will_not_load_is_named_and_the_rest_still_load(monkeypatch, caplog):
    loaded: list[str] = []
    opened: list[str] = []

    class Broker:
        @staticmethod
        def for_venue(venue):
            opened.append(venue)
            raise OSError("ledger unreadable")

    def load(name: str):
        if name == "sim.execution":
            raise ImportError("broken on purpose")
        loaded.append(name)
        return Broker

    monkeypatch.setattr(warm, "import_module", load)
    with caplog.at_level("ERROR", logger="execution.warm"):
        assert warm.warm_order_path() == ["sim.execution", warm.PAPER_BROKER]
    assert loaded[:-1] == [m for m in warm.ORDER_PATH_MODULES if m != "sim.execution"]
    assert opened == ["paper"]
    assert "could not load sim.execution before the first order" in caplog.text
    assert "could not open the Paper account before the first order" in caplog.text


@pytest.mark.parametrize("name", warm.ORDER_PATH_MODULES)
def test_every_warmed_module_exists(name):
    assert (BACKEND / (name.replace(".", "/") + ".py")).is_file() or (BACKEND / name.replace(".", "/") / "__init__.py").is_file()


def test_two_threads_asking_for_the_paper_broker_get_one(monkeypatch):
    """Startup opens Paper off the request loop while the loop may ask for it: one ledger, read once."""
    reads, gate = [], threading.Event()
    real = practice_broker._paper_ledger

    def slow_ledger(path, now):
        reads.append(path)
        gate.wait(5)
        return real(path, now)

    practice_broker.reset_for_tests("paper")
    monkeypatch.setattr(practice_broker, "_paper_ledger", slow_ledger)
    got: list = []
    threads = [threading.Thread(target=lambda: got.append(practice_broker.for_venue("paper"))) for _ in range(2)]
    for t in threads:
        t.start()
    time.sleep(0.05)
    gate.set()
    for t in threads:
        t.join(5)
    try:
        assert len(got) == 2 and got[0] is got[1]
        assert len(reads) == 1
    finally:
        practice_broker.reset_for_tests("paper")


def test_startup_warms_the_trading_path_before_restore_databases_and_ibkr(monkeypatch):
    order: list[str] = []
    monkeypatch.setattr(app_lifespan, "init_sentry", lambda: order.append("sentry"))
    monkeypatch.setattr(app_lifespan, "_warm_trading_path", lambda took: order.append("warm"))
    monkeypatch.setattr(app_lifespan, "_restore_caches", lambda: order.append("restore"))
    monkeypatch.setattr(app_lifespan, "_init_databases", lambda took: order.append("db"))

    async def body() -> None:
        reached = asyncio.Event()

        async def ibkr_side() -> None:   # the API health mark, then IBKR's connect, come after the local startup
            order.append("network")
            reached.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(app_lifespan, "_mark_nova_api_health", ibkr_side)
        async with app_lifespan.lifespan(FastAPI()):
            await asyncio.wait_for(reached.wait(), 3.0)

    asyncio.run(body())
    assert order == ["sentry", "warm", "restore", "db", "network"]
