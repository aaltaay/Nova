"""Daily P&L belongs to the READY IB instance, generation and account (#664)."""
from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest


class Event:
    def __init__(self):
        self.listeners = []

    def __iadd__(self, callback):
        self.listeners.append(callback)
        return self

    def __isub__(self, callback):
        self.listeners.remove(callback)
        return self

    def emit(self, *args):
        for callback in list(self.listeners):
            callback(*args)


class IB:
    def __init__(self):
        self.pnlEvent, self.errorEvent, self.disconnectedEvent = Event(), Event(), Event()
        self.requests, self.cancels = [], []
        self.pending = None
        self.failure = None
        self.wrapper = SimpleNamespace(subscriptions=SimpleNamespace(get_pnl=self.subscription))

    def subscription(self, account, model):
        return SimpleNamespace(reqId=len(self.requests))

    def reqPnL(self, account):
        self.requests.append(account)
        if self.failure:
            raise self.failure
        self.pending = SimpleNamespace(account=account, dailyPnL=float('nan'))
        return self.pending

    def cancelPnL(self, account):
        self.cancels.append(account)

    def isConnected(self):
        return True

    def update(self, value):
        self.pending.dailyPnL = value
        self.pnlEvent.emit(self.pending)


@pytest.fixture
def scope(monkeypatch):
    from ibkr import day_pnl
    day_pnl.reset_for_tests()
    scope = SimpleNamespace(ib=IB(), generation=1, account='account-a', ready=True)
    monkeypatch.setattr('ibkr.client.get_ib', lambda: scope.ib if scope.ready else None)
    monkeypatch.setattr('ibkr.client.current_generation', lambda: scope.generation)
    monkeypatch.setattr('ibkr.client.account_id', lambda: scope.account if scope.ready else None)
    yield day_pnl, scope
    day_pnl.reset_for_tests()


def start(day_pnl, scope):
    day_pnl.start(scope.ib, generation=scope.generation, account=scope.account)


def test_one_subscription_repeated_ready_and_memory_reads(scope):
    owner, s = scope
    start(owner, s)
    start(owner, s)
    assert owner.read()['daily_pnl'] is None
    s.ib.update(0.0)
    for _ in range(3):
        assert owner.read()['daily_pnl'] == 0.0
    assert s.ib.requests == ['account-a']
    assert len(s.ib.pnlEvent.listeners) == 1


@pytest.mark.parametrize('changed', ['generation', 'account', 'ib'])
def test_scope_change_refuses_old_values_and_callbacks_before_restarting(scope, changed):
    owner, s = scope
    start(owner, s)
    old_ib, old_pnl = s.ib, s.ib.pending
    old_callback = old_ib.pnlEvent.listeners[0]
    old_ib.update(-250)
    if changed == 'generation':
        s.generation += 1
    elif changed == 'account':
        s.account = 'account-b'
    else:
        s.ib = IB()
    assert owner.read()['daily_pnl'] is None
    old_pnl.dailyPnL = -999
    old_callback(old_pnl)
    assert owner.read()['daily_pnl'] is None
    start(owner, s)
    assert old_ib.cancels == ['account-a']
    assert owner.read()['daily_pnl'] is None
    old_callback(old_pnl)
    assert owner.read()['daily_pnl'] is None
    s.ib.update(3)
    assert owner.read()['daily_pnl'] == 3


def test_disconnected_read_and_callback_cannot_supply_last_known_daily_pnl(scope):
    owner, s = scope
    start(owner, s)
    s.ib.update(-200)
    s.ready = False
    s.ib.update(-300)
    assert owner.read()['daily_pnl'] is None
    assert 'disconnected' in owner.read()['error'].lower()
    s.ib.disconnectedEvent.emit()
    assert not s.ib.pnlEvent.listeners
    assert not s.ib.errorEvent.listeners


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf'), sys.float_info.max,
                                  None, True, '12'])
def test_invalid_broker_values_replace_a_previously_known_value_with_unknown(scope, value):
    owner, s = scope
    start(owner, s)
    s.ib.update(7)
    s.ib.update(value)
    result = owner.read()
    assert result['daily_pnl'] is None
    assert result['error']


def test_another_subscription_or_account_cannot_publish(scope):
    owner, s = scope
    start(owner, s)
    s.ib.pnlEvent.emit(SimpleNamespace(account=s.account, dailyPnL=-500))
    s.ib.pending.account = 'wrong-account'
    s.ib.update(-400)
    assert owner.read()['daily_pnl'] is None


def test_request_error_invalidates_pnl_without_treating_other_requests_as_its_error(scope):
    owner, s = scope
    start(owner, s)
    s.ib.update(2)
    s.ib.errorEvent.emit(99, 321, 'another request', None)
    assert owner.read()['daily_pnl'] == 2
    s.ib.errorEvent.emit(1, 321, 'PnL request rejected', None)
    assert owner.read()['daily_pnl'] is None
    assert 'PnL request rejected' in owner.read()['error']
    s.ib.update(4)
    assert owner.read()['daily_pnl'] == 4


def test_failed_start_is_unknown_and_does_not_hammer_requests_on_reads(scope):
    owner, s = scope
    s.ib.failure = RuntimeError('PnL subscription failed')
    start(owner, s)
    start(owner, s)
    for _ in range(3):
        assert owner.read()['daily_pnl'] is None
        assert 'subscription failed' in owner.read()['error']
    assert s.ib.requests == ['account-a']


