"""
IBKR Level 2 depth subscription manager — thin facade.

Hard cap: IBKR_MAX_DEPTH_SYMBOLS concurrent depth streams.

Contracts are qualified (conId) before depth/L1 requests — required by ib_async.
If depth entitlement is unavailable, falls back to L1 top-of-book.

Implementation split: state / handlers / subscribe / stream.

Facade owner: Phase 9 (Pattern-Driven Architecture).
Removal criterion: no production imports of ``ibkr.depth`` private attrs
(``_subscriptions``, ``_queues``, …) and tests call ``reset_all`` via the
public API only.
"""
from __future__ import annotations

import sys
import types

from constants import IBKR_DEPTH_RELEASE_GRACE_SEC

from ibkr.depth import state as _state

from ibkr.depth.handlers import (
    attach_update_handler as _attach_update_handler,
    detach_update_handler as _detach_update_handler,
    fallback_to_l1 as _fallback_to_l1,
    install_error_hook as _install_error_hook,
    on_ib_error as _on_ib_error,
    on_update_book as _on_update_book,
    on_update_ticker as _on_update_ticker,
)
from ibkr.depth.state import (
    current_book,
    has_queue,
    load_ib_types as _load_ib_types_impl,
    release_when_idle,
    reset_all,
    subscribed_symbols,
    viewer_count,
    ws_viewer_closed,
    ws_viewer_opened,
)
from ibkr.depth.subscribe import (
    evict_for_capacity as _evict_for_capacity,
    subscribe,
    subscribe_async,
    unsubscribe,
)
from ibkr.depth.stream import should_send_current_book, stream

_STATE_ATTRS = frozenset({
    "_contracts",
    "_error_hooked_ib_ids",
    "_queues",
    "_subscriptions",
    "_tickers",
    "_update_handlers",
    "_ws_viewers",
    "_subscribe_lock",
})

# Monkeypatchable by tests — subscribe resolves via facade attribute lookup.
_Stock = None


def _load_ib_types() -> bool:
    ok = _load_ib_types_impl()
    if ok:
        globals()["_Stock"] = _state._Stock
    return ok


class _DepthModule(types.ModuleType):
    """Proxy mutable state attrs so reload/assignment targets state.py."""

    def __getattr__(self, name: str):
        if name in _STATE_ATTRS:
            return getattr(_state, name)
        raise AttributeError(f"module {self.__name__!r} has no attribute {name!r}")

    def __setattr__(self, name: str, value) -> None:
        if name in _STATE_ATTRS:
            setattr(_state, name, value)
        else:
            types.ModuleType.__setattr__(self, name, value)


_mod = sys.modules[__name__]
if not isinstance(_mod, _DepthModule):
    _mod.__class__ = _DepthModule

__all__ = [
    "IBKR_DEPTH_RELEASE_GRACE_SEC",
    "current_book",
    "has_queue",
    "release_when_idle",
    "reset_all",
    "should_send_current_book",
    "stream",
    "subscribe",
    "subscribe_async",
    "subscribed_symbols",
    "unsubscribe",
    "viewer_count",
    "ws_viewer_closed",
    "ws_viewer_opened",
]
