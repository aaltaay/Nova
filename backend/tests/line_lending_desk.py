"""A stand-in desk for the line-lending tests (ADR 043 decision 6): three depth lines, the
Trader tabs' sockets on them, the tape lines, the focus sensor and the setup scanner's lanes.

The depth and tape fakes replace ``ibkr.depth`` / ``ibkr.tape_stream``'s functions; a
lent frame closes the lender's tab sockets at once, as a real socket does when it reads it.
"""
from __future__ import annotations

import time
from typing import Any

from constants_ibkr import IBKR_MAX_DEPTH_SYMBOLS


class Det:
    def __init__(self, state: str):
        self.state = state


class Lane:
    """A template in play: its armed / near setups and the trades it is scoring."""

    def __init__(self, setup: str = "first_pullback", *, near=(), armed=(), trades=()):
        self.setup = setup
        self.det = {s: Det("near") for s in near} | {s: Det("armed") for s in armed}
        self.active_id = {s: f"{s}-2026-10-01-1" for s in self.det}
        self.rows = {f"{s}-2026-10-01-0": {"symbol": s} for s in trades}

    def watching(self):
        return set(self.det)

    def trades(self, now):
        return list(self.rows)


class Desk:
    def __init__(self) -> None:
        self.lines: dict[str, dict[str, Any]] = {}
        self.tape: dict[str, int] = {}
        self.frames: list[tuple[str, dict]] = []
        self.unsubscribed: list[str] = []
        self.tape_dropped: list[str] = []
        self.tape_refused: str | None = None
        self.lanes: list[Lane] = []
        self.tab_tokens: dict[str, list[int]] = {}

    # -- depth ------------------------------------------------------------------
    def tab_line(self, symbol: str, sockets_open: int = 1, *, front: bool = False) -> None:
        """A Trader tab's Level 2 on ``symbol`` (``sockets_open`` sockets)."""
        from line_lending import sockets

        self.lines[symbol] = {"live": True, "viewers": sockets_open}
        self.tab_tokens[symbol] = [sockets.opened(symbol, tab=True, front=front, now=time.time() - 120)
                                   for _ in range(sockets_open)]

    def subscribed_symbols(self) -> list[str]:
        return list(self.lines)

    def is_live(self, symbol: str) -> bool:
        return bool(self.lines.get(symbol, {}).get("live"))

    def is_subscribed(self, symbol: str) -> bool:
        return symbol in self.lines

    def viewer_count(self, symbol: str) -> int:
        return int(self.lines.get(symbol, {}).get("viewers", 0))

    async def subscribe_async(self, symbol: str, *, live: bool = False) -> dict:
        if symbol in self.lines:
            return {"ok": True, "error": None}
        if len(self.lines) >= IBKR_MAX_DEPTH_SYMBOLS:
            idle = [s for s, row in self.lines.items() if row["viewers"] <= 0]
            if not idle:
                return {"ok": False, "error": f"Symbol cap reached ({IBKR_MAX_DEPTH_SYMBOLS} max)"}
            self.unsubscribe(idle[0])
        self.lines[symbol] = {"live": True, "viewers": 0}
        return {"ok": True, "error": None}

    def ws_viewer_opened(self, symbol: str) -> None:
        self.lines.setdefault(symbol, {"live": True, "viewers": 0})["viewers"] += 1

    def ws_viewer_closed(self, symbol: str) -> bool:
        row = self.lines.get(symbol)
        if row is None:
            return True
        row["viewers"] -= 1
        return row["viewers"] <= 0

    def unsubscribe(self, symbol: str) -> None:
        self.lines.pop(symbol, None)
        self.unsubscribed.append(symbol)

    def push_lent(self, symbol: str, frame: dict) -> None:
        from line_lending import sockets

        self.frames.append((symbol, dict(frame, type="lent")))
        for token in self.tab_tokens.pop(symbol, []):
            sockets.closed(symbol, token)
            self.ws_viewer_closed(symbol)

    # -- tape -------------------------------------------------------------------
    def tape_is_subscribed(self, symbol: str) -> bool:
        return symbol in self.tape

    async def tape_subscribe_async(self, symbol: str) -> dict:
        if self.tape_refused:
            return {"ok": False, "error": self.tape_refused}
        self.tape.setdefault(symbol, 0)
        return {"ok": True, "error": None}

    def tape_viewer_opened(self, symbol: str) -> None:
        self.tape[symbol] = self.tape.get(symbol, 0) + 1

    def tape_viewer_closed(self, symbol: str) -> bool:
        self.tape[symbol] = self.tape.get(symbol, 0) - 1
        return self.tape[symbol] <= 0

    def tape_unsubscribe(self, symbol: str) -> None:
        self.tape.pop(symbol, None)
        self.tape_dropped.append(symbol)


def window(symbol: str | None, tabs: list[str], *, visible: bool = True, instance: str = "w1",
           window_id: str = "main", page: str = "trader") -> dict:
    """One desk window's focus report (ADR 033)."""
    return {"schema_version": 1, "role": "main", "window_id": window_id, "instance_id": instance,
            "focused": visible, "visible": visible, "page": page, "tab": None, "symbol": symbol,
            "symbol_source": "trader_tab" if symbol else None, "trader_tabs": list(tabs),
            "last_input_ts": None, "reason": "focus", "ui_tag": None}


def install(monkeypatch) -> Desk:
    """Swap the depth and tape lines, the scanner's lanes and the IBKR session for the stand-ins."""
    from capture import feed_hold
    from ibkr import client, tape_stream
    from ibkr import depth as depth_facade
    from ibkr.depth import state as depth_state
    from l2 import continuous
    from leaderboard import auto_record
    from line_lending import borrowers, loans, sockets
    from sensors import focus_store
    from stock_mode import store

    desk = Desk()
    loans.reset_for_tests()
    sockets.reset_for_tests()
    focus_store.reset_for_tests()
    store.reset_for_tests()
    auto_record.reset_for_tests()
    feed_hold.reset_for_tests()
    for name in ("subscribed_symbols", "is_live", "is_subscribed", "viewer_count", "subscribe_async",
                 "ws_viewer_opened", "ws_viewer_closed", "unsubscribe"):
        monkeypatch.setattr(depth_facade, name, getattr(desk, name))
    monkeypatch.setattr(depth_state, "push_lent", desk.push_lent)
    monkeypatch.setattr(tape_stream, "is_subscribed", desk.tape_is_subscribed)
    monkeypatch.setattr(tape_stream, "subscribe_async", desk.tape_subscribe_async)
    monkeypatch.setattr(tape_stream, "ws_viewer_opened", desk.tape_viewer_opened)
    monkeypatch.setattr(tape_stream, "ws_viewer_closed", desk.tape_viewer_closed)
    monkeypatch.setattr(tape_stream, "unsubscribe", desk.tape_unsubscribe)

    async def stop(_symbol: str) -> None:
        return None

    monkeypatch.setattr(continuous, "stop", stop)
    monkeypatch.setattr(client, "is_ready", lambda: True)
    monkeypatch.setattr(borrowers, "_lanes", lambda: list(desk.lanes))
    return desk


def line_loan_lines() -> list[dict]:
    from bot.persist import read_audit_lines

    return [row for row in read_audit_lines(limit=500) if row.get("action") == "line_loan"]
