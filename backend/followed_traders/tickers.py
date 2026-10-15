"""A followed trade's ticker and averages, checked when the feed may have read them glued to a price. Pure.

With no space between a ticker and its price on the stream's bar, the feed's OCR can take the ticker's last letter for
a digit: the bar's "SOFI 14.03" comes back SOF 114.03, and the ticker one letter shorter can be a real stock trading
near the true one's price. It can also read that letter twice, once in the ticker and once in front of the price: the
bar's "RGTI 12.08" came back RGTI 112.08, and the feed took it for an add from 12.08 to 112.08 (2026-10-15). The feed
puts a lost letter back when the trader's own reads show the longer ticker; one read glued from first frame to last
reaches Nova as read. ``check`` asks IBKR's tape at the entry (``exits.view`` in the route, a fake in tests) which
reading of the first price fits, and reads every later average against the one before it (``averages``) -- never a
number from a ticker or an average that may be wrong. Shapes: architecture/schema/followed-traders.md ("A ticker glued
to its price", "The letter read twice, and a glued average").
"""
from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from followed_traders.constants_followed import (
    FOLLOWED_AVG_FACTOR,
    FOLLOWED_NO_SUCH_TICKER,
    FOLLOWED_TICKER_FIT_PCT,
)

TapeAt = Callable[[str], dict[str, Any]]   # symbol -> IBKR's tape at the trade's entry (an ``exits.stated`` dict)
# The digits OCR reads a ticker's last letter as, the feed's own pairs (its reader puts a glued O back itself).
DIGIT_TO_LETTER = {"1": "I", "5": "S", "8": "B"}
MAX_TICKER = 5                             # letters in a US stock ticker
# A price as the bar writes it: no leading zero before another digit, 2 decimals (4 under $1).
BAR_PRICE_RE = re.compile(r"^(?:0|[1-9]\d{0,5})\.(?:\d{2}|\d{4})$")
STATES = ("checking", "as_read", "corrected", "unchecked")
ET = ZoneInfo("America/New_York")


def price_text(price: float) -> str:
    """The bar's text for a price: 2 decimals, or the 4 it had."""
    return f"{price:.2f}" if round(price, 2) == price else f"{price:.4f}"


def unglued(symbol: str, price: float) -> tuple[str, float] | None:
    """``('SOF', 114.03)`` -> ``('SOFI', 14.03)``: the price's first digit put back on the ticker as the letter OCR
    took it for, when what is left is still a price the bar writes (above zero) and the ticker at most ``MAX_TICKER``
    letters; else None."""
    text = price_text(price)
    letter = DIGIT_TO_LETTER.get(text[0])
    if letter is None or not symbol.isalpha() or len(symbol) >= MAX_TICKER or not BAR_PRICE_RE.match(text[1:]):
        return None
    rest = float(text[1:])
    return (symbol + letter, rest) if rest > 0 else None


def doubled(symbol: str, price: float) -> float | None:
    """``('RGTI', 112.08)`` -> ``12.08``: the price without its first digit, when that digit is the one OCR reads the
    ticker's own last letter as -- the letter read twice, in the ticker and in front of the price -- and what is left
    is still a price the bar writes (above zero); else None. The shape alone proves nothing (a real RGTI 14.03 has
    it): only IBKR's tape, or the average before it, says which reading the bar showed."""
    text = price_text(price)
    letter = DIGIT_TO_LETTER.get(text[0])
    if letter is None or not symbol.isalpha() or not symbol.endswith(letter) or not BAR_PRICE_RE.match(text[1:]):
        return None
    rest = float(text[1:])
    return rest if rest > 0 else None


def fits(price: float, tape: dict[str, Any]) -> bool:
    """The price within ``FOLLOWED_TICKER_FIT_PCT`` of IBKR's trade at that time, or of its range widened as much."""
    tol = FOLLOWED_TICKER_FIT_PCT / 100.0
    if tape["state"] == "at" and tape["price"]:
        return abs(price / tape["price"] - 1.0) <= tol
    if tape["state"] == "range" and tape["low"] and tape["high"]:
        return tape["low"] * (1.0 - tol) <= price <= tape["high"] * (1.0 + tol)
    return False


