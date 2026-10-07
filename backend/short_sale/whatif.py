"""IBKR's margin for a stock, remembered (ADR 048 decision 2).

Margin comes from IBKR first: before a Paper or Sim order, and before a Live short, Nova asks
IBKR's what-if (``ibkr.margin_whatif``; nothing is placed). An answer is kept per stock and side as
its **ratio**: IBKR's maintenance change over the published rules' requirement for the same order
(``short_sale.margin``), so a volatile name IBKR charges extra on carries a ratio over 1. Every
practice margin figure -- buying power, the short check, the liquidation price -- scales that
stock's published maintenance by its ratio, and says which source it came from.

A ratio is read as current for ``SHORT_WHATIF_FRESH_SEC`` and kept as the stock's figure for
``SHORT_WHATIF_KEEP_SEC`` (IBKR's extra charge rarely moves within a day). Nothing waits on IBKR
under the execution lock: ``ask`` is awaited before it (a bot's short), ``request`` asks on a
worker thread (the ticket, the Trader tab) so the next order finds an answer. With no answer, or
on a past-day Sim replay that IBKR cannot speak for, the figure is the published rules'.

In memory only: a restart starts with the published rules until IBKR answers again.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from constants_shorts import (
    SHORT_MARGIN_SOURCE_PUBLISHED,
    SHORT_MARGIN_SOURCE_WHATIF,
    SHORT_WHATIF_FRESH_SEC,
    SHORT_WHATIF_KEEP_SEC,
    SHORT_WHATIF_TIMEOUT_SEC,
    SHORT_WHATIF_WORKERS,
)
from short_sale import margin

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Answer:
    """One what-if IBKR answered, as the stock's ratio."""

    symbol: str
    side: str                 # BUY: a long's figure; SELL: a short's
    qty: float
    price: float
    maint_change: float
    init_change: float | None
    published: float          # the published rules' maintenance for the same order
    ratio: float              # maint_change / published
    ts: float
    account: str | None

    @property
    def position_side(self) -> str:
        return "short" if self.side == "SELL" else "long"

    def age(self, now: float | None = None) -> float:
        return max(0.0, (time.time() if now is None else float(now)) - self.ts)

    def as_dict(self, now: float | None = None) -> dict[str, Any]:
        return {"source": SHORT_MARGIN_SOURCE_WHATIF, "side": self.side, "qty": self.qty, "price": self.price,
                "maint_change": self.maint_change, "init_change": self.init_change,
                "published": round(self.published, 2), "ratio": round(self.ratio, 4),
                "age_sec": round(self.age(now), 1), "account": self.account}


_answers: dict[tuple[str, str], Answer] = {}
_errors: dict[tuple[str, str], tuple[float, str]] = {}
_lock = threading.Lock()
_pool: ThreadPoolExecutor | None = None
_asking: set[tuple[str, str]] = set()


def _key(symbol: str, side: str) -> tuple[str, str]:
    return (symbol or "").strip().upper(), (side or "").strip().upper()


def remember(raw: dict[str, Any] | None) -> Answer | None:
    """Keep one ``ibkr.margin_whatif.ask`` answer as its stock's ratio; None when it gives none."""
    if not raw:
        return None
    key = _key(str(raw.get("symbol") or ""), str(raw.get("side") or ""))
    if not raw.get("ok"):
        with _lock:
            _errors[key] = (float(raw.get("ts") or time.time()), str(raw.get("error") or "no answer"))
        return None
    qty, price = float(raw.get("qty") or 0), float(raw.get("price") or 0)
    maint = raw.get("maint_change")
    side = "short" if key[1] == "SELL" else "long"
    published = margin.requirement(side, price, qty)
    if maint is None or not math.isfinite(float(maint)) or float(maint) <= 0 or published <= 0:
        with _lock:
            _errors[key] = (time.time(), f"IBKR's what-if gave no maintenance for this order ({maint})")
        return None
    answer = Answer(symbol=key[0], side=key[1], qty=qty, price=price, maint_change=float(maint),
                    init_change=raw.get("init_change"), published=published, ratio=float(maint) / published,
                    ts=float(raw.get("ts") or time.time()), account=raw.get("account"))
    with _lock:
        _answers[key] = answer
        _errors.pop(key, None)
    return answer


