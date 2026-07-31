"""Guard against a repeat of the 2026-07-31 empty gappers/gainers outage.

The 2026-07-30 ``ib_async`` pin bump (git ``c9f4c14``, for Error 10349 --
see PROBLEM_LOG 2026-07-30) replaced ``Wrapper.startReq`` /
``wrapper.reqId2Subscriber`` with a typed ``RequestRegistry`` / typed
subscription registry. ``ibkr/discovery.py`` still called the old facade,
so every one-shot scanner call raised ``AttributeError`` and gappers/gainers
stayed empty (``last_scan: 0``) while IBKR itself was connected -- see
PROBLEM_LOG 2026-07-31.

Unlike the other discovery tests, this file imports the REAL installed
``ib_async`` (no fakes) and constructs a real, unconnected ``IB()`` instance.
It exists so the next incompatible pin bump fails a pytest here -- loudly,
in CI, before market open -- instead of quietly emptying the scanner tables.
"""
from __future__ import annotations

import asyncio

import pytest

import ibkr.discovery as discovery

ib_async = pytest.importorskip("ib_async")


@pytest.fixture()
def real_ib():
    """A real, unconnected ib_async.IB() -- no Gateway required."""
    ib = ib_async.IB()
    try:
        yield ib
    finally:
        # Never connected, but be defensive about background handles.
        try:
            ib.disconnect()
        except Exception:
            pass


def test_wrapper_exposes_typed_request_registry(real_ib):
    """``_open_scan_future``'s primary path needs ``wrapper.requests.open``."""
    assert hasattr(real_ib.wrapper, "requests")
    assert callable(getattr(real_ib.wrapper.requests, "open", None))


def test_req_id_key_importable():
    """``_load_ib_types`` imports ``ReqIdKey`` from this module path."""
    from ib_async._requests import ReqIdKey

    key = ReqIdKey(123)
    assert key.reqId == 123


def test_wrapper_exposes_typed_subscription_registry(real_ib):
    """``recover_scanner_slots``'s primary path needs
    ``wrapper.subscriptions.subs_of_type``."""
    assert hasattr(real_ib.wrapper, "subscriptions")
    assert callable(getattr(real_ib.wrapper.subscriptions, "subs_of_type", None))


def test_scanner_sub_importable():
    """``recover_scanner_slots`` filters the subscription registry by this type."""
    from ib_async._subscriptions import ScannerSub

    assert hasattr(ScannerSub, "dataList")


def test_ib_still_exposes_scanner_request_and_cancel_methods(real_ib):
    assert callable(getattr(real_ib, "reqScannerSubscription", None))
    assert callable(getattr(real_ib, "cancelScannerSubscription", None))
    assert hasattr(real_ib, "errorEvent")


def test_load_ib_types_resolves_scanner_sub_and_req_id_key():
    """``_load_ib_types`` (unmocked) must populate the optional typed-registry
    globals discovery.py needs -- a silent import failure here would push
    every call onto the legacy fallback without anyone noticing."""
    discovery._Stock = None  # force a fresh resolution against the real package
    discovery._ScannerSub = None
    discovery._ReqIdKey = None
    assert discovery._load_ib_types() is True
    assert discovery._ScannerSub is not None
    assert discovery._ReqIdKey is not None


def test_open_scan_future_resolves_against_real_wrapper(real_ib):
    """End-to-end contract check: ``_open_scan_future`` must return a real,
    awaitable future when handed a genuine (unconnected) ib_async Wrapper --
    exactly the call that raised ``AttributeError: 'Wrapper' object has no
    attribute 'startReq'`` in the 2026-07-31 outage."""
    discovery._load_ib_types()

    class _FakeDataList:
        reqId = 999999  # unused by IBKR since we never send the real request

    future = discovery._open_scan_future(real_ib, _FakeDataList())
    assert isinstance(future, asyncio.Future)
    assert not future.done()
    # Clean up the registry entry this opened so it doesn't leak.
    real_ib.wrapper.requests.get(discovery._ReqIdKey(_FakeDataList.reqId)).future.cancel()