def check(trade: dict[str, Any], tape_at: TapeAt) -> dict[str, Any] | None:
    """The trade's ``ticker`` (schema): its first price's reading (``_entry``), then its averages read in order
    (``averages``). None when nothing about it can be glued. The longer ticker's tape is asked for only when neither
    the ticker as read nor its letter read twice fits."""
    entry = _entry(trade, tape_at)
    if entry is not None and entry["state"] in ("checking", "unchecked"):
        return entry
    walked = averages(trade, entry)
    if walked["problem"] is not None:
        return _said(trade, walked, "unchecked", walked["problem"])
    if walked["fixed"] is not None and (entry is None or entry["state"] == "as_read"):
        return _said(trade, walked, "corrected", walked["fixed"])
    return entry


def _entry(trade: dict[str, Any], tape_at: TapeAt) -> dict[str, Any] | None:
    """Which reading of the first price fits IBKR's tape at the entry, or None when it cannot be a glued one."""
    read_symbol, read_price = trade["symbol"], trade["entry_price"]
    longer, twice = unglued(read_symbol, read_price), doubled(read_symbol, read_price)
    if longer is None and twice is None:
        return None
    named = longer or (read_symbol, twice)    # the glued reading named while none fits

    def said(state: str, why: str | None, other: tuple[str, float] = named) -> dict[str, Any]:
        return {"state": state, "read_symbol": read_symbol, "read_price": read_price, "other_symbol": other[0],
                "other_price": other[1], "why": why}

    as_read = tape_at(read_symbol)
    if as_read["state"] == "pending":
        return said("checking", as_read["why"] or "reading IBKR's tape at the entry")
    if fits(read_price, as_read):
        return said("as_read", None)
    read = f"the bar read {read_symbol} {price_text(read_price)}"
    if twice is not None and fits(twice, as_read):
        return said("corrected", f"{read}; IBKR at the entry: {read_symbol} {_tape_text(as_read)}: its last "
                                 "letter was read again in front of its price", (read_symbol, twice))
    twice_nearer = twice is not None and _gap(twice, as_read) < _gap(read_price, as_read)
    nearer_why = (f"{read}; IBKR at the entry: {read_symbol} {_tape_text(as_read)}, nearer "
                  f"{price_text(twice or 0.0)} (its last letter read twice) than what was read, but not within "
                  f"{FOLLOWED_TICKER_FIT_PCT:g}%")
    if longer is None:
        return said("unchecked", nearer_why, (read_symbol, twice)) if twice_nearer else said("as_read", None)
    longer_tape = tape_at(longer[0])
    if longer_tape["state"] == "pending":
        return said("checking", longer_tape["why"] or f"reading IBKR's tape at the entry for {longer[0]}")
    if longer_tape["state"] == "unavailable" and longer_tape["why"] == FOLLOWED_NO_SUCH_TICKER:
        # no longer ticker: as read, unless the letter read twice is nearer IBKR's price
        return said("unchecked", nearer_why, (read_symbol, twice)) if twice_nearer else said("as_read", None)
    tapes = f"{read}; IBKR at the entry: {read_symbol} {_tape_text(as_read)}, {longer[0]} {_tape_text(longer_tape)}"
    if fits(longer[1], longer_tape):
        return said("corrected", f"{tapes}: the ticker was read glued to its price")
    return said("unchecked", f"{tapes}: neither fits")


