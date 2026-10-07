"""The commands an agent queues for the desk to run (ADR 050): show a stock-day in the Sim, move the playhead.

In memory, touched only from async routes on the API's event loop, so no lock: the main desk window long-polls
``next_for_desk`` and reports each step; an agent reads ``wait_get``. A new show replaces one not finished (a
queued one at once, a running one at its next report, which answers ``cancelled`` so the desk stops). A command
a window took but never reported on goes back in the queue (the window went away while its poll still waited),
at most ``_MAX_CLAIMS`` times; one that stops reporting mid-way fails.
"""
from __future__ import annotations

import asyncio
import copy
import time
import uuid
from collections.abc import Callable
from typing import Any

from constants_agent_desk import (
    AGENT_COMMAND_CLAIM_SEC,
    AGENT_COMMAND_FIRST_REPORT_SEC,
    AGENT_COMMAND_KEEP,
    AGENT_COMMAND_LEASE_SEC,
    AGENT_COMMAND_STALE_SEC,
    AGENT_DESK_LISTEN_SEC,
)

ACTIVE = ("queued", "running")
TERMINAL = ("done", "failed", "expired", "cancelled")
DESK_STATUSES = ("running", "done", "failed")
_MAX_CLAIMS = 3


class CommandBoard:
    def __init__(self, now: Callable[[], float] = time.time) -> None:
        self._now = now
        self._commands: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []
        self._changed: asyncio.Event | None = None
        self._desk_polls = 0
        self._last_poll: float | None = None
        self._last_window: str | None = None

    # ── Change notice ───────────────────────────────────────────────────────

    def _event(self) -> asyncio.Event:
        if self._changed is None:
            self._changed = asyncio.Event()
        return self._changed

    def _notify(self) -> None:
        event, self._changed = self._changed, asyncio.Event()
        if event is not None:
            event.set()

    async def _wait_change(self, timeout: float) -> bool:
        if timeout <= 0:
            return False
        try:
            await asyncio.wait_for(self._event().wait(), timeout=timeout)
        except TimeoutError:
            return False
        return True

    # ── State ───────────────────────────────────────────────────────────────

    def listening(self) -> bool:
        """A main desk window is waiting for commands now, or asked within ``AGENT_DESK_LISTEN_SEC``."""
        if self._desk_polls > 0:
            return True
        return self._last_poll is not None and self._now() - self._last_poll < AGENT_DESK_LISTEN_SEC

    def desk(self) -> dict[str, Any]:
        return {"listening": self.listening(), "last_poll_ts": self._last_poll, "window_id": self._last_window}

    def _finish(self, command: dict[str, Any], status: str, *, result: Any = None, error: str | None = None) -> None:
        command["status"] = status
        command["updated_ts"] = self._now()
        if result is not None:
            command["result"] = result
        if error is not None:
            command["error"] = error

    def _requeue(self, command: dict[str, Any]) -> None:
        if command["claims"] >= _MAX_CLAIMS:
            self._finish(command, "failed", error="desk windows took it and never ran it")
            return
        now = self._now()
        command.update(status="queued", claimed_by=None, claimed_ts=None, queued_ts=now, updated_ts=now)

    def _expire(self) -> None:
        now = self._now()
        for command in self._commands.values():
            if command["status"] == "queued" and now - command["queued_ts"] > AGENT_COMMAND_CLAIM_SEC:
                self._finish(command, "expired",
                             error="no desk window took it: is Nova's desk open (its main window, not the sample)?")
            elif command["status"] != "running":
                continue
            elif not command["steps"] and now - (command["claimed_ts"] or now) > AGENT_COMMAND_FIRST_REPORT_SEC:
                self._requeue(command)
            elif (now - command["updated_ts"] > AGENT_COMMAND_LEASE_SEC
                  or now - command["created_ts"] > AGENT_COMMAND_STALE_SEC):
                self._finish(command, "failed", error="the desk stopped reporting on it")

    def active(self, kind: str | None = None) -> list[dict[str, Any]]:
        self._expire()
        return [copy.deepcopy(c) for cid in self._order if (c := self._commands[cid])["status"] in ACTIVE
                and (kind is None or c["kind"] == kind)]

    def get(self, command_id: str) -> dict[str, Any] | None:
        self._expire()
        command = self._commands.get(command_id)
        return copy.deepcopy(command) if command else None

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        self._expire()
        return [copy.deepcopy(self._commands[cid]) for cid in reversed(self._order[-limit:])]

    # ── Agents ──────────────────────────────────────────────────────────────

    def create(self, kind: str, args: dict[str, Any], plan: dict[str, Any] | None) -> dict[str, Any]:
        self._expire()
        now = self._now()
        if kind == "show":
            for cid in self._order:
                other = self._commands[cid]
                if other["kind"] == "show" and other["status"] in ACTIVE:
                    self._finish(other, "cancelled", error="replaced by a newer show")
        command = {
            "id": uuid.uuid4().hex[:12], "kind": kind, "status": "queued", "created_ts": now, "updated_ts": now,
            "args": dict(args), "plan": plan, "step": None, "steps": [], "result": None, "error": None,
            "claimed_by": None, "claimed_ts": None, "claims": 0, "queued_ts": now,
        }
        self._commands[command["id"]] = command
        self._order.append(command["id"])
        while len(self._order) > AGENT_COMMAND_KEEP:
            self._commands.pop(self._order.pop(0), None)
        self._notify()
        return copy.deepcopy(command)

    def cancel(self, command_id: str) -> dict[str, Any] | None:
        command = self._commands.get(command_id)
        if command is None:
            return None
        if command["status"] in ACTIVE:
            self._finish(command, "cancelled", error="cancelled by the agent")
            self._notify()
        return copy.deepcopy(command)

    async def wait_get(self, command_id: str, wait: float) -> dict[str, Any] | None:
        """The command, after up to ``wait`` seconds for it to change (at once when it has finished)."""
        command = self.get(command_id)
        if command is None or command["status"] in TERMINAL or wait <= 0:
            return command
        seen = command["updated_ts"]
        deadline = self._now() + wait
        while True:
            remaining = deadline - self._now()
            if not await self._wait_change(remaining):
                return self.get(command_id)
            command = self.get(command_id)
            if command is None or command["updated_ts"] != seen or command["status"] in TERMINAL:
                return command

    # ── The desk ────────────────────────────────────────────────────────────

    async def next_for_desk(self, wait: float, window_id: str | None) -> dict[str, Any] | None:
        """The oldest queued command, now ``running`` and the desk's; ``None`` after ``wait`` seconds."""
        self._desk_polls += 1
        self._last_poll, self._last_window = self._now(), window_id
        try:
            deadline = self._now() + wait
            while True:
                self._expire()
                queued = [self._commands[cid] for cid in self._order if self._commands[cid]["status"] == "queued"]
                if queued:
                    command = queued[0]
                    command.update(status="running", claimed_by=window_id, claimed_ts=self._now(),
                                   claims=command["claims"] + 1, updated_ts=self._now())
                    self._notify()
                    return copy.deepcopy(command)
                if not await self._wait_change(deadline - self._now()):
                    return None
        finally:
            self._desk_polls -= 1
            self._last_poll = self._now()

    def release(self, command_id: str) -> None:
        """The window that took it is gone before it ran anything: back in the queue for another."""
        command = self._commands.get(command_id)
        if command is not None and command["status"] == "running" and not command["steps"]:
            self._requeue(command)
            self._notify()

    def report(self, command_id: str, *, status: str, step: str | None = None, text: str | None = None,
               result: Any = None, error: str | None = None) -> dict[str, Any] | None:
        """A step from the desk. A command already finished (cancelled, expired) answers as it is: the desk stops."""
        command = self._commands.get(command_id)
        if command is None:
            return None
        if command["status"] not in ACTIVE:
            return copy.deepcopy(command)
        if status not in DESK_STATUSES:
            raise ValueError(f"status must be one of {', '.join(DESK_STATUSES)}")
        now = self._now()
        if step is not None or text is not None:
            last = command["steps"][-1] if command["steps"] else None
            entry = {"step": step or command["step"], "ts": now, "text": text}
            if last is not None and last["step"] == entry["step"]:
                command["steps"][-1] = entry       # a step's progress replaces its last line
            else:
                command["steps"].append(entry)
            command["step"] = entry["step"]
        command["updated_ts"] = now
        if status in ("done", "failed"):
            self._finish(command, status, result=result, error=error)
        else:
            command["status"] = "running"
        self._notify()
        return copy.deepcopy(command)


BOARD = CommandBoard()
