"""Wake a polling loop the moment work arrives (operator report 2026-10-02, TNMG).

Nova's bot and the stock-mode runner tick every 0.5 s and read the setup scanner's
triggers from an inbox. A trigger that landed just after a tick waited for the next one:
TNMG's red to green triggered at 09:47:18.228 ET and the bot sent its entry at 18.644,
416 ms later, all of it the wait. ``Wake`` lets ``submit`` end that wait at once; the
poll stays the loop's heartbeat for everything else (TTL cancels, exits, the session).

Owner: one ``Wake`` per loop, bound by that loop's ``run``. Before ``bind`` (the tests,
which call ``submit`` and ``tick`` directly) ``set`` does nothing and ``sleep`` sleeps.
"""
from __future__ import annotations

import asyncio


class Wake:
    """An inbox's doorbell: ``set`` from the producer, ``sleep`` in the consumer's loop."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._event: asyncio.Event | None = None

    def bind(self) -> None:
        """Called from the consumer's ``run``, on its loop."""
        self._loop = asyncio.get_running_loop()
        self._event = asyncio.Event()

    def set(self) -> None:
        """Ring: the consumer's sleep ends now. Safe from any thread."""
        loop, event = self._loop, self._event
        if loop is None or event is None or loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            event.set()
        else:
            loop.call_soon_threadsafe(event.set)

    async def sleep(self, seconds: float) -> None:
        """Sleep ``seconds``, or until rung. A ring during the tick before ends it at once."""
        event = self._event
        if event is None:
            await asyncio.sleep(seconds)
            return
        try:
            await asyncio.wait_for(event.wait(), timeout=max(0.0, seconds))
        except asyncio.TimeoutError:  # maintainer: allow-swallow the poll elapsing is the normal end of the sleep
            pass
        event.clear()
