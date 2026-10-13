"""Each runner's industry, as IBKR classifies it (ADR 053): the small-cap climate's themes.

IBKR's contract details carry ``industry`` / ``category`` / ``subcategory`` ("Consumer, Non-cyclical" /
"Biotechnology" / "Medical-Biomedical/Gene"); a theme is the ``category``. Answers are kept in
``industries.json`` (``disk``) and asked again after ``MARKET_INDUSTRY_MAX_AGE_DAYS``; a symbol IBKR has not
answered for is ``Unclassified`` -- never guessed from its name.
"""
from __future__ import annotations

import threading
from typing import Any, Iterable

from constants_market_board import MARKET_INDUSTRY_MAX_AGE_DAYS, MARKET_UNCLASSIFIED
from market_board import disk

FILE = "industries.json"
_lock = threading.Lock()
_symbols: dict[str, dict[str, Any]] | None = None


def _load() -> dict[str, dict[str, Any]]:
    global _symbols
    if _symbols is None:
        data = disk.read(FILE) or {}
        got = data.get("symbols")
        _symbols = dict(got) if isinstance(got, dict) else {}
    return _symbols


def theme(symbol: str) -> str:
    with _lock:
        entry = _load().get(symbol.upper())
    category = (entry or {}).get("category")
    return str(category) if category else MARKET_UNCLASSIFIED


def missing(symbols: Iterable[str], now: float) -> list[str]:
    """Symbols with no answer yet, or one older than the max age, in the order given."""
    max_age = MARKET_INDUSTRY_MAX_AGE_DAYS * 86400.0
    with _lock:
        known = _load()
        out = []
        for sym in symbols:
            entry = known.get(sym.upper())
            if (entry is None or now - float(entry.get("at") or 0) > max_age) and sym.upper() not in out:
                out.append(sym.upper())
    return out


def put_many(answers: dict[str, dict[str, Any]], now: float) -> None:
    if not answers:
        return
    with _lock:
        known = _load()
        for sym, ans in answers.items():
            known[sym.upper()] = {"industry": ans.get("industry"), "category": ans.get("category"),
                                  "subcategory": ans.get("subcategory"), "at": now}
        disk.write(FILE, {"symbols": known})


def reset_for_tests() -> None:
    global _symbols
    with _lock:
        _symbols = None
