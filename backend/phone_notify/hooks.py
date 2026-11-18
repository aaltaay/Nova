"""The one entry the desk's producers call, and the hand-off to the sending thread.

Each producer hands over what it already has -- a HOD Momo alert, a setup's journal line, the hot list's new
names, a fill, a loss limit mark -- in one line of its own. Everything else happens here: the gate decides
(``gate``), the words are written (``words``), and the sending is queued to one thread of its own, so a
producer never waits for a push service. Callable from any thread: the uvicorn loop, the IB loop, a route's
thread.

Nothing here raises to a producer. A notification that fails is logged and kept as ``last_sent`` for the
phone's Notifications screen; the alert, the fill or the mark it was about is untouched.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from phone_notify import gate as gate_rules
from phone_notify import sender, store, words
from phone_notify.constants_phone_notify import (
    KIND_FILL,
    KIND_HOD,
    KIND_LEADER,
    KIND_LOSS_LIMIT,
    KIND_SETUP,
    KIND_TEST,
    PHONE_NOTIFY_ACCOUNT_VENUES,
    PHONE_NOTIFY_MARKET_KINDS,
    PHONE_NOTIFY_SETUP_STAGES,
    PHONE_NOTIFY_TTL_ACCOUNT_SEC,
    PHONE_NOTIFY_TTL_MARKET_SEC,
)

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_gate = gate_rules.Gate()
_pool: ThreadPoolExecutor | None = None
_last_sent: dict[str, Any] | None = None
# A setup's own numbers from its arm (trigger, stop), for the later lines that do not repeat them.
_setup_numbers: dict[str, dict[str, Any]] = {}
_SETUP_NUMBERS_MAX = 500
_RUNNING_UP_STRATEGY_ID = 12


def last_sent() -> dict[str, Any] | None:
    return dict(_last_sent) if _last_sent else None


def _how(symbol: str) -> str | None:
    """How ``symbol`` is on today's hot list (``star`` | ``auto``), or None; unreadable is None, said in the log."""
    try:
        from hot_list import store as hot_store

        doc, error = hot_store.current()
        if error or not doc:
            return None
        return next((str(e.get("how")) for e in doc.get("entries") or [] if e.get("symbol") == symbol), None)
    except Exception:
        logger.warning("PHONE NOTIFY: the hot list could not be read; %s is treated as not starred", symbol, exc_info=True)
        return None


def _deliver(kind: str, message: dict[str, Any]) -> dict[str, Any]:
    global _last_sent
    ttl = PHONE_NOTIFY_TTL_MARKET_SEC if kind in PHONE_NOTIFY_MARKET_KINDS else PHONE_NOTIFY_TTL_ACCOUNT_SEC
    try:
        result = sender.deliver(message, ttl=ttl)
    except Exception as exc:
        logger.exception("PHONE NOTIFY: sending failed")
        result = {"ok": False, "sent": 0, "failed": 0, "gone": 0, "error": f"sending failed ({type(exc).__name__})"}
    _last_sent = {"at": time.time(), "title": message.get("title") or "", "ok": bool(result["ok"]), "error": result["error"]}
    return result


def _queue(kind: str, message: dict[str, Any]) -> None:
    global _pool
    with _lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="phone-notify")
        pool = _pool
    pool.submit(_deliver, kind, message)


def offer(kind: str, event: dict[str, Any], message: Any, *, now: float | None = None) -> str:
    """Decide ``event`` and, on a yes, queue its notification. ``message``: a function that writes the words,
    called only on a yes. Returns ``"send"`` or the reason it was held back. Never raises."""
    try:
        if not store.devices():
            return "no_phone"
        ts = time.time() if now is None else now
        with _lock:
            verdict = _gate.decide(kind, event, settings=store.settings(), now=ts, how=_how)
        if verdict == gate_rules.SEND:
            _queue(kind, message())
        return verdict
    except Exception:
        logger.exception("PHONE NOTIFY: a %s event could not be judged; nothing was sent", kind)
        return "error"


def hod_alert(alert: dict[str, Any]) -> str:
    """A live HOD Momo alert (``alerts.hooks``). Running Up, most of the feed, is dropped before anything is read."""
    if alert.get("strategy_id") == _RUNNING_UP_STRATEGY_ID:
        return "running_up"
    return offer(KIND_HOD, {"symbol": alert.get("ticker"), "strategy_id": alert.get("strategy_id")}, lambda: words.hod(alert))


