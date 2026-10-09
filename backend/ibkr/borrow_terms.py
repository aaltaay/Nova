"""A stock's borrow in a trader's words: ETB, HTB, LOCATE or NSS, with the shares and the fee (pure).

Two IBKR sources, never another broker's:

- the live read (tick 236 on the stock's L1 line, ``ibkr/listing_flags.py``): the shares IBKR can lend
  (``shortable_shares``) and its shortable level (tick 46, ``shortable_level``: over 2.5 easy to borrow,
  1.5-2.5 a locate is needed, 1.5 or under nothing to lend). IBKR can send the level with no share count
  -- BIYA on 2026-10-07 read "unknown" all day while IBKR had nothing to lend;
- IBKR's public short-stock list (``move_reason/borrow_feed.py``, polled about every 15 min): the shares
  available and the annual fee, and when a stock left the list.

The list fills in the fee, and explains a live read with no count. It never lets a short through: the
execution door judges the live read alone (``ibkr/shortability.py``), and the list can only say why it
refuses. A live count, when there is one, wins over the list -- it is the fresher of the two.

``describe`` answers ``{schema_version: 1, term, chip, tone, text, source, shares, level, fee_rate,
list: {...} | None, list_age_sec, list_note}``:

- ``term``: ``ETB`` (a fee at or under ``IBKR_BORROW_HTB_FEE_PCT``), ``HTB`` (a higher fee, or fewer than
  ``IBKR_SHORTABLE_EST_MIN_SHARES`` shares), ``LOCATE``, ``NSS`` (nothing to borrow), ``SHORTABLE`` (IBKR
  lends but no fee or no count is known) or ``UNKNOWN``;
- ``tone``: ``ok`` | ``warn`` | ``bad`` | ``unknown``; ``chip``: the Level 2 chip ("HTB 50K · 181%");
- ``text``: one sentence for the SHORT CHECK row and the door's refusal;
- ``source``: ``live`` | ``list`` | None -- which source decided the term.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from constants_ibkr import (
    IBKR_BORROW_HTB_FEE_PCT,
    IBKR_BORROW_LIST_MAX_AGE_SEC,
    IBKR_BORROW_LIST_OLD_SEC,
    IBKR_SHORTABLE_EST_MIN_SHARES,
    IBKR_SHORTABLE_LEVEL_EASY,
    IBKR_SHORTABLE_LEVEL_LOCATE,
)

ET = ZoneInfo("America/New_York")
TONES = {"ETB": "ok", "SHORTABLE": "ok", "HTB": "warn", "LOCATE": "warn", "NSS": "bad", "UNKNOWN": "unknown"}


def _num(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def shares_short(n: float) -> str:
    """50000 -> "50K", 1234 -> "1.2K", 2500000 -> "2.5M", 400 -> "400"."""
    n = float(n)
    for div, unit in ((1_000_000, "M"), (1_000, "K")):
        if abs(n) >= div:
            v = n / div
            text = f"{v:.0f}" if v >= 10 else f"{v:.1f}".rstrip("0").rstrip(".")
            return f"{text}{unit}"
    return f"{n:.0f}"


def fee_text(fee: float) -> str:
    """181.05 -> "181%", 0.41 -> "0.4%", 12.3 -> "12%"."""
    return f"{fee:.0f}%" if fee >= 10 else f"{fee:.1f}".rstrip("0").rstrip(".") + "%"


def _clock(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M")


def _list_view(listing: dict[str, Any] | None, now: float) -> tuple[dict[str, Any] | None, float | None]:
    """The list read when it is young enough to use, and its age."""
    if not listing:
        return None, None
    polled = _num(listing.get("polled_at")) or _num(listing.get("as_of"))
    if polled is None:
        return None, None
    age = max(0.0, now - polled)
    if age > float(IBKR_BORROW_LIST_MAX_AGE_SEC):
        return None, age
    return listing, age


def _was_words(listing: dict[str, Any]) -> str:
    was = listing.get("was") or {}
    if not was.get("listed"):
        return ""
    bits = []
    if _num(was.get("available")) is not None:
        bits.append(shares_short(float(was["available"])))
    if _num(was.get("fee_rate")) is not None:
        bits.append(f"@ {fee_text(float(was['fee_rate']))}")
    return f"; was {' '.join(bits)}" if bits else ""


def _dropped_words(sym: str, listing: dict[str, Any]) -> str:
    changed = _num(listing.get("changed_at"))
    if changed is not None and (listing.get("was") or {}).get("listed"):
        return f"IBKR's short-stock list dropped {sym} at {_clock(changed)} ET{_was_words(listing)}"
    return f"{sym} is not on IBKR's short-stock list"


def describe(live: dict[str, Any] | None, listing: dict[str, Any] | None, *, symbol: str, now: float) -> dict[str, Any]:
    sym = (symbol or "").strip().upper()
    live = live or {}
    lst, list_age = _list_view(listing, now)
    shares = _num(live.get("shortable_shares")) if live.get("connected") and not live.get("error") else None
    level = _num(live.get("shortable_level")) if live.get("connected") and not live.get("error") else None
    list_fee = _num(lst.get("fee_rate")) if lst and lst.get("listed") else None
    list_avail = _num(lst.get("available")) if lst and lst.get("listed") else None
    min_shares = float(IBKR_SHORTABLE_EST_MIN_SHARES)
    fee_part = f" at {fee_text(list_fee)}/yr" if list_fee is not None else ""
    chip_fee = f" · {fee_text(list_fee)}" if list_fee is not None else ""

    def out(term: str, chip: str, text: str, source: str | None) -> dict[str, Any]:
        note = None
        if list_age is not None and list_age > float(IBKR_BORROW_LIST_OLD_SEC):
            note = f"IBKR's short-stock list is {list_age / 60:.0f} min old"
        return {"schema_version": 1, "term": term, "chip": chip, "tone": TONES[term], "text": text,
                "source": source, "shares": shares, "level": level, "fee_rate": list_fee,
                "list": lst, "list_age_sec": None if list_age is None else round(list_age, 1), "list_note": note}

    if not live.get("connected"):
        if lst and not lst.get("listed"):
            return out("NSS", "NSS", f"NSS: {_dropped_words(sym, lst)}. IBKR is not connected for a live read.", "list")
        return out("UNKNOWN", "BORROW ?", "IBKR is not connected, so Nova cannot read the borrow.", None)
    if live.get("error"):
        return out("UNKNOWN", "BORROW ?", f"IBKR's borrow read failed: {live['error']}.", None)

    if shares is not None:
        count = f"~{shares:,.0f}"
        if shares <= 0:
            return out("NSS", "NSS", f"NSS: IBKR has no {sym} to lend.", "live")
        if shares < min_shares:
            return out("HTB", f"HTB {shares_short(shares)}{chip_fee}",
                       f"HTB: IBKR lends only {count} {sym}{fee_part} (Nova shorts with {min_shares:,.0f} or more).",
                       "live")
        if list_fee is None:
            return out("SHORTABLE", f"SHORT {shares_short(shares)}",
                       f"IBKR lends {count} {sym}; its fee is not on IBKR's short-stock list.", "live")
        if list_fee > float(IBKR_BORROW_HTB_FEE_PCT):
            return out("HTB", f"HTB {shares_short(shares)}{chip_fee}",
                       f"HTB: IBKR lends {count} {sym}{fee_part}, a costly borrow.", "live")
        return out("ETB", f"ETB {shares_short(shares)}{chip_fee}", f"ETB: IBKR lends {count} {sym}{fee_part}.", "live")

    if level is not None:
        if level <= float(IBKR_SHORTABLE_LEVEL_LOCATE):
            extra = f" {_dropped_words(sym, lst)}." if lst and not lst.get("listed") else ""
            return out("NSS", "NSS", f"NSS: IBKR marks {sym} not available to short (level {level:g}).{extra}", "live")
        if level <= float(IBKR_SHORTABLE_LEVEL_EASY):
            return out("LOCATE", "LOCATE",
                       f"LOCATE: IBKR needs a locate before {sym} can be shorted, and Nova cannot request one.", "live")
        return out("SHORTABLE", f"SHORT{chip_fee}",
                   (f"IBKR marks {sym} shortable{fee_part} but sent no share count: Nova shorts only on a "
                    f"count of {min_shares:,.0f} or more."), "live")

    if lst is not None:
        when = f" (list of {_clock(float(lst['as_of']))} ET)" if _num(lst.get("as_of")) is not None else ""
        if not lst.get("listed"):
            return out("NSS", "NSS",
                       f"NSS: {_dropped_words(sym, lst)}. IBKR's live borrow data sent no share count.", "list")
        if list_avail is not None and list_avail < min_shares:
            return out("HTB", f"HTB {shares_short(list_avail)}{chip_fee}",
                       (f"HTB: IBKR's short-stock list shows only {list_avail:,.0f} {sym}{fee_part}{when}; "
                        "its live data sent no count."), "list")
        avail = f" {list_avail:,.0f}" if list_avail is not None else ""
        return out("UNKNOWN", "BORROW ?",
                   (f"IBKR's live data sent no share count; its short-stock list shows{avail} {sym}{fee_part}{when}. "
                    "Nova shorts on the live count only."), None)
    return out("UNKNOWN", "BORROW ?",
               f"IBKR sent no share count for {sym}, and its short-stock list is not read yet.", None)
