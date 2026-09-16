"""Generic-tick bookkeeping for the shared owner-aware L1 line (ADR 010).

``ib_async.IB.reqMktData`` is idempotent per qualified contract: a second call
returns the pooled ``Ticker`` and issues **no** IB request, so a caller that
needs an extra generic tick (e.g. 236 shortableShares) cannot get it by opening
its own line -- and its ``cancelMktData`` would close the one line the desk is
using for scanner / detail / HOD prices.

Adding a tick to a live line therefore means cancel + re-request. That is safe
for other owners because the ``Ticker`` is pooled per contract and is *not* set
done on close, so every attached ``updateEvent`` handler survives.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Documented STK generic ticks Nova may put in reqMktData genericTickList.
# Sources: TWS API "Generic tick required" column + the Warning 321 legal
# list IB printed on ZTG (100, 101, 105, 106, 165, 221/220, 225, 232/221,
# 233, 236, 258/47, 292, 375, 411, 456/59, ...). Tick TYPE 49 is absent.
STK_GENERIC_TICKS_LEGAL = frozenset({
    "47", "59", "100", "101", "104", "105", "106", "162", "165",
    "220", "221", "225", "232", "233", "236", "258",
    "292", "293", "294", "295", "318",
    "375", "411", "456", "460",
    "576", "577", "578", "586", "588", "595", "614", "619", "623",
})


def parse(generic_ticks: str | None) -> list[str]:
    return [part.strip() for part in str(generic_ticks or "").split(",") if part.strip()]


def sanitize(generic_ticks: str | None) -> list[str]:
    """Keep only documented legal STK generic ticks (Warning 321 / #178).

    Incoming tick types such as 49 (Halted -> ``ticker.halted``) are not
    requestable. Dropping them here is the last fence if a caller still asks.
    """
    kept: list[str] = []
    for tick in parse(generic_ticks):
        if tick in STK_GENERIC_TICKS_LEGAL:
            if tick not in kept:
                kept.append(tick)
            continue
        logger.warning(
            "IBKR ticks: dropped illegal STK generic tick %s "
            "(Halted is ticker.halted / tick type 49, not requestable)",
            tick,
        )
    return kept


def has_all(existing: str | None, requested: str | None) -> bool:
    have = set(sanitize(existing))
    # Parse the raw ask: illegal ticks (49) are never on the line, so
    # has_all("233", "49") is False. Sanitizing the ask would make
    # all([]) True and hide Warning 321 regressions.
    return all(tick in have for tick in parse(requested))


def merge(existing: str | None, requested: str | None) -> str:
    merged = sanitize(existing)
    for tick in sanitize(requested):
        if tick not in merged:
            merged.append(tick)
    return ",".join(merged)


def upgrade_line(ib: Any, symbol: str, sub: dict[str, Any], requested: str) -> bool:
    """Re-request ``symbol``'s L1 line with ``requested`` ticks added.

    Returns True when the line is live with the merged tick list. On failure the
    caller must drop the subscription entry: the old reqId is already cancelled,
    so leaving it in place would be a zombie that blocks a later re-subscribe.
    """
    contract = sub.get("contract")
    if ib is None or contract is None:
        return False
    merged = merge(sub.get("generic_ticks"), requested)
    try:
        ib.cancelMktData(contract)
        ticker = ib.reqMktData(contract, merged, False, False)
    except Exception as exc:
        logger.warning(
            "IBKR ticks: generic-tick upgrade failed for %s (%s -> %s): %s",
            symbol, sub.get("generic_ticks") or "-", merged, exc,
        )
        return False
    _reattach_handler(symbol, sub, ticker)
    sub["ticker"] = ticker
    sub["generic_ticks"] = merged
    logger.info(
        "IBKR ticks: upgraded %s L1 generic ticks to %s (owners=%s)",
        symbol, merged, sorted(sub.get("owners") or set()),
    )
    return True


def _reattach_handler(symbol: str, sub: dict[str, Any], ticker: Any) -> None:
    """Keep the owner's update handler bound if a fresh Ticker came back.

    The pooled Ticker is normally the same object, so this is a no-op. Guarding
    it means a pooling change upstream cannot silently take the desk's L1
    updates dark for this symbol.
    """
    previous = sub.get("ticker")
    handler = sub.get("handler")
    if handler is None or ticker is previous:
        return
    if previous is not None:
        try:
            previous.updateEvent -= handler
        except (ValueError, AttributeError, KeyError, TypeError) as exc:
            logger.debug("IBKR ticks: detach on upgrade for %s: %s", symbol, exc)
    ticker.updateEvent += handler
