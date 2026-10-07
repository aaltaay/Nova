"""Live's day cover and its short-entry cutoff (ADR 048 decision 5, step 6).

**The day cover** runs while ``IBKR_SHORT_ENABLED`` is on: with the switch off Nova cannot open a Live
short, and a short opened in TWS is the operator's (the 15:50 card still says to be flat by 15:55). A
Live short is due by the rule Paper's is (``hours.cover_due``: outside 09:35-15:55 by the wall clock), and
its cover goes out only in the regular session, 09:30 to the close (``hours.regular_session``): outside it
IBKR would hold a market order until the next open, and Nova never picks a Live limit price by itself.

Per short stock: every working Live order on it is cancelled first (``cancel_working``, origin
``day_cover``, aimed at Live whatever the desk shows), then one protective market BUY covers the short
(source ``flatten``, origin ``day_cover``, ``intent: "flatten"``). The door checks that cover under its
lock against IBKR's own position less the covers already working there (``execution.flatten_intent``),
so an order Nova could not cancel leaves the cover refused, never a buy past flat. A cover working at
IBKR is never sent twice. Each step is a ``day_cover`` line on the bot audit stream.

**The cutoff.** Nova's own Live short entries -- the SELLs its execution record sent as short entries --
lapse as Paper's do (``hours.entry_lapsed``: outside the short hours, or a later day than they were
placed) and are cancelled, whether or not the switch is on.

**The alarm** (``short_sale.cover_alarm``): a short due its cover that cannot get one -- IBKR not ready
(the short as IBKR last reported it), outside the regular session, or a cancel or the cover refused --
raises the alarm every desk window shows, until a cover goes out or the short is gone.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from constants_shorts import SHORT_CLOSE_RETRY_SEC
from execution.models import ExecutionCommand
from ibkr.errors import IbkrAccountError
from short_sale import closes, cover_alarm, hours

logger = logging.getLogger(__name__)

VENUE = "live"
_EPS = 1e-9
# IBKR's shorts as last read: what the alarm names while IBKR is not ready.
_last: dict[str, Any] = {"shorts": {}, "at": None}
_retry_at: dict[str, float] = {}           # symbol (or "#order id") -> monotonic time it may be tried again
_sent: dict[str, int] = {}                 # symbol -> the cover order Nova sent last
# order id -> (when Nova placed it as a short entry, or None: not one; when that was read). A "not one" is
# read again after _NOT_ENTRY_TTL_SEC: IBKR can list a new order before its execution row has the id.
_entries: dict[int, tuple[float | None, float]] = {}
_NOT_ENTRY_TTL_SEC = 5.0


def _book() -> tuple[dict[str, float], list[dict[str, Any]]] | None:
    """IBKR's own positions and working orders, or None while IBKR is not ready (logged once a read fails)."""
    from ibkr import client as _client
    from ibkr import live_book

    if not (_client.is_enabled() and _client.is_connected()) or _client.get_ib() is None:
        return None
    try:
        return live_book.positions(), live_book.open_rows()
    except IbkrAccountError:
        logger.warning("SHORTS: IBKR's book could not be read for Live's day cover", exc_info=True)
        return None


def _waiting(key: str) -> bool:
    return time.monotonic() < _retry_at.get(key, 0.0)


def _later(key: str) -> None:
    _retry_at[key] = time.monotonic() + SHORT_CLOSE_RETRY_SEC


def _oid(row: dict[str, Any]) -> int:
    try:
        return int(row.get("order_id") or 0)
    except (TypeError, ValueError):
        return 0


def _sym(row: dict[str, Any]) -> str:
    return str(row.get("symbol") or "").strip().upper()


