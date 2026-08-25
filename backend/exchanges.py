"""Listing-exchange lookup for scanner rows (NYSE / NASDAQ / AMEX / ARCA / …).

Populated from Alpaca /v2/assets responses when the tradable universe is
refreshed. Rows call ``attach_exchange`` so the UI can show where each
symbol is listed next to the ticker.

IBKR discovery does not run the Alpaca universe refresh, so
``normalize_ib_exchange`` maps ``contract.primaryExchange`` (already present
on every IB scanner row) onto the same option set the frontend filter
understands -- no extra IB call needed.
"""

from __future__ import annotations

# Frontend SCANNER_EXCHANGE_OPTIONS (frontend/src/constantGroups/market_ui.ts)
# kept in sync manually -- both sides are small, stable enums.
_KNOWN_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS", "IEX", "CBOE"}
# IB primaryExchange aliases that resolve to one of _KNOWN_EXCHANGES.
_IB_EXCHANGE_ALIASES = {
    "NASDAQ.NMS": "NASDAQ",
    "NASDAQGM": "NASDAQ",
    "NASDAQCM": "NASDAQ",
    "ISLAND": "NASDAQ",
    "NYSEARCA": "ARCA",
    "BATS": "BATS",
    "BZX": "BATS",
}

# symbol → Alpaca asset ``exchange`` field (e.g. "NASDAQ", "NYSE", "ARCA")
_symbol_exchange: dict[str, str] = {}


def normalize_ib_exchange(value: str | None) -> str | None:
    """Map an IB ``contract.primaryExchange`` value onto a known option.

    Returns ``None`` for anything unrecognized rather than guessing -- an
    unknown exchange must stay ``None`` so the UI filter treats it as
    unfiltered (fail open), not as a fabricated match.
    """
    if not value:
        return None
    upper = str(value).strip().upper()
    if upper in _KNOWN_EXCHANGES:
        return upper
    return _IB_EXCHANGE_ALIASES.get(upper)


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
