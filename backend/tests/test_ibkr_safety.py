"""
Tests for IBKR safety gates and depth-cap logic.
No live IB Gateway required — all tests run with environment mocking.
"""
import asyncio
import os
import importlib
import pytest


def _reload_safety_stack(monkeypatch, env: dict):
    for k in list(os.environ.keys()):
        if k.startswith("IBKR_"):
            monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import ibkr.safety as safety_mod
    import ibkr.client as client_mod
    import ibkr.orders as orders_mod
    importlib.reload(safety_mod)
    importlib.reload(client_mod)
    importlib.reload(orders_mod)
    return safety_mod, client_mod, orders_mod


class TestOrderSafetyGate:
    def test_disabled_blocks_order(self, monkeypatch):
        _safety, _client, orders_mod = _reload_safety_stack(monkeypatch, {})
        result = orders_mod.place_order("AAPL", "BUY", 10)
        assert result["ok"] is False
        assert "IBKR_ENABLED" in result["error"]

    def test_orders_kill_switch_blocks_even_when_connected(self, monkeypatch):
        """Live Gateway + ORDERS_ENABLED=false → no spending."""
        _safety, client_mod, orders_mod = _reload_safety_stack(monkeypatch, {
            "IBKR_ENABLED": "true",
            "IBKR_GATEWAY_MODE": "live",
            "IBKR_ORDERS_ENABLED": "false",
            "IBKR_LIVE_TRADING_CONFIRMED": "false",
        })
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
        monkeypatch.setattr(client_mod, "account_mode", lambda: "live")
        result = orders_mod.place_order("AAPL", "BUY", 10)
        assert result["ok"] is False
        assert "IBKR_ORDERS_ENABLED" in result["error"]

    def test_live_mode_orders_on_without_confirmation_blocks(self, monkeypatch):
        _safety, client_mod, orders_mod = _reload_safety_stack(monkeypatch, {
            "IBKR_ENABLED": "true",
            "IBKR_GATEWAY_MODE": "live",
            "IBKR_ORDERS_ENABLED": "true",
            "IBKR_LIVE_TRADING_CONFIRMED": "false",
        })
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
        monkeypatch.setattr(client_mod, "account_mode", lambda: "live")
        result = orders_mod.place_order("AAPL", "BUY", 10)
        assert result["ok"] is False
        assert "IBKR_LIVE_TRADING_CONFIRMED" in result["error"]

    def test_paper_orders_enabled_passes_gate(self, monkeypatch):
        _safety, client_mod, orders_mod = _reload_safety_stack(monkeypatch, {
            "IBKR_ENABLED": "true",
            "IBKR_GATEWAY_MODE": "paper",
            "IBKR_ORDERS_ENABLED": "true",
        })
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
        monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
        monkeypatch.setattr(client_mod, "broker_account_kind", lambda: "paper")
        monkeypatch.setattr(client_mod, "get_ib", lambda: None)
        result = orders_mod.place_order("AAPL", "BUY", 10)
        assert "IBKR_ORDERS_ENABLED" not in (result.get("error") or "")
        assert "IBKR_LIVE_TRADING_CONFIRMED" not in (result.get("error") or "")
        assert "Paper pin" not in (result.get("error") or "")
        assert result["ok"] is False  # no IB object — gate already passed

    def test_paper_mode_blocks_live_broker_accounts(self, monkeypatch):
        _safety, client_mod, orders_mod = _reload_safety_stack(monkeypatch, {
            "IBKR_ENABLED": "true",
            "IBKR_GATEWAY_MODE": "paper",
            "IBKR_ORDERS_ENABLED": "true",
        })
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
        monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
        monkeypatch.setattr(client_mod, "broker_account_kind", lambda: "live")
        result = orders_mod.place_order("AAPL", "BUY", 10)
        assert result["ok"] is False
        assert "Paper pin" in (result.get("error") or "")

    def test_paper_mode_blocks_unknown_broker_accounts(self, monkeypatch):
        _safety, client_mod, orders_mod = _reload_safety_stack(monkeypatch, {
            "IBKR_ENABLED": "true",
            "IBKR_GATEWAY_MODE": "paper",
            "IBKR_ORDERS_ENABLED": "true",
        })
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
        monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
        monkeypatch.setattr(client_mod, "broker_account_kind", lambda: "unknown")
        result = orders_mod.place_order("AAPL", "BUY", 10)
        assert result["ok"] is False
        assert "Paper pin" in (result.get("error") or "")

    def test_assert_orders_paper_pin_direct(self, monkeypatch):
        safety_mod, _, _ = _reload_safety_stack(monkeypatch, {
            "IBKR_ENABLED": "true",
            "IBKR_GATEWAY_MODE": "paper",
            "IBKR_ORDERS_ENABLED": "true",
        })
        ok, reason = safety_mod.assert_orders_allowed(
            client_enabled=True,
            connected=True,
            account_mode="live",
            broker_account_kind="paper",
        )
        assert ok is False
        assert "Paper pin" in reason

    def test_cancel_allowed_when_orders_locked(self, monkeypatch):
        _safety, client_mod, orders_mod = _reload_safety_stack(monkeypatch, {
            "IBKR_ENABLED": "true",
            "IBKR_GATEWAY_MODE": "live",
            "IBKR_ORDERS_ENABLED": "false",
        })
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
        monkeypatch.setattr(client_mod, "get_ib", lambda: None)
        result = orders_mod.cancel_order(1)
        # Gate allows cancel; fails only on missing IB
        assert "IBKR_ORDERS_ENABLED" not in (result.get("error") or "")
        assert result["ok"] is False
        assert "Not connected" in (result.get("error") or "")


