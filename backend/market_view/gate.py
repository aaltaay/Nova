"""The order gate: a desk order priced from a view that lags is refused (ADR 045).

"If it lags, then we cannot place an order." A ``manual`` place, bracket or replace that came
through the desk's routes (it carries ``client_timing``) also carries ``view``: when the operator
acted and which Level 2 book and quote the screen showed. ``check`` judges it against what Nova
knows now, before anything is validated or sent; ``late_at_send`` checks the clock again just
before the broker send. Flatten, KILL, cancels and Nova's own senders are exempt: they do not
price from the operator's screen, and getting flat must always work. On a Sim desk off the live
edge the market is the replay, so IBKR's feed health is not judged there.

The arithmetic mixes the desk's wall clock (``action_wall_ms``) with the backend's. That is
sound only because the backend binds 127.0.0.1 -- one machine, one clock; an action more than
``ORDER_CLOCK_SKEW_MS`` in the backend's future is refused, never trusted.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from constants_feed import FEED_GAP_SETTLE_SEC
from constants_market_view import (
    FEED_STALE,
    MARKET_VIEW_SCHEMA_VERSION,
    ORDER_CLOCK_SKEW_MS,
    ORDER_LATE,
    ORDER_MAX_ARRIVAL_MS,
    ORDER_MAX_IB_STALL_MS,
    ORDER_MAX_SEND_MS,
    ORDER_VIEW_MAX_LAG_MS,
    VIEW_GATE_EXEMPT_TEXT,
    VIEW_MISSING,
    VIEW_STALE,
)
from market_view import versions

logger = logging.getLogger(__name__)

GATED_OPERATIONS = ("place", "bracket", "replace")


@dataclass
class Check:
    """The gate's answer: ``verdict`` is ``ok``, ``refused``, ``exempt`` or ``missing``."""

    verdict: str
    code: str | None = None
    text: str | None = None
    measures: dict[str, Any] = field(default_factory=dict)

    @property
    def refused(self) -> bool:
        return self.verdict in ("refused", "missing")

    def record(self) -> dict[str, Any]:
        """The execution row's ``view_check``."""
        return {
            "schema_version": MARKET_VIEW_SCHEMA_VERSION,
            "verdict": self.verdict,
            "code": self.code,
            **self.measures,
        }


def applies(cmd: Any) -> bool:
    """The operator's own priced order from the desk -- not Flatten, KILL, a cancel or Nova's senders."""
    return (
        getattr(cmd, "operation", None) in GATED_OPERATIONS
        and getattr(cmd, "source", None) == "manual"
        and isinstance(getattr(cmd, "client_timing", None), dict)
    )


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None  # NaN is not a number here


def action_ms(cmd: Any) -> float | None:
    """When the operator acted (epoch ms): the view's own stamp, else the click in ``client_timing``."""
    view = getattr(cmd, "view", None) or {}
    stamp = _num(view.get("action_wall_ms")) if isinstance(view, dict) else None
    if stamp is None:
        stamp = _num((getattr(cmd, "client_timing", None) or {}).get("action_wall_ms"))
    return stamp


def _secs(ms: float) -> str:
    return f"{ms / 1000.0:.1f} s"


def _price(value: Any) -> str:
    num = _num(value)
    return f"{num:g}" if num is not None else "--"


def _nova_top(symbol: str) -> tuple[Any, Any]:
    try:
        from ibkr.depth.state import current_book

        book = current_book(symbol) or {}
        bids, asks = book.get("bids") or [], book.get("asks") or []
        return (bids[0].get("price") if bids else None), (asks[0].get("price") if asks else None)
    except Exception:
        logger.debug("view gate: no current book for %s", symbol, exc_info=True)
        return None, None


def _lag_ms(stream: str, symbol: str, shown: Any, act: float) -> tuple[float | None, bool]:
    """How long the version the screen showed had been replaced at the action, in ms.

    ``(lag, unknown)``: ``unknown`` for a version Nova never issued (another process's, or none).
    A version older than the kept history counts from the oldest kept, the least it can be.
    """
    if not isinstance(shown, dict):
        return None, False
    seq = shown.get("seq")
    if not isinstance(seq, int) or isinstance(seq, bool):
        return None, True
    state = versions.replaced(stream, symbol, seq)
    if state.unknown:
        return None, True
    if state.current or state.at is None:
        return 0.0, False
    return max(0.0, act - state.at * 1000.0), False


def _feed_behind(now: float) -> str | None:
    """Why Nova itself is behind IBKR right now, or None."""
    try:
        from ibkr import feed_pulse

        for gap in feed_pulse.gaps_for_tape(now):
            end = gap.get("end")
            if end is None:
                return f"no IBKR data for {now - gap['start']:.1f} s"
            if now - end < FEED_GAP_SETTLE_SEC:
                return f"IBKR's data is still catching up after {end - gap['start']:.1f} s without it"
    except Exception:
        logger.exception("view gate: the feed's gaps could not be read")
    return None


def _replay_desk() -> bool:
    """A Sim desk off the live edge trades its replay, not IBKR's feed: the feed's health is not its market's."""
    try:
        from sim.mode import is_replay_desk

        return bool(is_replay_desk())
    except Exception:
        logger.exception("view gate: the desk venue could not be read; judging the live feed")
        return False


def _ib_stall_ms() -> float | None:
    try:
        from perf import stall_watch

        return stall_watch.stalled_ms("ib")
    except Exception:
        logger.exception("view gate: the IB loop's stall could not be read")
        return None