def _entry_times(rows: list[dict[str, Any]]) -> dict[int, float]:
    """``{order id: placed at}`` for the working Live orders Nova sent as short entries (memoized by id)."""
    from execution import store_orders

    sells = [_oid(r) for r in rows if str(r.get("side") or "").upper() == "SELL" and _oid(r) > 0]
    now = time.monotonic()
    unknown = [oid for oid in sells if oid not in _entries
               or (_entries[oid][0] is None and now - _entries[oid][1] >= _NOT_ENTRY_TTL_SEC)]
    if unknown:
        found = store_orders.short_entries(unknown)
        for oid in unknown:
            led = found.get(oid)
            _entries[oid] = (float(led["created_ts"]) if led is not None else None, now)
    return {oid: ts for oid in sells if (ts := _entries.get(oid, (None, 0.0))[0]) is not None}


async def entry_cutoff(rows: list[dict[str, Any]], now: float) -> list[dict[str, Any]]:
    """Cancel each of Nova's working Live short entries that has lapsed."""
    from execution.service import execute

    out = []
    for oid, placed in _entry_times(rows).items():
        why = hours.entry_lapsed(placed, now)
        if why is None or _waiting(f"#{oid}"):
            continue
        symbol = next((_sym(r) for r in rows if _oid(r) == oid), "")
        receipt = await execute(ExecutionCommand(
            operation="cancel", idempotency_key=f"day_cover:live:cutoff:{oid}:{int(now)}", source="cancel_working",
            symbol=symbol or None, order_id=oid, target_venue=VENUE, origin="day_cover",  # type: ignore[arg-type]
        ))
        done = {"venue": VENUE, "symbol": symbol, "order_id": oid, "ok": bool(receipt.ok), "error": receipt.error,
                "reason_code": receipt.reason_code}
        closes._audit("day_cover", "cancelled" if receipt.ok else "failed",
                      f"live: the short entry {oid} ({symbol}) was cancelled before it could fill. {why}", done)
        if not receipt.ok:
            _later(f"#{oid}")
            logger.error("SHORTS: the Live short entry %s (%s) was not cancelled (tried again in %.0f s): %s",
                         oid, symbol, SHORT_CLOSE_RETRY_SEC, receipt.error)
        out.append(done)
    return out


def _alarm(symbol: str, qty: float, kind: str, text: str, *, error: str | None = None, code: str | None = None,
           last_seen: float | None = None) -> None:
    cover_alarm.raise_(VENUE, symbol, qty, kind=kind, text=text, error=error, reason_code=code, last_seen=last_seen)


async def _cover(symbol: str, qty: float, rows: list[dict[str, Any]], now: float) -> dict[str, Any]:
    """Cancel the stock's working Live orders, then cover the short at market."""
    from execution.service import execute

    stamp = f"day_cover:live:{symbol}:{int(now)}"
    mine = [r for r in rows if _sym(r) == symbol]
    cancelled, failed = [], []
    for row in [r for r in mine if _oid(r) > 0]:
        receipt = await execute(ExecutionCommand(
            operation="cancel", idempotency_key=f"{stamp}:cancel:{_oid(row)}", source="cancel_working",
            symbol=symbol, order_id=_oid(row), target_venue=VENUE, origin="day_cover",  # type: ignore[arg-type]
        ))
        (cancelled if receipt.ok else failed).append({"order_id": _oid(row), "error": receipt.error})
    outside = [r for r in mine if _oid(r) <= 0]     # placed outside Nova's API session: TWS only
    out: dict[str, Any] = {"venue": VENUE, "symbol": symbol, "side": "BUY", "qty": qty, "ok": False, "order_id": None,
                           "error": None, "reason_code": None, "cancelled": [c["order_id"] for c in cancelled],
                           "cancel_failed": [f["order_id"] for f in failed]}
    if failed or outside:
        words = [f"order {f['order_id']} ({f['error']})" for f in failed] + \
                [f"an order placed in TWS (perm id {r.get('perm_id') or '?'})" for r in outside]
        out["error"] = "Nova could not cancel " + "; ".join(words)
        _alarm(symbol, qty, "refused", (f"Nova could not cover {qty:g} {symbol} short on Live: it could not cancel "
                                        f"{'; '.join(words)} first. Cancel {'it' if len(words) == 1 else 'them'} in "
                                        "TWS and Nova covers at once, or cover it yourself now."),
               error=out["error"], code="DAY_COVER_CANCEL")
    else:
        receipt = await execute(ExecutionCommand(
            operation="place", idempotency_key=f"{stamp}:close", source="flatten", intent="flatten",
            symbol=symbol, side="BUY", qty=qty, order_type="MKT", outside_rth=False, tif="DAY", skip_risk=True,
            target_venue=VENUE, origin="day_cover",  # type: ignore[arg-type]
        ))
        out.update(ok=bool(receipt.ok), order_id=receipt.order_id, error=receipt.error, reason_code=receipt.reason_code)
        if receipt.ok:
            if receipt.order_id is not None:
                _sent[symbol] = int(receipt.order_id)
            cover_alarm.clear(VENUE, symbol)
        else:
            _alarm(symbol, qty, "refused", (f"Nova could not cover {qty:g} {symbol} short on Live: {receipt.error}. "
                                            "Cover it yourself now; Nova tries again every "
                                            f"{SHORT_CLOSE_RETRY_SEC:.0f} s."),
                   error=receipt.error, code=receipt.reason_code)
    closes._audit("day_cover", "closed" if out["ok"] else "failed",
                  f"live: Nova covers every short by {_when(now)} -- {qty:g} {symbol} covered at market", out)
    if not out["ok"]:
        _later(symbol)
        logger.error("SHORTS: Live's day cover of %s %s failed (tried again in %.0f s): %s", qty, symbol,
                     SHORT_CLOSE_RETRY_SEC, out["error"])
    return out


