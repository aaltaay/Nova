"""
Regression suite for Level 2 / IBKR depth stability.

Locks in failure modes from PROBLEM_LOG 2026-07-13:
  - Symbol cap reached while browsing (slot leak / no eviction)
  - Concurrent subscribe races firing multiple reqMktDepth
  - Transient empty DOM frames blanking a thin overnight book
  - MM / marketMaker forwarding for DAS montage labels
  - stream() heartbeats so WS clients do not starve

No live IB Gateway required — all IB calls are faked.
"""
from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

import pytest

from constants import IBKR_DEPTH_NUM_ROWS, IBKR_DEPTH_SMART, IBKR_MAX_DEPTH_SYMBOLS
from metrics import op_metrics


@pytest.fixture(autouse=True)
def reset_op_metrics():
    op_metrics.reset_for_tests()
    yield
    op_metrics.reset_for_tests()


class _FakeEvent:
    def __init__(self):
        self._listeners = []

    def __iadd__(self, fn):
        self._listeners.append(fn)
        return self

    def __isub__(self, fn):
        if fn in self._listeners:
            self._listeners.remove(fn)
        return self


class _FakeContract:
    def __init__(self, con_id=0, symbol="X"):
        self.conId = con_id
        self.symbol = symbol


class _FakeTicker:
    def __init__(self):
        self.updateEvent = _FakeEvent()
        self.domBids = []
        self.domAsks = []
        self.bid = None
        self.ask = None
        self.bidSize = None
        self.askSize = None


class _FakeIb:
    def __init__(self, qualify_delay: float = 0.0):
        self.errorEvent = _FakeEvent()
        self.depth_calls: list[dict] = []
        self.cancel_depth_calls: list = []
        self.l1_calls: list = []
        self.cancel_data_calls: list = []
        self._qualify_delay = qualify_delay
        self._next_con_id = 1000

    async def qualifyContractsAsync(self, contract):
        if self._qualify_delay:
            await asyncio.sleep(self._qualify_delay)
        self._next_con_id += 1
        contract.conId = self._next_con_id
        return [contract]

    def reqMktDepth(self, contract, numRows=5, isSmartDepth=False, mktDepthOptions=None):
        self.depth_calls.append(
            {"symbol": getattr(contract, "symbol", "?"), "numRows": numRows, "isSmartDepth": isSmartDepth}
        )
        return _FakeTicker()

    def cancelMktDepth(self, contract, isSmartDepth=False):
        self.cancel_depth_calls.append((getattr(contract, "symbol", "?"), isSmartDepth))

    def reqMktData(self, contract, *_args):
        self.l1_calls.append(getattr(contract, "symbol", "?"))
        return _FakeTicker()

    def cancelMktData(self, contract):
        self.cancel_data_calls.append(getattr(contract, "symbol", "?"))


@pytest.fixture
def depth(monkeypatch):
    import ibkr.depth as depth_mod
    import ibkr.client as client_mod

    importlib.reload(depth_mod)
    depth_mod.reset_all()
    fake_ib = _FakeIb()
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(client_mod, "is_ready", lambda: True)
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    monkeypatch.setattr(depth_mod, "_load_ib_types", lambda: True)
    monkeypatch.setattr(
        depth_mod,
        "_Stock",
        lambda symbol, *a, **k: _FakeContract(0, symbol),
    )
    depth_mod._subscribe_lock = None  # fresh lock per test under running loop
    return depth_mod, fake_ib


class TestConcurrentSubscribeRace:
    def test_same_symbol_concurrent_opens_fire_one_reqMktDepth(self, depth):
        depth_mod, fake_ib = depth
        fake_ib._qualify_delay = 0.05

        async def run():
            results = await asyncio.gather(
                depth_mod.subscribe_async("SHPH"),
                depth_mod.subscribe_async("SHPH"),
                depth_mod.subscribe_async("SHPH"),
            )
            return results

        results = asyncio.run(run())
        assert all(r["ok"] for r in results)
        assert len(fake_ib.depth_calls) == 1
        assert fake_ib.depth_calls[0]["isSmartDepth"] is IBKR_DEPTH_SMART
        assert fake_ib.depth_calls[0]["numRows"] == IBKR_DEPTH_NUM_ROWS
        assert depth_mod.subscribed_symbols() == ["SHPH"]
        stats = op_metrics.snapshot()["operations"]["ibkr.depth.subscribe"]
        assert stats["count"] == 1
        assert stats["error_count"] == 0


