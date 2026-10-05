"""The hand-off from the IB thread to one viewer's socket (ADR 045).

The IB thread (and Sim's feed, on the socket loop) put; the socket's own loop gets. Every put
takes the queue's lock, and the first put after the consumer drained wakes the consumer's loop
once (``call_soon_threadsafe``; ``set`` directly when already on it). An ``asyncio.Queue`` filled
from the IB thread was neither thread-safe nor woke the loop: a frame waited for some other
wake-up, and after a stall the socket replayed up to 100 old books in order (2026-10-05).

- ``LatestBookQueue`` (Level 2): one slot, the newest book (``BookVersion``) -- a newer one
  replaces an unsent one, counted in ``depth.viewer_skipped`` -- and a FIFO of control frames
  (``error``, ``lent``), which come out first.
- ``PrintQueue`` (Time & Sales, the setup scanner's tape): every print in order, the oldest
  dropped past ``maxsize`` and counted in ``tape.viewer_dropped``; ``drain_nowait`` hands a socket
  everything waiting at once.

Both keep the parts of the ``asyncio.Queue`` interface their readers use: ``get``,
``get_nowait`` (``asyncio.QueueEmpty`` when empty), ``put_nowait``, ``qsize``, ``empty``,
``full`` and ``maxsize``. ``put_nowait`` never raises ``asyncio.QueueFull``.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any

from perf.counters import incr as _count

logger = logging.getLogger(__name__)

_EMPTY = object()


@dataclass(frozen=True)
class BookVersion:
    """A Level 2 book as Nova applied it: ``seq`` / ``at`` from ``market_view.versions``."""

    seq: int
    at: float
    book: dict


class _Waking:
    """The thread-safe, coalesced wake-up of one consumer's loop."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._event: asyncio.Event | None = None
        self._wake_scheduled = False

    def _bind(self) -> asyncio.Event:
        loop = asyncio.get_running_loop()
        if self._loop is not loop or self._event is None:
            self._loop = loop
            self._event = asyncio.Event()
        return self._event

    def _notify(self) -> None:
        loop = self._loop
        if loop is None or self._wake_scheduled:
            return  # nobody waits yet (it checks before waiting), or a wake-up is already on its way
        self._wake_scheduled = True
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        try:
            if running is loop:
                self._fire()
            else:
                loop.call_soon_threadsafe(self._fire)
        except RuntimeError:
            # The consumer's loop is closed: its socket is gone, nothing to wake.
            self._wake_scheduled = False

    def _fire(self) -> None:
        self._wake_scheduled = False
        if self._event is not None:
            self._event.set()

    def _take(self) -> Any:
        raise NotImplementedError

    def get_nowait(self) -> Any:
        item = self._take()
        if item is _EMPTY:
            raise asyncio.QueueEmpty
        return item

    async def get(self) -> Any:
        event = self._bind()
        while True:
            item = self._take()
            if item is not _EMPTY:
                return item
            event.clear()
            item = self._take()  # anything put between the take and the clear
            if item is not _EMPTY:
                return item
            await event.wait()

    def empty(self) -> bool:
        return self.qsize() == 0

    def full(self) -> bool:
        return False

    def qsize(self) -> int:
        raise NotImplementedError


class LatestBookQueue(_Waking):
    """One Level 2 viewer: the newest book only, and its control frames first."""

    maxsize = 1

    def __init__(self) -> None:
        super().__init__()
        self._book: BookVersion | None = None
        self._control: deque[dict] = deque()

    def put_nowait(self, item: Any) -> None:
        with self._lock:
            if isinstance(item, BookVersion):
                if self._book is not None:
                    _count("depth.viewer_skipped")
                self._book = item
            else:
                self._control.append(item)
        self._notify()

    def _take(self) -> Any:
        with self._lock:
            if self._control:
                return self._control.popleft()
            if self._book is not None:
                book, self._book = self._book, None
                return book
        return _EMPTY

    def qsize(self) -> int:
        with self._lock:
            return len(self._control) + (1 if self._book is not None else 0)


class PrintQueue(_Waking):
    """One Time & Sales viewer: every print in order, the oldest dropped past ``maxsize``."""

    def __init__(self, maxsize: int, *, drop_counter: str = "tape.viewer_dropped") -> None:
        super().__init__()
        self.maxsize = maxsize
        self._items: deque[Any] = deque()
        self._drop_counter = drop_counter

    def put_nowait(self, item: Any) -> None:
        dropped = 0
        with self._lock:
            self._items.append(item)
            while len(self._items) > self.maxsize:
                self._items.popleft()
                dropped += 1
        if dropped:
            _count(self._drop_counter, dropped)
        self._notify()

    def _take(self) -> Any:
        with self._lock:
            if self._items:
                return self._items.popleft()
        return _EMPTY

    def drain_nowait(self) -> list[Any]:
        """Everything waiting, oldest first (empty when nothing is)."""
        with self._lock:
            items = list(self._items)
            self._items.clear()
        return items

    def qsize(self) -> int:
        with self._lock:
            return len(self._items)
