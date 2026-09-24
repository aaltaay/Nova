"""A Level 1 line belongs to the IBKR session that opened it (#565).

At every READY ``ibkr.ticks`` lets go of the L1 lines the last session left,
and each owner (scanner, HOD Momo, a Trader tab, ...) subscribes again (audit
G1). How a line is let go follows the rule tape and depth lines already use
(``ibkr.line_session.fate``, #562), read from ib_async's registry on the IB in
hand:

* ``gone`` -- a new session: that IB never made the request (a new ``IB()``,
  or ib_async's disconnect wiped its registry). The entry is forgotten and
  nothing is cancelled.
* ``kept`` -- the same socket, IBKR restored connectivity with its data kept
  (1102): the line lives. Its entry stays, with its owners and its handler.
* ``lost`` -- the same socket, restored with data lost (1101): IBKR forgot the
  line, but ib_async still holds its ``reqMktData``, and ``reqMktData`` is
  idempotent per contract -- an owner asking again would get the dead ticker
  back and nothing would reach IBKR. The line is cancelled on the current IB
  first, so the owner's next ``reqMktData`` is a real request.

Runs on the IB loop inside READY, under ``ibkr.ticks``' subscribe lock. A
cancel is one non-blocking socket write (ADR 010).
"""
from __future__ import annotations

import logging
from typing import Any

from constants import IBKR_L1_REGISTRY_KIND
from ibkr import line_session

logger = logging.getLogger(__name__)


def settle(subs: dict[str, dict[str, Any]], ib: Any, *, reason: str) -> int:
    """Let go of every L1 line of the last session; the number let go. Kept lines stay in ``subs``."""
    fates: dict[str, list[str]] = {line_session.GONE: [], line_session.KEPT: [], line_session.LOST: []}
    for symbol, sub in list(subs.items()):
        ticker = sub.get("ticker")
        contract = sub.get("contract")
        fate = line_session.fate(ib, contract, IBKR_L1_REGISTRY_KIND, ticker)
        fates[fate].append(symbol)
        if fate == line_session.KEPT:
            continue
        _detach(symbol, ticker, sub.get("handler"))
        if fate == line_session.LOST:
            _cancel(ib, symbol, contract)
        subs.pop(symbol, None)
    if fates[line_session.KEPT]:
        logger.info("IBKR ticks: %d L1 line(s) survived the connectivity restore, IBKR kept them (%s): %s",
                    len(fates[line_session.KEPT]), reason or "unspecified", ", ".join(fates[line_session.KEPT]))
    if fates[line_session.LOST]:
        logger.warning("IBKR ticks: IBKR lost %d L1 line(s) in the connectivity restore; cancelled them so "
                       "their owners ask again (%s): %s", len(fates[line_session.LOST]),
                       reason or "unspecified", ", ".join(fates[line_session.LOST]))
    if fates[line_session.GONE]:
        logger.warning("IBKR ticks: cleared %d L1 line(s) of the last IBKR session (%s)",
                       len(fates[line_session.GONE]), reason or "unspecified")
    return len(fates[line_session.GONE]) + len(fates[line_session.LOST])


def _detach(symbol: str, ticker: Any, handler: Any) -> None:
    if ticker is None or handler is None:
        return
    try:
        ticker.updateEvent -= handler
    except (ValueError, AttributeError, KeyError, TypeError) as exc:
        logger.debug("IBKR ticks: handler detach during settle for %s: %s", symbol, exc)


def _cancel(ib: Any, symbol: str, contract: Any) -> None:
    """Cancel the lost line on the current IB (ib_async unregisters it even when the send fails)."""
    try:
        ib.cancelMktData(contract)
    except Exception:
        logger.warning("IBKR ticks: cancelMktData for %s's lost L1 line raised", symbol, exc_info=True)
