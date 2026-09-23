"""Queue depths and drop counts, read once a second (ADR 026).

Each probe reads one owner's state without changing it. Probes import their
owner lazily and read module state by name; ``test_perf_gauges`` pins every
name, so a rename breaks a test instead of silently dropping a gauge. A probe
that fails is left out of the sample and logged once.
"""
from __future__ import annotations

import logging
from typing import Callable

from perf import counters

logger = logging.getLogger(__name__)

_failed: set[str] = set()


def _archive() -> dict[str, float]:
    from archive import write_queue

    stats = write_queue.stats()
    pending = sum(v for k, v in stats.items() if k != "dropped_pending")
    return {"archive.pending": pending, "archive.dropped": stats.get("dropped_pending", 0)}


def _viewer_queued(module) -> int:
    return sum(q.qsize() for qs in list(module._viewer_queues.values()) for q in list(qs))


def _depth() -> dict[str, float]:
    from ibkr.depth import state

    return {"depth.viewer_queued": _viewer_queued(state)}


def _tape() -> dict[str, float]:
    from ibkr import tape_stream

    return {"tape.viewer_queued": _viewer_queued(tape_stream)}


def _setups() -> dict[str, float]:
    from setup_scanner import engine

    eng = engine._engine
    return {"setups.inbox": len(eng.inbox) if eng is not None else 0}


def _ib_bridge() -> dict[str, float]:
    from ibkr import client_bridge

    return {"ib.run_coro_inflight": client_bridge._run_coro_inflight}


def _ws() -> dict[str, float]:
    import scanner_push

    return {"ws.scanner.clients": len(scanner_push._clients)}


def _l2() -> dict[str, float]:
    from l2 import batch

    return {"l2.batch.pending": sum(batch.pending_counts().values())}


PROBES: tuple[tuple[str, Callable[[], dict[str, float]]], ...] = (
    ("archive", _archive),
    ("depth", _depth),
    ("tape", _tape),
    ("setups", _setups),
    ("ib_bridge", _ib_bridge),
    ("ws", _ws),
    ("l2", _l2),
)


def read() -> dict[str, float]:
    """Every gauge that answered, plus the cumulative drop counters."""
    out: dict[str, float] = {}
    for name, probe in PROBES:
        try:
            out.update(probe())
        except Exception:
            if name not in _failed:
                _failed.add(name)
                logger.warning("perf gauges: probe %s failed; left out of samples", name, exc_info=True)
    out.update(counters.read())
    return out