def check(cmd: Any, *, now: float | None = None) -> Check:
    """Judge a command's view at the door (``Check.verdict``; ``refused`` / ``missing`` refuse it)."""
    if not applies(cmd):
        return Check("exempt")
    view = getattr(cmd, "view", None)
    if not isinstance(view, dict):
        return Check(
            "missing", VIEW_MISSING,
            "This order did not say which market it was priced from (an older desk), so it was not sent. "
            f"Update the desk, then place it again. {VIEW_GATE_EXEMPT_TEXT}",
        )
    t = time.time() if now is None else now
    symbol = str(getattr(cmd, "symbol", "") or view.get("symbol") or "").upper()
    act = action_ms(cmd)
    ingress_ns = getattr(cmd, "backend_ingress_wall_ns", None)
    arrival = (ingress_ns / 1e6) if ingress_ns else t * 1000.0
    measures: dict[str, Any] = {
        "arrival_ms": None, "book_lag_ms": None, "quote_lag_ms": None, "feed_gap": False, "ib_stall_ms": None,
    }

    def refuse(code: str, text: str) -> Check:
        return Check("refused", code, text, measures)

    if act is None:
        return refuse(VIEW_STALE, "Nova cannot tell when you acted, so it cannot tell how old your screen was. "
                      f"Nothing was sent. {VIEW_GATE_EXEMPT_TEXT}")
    measures["arrival_ms"] = round(arrival - act, 1)
    if act - arrival > ORDER_CLOCK_SKEW_MS:
        return refuse(VIEW_STALE, "The desk's clock and Nova's disagree, so Nova cannot tell how old your screen "
                      f"was. Nothing was sent. {VIEW_GATE_EXEMPT_TEXT}")

    instance = view.get("instance")
    if instance is not None:
        import instance_identity

        if instance != instance_identity.INSTANCE_ID:
            return refuse(VIEW_STALE, "Your screen's market came from a Nova backend that has since restarted. "
                          f"Nothing was sent: wait for Level 2 to refresh, then place it again. {VIEW_GATE_EXEMPT_TEXT}")

    book_lag, book_unknown = _lag_ms(versions.BOOK, symbol, view.get("book"), act)
    quote_lag, quote_unknown = _lag_ms(versions.QUOTE, symbol, view.get("quote"), act)
    measures["book_lag_ms"] = round(book_lag, 1) if book_lag is not None else None
    measures["quote_lag_ms"] = round(quote_lag, 1) if quote_lag is not None else None
    if book_unknown or quote_unknown:
        return refuse(VIEW_STALE, "Your screen showed a market Nova cannot place in time (it did not come from "
                      f"this backend). Nothing was sent: look again, then place it again. {VIEW_GATE_EXEMPT_TEXT}")
    if book_lag is not None and book_lag > ORDER_VIEW_MAX_LAG_MS:
        shown = view.get("book") or {}
        bid, ask = _nova_top(symbol)
        return refuse(VIEW_STALE, (
            f"Your Level 2 was {_secs(book_lag)} behind Nova's book when you acted: it showed bid "
            f"{_price(shown.get('bid'))} x ask {_price(shown.get('ask'))}, and Nova's is {_price(bid)} x {_price(ask)}. "
            f"Nothing was sent: look again, then place it again. {VIEW_GATE_EXEMPT_TEXT}"
        ))
    if quote_lag is not None and quote_lag > ORDER_VIEW_MAX_LAG_MS:
        return refuse(VIEW_STALE, (
            f"Your quote was {_secs(quote_lag)} behind Nova's when you acted. Nothing was sent: look again, "
            f"then place it again. {VIEW_GATE_EXEMPT_TEXT}"
        ))
    if arrival - act > ORDER_MAX_ARRIVAL_MS:
        return refuse(ORDER_LATE, (
            f"Your order reached Nova {_secs(arrival - act)} after your click (the desk or Nova was busy). Prices "
            f"move in that time, so it was not sent: place it again. {VIEW_GATE_EXEMPT_TEXT}"
        ))
    if _replay_desk():
        measures["feed_gap"] = None             # a replay order's market is the recording
        return Check("ok", measures=measures)
    behind = _feed_behind(t)
    stall = _ib_stall_ms()
    measures["feed_gap"] = behind is not None
    measures["ib_stall_ms"] = stall
    if behind is None and stall is not None and stall > ORDER_MAX_IB_STALL_MS:
        behind = f"its IBKR thread has been stuck for {_secs(stall)}"
    if behind is not None:
        return refuse(FEED_STALE, (
            f"Nova is behind the market right now ({behind}), so new orders wait until it catches up. "
            f"Nothing was sent. {VIEW_GATE_EXEMPT_TEXT}"
        ))
    return Check("ok", measures=measures)


def late_at_send(cmd: Any, *, now: float | None = None) -> Check | None:
    """Just before the broker send: refused ``ORDER_LATE`` when the action is too long ago, else None."""
    if not applies(cmd) or not isinstance(getattr(cmd, "view", None), dict):
        return None
    act = action_ms(cmd)
    if act is None:
        return None
    elapsed = (time.time() if now is None else now) * 1000.0 - act
    if elapsed <= ORDER_MAX_SEND_MS:
        return None
    return Check("refused", ORDER_LATE, (
        f"Your order would have reached the broker {_secs(elapsed)} after your click (Nova was busy). Prices move "
        f"in that time, so it was not sent: place it again. {VIEW_GATE_EXEMPT_TEXT}"
    ), {"send_ms": round(elapsed, 1)})
