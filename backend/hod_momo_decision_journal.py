"""HOD Momo's decision journal: one line each time a symbol's verdict changes kind, a file per trading day.

Why it exists: on 2026-10-13 nobody could say why PFAI's breakout alerted 18 s late. The decision ring keeps 20
checks a symbol in memory, a restart loses it, and the per-trade log (``hod_momo_trade_log``) rotates every ~10
minutes at a busy premarket, so the 08:20 decisions were gone by 09:20. This journal writes a line only when the
*kind* of a symbol's verdict changes -- ``master_liquidity:rvol`` to fired, fired to ``hod`` -- with the full
reasons and the figures behind them, so "why didn't X alert at 08:20" is answered from disk for days.

Like the trade log it only queues on the caller's thread (the IB loop) and one listener thread writes.
Files: ``<log dir>/hod-decisions-YYYY-MM-DD.jsonl`` (the 04:00 ET session day), kept
``HOD_MOMO_DECISION_JOURNAL_KEEP_DAYS``. Line shape: ``architecture/schema/scanner.md``.
"""
from __future__ import annotations

import atexit
import json
import logging
import logging.handlers
import queue
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from constants import HOD_MOMO_DECISION_JOURNAL_KEEP_DAYS, HOD_MOMO_DECISION_JOURNAL_SCHEMA_VERSION
from market import ET, session_key_et
from paths import log_dir

journal_log = logging.getLogger("hod_momo.decisions")
FILE_PREFIX = "hod-decisions-"
_last_kind: dict[str, tuple] = {}
_last_day: str | None = None
_NUMBER_TAIL = re.compile(r":(-?[\d.]+|None)$")


def reason_kind(reason: str | None) -> str | None:
    """A reason without its figures: ``hod(price=6.9<hod=8.8)`` -> ``hod``, ``surge:2.6 < 5.0% in 5min`` -> ``surge``."""
    if not reason:
        return None
    head = re.split(r"[(\s]", str(reason), maxsplit=1)[0]
    return _NUMBER_TAIL.sub("", head)


def _kind(gate: str | None, strategies: list[dict]) -> tuple:
    if gate:
        return ("gate", reason_kind(gate))
    return tuple(
        (item.get("id"), "fired" if item.get("passed") else reason_kind(item.get("blocked_by")))
        for item in strategies
        if item.get("blocked_by") != "disabled"
    )


def journal_path(day: str, directory: Path | None = None) -> Path:
    return (directory or log_dir()) / f"{FILE_PREFIX}{day}.jsonl"


def note(ts: float, symbol: str, price: float, snap: dict[str, Any], gate: str | None,
         strategies: list[dict]) -> bool:
    """Queue a line when ``symbol``'s verdict changed kind since its last line; True when one was queued."""
    global _last_day
    if not journal_log.isEnabledFor(logging.INFO):
        return False
    day = session_key_et(datetime.fromtimestamp(float(ts), ET))
    if day != _last_day:
        _last_kind.clear()
        _last_day = day
    kind = _kind(gate, strategies)
    if _last_kind.get(symbol) == kind:
        return False
    _last_kind[symbol] = kind
    line = {
        "schema_version": HOD_MOMO_DECISION_JOURNAL_SCHEMA_VERSION,
        "ts": round(float(ts), 3),
        "day": day,
        "symbol": symbol,
        "price": price,
        "volume": snap.get("volume"),
        "rvol": snap.get("rvol"),
        "change_pct": snap.get("change_pct"),
        "float_shares": snap.get("float_shares"),
        "session_high": snap.get("session_high"),
        "gate": gate,
        "fired": [item.get("id") for item in strategies if item.get("passed")],
        "blocked": {str(item.get("id")): item.get("blocked_by") for item in strategies
                    if not item.get("passed") and item.get("blocked_by") != "disabled"},
    }
    journal_log.info(json.dumps(line, separators=(",", ":"), default=str), extra={"nova_day": day})
    return True


def read(symbol: str, day: str, *, start: float | None = None, end: float | None = None,
         directory: Path | None = None) -> list[dict]:
    """``symbol``'s lines on ``day`` (oldest first), within ``start`` <= ts < ``end`` when given."""
    path = journal_path(day, directory)
    if not path.exists():
        return []
    want = (symbol or "").strip().upper()
    out: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            if f'"symbol":"{want}"' not in raw:
                continue
            try:
                row = json.loads(raw)
            except ValueError:
                continue  # a torn last line from a killed process: the rest of the day still reads
            if start is not None and row.get("ts", 0) < start:
                continue
            if end is not None and row.get("ts", 0) >= end:
                continue
            out.append(row)
    return out


class _DayFiles(logging.Handler):
    """Appends each record to its session day's file; prunes days past the keep window on a new day."""

    def __init__(self) -> None:
        super().__init__()
        self._day: str | None = None
        self._fh = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            day = getattr(record, "nova_day", None) or session_key_et()
            if day != self._day:
                self._open(day)
            self._fh.write(record.getMessage() + "\n")
            self._fh.flush()
        except Exception:  # noqa: BLE001 -- logging's own contract: report, never raise into the writer thread
            self.handleError(record)

    def _open(self, day: str) -> None:
        if self._fh is not None:
            self._fh.close()
        path = journal_path(day)
        self._fh = path.open("a", encoding="utf-8")  # noqa: SIM115 -- held open for the day
        self._day = day
        days = sorted(p for p in path.parent.glob(f"{FILE_PREFIX}*.jsonl"))
        for old in days[:-int(HOD_MOMO_DECISION_JOURNAL_KEEP_DAYS)]:
            try:
                old.unlink()
            except OSError:
                logging.getLogger(__name__).warning("HOD decision journal: could not prune %s", old.name)

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
        super().close()


_listener: logging.handlers.QueueListener | None = None
if not any(isinstance(h, logging.handlers.QueueHandler) for h in journal_log.handlers):
    _queue: queue.SimpleQueue = queue.SimpleQueue()
    journal_log.addHandler(logging.handlers.QueueHandler(_queue))
    journal_log.setLevel(logging.INFO)
    journal_log.propagate = False
    _listener = logging.handlers.QueueListener(_queue, _DayFiles())
    _listener.start()
    atexit.register(_listener.stop)
