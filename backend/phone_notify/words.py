"""The words of each notification, and the screen a tap opens. Pure.

A notification says what the desk already knows, in the desk's numbers: nothing is worked out here and a fact
the event does not carry is left out, never filled in. ``hash`` is the phone page's own route
(``frontend/src/phone/phoneRoute.ts``); ``tag`` lets a newer notification about the same thing replace the older.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from phone_notify.constants_phone_notify import NOTIFY_BODY_MAX_CHARS, NOTIFY_TZ

_ET = ZoneInfo(NOTIFY_TZ)
_VENUE = {"live": "Live", "paper": "Paper", "sim": "Sim"}
_OWNER = {"you": "You", "claude": "Claude", "brain": "The brain", "earlier_bots": "Earlier bots"}
_LINE = {"account": "the whole account", "you": "your trades", "bots": "Claude's and the brain's trades",
         "claude": "Claude's trades", "brain": "the brain's trades"}
_STAGE = {"armed": "armed", "near": "near the trigger", "triggered": "triggered"}


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:   # NaN is not a number here
        return None
    return float(value)


def price(value: Any) -> str | None:
    """A price as the desk prints it: two decimals from a dollar up, four under."""
    n = _num(value)
    if n is None:
        return None
    return f"{n:,.2f}" if abs(n) >= 1 else f"{n:.4f}".rstrip("0").rstrip(".")


def compact(value: Any) -> str | None:
    """A count in a few characters: 13,039,956 is "13.0M"."""
    n = _num(value)
    if n is None:
        return None
    for size, unit in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= size:
            scaled = n / size
            return f"{scaled:.0f}{unit}" if abs(scaled) >= 100 else f"{scaled:.1f}{unit}"
    return f"{n:.0f}"


def signed_pct(points: Any) -> str | None:
    """Percent points with a sign: 21.6 is "+21.6%"."""
    n = _num(points)
    if n is None:
        return None
    return f"{n:+,.0f}%" if abs(n) >= 1000 else f"{n:+.1f}%"


def shares(value: Any) -> str | None:
    n = _num(value)
    if n is None:
        return None
    return f"{abs(n):,.0f}" if abs(n) == int(abs(n)) else f"{abs(n):,.2f}"


def money(value: Any) -> str | None:
    n = _num(value)
    return None if n is None else f"${abs(n):,.2f}".replace(".00", "")


def _join(parts: list[str | None]) -> str:
    return " · ".join(p for p in parts if p)[:NOTIFY_BODY_MAX_CHARS]


def _trade_hash(symbol: str) -> str:
    return f"#/trade/{symbol}"


def hod(alert: dict[str, Any]) -> dict[str, Any]:
    """A HOD Momo alert, as ``hod_momo_models.alert_to_dict`` writes it."""
    symbol = str(alert.get("ticker") or "").upper()
    change = signed_pct(alert.get("change_pct"))
    # The desk's own strategy name, without the family word a small line has no room for.
    strategy = str(alert.get("strategy_name") or "").replace("Squeeze Alert - ", "").strip() or None
    px = price(alert.get("price"))
    rvol = _num(alert.get("rvol"))
    return {
        "title": " · ".join(p for p in (f"{symbol} hit HOD Momo", change) if p),
        "body": _join([
            strategy,
            f"${px}" if px else None,
            f"Vol {compact(alert.get('volume'))}" if _num(alert.get("volume")) is not None else None,
            f"RVol {rvol:,.0f}x" if rvol is not None and rvol >= 10 else (f"RVol {rvol:.1f}x" if rvol is not None else None),
            f"Float {compact(alert.get('float_shares'))}" if _num(alert.get("float_shares")) is not None else None,
        ]),
        "tag": f"hod-{symbol}",
        "hash": _trade_hash(symbol),
    }


def setup(line: dict[str, Any], stage: str, known: dict[str, Any] | None = None) -> dict[str, Any]:
    """A setup's stage from the scanner's journal line. ``known``: the setup's own numbers from its arm, for a
    later line that does not repeat them."""
    symbol = str(line.get("symbol") or "").upper()
    numbers = line.get("setup") if isinstance(line.get("setup"), dict) else (known or {})
    name = str(line.get("setup_type") or "setup").replace("_", " ")
    trigger, stop, last = price(numbers.get("trigger")), price(numbers.get("stop")), price(line.get("last"))
    return {
        "title": f"{symbol}: {name} {_STAGE.get(stage, stage)}",
        "body": _join([f"Trigger {trigger}" if trigger else None, f"Stop {stop}" if stop else None,
                       f"Last {last}" if last else None]),
        "tag": f"setup-{symbol}",
        "hash": _trade_hash(symbol),
    }


def leader(entry: dict[str, Any], top_n: int | None) -> dict[str, Any]:
    """A stock the hot list's leaders rule just added (``hot_list.service.add_auto``)."""
    symbol = str(entry.get("symbol") or "").upper()
    change = _num(entry.get("change_pct"))
    rank = entry.get("rank")
    where = f"the top {top_n} Gainers" if top_n else "the Gainers leaders"
    return {
        "title": f"{symbol} joined {where}",
        "body": _join([f"Number {rank}" if isinstance(rank, int) else None,
                       signed_pct(change * 100) if change is not None else None]),
        "tag": f"leader-{symbol}",
        "hash": _trade_hash(symbol),
    }


