"""What one Level 2 or Time & Sales socket was sent, said in the log when it closes.

Operator report 2026-11-17: the phone's tape "was not moving". The archive proved IBKR had delivered the prints to
Nova; nothing recorded what Nova had sent on to that socket, so the last hop could not be proved either way. Each
socket now leaves one INFO line: the stock, who asked, whether it was in front, how long it was open, how many
prints (or books) it was sent and when the last one went. Memory and the log only; never on the wire.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")


class Delivery:
    def __init__(self, kind: str, symbol: str, websocket: Any, *, front: bool) -> None:
        self.kind = kind          # "tape" | "depth"
        self.symbol = symbol
        self.front = front
        self.client = _client_of(websocket)
        self.opened = time.time()
        self.count = 0
        self.last: float | None = None

    def sent(self, count: int = 1) -> None:
        """*count* prints (or one book) went out on the socket now."""
        if count > 0:
            self.count += count
            self.last = time.time()

    def words(self, now: float | None = None) -> str:
        stamp = time.time() if now is None else now
        what = "print" if self.kind == "tape" else "book"
        name = "Time & Sales" if self.kind == "tape" else "Level 2"
        last = "none" if self.last is None else datetime.fromtimestamp(self.last, _ET).strftime("%H:%M:%S ET")
        return (f"{name} socket {self.symbol} from {self.client} closed after {stamp - self.opened:.1f} s: "
                f"{self.count} {what}{'' if self.count == 1 else 's'} sent, last {last}, front={int(self.front)}")

    def log(self) -> None:
        logger.info("%s", self.words())


def _client_of(websocket: Any) -> str:
    client = getattr(websocket, "client", None)
    host = getattr(client, "host", None)
    return str(host) if host else "unknown"