def averages(trade: dict[str, Any], ticker: dict[str, Any] | None) -> dict[str, Any]:
    """The trade's averages as the bar showed them, read in order from its first price as ``ticker`` shows it:
    ``{symbol, first, price, adds, fixed, problem}``. An add's average is kept when within ``FOLLOWED_AVG_FACTOR``
    of the one before it -- an add moves an average toward the price paid -- else its glued reading when that one is
    (``_readings``); an add whose average, put back, is the one before it is the same average read again and is left
    out. ``fixed`` says what was put back first (None when nothing was); ``problem`` names an average no add could
    make (None when every one reads)."""
    corrected = bool(ticker) and ticker["state"] == "corrected"
    symbol = ticker["other_symbol"] if corrected else trade["symbol"]
    first = ticker["other_price"] if corrected else trade["entry_price"]
    out: dict[str, Any] = {"symbol": symbol, "first": first, "price": first, "adds": [], "fixed": None,
                           "problem": None}
    avg = first
    latest = trade.get("price", trade["entry_price"])
    for add, ts in [*((a, a["ts"]) for a in trade.get("adds") or ()), (None, None)]:
        read = add["price"] if add is not None else latest
        got = _average(trade["symbol"], symbol, read, avg)
        if got is None:
            out["problem"] = (f"their average read {price_text(read)}{_at(ts)} after {price_text(avg)}: an average "
                              f"no add could make (more than {FOLLOWED_AVG_FACTOR:g}x the one before it)")
            return out
        if got != read and out["fixed"] is None:
            out["fixed"] = (f"their average read {symbol} {price_text(read)}{_at(ts)}: {price_text(got)} with the "
                            "ticker's last letter read in front of it")
        if add is None:
            out["price"] = got
        elif price_text(got) != price_text(avg):
            out["adds"].append({**add, "price": got, "prev_price": avg})
            avg = got
    return out


def settled(ticker: dict[str, Any] | None) -> bool:
    """True when the trade's ticker can be priced: no check needed, as read, or corrected."""
    return ticker is None or ticker["state"] in ("as_read", "corrected")


def shown(trade: dict[str, Any], ticker: dict[str, Any] | None) -> dict[str, Any]:
    """The trade as Nova shows it: corrected, the glued reading's ticker and first price, and every average read back
    in order (``averages``); otherwise as the feed has it."""
    if not ticker or ticker["state"] != "corrected":
        return trade
    walked = averages(trade, ticker)
    return {**trade, "symbol": walked["symbol"], "entry_price": walked["first"], "price": walked["price"],
            "adds": walked["adds"]}


def _said(trade: dict[str, Any], walked: dict[str, Any], state: str, why: str) -> dict[str, Any]:
    return {"state": state, "read_symbol": trade["symbol"], "read_price": trade["entry_price"],
            "other_symbol": walked["symbol"], "other_price": walked["first"], "why": why}


def _average(read_symbol: str, symbol: str, price: float, before: float) -> float | None:
    """An average as the bar showed it, after ``before``: as read, else its glued reading, within
    ``FOLLOWED_AVG_FACTOR`` of ``before``; None when neither is."""
    for got in (price, *_readings(read_symbol, symbol, price)):
        if got > 0 and before > 0 and 1.0 / FOLLOWED_AVG_FACTOR < got / before < FOLLOWED_AVG_FACTOR:
            return got
    return None


def _readings(read_symbol: str, symbol: str, price: float) -> list[float]:
    """A price's glued readings under the ticker shown: its letter read twice, and for a trade read under the ticker
    one letter shorter, the longer one's."""
    out = []
    twice = doubled(symbol, price)
    if twice is not None:
        out.append(twice)
    if read_symbol != symbol:
        longer = unglued(read_symbol, price)
        if longer is not None and longer[0] == symbol:
            out.append(longer[1])
    return out


def _gap(price: float, tape: dict[str, Any]) -> float:
    """How far a price is from IBKR's tape, as the log of their ratio (0 inside a range; inf with no price)."""
    if price <= 0:
        return math.inf
    if tape["state"] == "at" and tape["price"]:
        return abs(math.log(price / tape["price"]))
    if tape["state"] == "range" and tape["low"] and tape["high"]:
        return max(0.0, math.log(tape["low"] / price), math.log(price / tape["high"]))
    return math.inf


def _at(ts: float | None) -> str:
    return "" if ts is None else f" at {datetime.fromtimestamp(ts, ET):%H:%M:%S} ET"


def _tape_text(tape: dict[str, Any]) -> str:
    if tape["state"] == "at":
        return _money(tape["price"])
    if tape["state"] == "range":
        return f"{_money(tape['low'])}-{_money(tape['high'])}"
    return f"no price ({tape['why'] or 'not read'})"


def _money(price: float | None) -> str:
    return "?" if price is None else f"{price:.4f}" if abs(price) < 1 else f"{price:.2f}"
