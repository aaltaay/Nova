"""HOD Momo's disk writer: one thread writes the day's alert and session-high
files, so neither event loop does (#553, ADR 010).

The throttled hot paths -- the consolidation tick on the HTTP loop, session
highs on the IB loop -- hand it a snapshot and return. Building the JSON and
the atomic rewrite (4-10 MB of alerts by the afternoon) run here. There is one
slot per (kind, date): a newer snapshot of a file replaces a queued one, and
slots are written oldest first. The date is the one the caller captured, never
re-read at write time. Anything that must follow these writes -- a forced save,
the rollover archive's read-merge-write, shutdown -- calls ``drain()`` first.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable

import cache as _cache
from constants import HOD_MOMO_WRITER_DRAIN_TIMEOUT_SEC
from hod_momo_models import AlertObject, alert_to_dict
from metrics.op_metrics import timed_sync

logger = logging.getLogger(__name__)

_cond = threading.Condition()
_slots: dict[tuple[str, str], Callable[[], None]] = {}
_writing = False
_thread: threading.Thread | None = None


def submit(kind: str, date: str, write: Callable[[], None]) -> None:
    """Queue ``write`` as the newest snapshot of (kind, date); nothing touches disk here."""
    global _thread
    with _cond:
        _slots[(kind, date)] = write
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_run, name="hod-momo-writer", daemon=True)
            _thread.start()
        _cond.notify_all()


def submit_alerts(date: str, alerts: list[AlertObject], ts: float) -> None:
    """Queue ``date``'s alert file from the caller's copy of the list.

    Alerts are not mutated once they are in ``today_alerts`` (consolidation
    fields are set before the insert), so this thread may read them.
    """
    submit("alerts", date, lambda: _cache.save_hod_momo_snapshot_for_date(
        date, [alert_to_dict(alert) for alert in alerts], ts,
    ))


def submit_highs(date: str, payload: dict) -> None:
    """Queue ``date``'s session-highs file; ``payload`` holds copies, not state."""
    submit("highs", date, lambda: _cache.save_hod_momo_highs_for_date(date, payload))


def drain(timeout: float | None = HOD_MOMO_WRITER_DRAIN_TIMEOUT_SEC) -> bool:
    """Wait until every queued snapshot is on disk. False (and logged) when
    ``timeout`` ran out first; the caller then goes on without it."""
    with _cond:
        done = _cond.wait_for(lambda: not _slots and not _writing, timeout)
    if not done:
        logger.warning("HOD Momo writer: still busy after %ss; continuing without it", timeout)
    return done


def _run() -> None:
    global _writing
    while True:
        with _cond:
            _cond.wait_for(lambda: bool(_slots))
            key = next(iter(_slots))
            write = _slots.pop(key)
            _writing = True
        kind, date = key
        try:
            with timed_sync(f"hod.write_{kind}"):
                write()
        except Exception:
            logger.warning("HOD Momo writer: %s for %s failed", kind, date, exc_info=True)
        finally:
            with _cond:
                _writing = False
                _cond.notify_all()
