"""Diagnostics row for the L2 tape archive, the prints Paper resting orders fill on (ADR 020).

A resting Paper order fills only on prints the archive holds
(``practice.matcher`` reads ``l2.tape``), so an archive that stops writing
leaves every resting order waiting with nothing on the desk saying why. On
2026-09-24 the writer latched for 90 minutes and the only trace was
``/api/l2/status``. This row states it: which resting symbols cannot see their
prints, and every loss the writer counted (``ibkr.tape_sink``).
"""
from __future__ import annotations

from typing import Any

from constants_diagnostics import (
    DIAG_GROUP_PRACTICE,
    DIAG_STATE_FAIL,
    DIAG_STATE_OFF,
    DIAG_STATE_OK,
    DIAG_STATE_WARN,
)
from diagnostics.rows import row


def _names(symbols: list[str]) -> str:
    return ", ".join(symbols)


def tape_archive_rows(*, health: dict[str, Any], resting: list[str]) -> list[dict[str, Any]]:
    """``health`` is ``l2.tape.health()``; ``resting`` the symbols with an order resting on the live tape."""
    writer = health.get("writer") or {}
    symbols: dict[str, dict[str, Any]] = health.get("symbols") or {}
    resting = sorted({s.upper() for s in resting})
    # Prints arrive on the line but none has been archived for over a minute.
    blind = sorted(s for s, st in symbols.items()
                   if st.get("state") == "receiving" and st.get("sink_state") == "stale")
    unwatched = [s for s in resting if s not in symbols]
    blind_resting = [s for s in resting if s in blind]
    losing = bool(writer.get("losing"))
    error = writer.get("error")
    counts = f"{writer.get('written', 0)} written, {writer.get('dropped', 0)} lost this run"

    if resting and losing:
        state = DIAG_STATE_FAIL
        detail = f"resting {_names(resting)} can miss fills: {error}"
        cause = "The archive writer is losing prints now; a resting Paper order fills only on prints the archive holds."
        fix = ("It resumes on its own once it has room. If it stays, check disk space and the perf_stalls row. "
               "Fill now on the order sends a limit at the live bid / ask instead.")
    elif blind_resting or unwatched:
        state = DIAG_STATE_FAIL
        parts = []
        if blind_resting:
            parts.append(f"{_names(blind_resting)} printing but nothing archived for over a minute")
        if unwatched:
            parts.append(f"{_names(unwatched)} not archived")
        detail = "resting orders cannot fill: " + "; ".join(parts)
        cause = (f"The matcher reads resting orders' prints from the archive only. {error}" if error
                 else "The matcher reads resting orders' prints from the archive only.")
        fix = ("The matcher asks for a missing line every second (the log names why it would not open); "
               "if prints arrive and nothing is written, restart the backend. Fill now fills at the live bid / ask.")
    elif error or blind:
        state = DIAG_STATE_WARN
        detail = error or f"{_names(blind)} printing but nothing archived for over a minute"
        cause = ("Prints lost in that window cannot fill a resting order; the next print that crosses it still does."
                 if error else "The archive is not keeping these symbols' prints; none has a resting order.")
        fix = "Nothing to do unless it repeats; then check the perf_stalls row and disk space."
    elif not symbols and not resting:
        state = DIAG_STATE_OFF
        detail = "no symbol archived right now"
        cause = "A resting Paper order, a Level 2 panel or a recording adds one."
        fix = "Nothing to do."
    else:
        state = DIAG_STATE_OK
        detail = f"archiving {_names(sorted(symbols))} · {counts}"
        cause = "Resting Paper orders fill on the prints written here."
        fix = "Nothing to do."
    return [row(
        id="tape_archive",
        group=DIAG_GROUP_PRACTICE,
        title="Tape archive (Paper resting fills)",
        state=state,
        detail=detail,
        cause=cause,
        fix=fix,
        evidence={"writer": writer, "resting": resting, "blind": blind, "unwatched": unwatched,
                  "symbols": symbols},
    )]
