"""Ordered setup snapshots, drained on a worker before the scanner accepts more work.

The live engine owns this outbox on its loop. Rows are copied at acceptance,
never coalesced, and only removed after their ordered batch commits. A failed
batch stays at the head; the next tick must retry it before producing rows.
There is no independent producer or unlimited executor submission queue.
"""
from __future__ import annotations

import asyncio
from collections import deque
from copy import deepcopy
from itertools import islice
from typing import Any

from constants_setups import SETUPS_PERSIST_BATCH_ROWS


class OrderedOutbox:
    def __init__(self, store: Any):
        self.store = store
        self.pending: deque[dict] = deque()
        self.durable: dict[tuple[str, str], bool] = {}
        self._lock = asyncio.Lock()

    def begin_session(self, session: str) -> None:
        self.durable = {key: triggered for key, triggered in self.durable.items() if key[0] == session}

    def save(self, row: dict) -> None:
        self.pending.append(deepcopy(row))

    async def _drain(self) -> None:
        async with self._lock:
            while self.pending:
                batch = list(islice(self.pending, SETUPS_PERSIST_BATCH_ROWS))
                await asyncio.to_thread(self.store.upsert_batch, batch)
                for row in batch:
                    key = (row["session_date"], row["id"])
                    self.durable[key] = (bool(row.get("triggered_at")) if "triggered_at" in row
                                         else self.durable.get(key, False))
                    self.pending.popleft()

    async def flush(self) -> None:
        """Await durability; cancellation still joins all accepted writes before returning."""
        if not self.pending:
            return
        task = asyncio.create_task(self._drain())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                # Even repeated cancellation must not abandon a SQLite call or close its store underneath it.
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError
