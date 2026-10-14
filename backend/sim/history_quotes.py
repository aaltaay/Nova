"""The NBBO a Massive window carries: the bid and ask at the playhead, and each print's side (ADR 046).

Held as compact arrays (about 44 bytes a row) so a busy symbol-day fits a selection.
Nothing reads ahead:

- the bid and ask at the playhead are the last NBBO row at or before it;
- a print's side is judged against the last NBBO row strictly before the print, by
  the live tape's own rule (``ibkr/tape_side.classify_print_side``), so a replayed
  print is coloured the way the live tape colours one. A quote stamped at the
  print's own nanosecond cannot be ordered against it (trades and quotes carry
  separate SIP sequences) and is not used; a crossed quote, or none yet, decides
  nothing.

Pure: arrays, bisect and the tape rule.
"""
from __future__ import annotations

import bisect
import math
from array import array
from collections.abc import Iterable

from constants_sim import SIM_MASSIVE_EXCHANGES, SIM_MASSIVE_QUOTE_SOURCE, SIM_MASSIVE_SIDE_SOURCE

_NAN = float("nan")
_COLUMNS = ("ts", "bid", "bid_size", "bid_x", "ask", "ask_size", "ask_x")


def _num(value) -> float:
    return _NAN if value is None else float(value)


def _out(value: float) -> float | None:
    return None if math.isnan(value) else value


class QuoteSeries:
    """One window's NBBO rows in time order (an import builds one in file order and sorts it once)."""

    __slots__ = _COLUMNS

    def __init__(self, rows: Iterable[tuple] = ()):
        """``rows``: ``(ts, bid, bid_size, bid_x, ask, ask_size, ask_x, ...)``, oldest first; a missing side is
        ``None``. Fields past the seventh (the files' conditions and indicators) are not kept."""
        self.ts, self.bid, self.bid_size, self.ask, self.ask_size = (array("d") for _ in range(5))
        self.bid_x, self.ask_x = array("h"), array("h")
        for row in rows:
            self.append(row)

    def append(self, row: tuple) -> None:
        ts, bid, bid_size, bid_x, ask, ask_size, ask_x = row[:7]
        self.ts.append(float(ts))
        self.bid.append(_num(bid))
        self.bid_size.append(_num(bid_size))
        self.bid_x.append(int(bid_x or 0))
        self.ask.append(_num(ask))
        self.ask_size.append(_num(ask_size))
        self.ask_x.append(int(ask_x or 0))

    def __len__(self) -> int:
        return len(self.ts)

    def rows(self) -> list[tuple]:
        """Every row as ``(ts, bid, bid_size, bid_x, ask, ask_size, ask_x)``, a missing side ``None`` again."""
        return [(self.ts[i], _out(self.bid[i]), _out(self.bid_size[i]), self.bid_x[i], _out(self.ask[i]),
                 _out(self.ask_size[i]), self.ask_x[i]) for i in range(len(self))]

    def take(self, positions: Iterable[int]) -> QuoteSeries:
        """A series of the rows at ``positions``, in that order."""
        at = list(positions)
        out = QuoteSeries()
        for name in _COLUMNS:
            col = getattr(self, name)
            setattr(out, name, array(col.typecode, (col[i] for i in at)))
        return out

    def span(self, lo: int, hi: int) -> QuoteSeries:
        out = QuoteSeries()
        for name in _COLUMNS:
            setattr(out, name, getattr(self, name)[lo:hi])
        return out

    def within(self, start: float, end: float) -> QuoteSeries:
        """The rows with ``start <= ts < end``, in series order."""
        return self.take(i for i, t in enumerate(self.ts) if start <= t < end)

    def between(self, start: float, end: float) -> QuoteSeries:
        """A time-ordered series' rows in ``[start, end)``, after the one standing at ``start`` (if any)."""
        lo, hi = bisect.bisect_left(self.ts, start), bisect.bisect_left(self.ts, end)
        return self.span(max(0, lo - 1), max(hi, lo))

    def in_time_order(self) -> QuoteSeries:
        """This series ordered by ``ts`` (stable); itself when already in order."""
        ts = self.ts
        if all(ts[i - 1] <= ts[i] for i in range(1, len(ts))):
            return self
        return self.take(sorted(range(len(ts)), key=ts.__getitem__))

    def extend(self, other: QuoteSeries) -> None:
        for name in _COLUMNS:
            getattr(self, name).extend(getattr(other, name))

    def pack(self) -> bytes:
        from sim.print_table import pack_columns

        return pack_columns({name: getattr(self, name) for name in _COLUMNS}, {})

    @classmethod
    def unpack(cls, blob: bytes) -> QuoteSeries:
        from sim.print_table import unpack_columns

        columns, _extra = unpack_columns(blob)
        out = cls()
        for name in _COLUMNS:
            setattr(out, name, columns[name])
        if any(len(getattr(out, name)) != len(out.ts) for name in _COLUMNS):
            raise ValueError("a packed quote series' columns differ in length")
        return out

    def _row(self, i: int) -> dict | None:
        if i < 0:
            return None
        return dict(ts=self.ts[i], bid=_out(self.bid[i]), bid_size=_out(self.bid_size[i]),
                    bid_exchange=SIM_MASSIVE_EXCHANGES.get(self.bid_x[i]), ask=_out(self.ask[i]),
                    ask_size=_out(self.ask_size[i]), ask_exchange=SIM_MASSIVE_EXCHANGES.get(self.ask_x[i]))

    def at(self, t: float) -> dict | None:
        """The NBBO in force at ``t``: the last row at or before it, else ``None``."""
        return self._row(bisect.bisect_right(self.ts, float(t)) - 1)

    def before(self, t: float) -> dict | None:
        """The last NBBO row strictly before ``t``, else ``None``."""
        return self._row(bisect.bisect_left(self.ts, float(t)) - 1)


