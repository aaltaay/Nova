"""The current READY account's broker daily P&L subscription (#664).

Owner: this module; invalidated by IB-instance, READY generation, account or
connection changes. In-memory only. READY starts it on the IB loop; HTTP reads
never request, refresh or cancel anything. IBKR owns the daily reset and does
not report its timestamp through this API.
"""
from __future__ import annotations

import logging
import math
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from ibkr import client

logger = logging.getLogger(__name__)


@dataclass
class _Subscription:
    ib: Any
    generation: int
    account: str
    pnl: Any = None
    request_id: int | None = None
    daily: float | None = None
    updated_at: float | None = None
    error: str | None = 'IBKR daily P&L is pending its first update'
    on_pnl: Callable | None = None
    on_error: Callable | None = None
    on_disconnect: Callable | None = None


_lock = threading.Lock()
_subscription: _Subscription | None = None


def _scope() -> tuple[Any, int, str | None]:
    return client.get_ib(), client.current_generation(), client.account_id()


def _matches(sub: _Subscription, scope: tuple[Any, int, str | None]) -> bool:
    ib, generation, account = scope
    return ib is sub.ib and generation == sub.generation and account == sub.account


def _finite(value: Any) -> float | None:
    # IBKR's unset-double is finite, but is an absence rather than P&L.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and abs(number) != sys.float_info.max else None


def _retire(sub: _Subscription) -> bool:
    for name, slot in (('pnlEvent', 'on_pnl'), ('errorEvent', 'on_error'),
                       ('disconnectedEvent', 'on_disconnect')):
        callback = getattr(sub, slot)
        if callback is not None:
            try:
                event = getattr(sub.ib, name)
                event -= callback
            except Exception:
                logger.exception('IBKR: daily P&L listener could not be removed')
            setattr(sub, slot, None)
    if sub.pnl is not None:
        try:
            if not sub.ib.isConnected():
                return True
            sub.ib.cancelPnL(sub.account)
        except Exception:
            logger.exception('IBKR: prior daily P&L subscription could not be cancelled')
            return False
    return True


def _request_id(ib: Any, account: str) -> int | None:
    """The pinned ib_async registry owns the request id; the public PnL object does not."""
    registered = ib.wrapper.subscriptions.get_pnl(account, '')
    req_id = getattr(registered, 'reqId', None)
    return req_id if isinstance(req_id, int) else None


def start(ib: Any, *, generation: int, account: str | None) -> None:
    """On READY's IB loop: one subscription per IB instance/generation/account."""
    from ibkr.loop_supervisor import assert_ib_loop

    assert_ib_loop()
    global _subscription
    with _lock:
        old = _subscription
        if old is not None and old.ib is ib and old.generation == generation and old.account == account:
            return
        _subscription = None
    if old is not None:
        retired = _retire(old)
        if not retired and old.ib is ib:
            # reqPnL deduplicates by account. Reusing an uncancelled object would
            # relabel the prior generation's feed as this generation's source.
            with _lock:
                old.daily, old.updated_at = None, None
                old.error = 'Prior IBKR daily P&L subscription could not be cancelled; current daily P&L unavailable'
                _subscription = old
            return
    if not account:
        return
    sub = _Subscription(ib, generation, account)
    with _lock:
        _subscription = sub

    def on_pnl(pnl: Any) -> None:
        if pnl is not sub.pnl or getattr(pnl, 'account', None) != sub.account or not _matches(sub, _scope()):
            return
        daily = _finite(getattr(pnl, 'dailyPnL', None))
        with _lock:
            if _subscription is not sub:
                return
            sub.daily = daily
            sub.updated_at = time.time() if daily is not None else None
            sub.error = None if daily is not None else 'IBKR daily P&L update is invalid or unset'

    def on_error(req_id: int, code: int, message: str, *_args: Any) -> None:
        if sub.request_id is None or req_id != sub.request_id or not _matches(sub, _scope()):
            return
        with _lock:
            if _subscription is not sub:
                return
            sub.daily, sub.updated_at = None, None
            sub.error = f'IBKR daily P&L request error {code}: {message}'
        logger.warning('IBKR: %s', sub.error)

    def on_disconnect(*_args: Any) -> None:
        global _subscription
        with _lock:
            if _subscription is not sub:
                return
            _subscription = None
        _retire(sub)

    try:
        sub.pnl = ib.reqPnL(account)
        sub.request_id = _request_id(ib, account)
        ib.pnlEvent += on_pnl
        sub.on_pnl = on_pnl
        ib.errorEvent += on_error
        sub.on_error = on_error
        ib.disconnectedEvent += on_disconnect
        sub.on_disconnect = on_disconnect
    except Exception as exc:
        if _retire(sub):
            sub.pnl = None
        sub.error = f'IBKR daily P&L subscription failed: {type(exc).__name__}: {exc}'
        logger.exception('IBKR: daily P&L subscription failed')


def read() -> dict[str, Any]:
    """A value for the current READY scope, or a stated absence; never last-known P&L."""
    try:
        scope = _scope()
    except Exception as exc:
        return {'daily_pnl': None, 'updated_at': None,
                'error': f'IBKR daily P&L session read failed: {type(exc).__name__}: {exc}'}
    if scope[0] is None:
        return {'daily_pnl': None, 'updated_at': None,
                'error': 'IBKR daily P&L unavailable: Gateway disconnected or not READY'}
    with _lock:
        sub = _subscription
        if sub is None or not _matches(sub, scope):
            return {'daily_pnl': None, 'updated_at': None,
                    'error': 'IBKR daily P&L subscription unavailable for the current session/account'
                             + (f': {sub.error}' if sub is not None and sub.error else '')}
        return {'daily_pnl': sub.daily, 'updated_at': sub.updated_at, 'error': sub.error}


def reset_for_tests() -> None:
    global _subscription
    with _lock:
        old, _subscription = _subscription, None
    if old is not None:
        _retire(old)
