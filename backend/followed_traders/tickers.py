"""A followed trade's ticker, checked when the feed may have read it glued to its price. Pure.

With no space between a ticker and its price on the stream's bar, the feed's OCR can take the ticker's last letter for
a digit: the bar's "SOFI 14.03" comes back SOF 114.03, and the ticker one letter shorter can be a real stock trading
near the true one's price. The feed puts such a read back when the trader's own reads show the longer ticker; one
read glued from first frame to last reaches Nova as read. ``check`` asks IBKR's tape at the entry (``exits.view`` in the route, a fake in tests) which reading fits:
the ticker as read, the longer one, or neither -- never a number from a ticker that may be wrong. Shapes:
architecture/schema/followed-traders.md ("A ticker glued to its price").
"""
from __future__ import annotations

import re
from typing import Any, Callable

from followed_traders.constants_followed import FOLLOWED_NO_SUCH_TICKER, FOLLOWED_TICKER_FIT_PCT

TapeAt = Callable[[str], dict[str, Any]]   # symbol -> IBKR's tape at the trade's entry (an ``exits.stated`` dict)
# The digits OCR reads a ticker's last letter as, the feed's own pairs (its reader puts a glued O back itself).
DIGIT_TO_LETTER = {"1": "I", "5": "S", "8": "B"}
MAX_TICKER = 5                             # letters in a US stock ticker
# A price as the bar writes it: no leading zero before another digit, 2 decimals (4 under $1).
BAR_PRICE_RE = re.compile(r"^(?:0|[1-9]\d{0,5})\.(?:\d{2}|\d{4})$")
STATES = ("checking", "as_read", "corrected", "unchecked")


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


def fits(price: float, tape: dict[str, Any]) -> bool:
    """The price within ``FOLLOWED_TICKER_FIT_PCT`` of IBKR's trade at that time, or of its range widened as much."""
    tol = FOLLOWED_TICKER_FIT_PCT / 100.0
    if tape["state"] == "at" and tape["price"]:
        return abs(price / tape["price"] - 1.0) <= tol
    if tape["state"] == "range" and tape["low"] and tape["high"]:
        return tape["low"] * (1.0 - tol) <= price <= tape["high"] * (1.0 + tol)
    return False


def check(trade: dict[str, Any], tape_at: TapeAt) -> dict[str, Any] | None:
    """The trade's ``ticker`` (schema), or None when its read cannot be a glued one. The longer ticker's tape is
    asked for only when the ticker as read does not fit."""
    read_symbol, read_price = trade["symbol"], trade["entry_price"]
    other = unglued(read_symbol, read_price)
    if other is None:
        return None

    def said(state: str, why: str | None) -> dict[str, Any]:
        return {"state": state, "read_symbol": read_symbol, "read_price": read_price, "other_symbol": other[0],
                "other_price": other[1], "why": why}

    as_read = tape_at(read_symbol)
    if as_read["state"] == "pending":
        return said("checking", as_read["why"] or "reading IBKR's tape at the entry")
    if fits(read_price, as_read):
        return said("as_read", None)
    longer = tape_at(other[0])
    if longer["state"] == "pending":
        return said("checking", longer["why"] or f"reading IBKR's tape at the entry for {other[0]}")
    if longer["state"] == "unavailable" and longer["why"] == FOLLOWED_NO_SUCH_TICKER:
        return said("as_read", None)                 # no glued reading exists
    tapes = (f"the bar read {read_symbol} {price_text(read_price)}; IBKR at the entry: "
             f"{read_symbol} {_tape_text(as_read)}, {other[0]} {_tape_text(longer)}")
    if fits(other[1], longer):
        return said("corrected", f"{tapes}: the ticker was read glued to its price")
    return said("unchecked", f"{tapes}: neither fits")


def settled(ticker: dict[str, Any] | None) -> bool:
    """True when the trade's ticker can be priced: no check needed, as read, or corrected."""
    return ticker is None or ticker["state"] in ("as_read", "corrected")


def shown(trade: dict[str, Any], ticker: dict[str, Any] | None) -> dict[str, Any]:
    """The trade as Nova shows it: corrected, the longer ticker with every price the feed read put back the same way;
    otherwise as the feed has it."""
    if not ticker or ticker["state"] != "corrected":
        return trade
    read, whole = trade["symbol"], ticker["other_symbol"]

    def back(price: float | None) -> float | None:
        got = None if price is None else unglued(read, price)
        return got[1] if got and got[0] == whole else price

    return {**trade, "symbol": whole, "entry_price": back(trade["entry_price"]), "price": back(trade["price"]),
            "adds": [{**a, "price": back(a["price"]), "prev_price": back(a["prev_price"])} for a in trade["adds"]]}


def _tape_text(tape: dict[str, Any]) -> str:
    if tape["state"] == "at":
        return _money(tape["price"])
    if tape["state"] == "range":
        return f"{_money(tape['low'])}-{_money(tape['high'])}"
    return f"no price ({tape['why'] or 'not read'})"


def _money(price: float | None) -> str:
    return "?" if price is None else f"{price:.4f}" if abs(price) < 1 else f"{price:.2f}"