def snapshot_fields(series: QuoteSeries | None, t: float, status: str | None) -> dict:
    """The snapshot's bid / ask block at ``t``; every field ``None`` when the window holds no quote yet.

    ``quote_status`` says why one is missing: ``not_downloaded`` (the day's quotes file is not
    on disk yet), ``none`` (the ticker had no quote in the window), ``complete``.
    """
    row = series.at(t) if series is not None and len(series) else None
    return dict(bid=row["bid"] if row else None, ask=row["ask"] if row else None,
                bid_size=row["bid_size"] if row else None, ask_size=row["ask_size"] if row else None,
                bid_exchange=row["bid_exchange"] if row else None, ask_exchange=row["ask_exchange"] if row else None,
                quote_ts=row["ts"] if row else None, quote_source=SIM_MASSIVE_QUOTE_SOURCE if series is not None else None,
                quote_status=status)


def attach_sides(series: QuoteSeries, prints: list[dict]) -> int:
    """Set ``side`` / ``bid`` / ``ask`` / ``side_source`` on prints the NBBO decides; return how many."""
    from ibkr.tape_side import TAPE_SIDE_UNKNOWN, classify_print_side

    decided = 0
    for row in prints:
        row.update(side=None, bid=None, ask=None, side_source=None)
        quote = series.before(row["ts"])
        if quote is None:
            continue
        side = classify_print_side(row["price"], quote["bid"], quote["ask"])
        if side == TAPE_SIDE_UNKNOWN:
            continue
        row.update(side=side, bid=quote["bid"], ask=quote["ask"], side_source=SIM_MASSIVE_SIDE_SOURCE)
        decided += 1
    return decided


def top_of_book(series: QuoteSeries | None, symbol: str, t: float) -> dict | None:
    """The NBBO at ``t`` as a one-level book flagged ``l1_fallback`` (best bid and ask only, never depth)."""
    row = series.at(t) if series is not None and len(series) else None
    if row is None or (row["bid"] is None and row["ask"] is None):
        return None

    def level(price, size, venue):
        return [{"price": price, "size": size, "exchange": venue or "", "mm": venue or ""}] if price is not None else []
    return dict(symbol=symbol, bids=level(row["bid"], row["bid_size"], row["bid_exchange"]),
                asks=level(row["ask"], row["ask_size"], row["ask_exchange"]), ts=row["ts"],
                age_sec=max(0.0, float(t) - row["ts"]), l1_fallback=True, session_id=None, source=SIM_MASSIVE_QUOTE_SOURCE)