class TestDepthCap:
    def setup_method(self):
        import ibkr.depth as depth_mod
        importlib.reload(depth_mod)
        self.depth = depth_mod

    def test_subscribe_when_disconnected_returns_error(self, monkeypatch):
        import ibkr.client as client_mod
        monkeypatch.setattr(client_mod, "is_connected", lambda: False)
        result = self.depth.subscribe("AAPL")
        assert result["ok"] is False
        assert "connect" in result["error"].lower()

    def test_subscribe_evicts_idle_when_at_cap(self):
        from constants import IBKR_MAX_DEPTH_SYMBOLS
        for i in range(IBKR_MAX_DEPTH_SYMBOLS):
            self.depth._subscriptions[f"SYM{i}"] = {}
        self.depth._ws_viewers["SYM0"] = 1  # busy
        asyncio.run(self.depth._evict_for_capacity("EXTRA"))
        assert "SYM0" in self.depth._subscriptions
        assert len(self.depth._subscriptions) == IBKR_MAX_DEPTH_SYMBOLS - 1
        assert "EXTRA" not in self.depth._subscriptions

    def test_subscribe_force_evicts_when_all_slots_look_busy(self):
        from constants import IBKR_MAX_DEPTH_SYMBOLS
        for i in range(IBKR_MAX_DEPTH_SYMBOLS):
            self.depth._subscriptions[f"SYM{i}"] = {}
            self.depth._ws_viewers[f"SYM{i}"] = 1  # leaked viewer counts
        asyncio.run(self.depth._evict_for_capacity("EXTRA"))
        assert len(self.depth._subscriptions) == IBKR_MAX_DEPTH_SYMBOLS - 1
        # Force path clears the leaked viewer count on the victim.
        assert sum(1 for s in ("SYM0", "SYM1", "SYM2") if s in self.depth._subscriptions) == 2

    def test_resubscribe_same_symbol_is_idempotent(self, monkeypatch):
        import ibkr.client as client_mod
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        self.depth._subscriptions["AAPL"] = {}
        result = self.depth.subscribe("AAPL")
        assert result["ok"] is True

    def test_subscribed_symbols_list(self):
        self.depth._subscriptions = {"AAPL": {}, "TSLA": {}}
        assert set(self.depth.subscribed_symbols()) == {"AAPL", "TSLA"}