def setup_line(line: dict[str, Any]) -> str:
    """One line of the live setup scanner's journal (``setup_scanner.hooks.default_journal``)."""
    stage = str(line.get("event") or "")
    if stage not in PHONE_NOTIFY_SETUP_STAGES:
        return "not_a_stage"
    setup_id = str(line.get("setup_id") or "")
    if setup_id and isinstance(line.get("setup"), dict):
        with _lock:
            if len(_setup_numbers) >= _SETUP_NUMBERS_MAX:
                _setup_numbers.clear()
            _setup_numbers[setup_id] = {k: line["setup"].get(k) for k in ("trigger", "stop")}
    known = _setup_numbers.get(setup_id)
    event = {"symbol": line.get("symbol"), "stage": stage, "setup_id": setup_id,
             "source": line.get("source"), "playing": line.get("playing")}
    return offer(KIND_SETUP, event, lambda: words.setup(line, stage, known))


def new_leaders(entries: list[dict[str, Any]], auto_n: Any = None) -> None:
    """The names the hot list's leaders rule just added (``hot_list.service.add_auto``), and the rule's own N."""
    top_n = auto_n if isinstance(auto_n, int) and not isinstance(auto_n, bool) and auto_n > 0 else None
    for entry in entries:
        offer(KIND_LEADER, {"symbol": entry.get("symbol")}, lambda entry=entry: words.leader(entry, top_n))


def fill(*, symbol: Any, side: Any, qty: Any, price: Any, venue: str, owner: str | None, fill_id: Any = None) -> str:
    """One fill on Live or Paper. A Sim fill is dropped here: a replay is another day's market."""
    if venue not in PHONE_NOTIFY_ACCOUNT_VENUES:
        return "not_this_venue"
    event = {"symbol": symbol, "side": side, "qty": qty, "price": price, "venue": venue, "owner": owner, "id": fill_id}
    return offer(KIND_FILL, event, lambda: words.fill(event))


def live_fill(trade: Any, ib_fill: Any) -> str:
    """One execution IBKR reported (``execution.telemetry_handlers``). Every Live fill is the operator's (ADR 072).
    A field the objects do not carry is left out of the words, never a reason to fail."""
    execution = getattr(ib_fill, "execution", None)
    return fill(symbol=getattr(getattr(trade, "contract", None), "symbol", None), side=getattr(execution, "side", None),
                qty=getattr(execution, "shares", None), price=getattr(execution, "price", None), venue="live",
                owner="you", fill_id=getattr(execution, "execId", None))


def practice_fill(row: dict[str, Any] | None, venue: str) -> str:
    """A practice ledger row that just filled (``practice.broker``); whose it is comes from the row."""
    if not row or venue not in PHONE_NOTIFY_ACCOUNT_VENUES:
        return "not_this_venue"
    try:
        from owners.whose import by_of

        owner = by_of(row)
    except Exception:
        logger.warning("PHONE NOTIFY: could not read whose fill this is; said without a name", exc_info=True)
        owner = None
    return fill(symbol=row.get("symbol"), side=row.get("side"), qty=row.get("filled_qty") or row.get("qty"),
                price=row.get("avg_fill_price"), venue=venue, owner=owner, fill_id=row.get("order_id"))


def loss_limit_mark(*, account: str, line: str, mark: str, loss: Any, limit: Any, auto_sell: bool = False) -> str:
    """The daily loss limit warned or tripped (``loss_limit.watch``)."""
    event = {"venue": account, "line": line, "mark": mark, "loss": loss, "limit": limit, "auto_sell": auto_sell}
    return offer(KIND_LOSS_LIMIT, event, lambda: words.loss_limit(event))


def send_test() -> dict[str, Any]:
    """Send one notification now and wait for the push services' answers: the screen's Send a test."""
    return _deliver(KIND_TEST, words.test(time.time()))


def reset_for_tests() -> None:
    global _gate, _last_sent
    with _lock:
        _gate = gate_rules.Gate()
        _last_sent = None
        _setup_numbers.clear()
