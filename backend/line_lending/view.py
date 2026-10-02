"""``GET /api/ibkr/depth/lines``: who holds each Level 2 line, and the loans (ADR 044 decision 6).

``{schema_version: 1, cap, lines: [{symbol, held_by, front, viewers}], lending: {on, loans, recent, error}}``
-- ``held_by`` is ``replay`` (a Sim replay slot), ``loan``, ``auto_record``, ``record`` (a Session
Record or the L2 recorder) or ``tab`` (a Trader tab's or another panel's Level 2); ``front`` whether
a visible window shows the symbol's Trader tab (null while the focus is unknown); ``viewers``
``ibkr.depth``'s count (sockets and holds alike). Reads memory only.
"""
from __future__ import annotations

import time
from typing import Any

from constants_ibkr import IBKR_MAX_DEPTH_SYMBOLS
from line_lending import focus as _focus
from line_lending import lines, loans
from line_lending.constants_line_lending import LINE_LENDING_SCHEMA_VERSION


def build(now: float | None = None) -> dict[str, Any]:
    from ibkr import depth

    ts = time.time() if now is None else float(now)
    focus = _focus.read(ts)
    loan_lines = loans.loan_lines()
    auto = lines.auto_record_symbols()
    rows = [{"symbol": sym,
             "held_by": lines.holder_of(sym, loan_lines=loan_lines, auto_symbols=auto),
             "front": focus.is_front(sym),
             "viewers": depth.viewer_count(sym)}
            for sym in sorted(depth.subscribed_symbols())]
    return {"schema_version": LINE_LENDING_SCHEMA_VERSION, "generated_at": ts, "cap": IBKR_MAX_DEPTH_SYMBOLS,
            "lines": rows, "lending": loans.view()}
