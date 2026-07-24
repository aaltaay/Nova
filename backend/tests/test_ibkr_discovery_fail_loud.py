"""IB discovery must raise on transport failure — never disguise as []."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from ibkr import discovery as discovery
from ibkr.errors import IbkrDiscoveryError
from metrics import op_metrics


@pytest.fixture(autouse=True)
def reset_op_metrics():
    op_metrics.reset_for_tests()
    yield
    op_metrics.reset_for_tests()


@pytest.mark.asyncio
async def test_scan_symbols_raises_when_disconnected(monkeypatch):
    monkeypatch.setattr(discovery._client, "get_ib", lambda: None)
    with pytest.raises(IbkrDiscoveryError, match="not connected"):
        await discovery.scan_symbols("TOP_PERC_GAIN")


@pytest.mark.asyncio
async def test_scan_symbols_raises_on_scanner_request_timeout(monkeypatch):
    """One-shot scanner must time out without leaking the IBKR subscription.

    Wrapping ``reqScannerDataAsync`` in ``asyncio.wait_for`` used to abandon
    the await on timeout *before* ib_async's cancel ran — leaking toward
    Error 322 (max 10 simultaneous API scanner subscriptions).
    """
    cancelled: list[object] = []

    class _DataList:
        def __init__(self):
            self.reqId = 42

    class _Wrapper:
        def startReq(self, req_id, container=None):
            fut: asyncio.Future = asyncio.get_running_loop().create_future()
            # Never complete — forces the local wait_for timeout path.
            return fut

    class _HangingIB:
        def __init__(self):
            self.wrapper = _Wrapper()
            self.client = self

        def reqScannerSubscription(self, _subscription, *_a, **_k):
            return _DataList()

        def cancelScannerSubscription(self, data_list):
            cancelled.append(data_list.reqId)

        def cancelScannerSubscription_client(self, req_id):
            cancelled.append(req_id)

    monkeypatch.setattr(discovery._client, "get_ib", lambda: _HangingIB())
    monkeypatch.setattr(discovery, "_load_ib_types", lambda: True)
    monkeypatch.setattr(discovery, "IBKR_SCAN_REQUEST_TIMEOUT_SEC", 0.05)

    class _Sub:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.belowPrice = None

    monkeypatch.setattr(discovery, "_ScannerSubscription", _Sub)
    discovery.reset_scan_cache()
    discovery._scan_lock = None

    with pytest.raises(IbkrDiscoveryError, match="timed out"):
        await discovery.scan_symbols("TOP_PERC_GAIN")

    assert cancelled == [42], "timeout must cancel the scanner subscription"
    stats = op_metrics.snapshot()["operations"]["ibkr.scanner.oneshot"]
    assert stats["count"] == 1
    assert stats["error_count"] == 1


@pytest.mark.asyncio
async def test_scan_symbols_cancels_subscription_on_success(monkeypatch):
    cancelled: list[int] = []

    class _Row:
        class contractDetails:
            class contract:
                symbol = "AAA"

    class _DataList:
        def __init__(self):
            self.reqId = 7

    class _Wrapper:
        def startReq(self, req_id, container=None):
            fut: asyncio.Future = asyncio.get_running_loop().create_future()
            fut.set_result([_Row()])
            return fut

    class _IB:
        def __init__(self):
            self.wrapper = _Wrapper()

        def reqScannerSubscription(self, _subscription, *_a, **_k):
            return _DataList()

        def cancelScannerSubscription(self, data_list):
            cancelled.append(data_list.reqId)

    monkeypatch.setattr(discovery._client, "get_ib", lambda: _IB())
    monkeypatch.setattr(discovery, "_load_ib_types", lambda: True)

    class _Sub:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.belowPrice = None

    monkeypatch.setattr(discovery, "_ScannerSubscription", _Sub)
    discovery.reset_scan_cache()
    discovery._scan_lock = None

    symbols = await discovery.scan_symbols("TOP_PERC_GAIN")
    assert symbols == ["AAA"]
    assert cancelled == [7]
    stats = op_metrics.snapshot()["operations"]["ibkr.scanner.oneshot"]
    assert stats["count"] == 1
    assert stats["error_count"] == 0


@pytest.mark.asyncio
async def test_snapshot_require_success_raises_on_qualify_timeout(monkeypatch):
    """qualifyContractsAsync must be locally bounded too — an unbounded batch
    qualify on the discovery/table-reprice path is the same wedge risk
    ibkr/ticks.py already guards against for single-symbol L1 subscribes."""

    class _HangingIB:
        async def qualifyContractsAsync(self, *_contracts):
            await asyncio.sleep(60)

    monkeypatch.setattr(discovery._client, "get_ib", lambda: _HangingIB())
    monkeypatch.setattr(discovery, "_load_ib_types", lambda: True)
    monkeypatch.setattr(discovery, "IBKR_DISCOVERY_QUALIFY_TIMEOUT_SEC", 0.05)
    monkeypatch.setattr(discovery, "_Stock", lambda *a, **k: object())
    discovery._qualified_contracts.clear()

    with pytest.raises(IbkrDiscoveryError, match="qualify batch timed out"):
        await discovery.snapshot_quotes(["AAA"], require_success=True)


@pytest.mark.asyncio
async def test_snapshot_require_success_raises_on_timeout(monkeypatch):
    class _IB:
        async def reqTickersAsync(self, *_a, **_k):
            raise asyncio.TimeoutError()

    monkeypatch.setattr(discovery._client, "get_ib", lambda: _IB())
    monkeypatch.setattr(discovery, "_load_ib_types", lambda: True)
    discovery._qualified_contracts.clear()
    discovery._qualified_contracts["AAA"] = object()

    class _Lock:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

    monkeypatch.setattr(discovery, "_get_snapshot_lock", lambda: _Lock())

    with pytest.raises(IbkrDiscoveryError, match="snapshot timeout"):
        await discovery.snapshot_quotes(["AAA"], require_success=True)


class _FakeErrorEvent:
    """Stands in for ib_async's eventkit Event — synchronous +=/-=/emit only."""

    def __init__(self):
        self._listeners: list = []

    def __iadd__(self, listener):
        self._listeners.append(listener)
        return self

    def __isub__(self, listener):
        if listener in self._listeners:
            self._listeners.remove(listener)
        return self

    def fire(self, *args):
        for listener in list(self._listeners):
            listener(*args)