def test_partial_listener_setup_is_retired_and_cannot_supply_a_value(scope):
    owner, s = scope
    class Broken(Event):
        def __iadd__(self, callback):
            raise RuntimeError('error listener unavailable')
    s.ib.errorEvent = Broken()
    start(owner, s)
    assert not s.ib.pnlEvent.listeners
    assert s.ib.cancels == ['account-a']
    s.ib.update(6)
    assert owner.read()['daily_pnl'] is None
    assert 'listener unavailable' in owner.read()['error']


def test_missing_account_starts_no_subscription(scope):
    owner, s = scope
    s.account = None
    start(owner, s)
    assert not s.ib.requests
    assert owner.read()['daily_pnl'] is None


def test_failed_retirement_cannot_relabel_an_old_subscription_as_a_new_generation(scope, monkeypatch):
    owner, s = scope
    start(owner, s)
    s.ib.update(-250)
    def failed(account):
        raise RuntimeError('old subscription cannot be cancelled')
    monkeypatch.setattr(s.ib, 'cancelPnL', failed)
    s.generation += 1
    start(owner, s)
    assert s.ib.requests == ['account-a']
    assert owner.read()['daily_pnl'] is None
    assert 'cancel' in owner.read()['error']


def test_a_failed_scope_read_is_unknown_not_a_raised_route_error(scope, monkeypatch):
    owner, s = scope
    start(owner, s)
    s.ib.update(6)
    def failed():
        raise RuntimeError('session read failed')
    monkeypatch.setattr('ibkr.client.get_ib', failed)
    assert owner.read()['daily_pnl'] is None
    assert 'session read failed' in owner.read()['error']


def test_ready_wiring_starts_on_the_ib_loop_with_current_scope(scope, monkeypatch):
    from ibkr import loop_supervisor, session_usable
    import threading
    owner, s = scope
    calls = []
    monkeypatch.setattr(owner, 'start', lambda ib, **kw: calls.append((ib, kw, threading.current_thread().name)))
    loop_supervisor.stop()
    loop = loop_supervisor.start()
    try:
        async def ready():
            session_usable._wire_daily_pnl(s.ib, s.generation)
        future = asyncio.run_coroutine_threadsafe(ready(), loop)
        future.result(3)
    finally:
        loop_supervisor.stop()
    assert calls == [(s.ib, {'generation': 1, 'account': 'account-a'}, 'nova-ib-loop')]


def test_failed_pnl_subscription_does_not_interrupt_other_ready_side_effects(scope, monkeypatch):
    from ibkr import session_usable
    owner, s = scope
    def failed(*args, **kwargs):
        raise RuntimeError('daily subscription unavailable')
    monkeypatch.setattr(owner, 'start', failed)
    session_usable._wire_daily_pnl(s.ib, s.generation)


def test_real_ib_async_registry_routes_the_pnl_error_to_its_subscription(scope, monkeypatch):
    from ib_async import IB as RealIB
    owner, s = scope
    s.ib = RealIB()
    monkeypatch.setattr(s.ib.client, 'getReqId', lambda: 42)
    monkeypatch.setattr(s.ib.client, 'reqPnL', lambda *args: None)
    monkeypatch.setattr(s.ib.client, 'cancelPnL', lambda *args: None)
    start(owner, s)
    s.ib.wrapper.pnl(42, 5.0, 300.0, 0.0)
    assert owner.read()['daily_pnl'] == 5.0
    s.ib.errorEvent.emit(42, 321, 'real subscription error', None)
    assert owner.read()['daily_pnl'] is None


@pytest.mark.parametrize('failed_subscription', [False, True])
def test_earn_usable_wires_daily_pnl_without_losing_other_ready_hooks(scope, monkeypatch, failed_subscription):
    from ibkr import client, loop_supervisor, session_state, session_usable
    owner, s = scope
    session_state.reset_for_testing()
    session_usable.reset_for_tests()
    ready_hooks = []
    async def noop(*args, **kwargs):
        return None
    async def ready(*args, **kwargs):
        ready_hooks.append('ready')
    monkeypatch.setattr('ibkr.account.refresh_positions_cache', noop)
    monkeypatch.setattr('ibkr.account_stream.ensure_account_updates', noop)
    monkeypatch.setattr('ibkr.completed_orders_warm.schedule', lambda ib: ready_hooks.append('history'))
    monkeypatch.setattr('ibkr.line_session.on_session_ready', lambda gen: ready_hooks.append(gen))
    monkeypatch.setattr(session_usable, '_wire_order_events', lambda ib: None)
    monkeypatch.setattr(client, '_on_session_ready', ready)
    if failed_subscription:
        s.ib.failure = RuntimeError('subscription refused')
    loop_supervisor.stop()
    loop = loop_supervisor.start()
    try:
        future = asyncio.run_coroutine_threadsafe(session_usable.earn_usable(s.ib, 'test'), loop)
        assert future.result(3) == (True, 'ok')
        assert session_state.is_ready()
        assert s.ib.requests == ['account-a']
        assert ready_hooks == ['history', 'ready', 1]
        if failed_subscription:
            assert owner.read()['daily_pnl'] is None
        else:
            s.ib.update(0)
            assert owner.read()['daily_pnl'] == 0
    finally:
        loop_supervisor.stop()
        session_state.reset_for_testing()
        session_usable.reset_for_tests()