def fill(event: dict[str, Any]) -> dict[str, Any]:
    """One fill: ``{symbol, side, qty, price, venue, owner}``; ``owner`` None is one of Nova's own closes."""
    symbol = str(event.get("symbol") or "").upper()
    side = str(event.get("side") or "").upper()
    # IBKR says BOT / SLD, the practice ledger BUY / SELL. A side the fill does not carry is not guessed.
    did = "Bought" if side in ("BUY", "BOT") else "Sold" if side in ("SELL", "SLD") else None
    qty, px = shares(event.get("qty")), price(event.get("price"))
    owner = event.get("owner")
    return {
        "title": " ".join(p for p in ("Filled ·", did, qty, symbol, f"at {px}" if px else None) if p),
        "body": _join([_VENUE.get(str(event.get("venue")), None),
                       _OWNER.get(str(owner)) if owner else "Nova's own close"]),
        # Each fill is its own notification: two fills on one stock are two facts.
        "tag": f"fill-{symbol}-{event.get('id') or ''}",
        "hash": _trade_hash(symbol),
    }


def loss_limit(event: dict[str, Any]) -> dict[str, Any]:
    """A mark of the daily loss limit: ``{mark: "warned" | "tripped", venue, line, loss, limit, auto_sell}``."""
    venue = _VENUE.get(str(event.get("venue")), str(event.get("venue") or ""))
    tripped = event.get("mark") == "tripped"
    loss, limit = money(event.get("loss")), money(event.get("limit"))
    whose = _LINE.get(str(event.get("line")), str(event.get("line") or ""))
    return {
        "title": f"Loss limit {'reached' if tripped else 'warning'} · {venue}",
        "body": _join([
            f"Down {loss} against the {limit} limit" if loss and limit else None,
            whose[:1].upper() + whose[1:] if whose else None,
            "Auto sell is closing what was opened today" if tripped and event.get("auto_sell") else None,
        ]),
        "tag": f"loss-limit-{event.get('venue')}-{event.get('line')}",
        "hash": "#/account",
    }


def test(now: float) -> dict[str, Any]:
    at = datetime.fromtimestamp(now, _ET).strftime("%H:%M:%S")
    return {
        "title": "Nova can reach this phone",
        "body": f"A test your PC sent at {at} New York time. Nothing happened on the desk.",
        "tag": "nova-test",
        "hash": "#/notify",
    }
