"""Paper and Sim fill an SSR short only above the bid (ADR 048 decision 4).

Under SSR (Reg SHO Rule 201) a short may execute only above the national best bid: a buyer has to
lift it. So when a practice short entry would fill -- at placement or on a print -- and SSR is on or
unknown for the stock, it fills only at a price over the venue's bid at that moment; otherwise it
keeps resting (it is never cancelled for SSR). On a print "that moment" is the print's own: the bid
that stood when it traded (``bid_at`` on the venue's reference: the NBBO before it on a Massive
window, the recorded quote on a recording, the top of book the live print met at receipt) --
never the bid at the playhead or at the matcher's pass, which a jump or a late read moves. A bid
Nova cannot see proves nothing, so the short rests. A cover is never held by SSR.

The SSR read (``short_sale.ssr``) is reused for ``SSR_FILL_MEMO_SEC`` per venue and stock.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from constants_shorts import SSR_FILL_MEMO_SEC
from short_sale import ssr
from short_sale.hours import ET

_memo: dict[tuple[str, str], tuple[float, float, bool]] = {}
_EPS = 1e-9


def effective_on(venue: str, symbol: str, at: float, reference: Any) -> bool:
    """Whether SSR binds ``symbol`` on ``venue`` at ``at`` (unknown counts as on)."""
    from short_sale.facts import is_replay

    key = (venue, symbol)
    wall = time.monotonic()
    got = _memo.get(key)
    if got is not None and wall - got[0] <= SSR_FILL_MEMO_SEC and abs(at - got[1]) <= SSR_FILL_MEMO_SEC:
        return got[2]
    if is_replay(venue):
        day = datetime.fromtimestamp(at, ET).date().isoformat()
        read = ssr.replay(symbol, at, day, reference.prints_between)
    else:
        read = ssr.live(symbol, at)
    _memo[key] = (wall, at, read.effective_on)
    return read.effective_on


def _bid(reference: Any, symbol: str, at: float, on_print: bool) -> float | None:
    if not on_print:
        return reference.reference(symbol).bid
    getter = getattr(reference, "bid_at", None)
    return getter(symbol, at) if callable(getter) else None


def allows(venue: str, row: dict[str, Any], price: float, reference: Any, at: float, *,
           on_print: bool = False) -> bool:
    """A short entry ``row`` may fill at ``price`` at ``at``: SSR is off, or ``price`` is over the bid then.

    ``on_print``: ``at`` is a print's time and the bid is the one that stood then; otherwise the
    order is being placed and the bid is the venue's now.
    """
    if not row.get("short_entry"):
        return True
    symbol = str(row.get("symbol") or "").upper()
    if not effective_on(venue, symbol, at, reference):
        return True
    bid = _bid(reference, symbol, at, on_print)
    return bid is not None and float(price) > float(bid) + _EPS


def reset_for_tests() -> None:
    _memo.clear()
