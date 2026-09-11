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


def parse(generic_ticks: str | None) -> list[str]:
    return [part.strip() for part in str(generic_ticks or "").split(",") if part.strip()]


def has_all(existing: str | None, requested: str | None) -> bool:
    have = set(parse(existing))
    return all(tick in have for tick in parse(requested))


def merge(existing: str | None, requested: str | None) -> str:
    merged = parse(existing)
    for tick in parse(requested):
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
