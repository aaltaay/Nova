"""LULD on the Level 2 ladder (ADR 047): ``{"type": "luld", "data": view}`` on the depth socket.

The socket asks ``LuldPush.frame`` at most every ``LULD_PUSH_SEC``. A frame goes out when the
view changes -- the bands, the state, a limit state starting or running out -- and every
``LULD_REPEAT_SEC`` otherwise, so a quiet ladder still knows its line is current. The desk counts a
limit state's 15 seconds down itself, from ``limit.pause_at``.

Which view: the live feed's (``live.py``), or on a Sim desk off the live edge the loaded Session
Record's at the playhead (``replay.py``).

Owner: each socket's own ``LuldPush`` (in memory, gone with the socket).
"""
from __future__ import annotations

import time
from typing import Any

from luld import live, views
from luld.constants_luld import LULD_REPEAT_SEC


def source_view(symbol: str, now: float | None = None) -> dict[str, Any]:
    """The view the desk's venue shows: the live feed, or a replay at its playhead."""
    from sim.mode import is_replay_desk

    if is_replay_desk():
        from luld import replay

        return replay.view(symbol)
    return live.view(symbol, now)


class LuldPush:
    """One socket's last LULD frame."""

    def __init__(self, symbol: str) -> None:
        self.symbol = (symbol or "").upper()
        self.sig: tuple | None = None
        self.sent_at = 0.0

    def frame(self, now: float | None = None) -> dict[str, Any] | None:
        """The next view for this socket, or None when nothing changed and one went out lately."""
        mono = time.monotonic()
        view = source_view(self.symbol, now)
        sig = views.signature(view)
        if sig == self.sig and mono - self.sent_at < LULD_REPEAT_SEC:
            return None
        self.sig, self.sent_at = sig, mono
        return view
