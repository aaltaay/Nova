"""A historical window as the eyes read it (ADR 052): the Sim's loaded download, made a ``Recording``.

The Sim eyes run today's templates over whatever the Sim desk replays, so a window loaded from
the Massive flat files or an IBKR download (``sim.history_playback``) gets the same lanes a
Session Record gets (``eyes/replay.py``). What the window holds decides what the lanes can read:

- **Prints**: every print of the window, each with the side the window's NBBO gives it -- the last
  quote strictly before the print, as the Sim tape colours it (``history_quotes.attach_sides``).
  The rows are copied small (time, price, size, exchange, side, whether it sets a price); the
  window's own rows are shared and never touched.
- **The book**: a Massive window's NBBO, sampled as the live tape feed samples Level 2, as a
  one-level book -- the best bid and ask with their sizes. It is not Level 2: a wall behind the
  inside is invisible, and ``book`` says ``nbbo``. An IBKR download carries no bid or ask: no
  book, no sides, and the tape gate reads blind there -- nothing goes, so nothing is traded.
- **Bars**: the bar archive's one-minute bars of the day (the bars the live eyes saw, 04:00 on)
  when Nova has them, else the window's own candles -- the ones the Sim chart draws.
- **Spans**: the window's downloaded ranges; outside them nothing is near and nothing triggers.

Nothing here reads past a moment by itself: ``EyesReplay`` steps the lanes forward and asks only
for what is at or before its clock.
"""
from __future__ import annotations

import bisect
import logging
from typing import Any

from constants_eyes import EYES_REPLAY_BOOK_SAMPLE_SEC, EYES_REPLAY_PRICE_STEP_SEC
from eyes.recording import Recording, _ticks, archive_bars
from setup_scanner.bars import Bar, bar_from

logger = logging.getLogger(__name__)

BOOK_NBBO = "nbbo"
BOOK_NONE = "none"
_WINDOW_BARS = 16 * 60


def key_of(spec: dict[str, Any]) -> tuple:
    """What makes a loaded window another one for the eyes: the window, its source, and how much of it is
    downloaded (a download still fetching grows)."""
    return ("historical", str(spec.get("symbol") or "").upper(), spec.get("date"), spec.get("start"),
            spec.get("end"), spec.get("source"), spec.get("job_id"), int(spec.get("trade_count") or 0),
            spec.get("quote_status"))


def _side(quotes: Any, ts: float, price: float) -> str | None:
    """The print's side against the last NBBO strictly before it; None without one (never guessed)."""
    from ibkr.tape_side import TAPE_SIDE_UNKNOWN, classify_print_side

    i = bisect.bisect_left(quotes.ts, ts) - 1
    if i < 0:
        return None
    bid, ask = quotes.bid[i], quotes.ask[i]
    side = classify_print_side(price, None if bid != bid else bid, None if ask != ask else ask)
    return None if side == TAPE_SIDE_UNKNOWN else side


def _prints(rows: tuple, quotes: Any, sets_price: Any) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        ts, price = float(row["ts"]), float(row["price"])
        out.append({"ts": ts, "price": price, "size": row.get("size"), "exchange": row.get("exchange"),
                    "side": _side(quotes, ts, price) if quotes is not None and len(quotes) else None,
                    "sets_price": bool(sets_price(row))})
    return out


def _level(price: float, size: float) -> list[dict]:
    if price != price or price <= 0:            # NaN: no quote on that side
        return []
    return [{"price": price, "size": 0.0 if size != size else size}]


def nbbo_books(quotes: Any, spans: list[tuple[float, float]],
               step: float = EYES_REPLAY_BOOK_SAMPLE_SEC) -> list[tuple[float, dict]]:
    """The NBBO as one-level books, sampled every ``step`` inside the downloaded spans -- the quote in force
    at each sample, as the live tape feed samples the book a held line shows. Never before the first quote,
    never outside a span (a stretch not downloaded has no book)."""
    out: list[tuple[float, dict]] = []
    if quotes is None or not len(quotes):
        return out
    last_i, book = -1, None
    for a, b in spans:
        t = (int(a // step) + 1) * step if a % step else float(a)
        while t <= b:
            i = bisect.bisect_right(quotes.ts, t) - 1
            if i >= 0:
                if i != last_i:
                    last_i = i
                    book = {"bids": _level(quotes.bid[i], quotes.bid_size[i]),
                            "asks": _level(quotes.ask[i], quotes.ask_size[i]), "l1_fallback": True}
                out.append((t, book))
            t += step
    return out


def _window_bars(selection: Any) -> list[Bar]:
    """The window's own one-minute candles, completed ones only (the ones the Sim chart draws)."""
    from datetime import datetime

    spec = selection.spec
    out: list[Bar] = []
    for row in selection.candles.bars(spec["symbol"], "1Min", _WINDOW_BARS, spec["end_ts"]):
        if row.get("partial"):
            continue
        t = row.get("t")
        ts = datetime.fromisoformat(t).timestamp() if isinstance(t, str) else float(t)
        bar = bar_from({"t": ts, "o": row["o"], "h": row["h"], "l": row["l"], "c": row["c"], "v": row["v"]})
        if bar is not None:
            out.append(bar)
    return sorted(out, key=lambda b: b.t)


def from_selection(selection: Any, *, bars_fn: Any = archive_bars) -> Recording:
    """The loaded window as a ``Recording``. Raises ``ValueError`` when it holds no prints to read."""
    from sim.history_playback import _sets_price

    spec = selection.spec
    sym, date = str(spec["symbol"]).upper(), str(spec["date"])
    if not selection.prints:
        raise ValueError(f"the {sym} {date} window holds no prints yet")
    quotes = selection.quotes if selection.quotes is not None and len(selection.quotes) else None
    prints = _prints(selection.prints, quotes, _sets_price)
    try:
        bars, bars_source = bars_fn(sym, date), "archive"
    except Exception:
        logger.warning("eyes: archive bars unread for %s %s", sym, date, exc_info=True)
        bars, bars_source = [], "archive"
    if not bars:
        bars, bars_source = _window_bars(selection), "window"
    spans = [(float(a), float(b)) for a, b in (spec.get("coverage") or [])]
    books = nbbo_books(quotes, spans)
    return Recording(date=date, symbol=sym, prints=prints, print_ts=[p["ts"] for p in prints],
                     ticks=_ticks(prints, EYES_REPLAY_PRICE_STEP_SEC), books=books, book_ts=[t for t, _ in books],
                     bars=bars, bars_source=bars_source if bars else "none", spans=spans,
                     prev_close=selection.prev_close,
                     diagnostics={"book": BOOK_NBBO if quotes is not None else BOOK_NONE,
                                  "sides": BOOK_NBBO if quotes is not None else BOOK_NONE,
                                  "source": spec.get("source") or "ibkr"})


def load_loaded() -> Recording:
    """The window the Sim desk has loaded now. Raises ``ValueError`` when none is."""
    from sim import history_playback

    selection = history_playback.selected()
    if selection is None:
        raise ValueError("no historical window is loaded")
    return from_selection(selection)
