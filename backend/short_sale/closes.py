"""Nova's own closes on Paper and Sim: the day cover and the margin call (ADR 048 decisions 4 and 5).

**The day cover.** At 15:55 ET by the venue's clock (12:55 on an early close; ``short_sale.hours``)
Nova covers every short still open on the venue, and any short it finds outside its day's hours
(one that survived a closed Nova). That stock's working orders go first -- its short entries,
then its stop, target and covers -- so nothing fills after the cover and opens a long.

**The margin call.** IBKR sends no margin call: when equity falls under the maintenance
requirement it liquidates. When a practice account's equity is under its maintenance
(``Ledger.maintenance``: IBKR's what-if ratio per stock, else the published rules), Nova closes the
position that needs the most -- shorts first -- at market, one a pass, until the account fits.

Every close is an ordinary order through the execution door (ADR 007): source ``flatten``
(protective: never refused by the kill switch, the day lock or the arm latch), origin
``day_cover`` / ``margin_call`` (the Orders table's "Sent by"), sent to the venue it closes on
(``target_venue``) whatever the desk shows. Each is a ``day_cover`` / ``margin_call`` line on the
bot audit stream. A close the venue refuses is logged and tried again ``SHORT_CLOSE_RETRY_SEC``
later, not on every pass. Live's day cover and its alarm come with ADR 048's last step.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from constants_shorts import SHORT_CLOSE_RETRY_SEC
from execution.models import ExecutionCommand
from short_sale import hours

logger = logging.getLogger(__name__)

PRACTICE_VENUES = ("paper", "sim")
_EPS = 1e-9
# (venue, symbol, origin) -> the monotonic time a refused close may be tried again.
_retry_at: dict[tuple[str, str, str], float] = {}


def _waiting(venue: str, symbol: str, origin: str) -> bool:
    return time.monotonic() < _retry_at.get((venue, symbol, origin), 0.0)


def _audit(action: str, outcome: str, reason: str, inputs: dict[str, Any]) -> None:
    try:
        from bot.audit import record

        record(action=action, outcome=outcome, reason=reason, inputs=inputs)
    except Exception:  # the close stands; only its audit line is lost, and the log says so
        logger.exception("SHORTS: the %s audit line for %s was not written", action, inputs.get("symbol"))


def _working(broker: Any, symbol: str) -> list[dict[str, Any]]:
    rows = [r for r in broker.working_orders() if str(r.get("symbol") or "").upper() == symbol]
    return sorted(rows, key=lambda r: (not r.get("short_entry"), int(r.get("order_id") or 0)))


async def close(broker: Any, row: dict[str, Any], *, origin: str, reason: str, now: float) -> dict[str, Any]:
    """Cancel ``row``'s stock's working orders on the broker's venue, then close the position at market."""
    from execution.service import execute

    venue = str(broker.venue)
    symbol = str(row["symbol"]).upper()
    qty = abs(float(row["qty"]))
    side = "BUY" if float(row["qty"]) < 0 else "SELL"
    stamp = f"{origin}:{venue}:{symbol}:{int(now)}"
    cancelled, failed = [], []
    for order in _working(broker, symbol):
        receipt = await execute(ExecutionCommand(
            operation="cancel", idempotency_key=f"{stamp}:cancel:{order['order_id']}", source="cancel_working",
            symbol=symbol, order_id=int(order["order_id"]), target_venue=venue, origin=origin,  # type: ignore[arg-type]
        ))
        (cancelled if receipt.ok else failed).append(int(order["order_id"]))
    receipt = await execute(ExecutionCommand(
        operation="place", idempotency_key=f"{stamp}:close", source="flatten", symbol=symbol, side=side,
        qty=qty, order_type="MKT", outside_rth=True, skip_risk=True, target_venue=venue,
        origin=origin,  # type: ignore[arg-type]
    ))
    out = {"venue": venue, "symbol": symbol, "side": side, "qty": qty, "ok": bool(receipt.ok),
           "order_id": receipt.order_id, "error": receipt.error, "reason_code": receipt.reason_code,
           "cancelled": cancelled, "cancel_failed": failed}
    _audit(origin, "closed" if receipt.ok else "failed", reason, out)
    if receipt.ok:
        _retry_at.pop((venue, symbol, origin), None)
    else:
        _retry_at[(venue, symbol, origin)] = time.monotonic() + SHORT_CLOSE_RETRY_SEC
        logger.error("SHORTS: %s of %s %s on %s failed (tried again in %.0f s): %s", origin, side, symbol, venue,
                     SHORT_CLOSE_RETRY_SEC, receipt.error)
    return out


def _closing(broker: Any, symbol: str) -> bool:
    """A close Nova sent is still working on ``symbol``: never send a second."""
    return any(r.get("order_origin") in ("day_cover", "margin_call") and r.get("effect") == "closes"
               for r in _working(broker, symbol))


async def day_cover(broker: Any) -> list[dict[str, Any]]:
    """Cover every short on the broker's venue when its clock stands past the day's cover time."""
    now = float(broker.reference.now_ts())
    if not hours.cover_due(now):
        return []
    out = []
    for row in broker.positions():
        symbol = str(row["symbol"]).upper()
        if float(row.get("qty") or 0) < -_EPS and not _closing(broker, symbol) \
                and not _waiting(str(broker.venue), symbol, "day_cover"):
            got = hours.hours_on(now)
            when = f"{hours.clock(got.cover_ts)} ET" if got is not None and now >= got.cover_ts else "the close"
            out.append(await close(broker, row, origin="day_cover", now=now, reason=(
                f"{broker.venue}: Nova covers every short by {when} -- {abs(float(row['qty'])):g} "
                f"{row['symbol']} covered at market")))
    return out


async def margin_call(broker: Any) -> list[dict[str, Any]]:
    """Close the position that needs the most margin while the account's equity is under its maintenance."""
    from practice import margin as practice_margin

    held = broker.positions()      # marks every position at the venue's last price first
    ledger = broker.ledger
    equity, maint = float(ledger.net_liquidation()), float(ledger.maintenance())
    if equity >= maint - _EPS:
        return []
    rows = [r for r in held if abs(float(r.get("qty") or 0)) > _EPS and not _closing(broker, str(r["symbol"]).upper())
            and not _waiting(str(broker.venue), str(r["symbol"]).upper(), "margin_call")]
    if not rows:
        return []
    worst = max(rows, key=lambda r: (float(r["qty"]) < 0, practice_margin.position_maintenance(r, ledger.margin_ratio)))
    now = float(broker.reference.now_ts())
    return [await close(broker, worst, origin="margin_call", now=now, reason=(
        f"{broker.venue}: equity {equity:,.2f} fell under the maintenance requirement {maint:,.2f} -- IBKR "
        f"liquidates; {abs(float(worst['qty'])):g} {worst['symbol']} closed at market"))]


async def pass_once() -> list[dict[str, Any]]:
    """One pass over every practice venue this process has loaded: the day cover, then the margin call."""
    from practice.broker import loaded

    out: list[dict[str, Any]] = []
    for venue in PRACTICE_VENUES:
        broker = loaded(venue)
        if broker is None:
            continue
        try:
            out += await day_cover(broker)
            out += await margin_call(broker)
        except Exception:  # one venue's failure never stops the other's closes; the next pass tries again
            logger.exception("SHORTS: the %s close pass failed", venue)
    return out


def reset_for_tests() -> None:
    _retry_at.clear()