class TestDepthWsViewerRefcount:
    """Multiple DepthLadder mounts (side panel + trading tab) can watch the same
    symbol; the line must only release once the LAST viewer disconnects."""

    def setup_method(self):
        import ibkr.depth as depth_mod
        importlib.reload(depth_mod)
        self.depth = depth_mod

    def test_single_viewer_open_close_releases(self):
        self.depth.ws_viewer_opened("AAPL")
        assert self.depth.ws_viewer_closed("AAPL") is True

    def test_second_viewer_defers_release_until_last_closes(self):
        self.depth.ws_viewer_opened("AAPL")
        self.depth.ws_viewer_opened("AAPL")
        assert self.depth.ws_viewer_closed("AAPL") is False
        assert self.depth.ws_viewer_closed("AAPL") is True

    def test_close_without_open_does_not_go_negative(self):
        assert self.depth.ws_viewer_closed("AAPL") is True
        assert self.depth.ws_viewer_closed("AAPL") is True

    def test_viewers_tracked_independently_per_symbol(self):
        self.depth.ws_viewer_opened("AAPL")
        self.depth.ws_viewer_opened("TSLA")
        assert self.depth.ws_viewer_closed("TSLA") is True
        assert self.depth.ws_viewer_closed("AAPL") is True

    def test_release_when_idle_true_after_grace(self, monkeypatch):
        import asyncio
        monkeypatch.setattr(self.depth, "IBKR_DEPTH_RELEASE_GRACE_SEC", 0)
        self.depth.ws_viewer_opened("AAPL")
        assert self.depth.ws_viewer_closed("AAPL") is True
        assert asyncio.run(self.depth.release_when_idle("AAPL")) is True

    def test_release_when_idle_false_if_viewer_reattaches(self, monkeypatch):
        import asyncio
        monkeypatch.setattr(self.depth, "IBKR_DEPTH_RELEASE_GRACE_SEC", 0.05)

        async def scenario():
            self.depth.ws_viewer_opened("AAPL")
            assert self.depth.ws_viewer_closed("AAPL") is True
            task = asyncio.create_task(self.depth.release_when_idle("AAPL"))
            await asyncio.sleep(0.01)
            self.depth.ws_viewer_opened("AAPL")
            return await task

        assert asyncio.run(scenario()) is False
        assert self.depth.viewer_count("AAPL") == 1


class _FakeEvent:
    """Minimal stand-in for ib_async's Event, supporting += like the real one."""
    def __init__(self):
        self._listeners = []

    def __iadd__(self, fn):
        self._listeners.append(fn)
        return self

    def __isub__(self, fn):
        if fn in self._listeners:
            self._listeners.remove(fn)
        return self

    def emit(self, *args):
        for fn in list(self._listeners):
            fn(*args)


class _FakeContract:
    def __init__(self, conId):
        self.conId = conId


class _FakeTicker:
    def __init__(self):
        self.updateEvent = _FakeEvent()


class _FakeIbForErrors:
    def __init__(self):
        self.errorEvent = _FakeEvent()
        self.cancel_depth_calls = []
        self.l1_calls = []

    def cancelMktDepth(self, contract, isSmartDepth=False):
        self.cancel_depth_calls.append((contract, isSmartDepth))

    def reqMktData(self, contract, *_args):
        self.l1_calls.append(contract)
        return _FakeTicker()


class _FakeIbForSmartDepth(_FakeIbForErrors):
    def __init__(self):
        super().__init__()
        self.depth_calls = []

    async def qualifyContractsAsync(self, contract):
        contract.conId = 265598
        return [contract]

    def reqMktDepth(self, contract, numRows=5, isSmartDepth=False, mktDepthOptions=None):
        self.depth_calls.append(
            {"contract": contract, "numRows": numRows, "isSmartDepth": isSmartDepth}
        )
        return _FakeTicker()