class TestScannerSlotRecovery:
    """IBKR Error 322 (slot exhausted) must not look like an empty market —
    see PROBLEM_LOG 2026-07-23 IBKR scanner subscription leak."""

    def _row(self, symbol: str):
        class _Row:
            class contractDetails:
                class contract:
                    pass
        _Row.contractDetails.contract.symbol = symbol
        return _Row()

    @pytest.mark.asyncio
    async def test_scan_symbols_recovers_and_retries_once_on_error_322(self, monkeypatch):
        from constants import IBKR_ERROR_SCANNER_SLOT_EXHAUSTED

        cancelled: list[int] = []
        attempts: list[int] = []
        row = self._row("CCC")

        class _Wrapper:
            def startReq(self, req_id, container=None):
                attempts.append(req_id)
                fut: asyncio.Future = asyncio.get_running_loop().create_future()
                if len(attempts) == 1:
                    # Simulate IBKR firing Error 322 then resolving the
                    # request's own future to [] (RaiseRequestErrors=False).
                    fake_ib.errorEvent.fire(
                        req_id, IBKR_ERROR_SCANNER_SLOT_EXHAUSTED, "slot exhausted", None,
                    )
                    fut.set_result([])
                else:
                    fut.set_result([row])
                return fut

        class _FakeIB:
            def __init__(self):
                self.wrapper = _Wrapper()
                self.errorEvent = _FakeErrorEvent()
                self._next_req_id = 500

            def reqScannerSubscription(self, _subscription, *_a, **_k):
                self._next_req_id += 1
                return SimpleNamespace(reqId=self._next_req_id)

            def cancelScannerSubscription(self, data_list):
                cancelled.append(data_list.reqId)

        fake_ib = _FakeIB()
        monkeypatch.setattr(discovery._client, "get_ib", lambda: fake_ib)
        monkeypatch.setattr(discovery, "_load_ib_types", lambda: True)

        class _Sub:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
                self.belowPrice = None

        monkeypatch.setattr(discovery, "_ScannerSubscription", _Sub)
        discovery.reset_scan_cache()
        discovery._scan_lock = None
        discovery._inflight_scan_reqids.clear()

        symbols = await discovery.scan_symbols("TOP_PERC_GAIN")

        assert symbols == ["CCC"]
        assert len(attempts) == 2, "must recover the slot and retry exactly once"
        assert len(cancelled) == 2, "both attempts' subscriptions must be cancelled"
        assert discovery._inflight_scan_reqids == set()

    @pytest.mark.asyncio
    async def test_scan_symbols_fails_loud_on_two_consecutive_error_322(self, monkeypatch):
        """A second consecutive Error 322 (recovery did not free a slot) must
        surface as a normal discovery failure, not loop forever."""
        from constants import IBKR_ERROR_SCANNER_SLOT_EXHAUSTED

        class _Wrapper:
            def startReq(self, req_id, container=None):
                fut: asyncio.Future = asyncio.get_running_loop().create_future()
                fake_ib.errorEvent.fire(
                    req_id, IBKR_ERROR_SCANNER_SLOT_EXHAUSTED, "slot exhausted", None,
                )
                fut.set_result([])
                return fut

        class _FakeIB:
            def __init__(self):
                self.wrapper = _Wrapper()
                self.errorEvent = _FakeErrorEvent()
                self._next_req_id = 700

            def reqScannerSubscription(self, _subscription, *_a, **_k):
                self._next_req_id += 1
                return SimpleNamespace(reqId=self._next_req_id)

            def cancelScannerSubscription(self, _data_list):
                pass

        fake_ib = _FakeIB()
        monkeypatch.setattr(discovery._client, "get_ib", lambda: fake_ib)
        monkeypatch.setattr(discovery, "_load_ib_types", lambda: True)

        class _Sub:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
                self.belowPrice = None

        monkeypatch.setattr(discovery, "_ScannerSubscription", _Sub)
        discovery.reset_scan_cache()
        discovery._scan_lock = None
        discovery._inflight_scan_reqids.clear()

        with pytest.raises(discovery.IbkrDiscoveryError, match="failed"):
            await discovery.scan_symbols("TOP_PERC_GAIN")


