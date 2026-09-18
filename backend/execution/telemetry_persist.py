"""Ledger writes issued from IB callbacks (kept out of telemetry.py size budget).

Every function here queues one SQLite write through
:mod:`execution.persist_queue` so ``orderStatus`` / ``execDetails`` never open a
database connection on the IB connect-loop (ADR 010). Ordering is FIFO, so ack
lands before facts and facts before the fill row.
"""
from __future__ import annotations

import logging
from typing import Any

from execution import persist_queue

logger = logging.getLogger(__name__)


def submit_ack(
    order_id: int,
    ack_ns: int,
    status: str,
    execution_id: str | None,
    *,
    allow_upgrade: bool = False,
) -> None:
    def _write() -> None:
        from execution import store

        store.mark_ack_by_order_id(
            order_id, ack_ns, broker_status=status,
            execution_id=execution_id,
            allow_status_upgrade=allow_upgrade,
        )

    persist_queue.submit(f"ack order {order_id}", _write)


def submit_facts(
    order_id: int,
    execution_id: str,
    *,
    perm_id: int | None,
    filled_qty: float | None,
    avg_fill_price: float | None,
    commission: float | None = None,
) -> None:
    def _write() -> None:
        from execution.store_facts import record_broker_facts

        record_broker_facts(
            execution_id,
            perm_id=perm_id,
            filled_qty=filled_qty,
            avg_fill_price=avg_fill_price,
            commission=commission,
        )
        try:
            from journal.flatten_close import on_flatten_fill_recorded

            on_flatten_fill_recorded(execution_id)
        except Exception:
            logger.exception(
                "journal flatten_close failed after facts for %s", execution_id
            )

    persist_queue.submit(f"facts order {order_id}", _write)


def submit_fill_evidence(**kwargs: Any) -> None:
    def _write() -> None:
        from execution import evidence_store

        evidence_store.record_fill(**kwargs)

    persist_queue.submit(f"fill evidence order {kwargs.get('order_id')}", _write)


def submit_filled(order_id: int, filled_ns: int, execution_id: str | None) -> None:
    def _write() -> None:
        from execution import store

        store.mark_filled_by_order_id(
            order_id, filled_ns, execution_id=execution_id,
        )

    persist_queue.submit(f"fill order {order_id}", _write)


def submit_round_trip(watch: Any) -> None:
    def _write() -> None:
        from journal.round_trip import notify_watch_filled

        notify_watch_filled(watch)

    persist_queue.submit(f"round-trip order {watch.order_id}", _write)