class TestSmartDepthFlag:
    """SMART-routed depth must pass isSmartDepth=True or IBKR rejects with 10092
    even when NASDAQ TotalView is subscribed (PROBLEM_LOG 2026-07-13)."""

    def setup_method(self):
        import ibkr.depth as depth_mod
        importlib.reload(depth_mod)
        # Import-time reset was removed (Phase 2); clear leftover subscriptions.
        depth_mod.reset_all()
        self.depth = depth_mod

    def test_subscribe_async_requests_smart_depth(self, monkeypatch):
        import asyncio
        from constants import IBKR_DEPTH_NUM_ROWS, IBKR_DEPTH_SMART
        import ibkr.client as client_mod

        fake_ib = _FakeIbForSmartDepth()
        monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        monkeypatch.setattr(self.depth, "_load_ib_types", lambda: True)
        monkeypatch.setattr(self.depth, "_Stock", lambda *a, **k: _FakeContract(0))

        result = asyncio.run(self.depth.subscribe_async("AAPL"))
        assert result["ok"] is True
        assert len(fake_ib.depth_calls) == 1
        assert fake_ib.depth_calls[0]["isSmartDepth"] is IBKR_DEPTH_SMART
        assert fake_ib.depth_calls[0]["numRows"] == IBKR_DEPTH_NUM_ROWS

    def test_fallback_cancels_with_matching_smart_flag(self, monkeypatch):
        import asyncio
        from constants import IBKR_DEPTH_SMART, IBKR_ERROR_DEPTH_NOT_SUPPORTED
        import ibkr.client as client_mod

        fake_ib = _FakeIbForErrors()
        monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
        contract = _FakeContract(265598)
        self.depth._contracts["AAPL"] = contract
        self.depth._subscriptions["AAPL"] = {"bids": [], "asks": [], "l1_fallback": False}
        self.depth._queues["AAPL"] = asyncio.Queue(maxsize=100)

        self.depth._on_ib_error(1, IBKR_ERROR_DEPTH_NOT_SUPPORTED, "not supported", contract)
        assert fake_ib.cancel_depth_calls == [(contract, IBKR_DEPTH_SMART)]


class TestDepthAsyncErrorFallback:
    """Error 10092 ('Deep market data not supported') arrives asynchronously
    AFTER reqMktDepth() already returned, so the try/except around that call
    never sees it — without this fallback the DepthLadder hangs on "Waiting
    for book data" forever. See PROBLEM_LOG 2026-07-13."""

    def setup_method(self):
        import ibkr.depth as depth_mod
        importlib.reload(depth_mod)
        self.depth = depth_mod

    def test_matching_conid_falls_back_to_l1(self, monkeypatch):
        import asyncio
        from constants import IBKR_DEPTH_SMART, IBKR_ERROR_DEPTH_NOT_SUPPORTED
        import ibkr.client as client_mod
        fake_ib = _FakeIbForErrors()
        monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)

        contract = _FakeContract(890751584)
        self.depth._contracts["SHPH"] = contract
        self.depth._subscriptions["SHPH"] = {"bids": [], "asks": [], "l1_fallback": False}
        self.depth._queues["SHPH"] = asyncio.Queue(maxsize=100)

        self.depth._on_ib_error(6, IBKR_ERROR_DEPTH_NOT_SUPPORTED, "Deep market data is not supported", contract)

        assert self.depth._subscriptions["SHPH"]["l1_fallback"] is True
        assert fake_ib.cancel_depth_calls == [(contract, IBKR_DEPTH_SMART)]
        assert fake_ib.l1_calls == [contract]
        # A viewer already connected before the async rejection arrived must
        # learn about the fallback via the queue — it won't re-poll
        # current_book() on its own (see PROBLEM_LOG 2026-07-13).
        queued = self.depth._queues["SHPH"].get_nowait()
        assert queued["l1_fallback"] is True

    def test_unrelated_error_code_ignored(self, monkeypatch):
        import ibkr.client as client_mod
        fake_ib = _FakeIbForErrors()
        monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)

        contract = _FakeContract(1)
        self.depth._contracts["AAPL"] = contract
        self.depth._subscriptions["AAPL"] = {"bids": [], "asks": [], "l1_fallback": False}

        self.depth._on_ib_error(1, 200, "No security definition found", contract)

        assert self.depth._subscriptions["AAPL"]["l1_fallback"] is False
        assert fake_ib.l1_calls == []

    def test_already_on_l1_is_not_re_triggered(self, monkeypatch):
        from constants import IBKR_ERROR_DEPTH_NOT_SUPPORTED
        import ibkr.client as client_mod
        fake_ib = _FakeIbForErrors()
        monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)

        contract = _FakeContract(2)
        self.depth._contracts["TSLA"] = contract
        self.depth._subscriptions["TSLA"] = {"bids": [], "asks": [], "l1_fallback": True}

        self.depth._on_ib_error(2, IBKR_ERROR_DEPTH_NOT_SUPPORTED, "Deep market data is not supported", contract)

        assert fake_ib.l1_calls == []

    def test_install_error_hook_is_idempotent_per_ib_instance(self):
        fake_ib = _FakeIbForErrors()
        self.depth._install_error_hook(fake_ib)
        self.depth._install_error_hook(fake_ib)
        assert len(fake_ib.errorEvent._listeners) == 1