def test_recover_scanner_slots_only_cancels_scan_data_list_entries(monkeypatch):
    """Recovery must never touch live mktData/bars subscribers — only actual
    open scanner subscriptions (ScanDataList containers)."""

    class _FakeScanDataList:
        def __init__(self, req_id):
            self.reqId = req_id

    class _OtherSubscriber:
        """Stands in for a live mktData/bars subscriber — must be left alone."""

        def __init__(self, req_id):
            self.reqId = req_id

    monkeypatch.setattr(discovery, "_ScanDataList", _FakeScanDataList)
    monkeypatch.setattr(discovery, "_load_ib_types", lambda: True)
    discovery._inflight_scan_reqids.clear()

    scan_entry = _FakeScanDataList(11)
    other_entry = _OtherSubscriber(22)
    registry = {11: scan_entry, 22: other_entry}

    class _Wrapper:
        reqId2Subscriber = registry

    cancelled: list[object] = []

    class _FakeIB:
        wrapper = _Wrapper()

        def cancelScannerSubscription(self, data_list):
            cancelled.append(data_list)
            registry.pop(data_list.reqId, None)

    recovered = discovery.recover_scanner_slots(_FakeIB())

    assert recovered == 1
    assert cancelled == [scan_entry]
    assert 22 in registry, "non-scanner subscriber must never be cancelled"
    assert 11 not in registry


def test_recover_scanner_slots_uses_tracked_reqids_when_not_in_registry(monkeypatch):
    """Belt-and-suspenders path: a reqId this process still has recorded as
    in-flight must be reclaimed even if it fell out of the wrapper registry
    (e.g. a finally-block cancel that itself raised)."""
    monkeypatch.setattr(discovery, "_ScanDataList", type("_Sentinel", (), {}))
    monkeypatch.setattr(discovery, "_load_ib_types", lambda: True)
    discovery._inflight_scan_reqids.clear()
    discovery._inflight_scan_reqids.add(99)

    calls: list[int] = []

    class _Wrapper:
        reqId2Subscriber: dict = {}

    class _Client:
        def cancelScannerSubscription(self, req_id):
            calls.append(req_id)

    class _FakeIB:
        wrapper = _Wrapper()
        client = _Client()

    recovered = discovery.recover_scanner_slots(_FakeIB())

    assert recovered == 1
    assert calls == [99]
    assert discovery._inflight_scan_reqids == set()


def test_recover_scanner_slots_returns_zero_when_ib_none():
    assert discovery.recover_scanner_slots(None) == 0