class _DepthRejectedIb(_FakeIb):
    """reqMktDepth always fails (no L2 entitlement) — exercises L1 fallback."""

    def reqMktDepth(self, contract, numRows=5, isSmartDepth=False, mktDepthOptions=None):
        raise RuntimeError("no market data permissions for depth")


@pytest.fixture
def ticks_clean():
    """Empty ibkr.ticks owner map + a lock bound to the test's own loop."""
    import ibkr.ticks as ticks_mod

    ticks_mod._subs.clear()
    ticks_mod._subscribe_lock = None
    yield ticks_mod
    ticks_mod._subs.clear()
    ticks_mod._subscribe_lock = None


class TestDepthL1FallbackReusesTicksStream:
    """When depth is unavailable, the L1 fallback must go through ibkr.ticks.

    ``IB.reqMktData`` is idempotent per qualified contract, so a private line
    hands back the same pooled ticker while depth's ``cancelMktData`` would
    close the desk's stream (D-020). The fallback therefore takes an owner on
    the shared line and releases it on unsubscribe.
    """

    def test_attaches_to_existing_ticks_stream_instead_of_second_reqmktdata(
        self, depth, ticks_clean, monkeypatch,
    ):
        depth_mod, _ = depth
        fake_ib = _DepthRejectedIb()
        import ibkr.client as client_mod
        monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)

        async def scenario():
            assert await ticks_clean.subscribe("AAPL", ticks_clean.OWNER_SCANNER)
            return await depth_mod.subscribe_async("AAPL")

        result = asyncio.run(scenario())
        assert result["ok"] is True
        assert fake_ib.l1_calls == ["AAPL"]  # scanner's line only, no second one
        assert ticks_clean.owners_for("AAPL") == {"scanner", "depth"}
        stats = op_metrics.snapshot()["operations"]["ibkr.depth.subscribe"]
        assert stats["count"] == 1
        assert stats["error_count"] == 1
        from ibkr.depth import state as depth_state
        assert depth_state.is_shared_l1("AAPL") is True

        depth_mod.unsubscribe("AAPL")
        assert fake_ib.cancel_data_calls == []  # scanner still owns the line
        assert ticks_clean.owners_for("AAPL") == {"scanner"}

    def test_takes_a_ticks_owner_when_no_stream_exists(
        self, depth, ticks_clean, monkeypatch,
    ):
        depth_mod, _ = depth
        fake_ib = _DepthRejectedIb()
        import ibkr.client as client_mod
        monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)

        result = asyncio.run(depth_mod.subscribe_async("AAPL"))
        assert result["ok"] is True
        assert fake_ib.l1_calls == ["AAPL"]  # opened once, owned by ticks
        assert ticks_clean.owners_for("AAPL") == {"depth"}
        from ibkr.depth import state as depth_state
        assert depth_state.is_shared_l1("AAPL") is True

        depth_mod.unsubscribe("AAPL")
        # Last owner left, so ticks -- not depth -- cancelled the line.
        assert fake_ib.cancel_data_calls == ["AAPL"]
        assert ticks_clean.owners_for("AAPL") == set()

    def test_depth_only_unsubscribe_does_not_cancel_ticks_mktdata(
        self, depth, ticks_clean,
    ):
        """reqMktDepth success + tab remount must not steal the focused L1 (#237)."""
        depth_mod, fake_ib = depth
        ticks_clean._subs["DAIC"] = {
            "owners": {ticks_clean.OWNER_DETAIL},
            "ticker": _FakeTicker(),
            "contract": _FakeContract(1, "DAIC"),
            "handler": None,
            "generic_ticks": "233",
            "last_price": 1.0,
            "last_update_ts": None,
        }
        result = asyncio.run(depth_mod.subscribe_async("DAIC"))
        assert result["ok"] is True
        assert fake_ib.depth_calls
        assert ticks_clean.owners_for("DAIC") == {"detail"}

        depth_mod.unsubscribe("DAIC")
        assert fake_ib.cancel_data_calls == []
        assert ticks_clean.owners_for("DAIC") == {"detail"}


class TestCapEvictionForActiveViewer:
    def test_subscribe_at_full_cap_with_live_viewers_is_refused(self, depth):
        """D-027: three live ladders stay; a 4th subscribe is refused."""
        depth_mod, fake_ib = depth
        for i, sym in enumerate(["EHGO", "GFUZ", "LVLU"]):
            depth_mod._subscriptions[sym] = {"bids": [], "asks": [], "l1_fallback": False}
            depth_mod._viewer_queues[sym] = [asyncio.Queue(maxsize=100)]
            depth_mod._contracts[sym] = _FakeContract(10 + i, sym)
            depth_mod._ws_viewers[sym] = 3

        result = asyncio.run(depth_mod.subscribe_async("SHPH"))
        assert result["ok"] is False, result
        assert "cap" in (result.get("error") or "").lower()
        assert "SHPH" not in depth_mod.subscribed_symbols()
        assert set(depth_mod.subscribed_symbols()) == {"EHGO", "GFUZ", "LVLU"}
        assert fake_ib.depth_calls == []

    def test_idle_slot_is_preferred_over_busy_slot(self, depth):
        depth_mod, fake_ib = depth
        depth_mod._subscriptions["BUSY"] = {"bids": [], "asks": [], "l1_fallback": False}
        depth_mod._subscriptions["IDLE"] = {"bids": [], "asks": [], "l1_fallback": False}
        depth_mod._subscriptions["IDLE2"] = {"bids": [], "asks": [], "l1_fallback": False}
        depth_mod._ws_viewers["BUSY"] = 1

        asyncio.run(depth_mod._evict_for_capacity("NEW"))
        assert "BUSY" in depth_mod._subscriptions
        idle_left = [s for s in ("IDLE", "IDLE2") if s in depth_mod._subscriptions]
        assert len(idle_left) == 1
        assert len(depth_mod._subscriptions) == IBKR_MAX_DEPTH_SYMBOLS - 1


class TestMarketMakerForwarding:
    def test_dom_levels_include_mm_for_das_montage(self, depth):
        depth_mod, _fake_ib = depth
        depth_mod._subscriptions["SHPH"] = {"bids": [], "asks": [], "l1_fallback": False}
        depth_mod._viewer_queues["SHPH"] = [asyncio.Queue(maxsize=100)]

        from tests.depth_ticks import depth_ticker

        ticker = depth_ticker(
            bids=[(4.78, 100, "OVERNIGHT"), (4.77, 50, "ISLAND")],
            asks=[(4.83, 200, "OVERNIGHT")],
        )
        depth_mod._on_update_book(ticker, "SHPH")
        book = depth_mod.current_book("SHPH")
        assert book is not None
        assert book["bids"][0]["mm"] == "OVERNIGHT"
        assert book["bids"][1]["mm"] == "ISLAND"
        assert book["asks"][0]["mm"] == "OVERNIGHT"
        assert depth_mod.should_send_current_book(book) is True

    def test_thin_overnight_book_is_sent_to_fresh_ws_viewer(self, depth):
        depth_mod, _fake_ib = depth
        book = {
            "bids": [{"price": 4.78, "size": 100, "side": "bid", "mm": "OVERNIGHT"}],
            "asks": [{"price": 4.83, "size": 200, "side": "ask", "mm": "OVERNIGHT"}],
            "l1_fallback": False,
        }
        assert depth_mod.should_send_current_book(book) is True

    def test_l1_fallback_rows_tag_mm_as_l1(self, depth):
        depth_mod, _fake_ib = depth
        depth_mod._subscriptions["AAPL"] = {"bids": [], "asks": [], "l1_fallback": True}
        depth_mod._viewer_queues["AAPL"] = [asyncio.Queue(maxsize=100)]
        ticker = SimpleNamespace(bid=190.0, bidSize=10, ask=190.1, askSize=12)
        depth_mod._on_update_ticker(ticker, "AAPL")
        book = depth_mod.current_book("AAPL")
        assert book["l1_fallback"] is True
        assert book["bids"][0]["mm"] == "L1"
        assert book["asks"][0]["mm"] == "L1"