class TestUpdateHandlerReplacement:
    """ib_async caches Ticker objects per contract hash, so reqMktData(contract)
    after reqMktDepth(contract) on the same contract can return the SAME
    Ticker instance. Attaching the L1 fallback listener without detaching the
    original depth listener left both firing on every real tick — the stale
    depth handler kept pushing an empty book (l1_fallback=False) that raced
    with the real L1 book (l1_fallback=True), flickering the DepthLadder
    between empty and populated forever. See PROBLEM_LOG 2026-07-13."""

    def setup_method(self):
        import ibkr.depth as depth_mod
        importlib.reload(depth_mod)
        self.depth = depth_mod

    def test_fallback_detaches_old_depth_listener_from_shared_ticker(self, monkeypatch):
        import asyncio
        import ibkr.client as client_mod

        shared_ticker = _FakeTicker()

        class _FakeIbSharedTicker(_FakeIbForErrors):
            def reqMktData(self, contract, *_args):
                self.l1_calls.append(contract)
                return shared_ticker

        fake_ib = _FakeIbSharedTicker()
        monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)

        contract = _FakeContract(890751584)
        self.depth._contracts["SHPH"] = contract
        self.depth._subscriptions["SHPH"] = {"bids": [], "asks": [], "l1_fallback": False}
        self.depth._queues["SHPH"] = asyncio.Queue(maxsize=100)
        # Simulate reqMktDepth() having wired the depth handler onto the same
        # ticker object that reqMktData() will later return for the fallback.
        self.depth._attach_update_handler(
            "SHPH", shared_ticker, lambda t: self.depth._on_update_book(t, "SHPH")
        )

        self.depth._fallback_to_l1("SHPH", contract)
        assert len(shared_ticker.updateEvent._listeners) == 1

        shared_ticker.bid = 1.23
        shared_ticker.bidSize = 100
        shared_ticker.ask = 1.24
        shared_ticker.askSize = 50
        shared_ticker.domBids = []
        shared_ticker.domAsks = []
        shared_ticker.updateEvent.emit(shared_ticker)

        book = self.depth._subscriptions["SHPH"]
        assert book["l1_fallback"] is True
        assert book["bids"][0]["price"] == 1.23


class TestShouldSendCurrentBook:
    """A fresh WS viewer attaching to an already-subscribed symbol should get
    today's snapshot immediately instead of waiting for the next tick — but
    not the pre-first-tick placeholder, which would show an empty ladder
    instead of the more honest "Connecting…" state."""

    def setup_method(self):
        import ibkr.depth as depth_mod
        importlib.reload(depth_mod)
        self.depth = depth_mod

    def test_none_book_is_not_sent(self):
        assert self.depth.should_send_current_book(None) is False

    def test_placeholder_pre_first_tick_is_not_sent(self):
        book = {"bids": [], "asks": [], "l1_fallback": False}
        assert self.depth.should_send_current_book(book) is False

    def test_l1_fallback_with_no_ticks_yet_is_sent(self):
        book = {"bids": [], "asks": [], "l1_fallback": True}
        assert self.depth.should_send_current_book(book) is True

    def test_populated_depth_book_is_sent(self):
        book = {"bids": [{"price": 1.0, "size": 100, "side": "bid"}], "asks": [], "l1_fallback": False}
        assert self.depth.should_send_current_book(book) is True


class TestAccountSummaryCache:
    def test_summary_from_items_usd(self):
        import ibkr.account as account_mod

        class Item:
            def __init__(self, tag, value, currency="USD"):
                self.tag = tag
                self.value = value
                self.currency = currency

        out = account_mod._summary_from_items([
            Item("NetLiquidation", "600.00"),
            Item("BuyingPower", "600.00"),
            Item("TotalCashValue", "600.00", "EUR"),  # skipped
        ])
        assert out["connected"] is True
        assert out["NetLiquidation"] == 600.0
        assert out["BuyingPower"] == 600.0
        assert "TotalCashValue" not in out
