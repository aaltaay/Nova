"""Listing-exchange lookup for scanner rows (NYSE / NASDAQ / AMEX / ARCA / …).

Populated from Alpaca /v2/assets responses when the tradable universe is
refreshed. Rows call ``attach_exchange`` so the UI can show where each
symbol is listed next to the ticker.
"""

from __future__ import annotations

# symbol → Alpaca asset ``exchange`` field (e.g. "NASDAQ", "NYSE", "ARCA")
_symbol_exchange: dict[str, str] = {}


def clear() -> None:
    """Drop the map (e.g. when the assets cache is force-invalidated)."""
    _symbol_exchange.clear()


def update_from_assets(assets: list[dict]) -> None:
    """Merge exchange fields from Alpaca asset dicts into the lookup map."""
    for asset in assets:
        sym = asset.get("symbol")
        exch = asset.get("exchange")
        if sym and exch:
            _symbol_exchange[str(sym)] = str(exch)


def exchange_for(symbol: str) -> str | None:
    """Return the listing exchange for ``symbol``, or None if unknown."""
    if not symbol:
        return None
    return _symbol_exchange.get(symbol) or _symbol_exchange.get(symbol.upper())


def attach_exchange(row: dict, symbol_key: str = "symbol") -> dict:
    """Set ``row["exchange"]`` from the lookup map when missing or empty.

    Mutates and returns ``row``. Safe to call repeatedly (WS updates that
    spread ``**g`` keep an existing exchange).
    """
    if row.get("exchange"):
        return row
    exch = exchange_for(str(row.get(symbol_key) or ""))
    if exch:
        row["exchange"] = exch
    else:
        row.setdefault("exchange", None)
    return row


def attach_exchanges(rows: list[dict], symbol_key: str = "symbol") -> list[dict]:
    """Attach listing exchange to every row in ``rows``."""
    for row in rows:
        attach_exchange(row, symbol_key=symbol_key)
    return rows
