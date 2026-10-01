"""Kill switch (D-037, ADR 025): a persisted latch that blocks every place, and a sweep of every venue.

Ported from the retired Phase D executor tests. No live IB Gateway: IBKR calls
are mocked; the latch file lives in the per-test cache dir (conftest).

Spec D (2026-09-30), #656: the sweep cancels the working orders of every venue that has any --
Live while IBKR is connected, Paper always (even with the Gateway down), Sim when a scratch
ledger is loaded -- each through the execution door with an explicit target venue, on the
caller's own loop. A read that fails is a stated failure, never "nothing to cancel".
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kill_switch
import nova_os.events_db as events_db
from execution import inflight
from ibkr import client as client_mod
from kill_switch import state as kill_state
from kill_switch import sweep as kill_sweep
from practice import broker as practice_broker
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue


@pytest.fixture(autouse=True)
def _events_db():
    events_db.init_db()


def _trip() -> dict:
    return asyncio.run(kill_switch.trip())


def _venues(monkeypatch, live=None, paper=None, sim=None):
    """Each venue's working orders as rows (None: that venue holds none); cancels recorded, not sent."""
    sent: list[tuple[str, int]] = []
    monkeypatch.setattr(kill_sweep, "_live_rows", lambda: (list(live or []), None, None))
    monkeypatch.setattr(kill_sweep, "_paper_rows", lambda: (list(paper or []), None, None))
    monkeypatch.setattr(kill_sweep, "_sim_rows", lambda: (list(sim or []), None, None))

    async def fake_cancel(venue, order_id, symbol):
        sent.append((venue, order_id))
        return True, None

    monkeypatch.setattr(kill_sweep, "cancel_via_door", fake_cancel)
    return sent


def _by_venue(result: dict) -> dict:
    return {row["venue"]: row for row in result["sweep"]}


class TestLatch:
    def test_clean_cache_dir_is_not_tripped(self):
        assert kill_switch.is_tripped() is False

    def test_trip_persists_across_process_restart(self, monkeypatch):
        _venues(monkeypatch)
        assert _trip()["persisted"] is True
        kill_switch.reset_for_tests()  # a fresh process reads the latch from disk
        assert kill_switch.is_tripped() is True
        assert kill_switch.status()["tripped"] is True

    def test_reset_persists_across_process_restart(self, monkeypatch):
        _venues(monkeypatch)
        _trip()
        assert kill_switch.reset()["persisted"] is True
        kill_switch.reset_for_tests()
        assert kill_switch.is_tripped() is False

    def test_a_latch_that_cannot_be_written_says_so(self, monkeypatch):
        _venues(monkeypatch)
        monkeypatch.setattr(kill_state, "_path", lambda: Path("Z:/no/such/dir/kill.json"))
        result = _trip()
        assert result["tripped"] is True and result["persisted"] is False

    def test_unreadable_latch_fails_tripped(self):
        kill_state._path().write_text("{not json", encoding="utf-8")
        assert kill_switch.is_tripped() is True

    def test_unknown_schema_version_fails_tripped(self):
        kill_state._path().write_text(
            json.dumps({"schema_version": 99, "tripped": False}), encoding="utf-8",
        )
        assert kill_switch.is_tripped() is True

    def test_trip_writes_a_receipt_stamped_with_the_desk_venue(self, monkeypatch):
        from nova_os.events import get_events

        reset_venue()
        try:
            set_venue("paper", persist=False)
            _venues(monkeypatch, paper=[{"order_id": 4, "symbol": "AAPL"}])
            result = _trip()
        finally:
            reset_venue()
        assert result["receipt_error"] is None
        event = get_events(limit=5)[0]
        assert event["payload"]["event"] == "kill_switch"
        assert event["payload"]["venue"] == "paper"
        assert event["mode"] is None                                  # never the retired Nova OS "signal"
        assert {row["venue"] for row in event["payload"]["sweep"]} == {"live", "paper", "sim"}


