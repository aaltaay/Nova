"""D-006: HTTP yield must not wait on Sentry or disk restore."""
from __future__ import annotations

import asyncio
import threading
import time

from fastapi import FastAPI

import app_lifespan


def test_lifespan_yields_before_sentry_and_restore(monkeypatch):
    """Daily start probes /livez while Sentry/cache/db are still running.

    If those stay on the event loop (or before yield), the listener is dark
    for ~94s and HealthWaitSec expires. Yield first; run them off-loop.
    """
    hold = threading.Event()
    order: list[str] = []

    def sentry() -> bool:
        order.append("sentry_enter")
        hold.wait(timeout=2.0)
        order.append("sentry_done")
        return False

    monkeypatch.setattr(app_lifespan, "init_sentry", sentry)
    monkeypatch.setattr(
        app_lifespan, "_restore_caches", lambda: order.append("restore")
    )
    monkeypatch.setattr(
        app_lifespan, "_init_databases", lambda: order.append("db")
    )

    async def _body() -> None:
        network_started = asyncio.Event()

        async def park_network() -> None:
            network_started.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(app_lifespan, "_mark_nova_api_health", park_network)

        async with app_lifespan.lifespan(FastAPI()):
            for _ in range(100):
                if "sentry_enter" in order:
                    break
                await asyncio.sleep(0.01)
            assert "sentry_enter" in order
            assert "sentry_done" not in order
            t0 = time.monotonic()
            await asyncio.sleep(0.05)
            assert time.monotonic() - t0 < 0.2
            hold.set()
            for _ in range(100):
                if "sentry_done" in order and "restore" in order and "db" in order:
                    break
                await asyncio.sleep(0.01)
            assert "sentry_done" in order
            assert "restore" in order
            assert "db" in order
            for _ in range(50):
                if network_started.is_set():
                    break
                await asyncio.sleep(0.01)
            assert network_started.is_set()

    asyncio.run(asyncio.wait_for(_body(), timeout=3.0))


def test_scan_and_health_do_not_500_during_delayed_restore(monkeypatch):
    """Empty caches during the new listen window must not crash the desk."""
    hold = threading.Event()
    restore_entered = threading.Event()

    def slow_restore() -> None:
        restore_entered.set()
        hold.wait(timeout=5.0)

    monkeypatch.setattr(app_lifespan, "init_sentry", lambda: False)
    monkeypatch.setattr(app_lifespan, "_restore_caches", slow_restore)
    monkeypatch.setattr(app_lifespan, "_init_databases", lambda: None)

    async def park_network() -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(app_lifespan, "_mark_nova_api_health", park_network)

    from fastapi.testclient import TestClient
    from main import app

    try:
        with TestClient(app) as client:
            assert restore_entered.wait(timeout=1.0), "restore should start after yield"
            live = client.get("/livez")
            assert live.status_code == 200
            assert live.json()["status"] == "alive"
            health = client.get("/api/health")
            assert health.status_code == 200
            gappers = client.get("/api/gappers")
            assert gappers.status_code == 200
            assert isinstance(gappers.json()["gappers"], list)
            movers = client.get("/api/movers")
            assert movers.status_code == 200
            assert isinstance(movers.json()["gainers"], list)
            assert isinstance(movers.json()["losers"], list)
            assert not hold.is_set()
    finally:
        hold.set()