def _when(now: float) -> str:
    got = hours.hours_on(now)
    return f"{hours.clock(got.cover_ts)} ET" if got is not None and now >= got.cover_ts else "the open"


def _covering(rows: list[dict[str, Any]], symbol: str) -> bool:
    """Nova's last cover of ``symbol`` is still working at IBKR."""
    oid = _sent.get(symbol)
    return oid is not None and any(_oid(r) == oid for r in rows)


async def pass_once(now: float | None = None) -> list[dict[str, Any]]:
    """One look at Live: the cutoff, then the day cover; never raises (the practice closes run beside it)."""
    from ibkr import safety

    now = time.time() if now is None else float(now)
    out: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    try:
        book = _book()
        if book is not None:
            positions, rows = book
            _last.update(shorts={s: -q for s, q in positions.items() if q < -_EPS}, at=now)
            out += await entry_cutoff(rows, now)
        if not safety.short_enabled():
            cover_alarm.keep_only(VENUE, set())          # Nova places nothing at Live's cover while it is off
            return out
        shorts: dict[str, float] = dict(_last["shorts"])
        cover_alarm.keep_only(VENUE, set(shorts))
        if not shorts or not hours.cover_due(now):
            return out
        if book is None:
            seen = hours.clock(float(_last["at"])) if _last["at"] else "?"
            for symbol, qty in shorts.items():
                _alarm(symbol, qty, "disconnected", (f"Nova cannot cover {qty:g} {symbol} short on Live: IBKR is not "
                                                     f"connected (last seen short at {seen} ET). Cover it in TWS or "
                                                     "on your phone now."), last_seen=_last["at"])
            return out
        if not hours.regular_session(now):
            for symbol, qty in shorts.items():
                _alarm(symbol, qty, "outside_session",
                       (f"{qty:g} {symbol} is still short on Live outside the regular session: Nova sends a market "
                        "cover only from 09:30 ET to the close. Cover it yourself in extended hours now, or Nova "
                        "covers it at 09:30."))
            return out
        for symbol, qty in shorts.items():
            if _covering(rows, symbol) or _waiting(symbol):
                continue
            out.append(await _cover(symbol, qty, rows, now))
    except Exception:
        logger.exception("SHORTS: Live's day cover pass failed -- the next pass tries again")
    return out


def reset_for_tests() -> None:
    _last.update(shorts={}, at=None)
    _retry_at.clear()
    _sent.clear()
    _entries.clear()