class TestSweep:
    def test_every_venues_working_orders_are_cancelled_live_first(self, monkeypatch):
        sent = _venues(
            monkeypatch,
            live=[{"order_id": 55, "symbol": "TSLA"}],
            paper=[{"order_id": 3, "symbol": "AAPL"}, {"order_id": 4, "symbol": "IMCC"}],
            sim=[{"order_id": 3, "symbol": "GRML"}],
        )
        result = _trip()
        assert sent == [("live", 55), ("paper", 3), ("paper", 4), ("sim", 3)]
        venues = _by_venue(result)
        assert venues["live"]["cancelled"] == [55] and venues["paper"]["cancelled"] == [3, 4]
        assert venues["sim"]["cancelled"] == [3]
        assert result["tripped"] is True
        assert result["cancelled_order_ids"] == [55, 3, 4, 3]       # legacy: every venue's, summed
        assert result["failed_cancel_order_ids"] == []

    def test_the_latch_is_set_before_the_sweep(self, monkeypatch):
        seen: list[bool] = []
        _venues(monkeypatch, paper=[{"order_id": 7}])

        async def watch(venue, order_id, symbol):
            seen.append(kill_switch.is_tripped())
            return True, None

        monkeypatch.setattr(kill_sweep, "cancel_via_door", watch)
        _trip()
        assert seen == [True]

    def test_live_with_the_gateway_down_is_stated_and_paper_is_still_swept(self, monkeypatch):
        """#656: Paper's orders are cancelled with the Gateway down; Live says why it was not swept."""
        sent = _venues(monkeypatch, paper=[{"order_id": 9, "symbol": "AAPL"}])
        monkeypatch.setattr(kill_sweep, "_live_rows", _real_live_rows)
        monkeypatch.setattr(client_mod, "is_connected", lambda: False)
        result = _trip()
        venues = _by_venue(result)
        assert venues["live"]["error"] == "Gateway disconnected: Live orders were not swept"
        assert venues["live"]["cancelled"] == []
        assert venues["paper"]["cancelled"] == [9] and sent == [("paper", 9)]

    def test_a_failed_read_is_a_failure_never_nothing_to_cancel(self, monkeypatch):
        _venues(monkeypatch)

        def unreadable():
            raise OSError("practice-paper.json locked")

        monkeypatch.setattr(kill_sweep, "_paper_rows", unreadable)
        venues = _by_venue(_trip())
        assert "could not be read" in venues["paper"]["error"]
        assert "practice-paper.json locked" in venues["paper"]["error"]

    def test_a_refused_cancel_is_listed_with_its_reason(self, monkeypatch):
        _venues(monkeypatch, paper=[{"order_id": 9}, {"order_id": 10}])

        async def refuse_nine(venue, order_id, symbol):
            return (False, "order 9 not open") if order_id == 9 else (True, None)

        monkeypatch.setattr(kill_sweep, "cancel_via_door", refuse_nine)
        result = _trip()
        paper = _by_venue(result)["paper"]
        assert paper["failed"] == [9] and paper["cancelled"] == [10]
        assert "order 9 not open" in paper["error"]
        assert result["failed_cancel_order_ids"] == [9]
        assert kill_switch.is_tripped() is True

    def test_an_order_nova_cannot_cancel_is_named(self, monkeypatch):
        _venues(monkeypatch, live=[{"order_id": 0, "symbol": "SPY", "perm_id": 123}])
        live = _by_venue(_trip())["live"]
        assert live["cancelled"] == [] and "cancel it in TWS" in live["error"] and "123" in live["error"]

    def test_sim_with_nothing_loaded_says_so(self, monkeypatch):
        practice_broker.reset_for_tests("sim")
        monkeypatch.setattr(client_mod, "is_connected", lambda: False)
        _venues(monkeypatch)
        monkeypatch.setattr(kill_sweep, "_sim_rows", _real_sim_rows)
        sim = _by_venue(_trip())["sim"]
        assert sim["error"] is None and sim["cancelled"] == [] and "not open in this process" in sim["note"]


_real_live_rows = kill_sweep._live_rows
_real_sim_rows = kill_sweep._sim_rows


class FakeLive:
    """A live market that prices AAPL and never prints on its own."""

    def reference(self, symbol: str) -> Reference:
        return Reference(10.0, 9.98, 10.02, live=True)

    def admission(self, symbol: str):
        return True, "OK", None

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return 1_700_000_000.0

    def session_close_ts(self, ts: float) -> float:
        return ts + 86_400


class TestThroughTheDoor:
    """The real door, the real Paper ledger: the desk on Live with IBKR down, Paper's order cancelled."""

    @pytest.fixture
    def paper_order(self, monkeypatch):
        reset_venue()
        practice_broker.reset_for_tests()
        inflight.reset_for_tests()
        monkeypatch.setattr(practice_broker, "LiveReference", lambda: FakeLive())
        broker = practice_broker.for_venue("paper")
        raw = broker.place("AAPL", "BUY", 1, "LMT", limit_price=9.0)
        assert raw["broker_status"] == "Submitted"
        set_venue("live", persist=False)
        monkeypatch.setattr(client_mod, "is_connected", lambda: False)
        yield SimpleNamespace(broker=broker, order_id=int(raw["order_id"]))
        practice_broker.reset_for_tests()
        reset_venue()

    def test_papers_order_is_cancelled_from_a_live_desk_with_the_gateway_down(self, paper_order):
        result = _trip()
        venues = _by_venue(result)
        assert venues["paper"]["cancelled"] == [paper_order.order_id]
        assert venues["paper"]["error"] is None
        assert paper_order.broker.working_orders() == []
        assert venues["live"]["error"] == "Gateway disconnected: Live orders were not swept"

    def test_the_sweep_waits_for_the_doors_lock_on_the_same_loop(self, paper_order, monkeypatch):
        """#656: the cancels ran under asyncio.run, a second loop that raised on the held lock."""
        from execution import service

        # A lock first contended under another test's loop is bound to that loop for good --
        # the very failure this test is about; this one starts unbound.
        monkeypatch.setattr(service, "_lock", asyncio.Lock())

        async def scenario() -> dict:
            async with service._lock:                       # an order is being checked right now
                pending = asyncio.ensure_future(kill_switch.trip())
                await asyncio.sleep(0.05)
                assert not pending.done()                   # the sweep waits its turn
            return await pending

        result = asyncio.run(scenario())
        assert _by_venue(result)["paper"]["cancelled"] == [paper_order.order_id]


class TestRoutes:
    def test_status_trip_reset(self, monkeypatch):
        from main import app

        _venues(monkeypatch, paper=[{"order_id": 2, "symbol": "AAPL"}])
        client = TestClient(app)
        assert client.get("/api/kill-switch").json()["tripped"] is False
        tripped = client.post("/api/kill-switch").json()
        assert tripped["tripped"] is True
        assert _by_venue(tripped)["paper"]["cancelled"] == [2]
        assert client.get("/api/kill-switch").json()["tripped"] is True
        assert client.post("/api/kill-switch/reset").json()["tripped"] is False

    def test_retired_executor_routes_are_gone(self):
        from main import app

        client = TestClient(app)
        assert client.get("/api/strategy/executor/status").status_code == 404
        assert client.get("/api/nova-os/decide").status_code == 404