def answer_for(symbol: str, side: str, *, now: float | None = None) -> Answer | None:
    """The stock's kept answer for ``side``, while it is younger than ``SHORT_WHATIF_KEEP_SEC``."""
    with _lock:
        answer = _answers.get(_key(symbol, side))
    if answer is None or answer.age(now) > SHORT_WHATIF_KEEP_SEC:
        return None
    return answer


def fresh(symbol: str, side: str, *, now: float | None = None) -> bool:
    answer = answer_for(symbol, side, now=now)
    return answer is not None and answer.age(now) <= SHORT_WHATIF_FRESH_SEC


def last_error(symbol: str, side: str) -> str | None:
    with _lock:
        got = _errors.get(_key(symbol, side))
    return got[1] if got else None


def ratio(symbol: str, position_side: str, *, published_only: bool = False,
          now: float | None = None) -> tuple[float, str]:
    """``(ratio, source)`` for a ``"long"`` or ``"short"`` position in ``symbol``: IBKR's, else 1."""
    if not published_only:
        answer = answer_for(symbol, "SELL" if position_side == "short" else "BUY", now=now)
        if answer is not None:
            return answer.ratio, SHORT_MARGIN_SOURCE_WHATIF
    return 1.0, SHORT_MARGIN_SOURCE_PUBLISHED


async def ask(symbol: str, side: str, qty: float, price: float, *,
              timeout: float = SHORT_WHATIF_TIMEOUT_SEC) -> Answer | None:
    """Ask IBKR now and keep the answer; None when IBKR does not give one in time."""
    from ibkr import margin_whatif
    from ibkr.loop_supervisor import on_ib

    try:
        raw = await on_ib(margin_whatif.ask(symbol, side, qty, price, timeout=timeout), timeout + 0.5,
                          label="margin what-if")
    except Exception as exc:  # the IB loop is gone or too slow: the published rules stand
        logger.info("what-if for %s %s not answered: %s", side, symbol, exc)
        remember({"ok": False, "symbol": symbol, "side": side, "error": f"IBKR did not answer ({exc})"})
        return None
    return remember(raw)


def _ask_in_background(key: tuple[str, str], qty: float, price: float) -> None:
    from ibkr import margin_whatif
    from ibkr.client_bridge import run_coro

    try:
        raw = run_coro(margin_whatif.ask(key[0], key[1], qty, price, timeout=SHORT_WHATIF_TIMEOUT_SEC),
                       SHORT_WHATIF_TIMEOUT_SEC + 0.5, label="margin what-if")
        remember(raw)
    except Exception as exc:  # no IB loop, a stale session: the published rules stand, and say why
        remember({"ok": False, "symbol": key[0], "side": key[1], "error": f"IBKR did not answer ({exc})"})
    finally:
        with _lock:
            _asking.discard(key)


def request(symbol: str, side: str, qty: float, price: float) -> bool:
    """Ask IBKR on a worker thread unless an answer is fresh or a question is on its way."""
    key = _key(symbol, side)
    if not key[0] or key[1] not in ("BUY", "SELL") or not (qty > 0 and price > 0):
        return False
    if fresh(*key):
        return False
    from ibkr import client as _client

    if not _client.is_ready():
        return False
    global _pool
    with _lock:
        if key in _asking:
            return False
        _asking.add(key)
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=SHORT_WHATIF_WORKERS, thread_name_prefix="nova-whatif")
        pool = _pool
    pool.submit(_ask_in_background, key, float(qty), float(price))
    return True


def reset_for_tests() -> None:
    with _lock:
        _answers.clear()
        _errors.clear()
        _asking.clear()