class TestStreamHeartbeat:
    def test_stream_yields_none_on_timeout_then_book(self, depth, monkeypatch):
        depth_mod, _fake_ib = depth
        depth_mod._subscriptions["SHPH"] = {"bids": [], "asks": [], "l1_fallback": False}
        q: asyncio.Queue = asyncio.Queue(maxsize=100)

        async def run():
            # Shrink the heartbeat timeout so the test stays fast.
            real_wait_for = asyncio.wait_for

            async def fast_wait_for(awaitable, timeout):
                return await real_wait_for(awaitable, timeout=0.02)

            monkeypatch.setattr(asyncio, "wait_for", fast_wait_for)
            gen = depth_mod.stream(q)
            first = await gen.__anext__()
            assert first is None  # heartbeat
            await q.put({"bids": [{"price": 1.0, "size": 1, "side": "bid", "mm": "OVERNIGHT"}],
                         "asks": [], "l1_fallback": False})
            second = await gen.__anext__()
            assert second["bids"][0]["mm"] == "OVERNIGHT"
            await gen.aclose()

        asyncio.run(run())

    def test_stream_broadcasts_to_two_viewer_queues_of_same_symbol(self, depth):
        """2026-08-25: proved live in tape_stream.py that a single shared
        queue makes concurrent viewers competing consumers -- depth has the
        identical shape, fixed preemptively here before it was reported.
        """
        from ibkr.depth import state as depth_state

        depth_mod, _fake_ib = depth
        depth_mod._subscriptions["SHPH"] = {"bids": [], "asks": [], "l1_fallback": False}
        q1 = depth_mod.open_viewer_queue("SHPH")
        q2 = depth_mod.open_viewer_queue("SHPH")

        depth_state.push_book("SHPH", {"bids": [{"price": 4.5}], "asks": [], "l1_fallback": False})

        assert q1.get_nowait()["bids"][0]["price"] == 4.5
        assert q2.get_nowait()["bids"][0]["price"] == 4.5


class TestViewerLeakDoesNotBlockActiveSymbol:
    def test_live_viewers_are_not_force_evicted(self, depth):
        depth_mod, _fake_ib = depth
        for i in range(IBKR_MAX_DEPTH_SYMBOLS):
            sym = f"SYM{i}"
            depth_mod._subscriptions[sym] = {}
            depth_mod._ws_viewers[sym] = 5
        asyncio.run(depth_mod._evict_for_capacity("EXTRA"))
        assert len(depth_mod._subscriptions) == IBKR_MAX_DEPTH_SYMBOLS
        assert sum(depth_mod._ws_viewers.values()) == 5 * IBKR_MAX_DEPTH_SYMBOLS

    def test_release_grace_lets_strictmode_reattach(self, depth, monkeypatch):
        depth_mod, _fake_ib = depth
        monkeypatch.setattr(depth_mod, "IBKR_DEPTH_RELEASE_GRACE_SEC", 0.05)

        async def scenario():
            depth_mod.ws_viewer_opened("SHPH")
            assert depth_mod.ws_viewer_closed("SHPH") is True
            task = asyncio.create_task(depth_mod.release_when_idle("SHPH"))
            await asyncio.sleep(0.01)
            depth_mod.ws_viewer_opened("SHPH")  # remount reattach
            return await task

        assert asyncio.run(scenario()) is False
        assert depth_mod.viewer_count("SHPH") == 1
