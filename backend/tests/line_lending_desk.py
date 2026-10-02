"""A stand-in desk for the line-lending tests (ADR 043 decision 6): three depth lines and three
AllLast lines (IBKR counts tick-by-tick lines like depth lines), the Trader tabs' sockets on them,
the focus sensor and the setup scanner's lanes.

The fakes replace ``ibkr.depth`` / ``ibkr.tape_stream`` / ``ibkr.tape_line`` /
``ibkr.tape_recording``'s functions; a lent frame closes the lender's tab sockets at once, as a
real socket does when it reads it.
"""
from __future__ import annotations

import time
from typing import Any

from constants_ibkr import IBKR_MAX_DEPTH_SYMBOLS

TAPE_CAP = 3
CAP_ERROR = "Max number of tick-by-tick requests has been reached."


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
        self.tape: dict[str, int] = {}               # symbol -> viewers, while its AllLast line is up
        self.tape_viewers: dict[str, int] = {}       # symbol -> viewers counted (a line may be down)
        self.frames: list[tuple[str, dict]] = []
        self.tape_frames: list[tuple[str, dict]] = []
        self.unsubscribed: list[str] = []
        self.tape_dropped: list[tuple[str, str]] = []
        self.tape_refused: str | None = None
        self.tape_ended: dict[str, dict[str, Any]] = {}
        self.last_print: dict[str, float] = {}
        self.guard: dict[str, float] = {}
        self.tape_asked: list[str] = []
        self.lanes: list[Lane] = []
        self.tab_tokens: dict[str, list[int]] = {}
        self.tape_tokens: dict[str, list[int]] = {}

    # -- a Trader tab -----------------------------------------------------------------
    def tab_line(self, symbol: str, sockets_open: int = 1, *, front: bool = False, tape: bool = True) -> None:
        """A Trader tab's Level 2 (and, with ``tape``, its Time & Sales) on ``symbol``."""
        from line_lending import sockets

        self.lines[symbol] = {"live": True, "viewers": sockets_open}
        self.tab_tokens[symbol] = [sockets.opened(symbol, tab=True, front=front, now=time.time() - 120)
                                   for _ in range(sockets_open)]
        if tape:
            self.tape[symbol] = sockets_open
            self.tape_viewers[symbol] = sockets_open
            self.tape_tokens[symbol] = [sockets.opened(symbol, tab=True, front=front, now=time.time() - 120,
                                                       kind=sockets.TAPE) for _ in range(sockets_open)]

    # -- depth ------------------------------------------------------------------------
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

    # -- tape -------------------------------------------------------------------------
    def tape_is_subscribed(self, symbol: str) -> bool:
        return symbol in self.tape

    def tape_viewer_count(self, symbol: str) -> int:
        return self.tape_viewers.get(symbol, 0)

    async def tape_subscribe_async(self, symbol: str) -> dict:
        self.tape_asked.append(symbol)
        if symbol in self.tape:
            return {"ok": True, "error": None}
        if self.tape_refused:
            return {"ok": False, "error": self.tape_refused}
        if len(self.tape) >= TAPE_CAP:
            return {"ok": False, "error": CAP_ERROR}
        self.tape[symbol] = 0
        self.tape_ended.pop(symbol, None)
        return {"ok": True, "error": None}

    def tape_viewer_opened(self, symbol: str) -> None:
        self.tape_viewers[symbol] = self.tape_viewers.get(symbol, 0) + 1

    def tape_viewer_closed(self, symbol: str) -> bool:
        self.tape_viewers[symbol] = self.tape_viewers.get(symbol, 0) - 1
        return self.tape_viewers[symbol] <= 0

    def tape_unsubscribe(self, symbol: str) -> None:
        """A closed socket's linger: the line stays up 16 s (the lending module must not wait for it)."""

    def tape_push_lent(self, symbol: str, frame: dict) -> None:
        from line_lending import sockets

        self.tape_frames.append((symbol, dict(frame, type="lent")))
        for token in self.tape_tokens.pop(symbol, []):
            sockets.closed(symbol, token, sockets.TAPE)
            self.tape_viewer_closed(symbol)

    def drop_tape_line(self, symbol: str, why: str) -> bool:
        if symbol not in self.tape:
            return False
        self.tape.pop(symbol)
        self.tape_dropped.append((symbol, why))
        self.guard[symbol] = 16.0
        return True

    def end_tape(self, symbol: str, code: int = 10190, message: str = CAP_ERROR) -> None:
        """IBKR ends a line after the request (its error arrives on its own)."""
        self.tape.pop(symbol, None)
        self.tape_ended[symbol] = {"at": time.time(), "cause": "ib_error", "code": code, "message": message}
        self.guard[symbol] = 16.0

    def ended(self, symbol: str) -> dict[str, Any] | None:
        return self.tape_ended.get(symbol)

    def guard_remaining(self, symbol: str, now: float | None = None) -> float:
        return self.guard.get(symbol, 0.0)

    def producer_status(self, symbol: str) -> dict:
        return {"last_print_ts": self.last_print.get(symbol)}


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
    from ibkr import client, tape_line, tape_recording, tape_stream
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
    for name, fake in (("is_subscribed", desk.tape_is_subscribed), ("viewer_count", desk.tape_viewer_count),
                       ("subscribe_async", desk.tape_subscribe_async), ("ws_viewer_opened", desk.tape_viewer_opened),
                       ("ws_viewer_closed", desk.tape_viewer_closed), ("unsubscribe", desk.tape_unsubscribe),
                       ("push_lent", desk.tape_push_lent), ("guard_remaining", desk.guard_remaining)):
        monkeypatch.setattr(tape_stream, name, fake)
    monkeypatch.setattr(tape_line, "drop_line", desk.drop_tape_line)
    monkeypatch.setattr(tape_line, "ended", desk.ended)
    monkeypatch.setattr(tape_recording, "producer_status", desk.producer_status)

    async def stop(_symbol: str) -> None:
        return None

    monkeypatch.setattr(continuous, "stop", stop)
    monkeypatch.setattr(client, "is_ready", lambda: True)
    monkeypatch.setattr(borrowers, "_lanes", lambda: list(desk.lanes))
    return desk


def line_loan_lines() -> list[dict]:
    from bot.persist import read_audit_lines

    return [row for row in read_audit_lines(limit=500) if row.get("action") == "line_loan"]
