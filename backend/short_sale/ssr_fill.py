"""Paper and Sim fill an SSR short only above the bid (ADR 048 decision 4).

Under SSR (Reg SHO Rule 201) a short may execute only above the national best bid: a buyer has to
lift it. So when a practice short entry would fill -- at placement or on a print -- and SSR is on or
unknown for the stock, it fills only at a price over the venue's bid at that moment; otherwise it
keeps resting (it is never cancelled for SSR). A bid Nova cannot see proves nothing, so the short
rests. A cover is never held by SSR.

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


def allows(venue: str, row: dict[str, Any], price: float, reference: Any, at: float) -> bool:
    """A short entry ``row`` may fill at ``price`` now: SSR is off, or ``price`` is over the bid."""
    if not row.get("short_entry"):
        return True
    symbol = str(row.get("symbol") or "").upper()
    if not effective_on(venue, symbol, at, reference):
        return True
    bid = reference.reference(symbol).bid
    return bid is not None and float(price) > float(bid) + _EPS


def reset_for_tests() -> None:
    _memo.clear()
