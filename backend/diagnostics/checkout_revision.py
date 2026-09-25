"""The revision of the checkout this API runs from, as it is on disk now.

``process_info.REVISION`` is what this process loaded when it started, and a restart
loads whatever the checkout holds then -- newer code only after a pull (operator report
2026-09-25: a Reload at 07:56 ET came up v1017 again because the checkout itself was
still v1017 until 07:57). ``/api/health`` and the checklist carry it as ``checkout_tag``
so the desk can say whether a restart would help.

``/api/health`` runs on the HTTP loop, so a reader never waits on git: it gets the last
answer, and an answer older than ``DIAG_CHECKOUT_REVISION_TTL_SEC`` starts one re-read on
a worker thread. A packaged engine has no checkout: always ``None``.
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from collections.abc import Callable

from constants_diagnostics import DIAG_CHECKOUT_REVISION_TTL_SEC
from diagnostics.process_info import REVISION, read_checkout_tag

logger = logging.getLogger(__name__)


def _spawn_daemon(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="checkout-revision", daemon=True).start()


class CheckoutRevision:
    """The last answer, re-read off the caller's thread once it is older than ``ttl_sec``."""

    def __init__(
        self,
        initial: str | None,
        read: Callable[[], str | None],
        *,
        ttl_sec: float,
        clock: Callable[[], float] = time.monotonic,
        spawn: Callable[[Callable[[], None]], None] = _spawn_daemon,
    ) -> None:
        self._value = initial
        self._read = read
        self._ttl = float(ttl_sec)
        self._clock = clock
        self._spawn = spawn
        # The process start's own read of the checkout is the first answer.
        self._read_at = clock()
        self._reading = False
        self._lock = threading.Lock()

    def current(self) -> str | None:
        """The last answer; never waits. A stale one starts a single re-read."""
        with self._lock:
            value = self._value
            stale = not self._reading and self._clock() - self._read_at >= self._ttl
            if stale:
                self._reading = True
        if stale:
            try:
                self._spawn(self._refresh)
            except Exception:
                logger.warning("checkout revision: could not start a re-read", exc_info=True)
                with self._lock:
                    self._reading = False
                    self._read_at = self._clock()
        return value

    def _refresh(self) -> None:
        try:
            value = self._read()
        except Exception:
            # Unknown, never the last answer passed off as now.
            logger.warning("checkout revision: re-read failed", exc_info=True)
            value = None
        with self._lock:
            self._value = value
            self._read_at = self._clock()
            self._reading = False


_FROZEN = bool(getattr(sys, "frozen", False))
_CHECKOUT = CheckoutRevision(
    None if _FROZEN else REVISION.get("release_tag"),
    read_checkout_tag,
    ttl_sec=DIAG_CHECKOUT_REVISION_TTL_SEC,
)


def checkout_tag() -> str | None:
    """The checkout's ``vNNN`` on disk as last read; None for a packaged engine or when git is silent."""
    return None if _FROZEN else _CHECKOUT.current()
