"""Event-sourced practice ledger (ADR 020). Pure bookkeeping; never talks to IBKR.

Events -- ``placed`` / ``replaced`` / ``cancelled`` / ``expired`` / ``filled`` /
``rollover`` -- carry ``ts`` (the venue's time: the replay playhead on Sim, the wall clock
on Paper; the row stamps), ``wall_ts`` (when it really happened, kept for forensics), the ADR
007 command ``source`` and the ``bot_id``. Every derived number -- cash,
positions with average cost, realized P&L, marks, working and closed orders,
the day figures -- is replayed from them, so ``unwind_to(ts)`` (Sim's time
travel) simply drops what happened after ``ts`` and re-derives.

Fees (``practice.fees``) are charged at the fill and stored on the event, so a
later rate change never rewrites history; realized P&L is net of them.
Buying power (``practice.margin``) is what the broker checks before it admits
an order and again when a resting order fills. The day figures roll at
``PRACTICE_DAY_ROLLOVER_HOUR_ET`` through a ``rollover`` event that records
the equity at the boundary: ``day_pnl`` is net liquidation less that equity.
Persistence lives in ``practice.persist``.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from constants_practice import (
    PRACTICE_ACCOUNT_ID_PAPER,
    PRACTICE_ACCOUNT_ID_SIM,
    PRACTICE_LEDGER_SCHEMA_VERSION,
    PRACTICE_ORDER_STATUS_EXPIRED,
    PRACTICE_STARTING_CASH,
    PRACTICE_VENUE_PAPER,
    PRACTICE_VENUE_SIM,
)
from practice import margin
from practice.clock import ET, day_start_ts, iso_et, iso_utc  # noqa: F401 -- ET re-exported for persist
from practice.fees import Fees, for_fill

logger = logging.getLogger(__name__)

_EPS = 1e-9

EVENT_PLACED = "placed"
EVENT_REPLACED = "replaced"
EVENT_CANCELLED = "cancelled"
EVENT_EXPIRED = "expired"  # a DAY order past its session close (practice.order_rules)
EVENT_FILLED = "filled"
EVENT_ROLLOVER = "rollover"
EVENT_TYPES = (EVENT_PLACED, EVENT_REPLACED, EVENT_CANCELLED, EVENT_EXPIRED, EVENT_FILLED, EVENT_ROLLOVER)

ACCOUNT_IDS = {
    PRACTICE_VENUE_PAPER: PRACTICE_ACCOUNT_ID_PAPER,
    PRACTICE_VENUE_SIM: PRACTICE_ACCOUNT_ID_SIM,
}


class Ledger:
    """One practice account, replayed from its events."""

    def __init__(
        self,
        starting_cash: float = PRACTICE_STARTING_CASH,
        *,
        created_ts: float | None = None,
        events: list[dict[str, Any]] | None = None,
    ) -> None:
        cash = float(starting_cash)
        if not cash > 0:
            raise ValueError("starting_cash must be positive")
        self.starting_cash = cash
        self.created_ts = float(created_ts) if created_ts is not None else time.time()
        self.events: list[dict[str, Any]] = [dict(e) for e in (events or [])]
        self._derive()

    # ------------------------------------------------------------------ derive
    def _derive(self) -> None:
        self.cash = self.starting_cash
        self.realized = 0.0
        self._positions: dict[str, dict[str, float]] = {}
        self._working: dict[int, dict[str, Any]] = {}
        self._closed: list[dict[str, Any]] = []
        self._marks: dict[str, float] = {}
        self._next_id = 1
        self.day_started_ts = day_start_ts(self.created_ts)
        self.day_start_equity = self.starting_cash
        # Realized P&L when the current practice day began; replayed, never stored.
        self.realized_at_day_start = 0.0
        for event in self.events:
            self._apply(event)

    def _apply(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == EVENT_PLACED:
            self._apply_placed(event)
        elif kind == EVENT_REPLACED:
            self._apply_replaced(event)
        elif kind in (EVENT_CANCELLED, EVENT_EXPIRED):
            self._apply_cancelled(event)
        elif kind == EVENT_FILLED:
            self._apply_filled(event)
        elif kind == EVENT_ROLLOVER:
            self.day_started_ts = float(event["ts"])
            self.day_start_equity = float(event["equity"])
            self.realized_at_day_start = self.realized
        else:
            raise ValueError(f"unknown ledger event {kind!r}")

    def _append(self, event: dict[str, Any]) -> dict[str, Any]:
        event.setdefault("wall_ts", time.time())
        self.events.append(event)
        self._apply(event)
        return event

    @staticmethod
    def _stamp(event: dict[str, Any]) -> str:
        # The venue's time (Sim: the playhead a rewind unwinds by), never wall time (R27).
        return iso_utc(event["ts"])

    def _apply_placed(self, event: dict[str, Any]) -> None:
        row = dict(event["row"])
        oid = int(row["order_id"])
        if oid in self._working:
            logger.warning("PRACTICE ledger: duplicate placed event for order %s ignored", oid)
            return
        if not float(row.get("filled_qty") or 0):
            row["commission"] = None  # no fill, no commission -- older events stamped 0.0 (QA C30)
        self._working[oid] = row
        self._next_id = max(self._next_id, oid + 1)

    def _apply_replaced(self, event: dict[str, Any]) -> None:
        row = self._working.get(int(event["order_id"]))
        if row is None:
            return
        if event.get("limit_price") is not None:
            row["limit_price"] = float(event["limit_price"])
        if event.get("stop_price") is not None:
            row["stop_price"] = float(event["stop_price"])
        row["placed_ts"] = float(event["ts"])
        row["updated_at"] = self._stamp(event)

    def _apply_cancelled(self, event: dict[str, Any]) -> None:
        row = self._working.pop(int(event["order_id"]), None)
        if row is None:
            return
        row["status"] = PRACTICE_ORDER_STATUS_EXPIRED if event.get("type") == EVENT_EXPIRED else "Cancelled"
        row["updated_at"] = self._stamp(event)
        row["remaining_qty"] = float(row.get("qty") or 0) - float(row.get("filled_qty") or 0)
        if event.get("reason"):
            row["error"] = event["reason"]
            row["reason_code"] = event.get("code")
        self._closed.append(row)

    def _apply_filled(self, event: dict[str, Any]) -> None:
        row = self._working.pop(int(event["order_id"]), None)
        if row is None:
            return
        qty = float(row["qty"])
        price = float(event["price"])
        fees = Fees.from_dict(event.get("fees"))
        stamp = self._stamp(event)
        row.update(
            filled_qty=qty, remaining_qty=0.0, avg_fill_price=price,
            fill_basis=event.get("basis"), status="Filled", filled_at=stamp,
            updated_at=stamp, held_until=None, commission=fees.commission,
            fees=fees.as_dict(), fill_ts=float(event["ts"]),
        )
        symbol = str(row["symbol"]).upper()
        self._marks[symbol] = price
        self._apply_position(symbol, str(row["side"]).upper(), qty, price, fees.total)
        self._closed.append(row)

    def _apply_position(self, symbol: str, side: str, qty: float, price: float, fee_total: float) -> None:
        pos = self._positions.setdefault(symbol, {"qty": 0.0, "avg_cost": 0.0, "realized": 0.0})
        cur = float(pos["qty"])
        avg = float(pos["avg_cost"])
        pnl = -float(fee_total)
        if side == "BUY":
            self.cash -= qty * price
            new_qty = cur + qty
            if cur < -_EPS:  # covering a short; any excess opens a long at this price
                pnl += (avg - price) * min(qty, -cur)
                pos["avg_cost"] = price if new_qty > _EPS else avg
            else:
                pos["avg_cost"] = (avg * cur + qty * price) / new_qty if new_qty > _EPS else 0.0
        else:
            self.cash += qty * price
            new_qty = cur - qty
            if cur > _EPS:  # closing a long; any excess opens a short at this price
                pnl += (price - avg) * min(qty, cur)
                pos["avg_cost"] = price if new_qty < -_EPS else avg
            else:
                pos["avg_cost"] = (avg * (-cur) + qty * price) / (-new_qty) if new_qty < -_EPS else 0.0
        pos["qty"] = new_qty
        if abs(new_qty) < _EPS:
            pos["qty"] = 0.0
            pos["avg_cost"] = 0.0
        self.cash -= float(fee_total)
        self.realized += pnl
        pos["realized"] = float(pos["realized"]) + pnl

    # --------------------------------------------------------------- mutations
    def alloc_id(self) -> int:
        oid = self._next_id
        self._next_id += 1
        return oid

    def rollover(self, now_ts: float) -> bool:
        """Start a new practice day when ``now_ts`` has crossed the rollover hour."""
        boundary = day_start_ts(now_ts)
        if boundary <= self.day_started_ts + _EPS:
            return False
        self._append({"type": EVENT_ROLLOVER, "ts": boundary, "equity": self.net_liquidation()})
        return True

    def place(self, row: dict[str, Any], *, ts: float, source: str, bot_id: str | None = None) -> dict[str, Any]:
        oid = int(row["order_id"])
        if oid in self._working:
            raise ValueError(f"order {oid} is already working")
        self.rollover(ts)
        # The row's attribution is the event's: a fill or cancel later reads it back.
        stamped = {**row, "order_source": source, "bot_id": bot_id}
        self._append({
            "type": EVENT_PLACED, "ts": float(ts), "source": source, "bot_id": bot_id,
            "row": stamped,
        })
        return dict(self._working[oid])

    def replace(
        self, order_id: int, *, ts: float, limit_price: float | None = None, stop_price: float | None = None,
    ) -> dict[str, Any] | None:
        oid = int(order_id)
        if oid not in self._working:
            return None
        self.rollover(ts)
        self._append({
            "type": EVENT_REPLACED, "ts": float(ts), "order_id": oid,
            "limit_price": float(limit_price) if limit_price is not None else None,
            "stop_price": float(stop_price) if stop_price is not None else None,
        })
        return dict(self._working[oid])

    def cancel(
        self, order_id: int, *, ts: float, reason: str | None = None, code: str | None = None,
        source: str = "manual", bot_id: str | None = None, kind: str = EVENT_CANCELLED,
    ) -> dict[str, Any] | None:
        """Close a working order unfilled; ``kind`` is ``cancelled`` or ``expired`` (a DAY order past its close)."""
        oid = int(order_id)
        if oid not in self._working:
            return None
        self.rollover(ts)
        self._append({
            "type": kind, "ts": float(ts), "order_id": oid, "reason": reason,
            "code": code, "source": source, "bot_id": bot_id,
        })
        return dict(self._closed[-1])

    def fill(
        self, order_id: int, *, ts: float, price: float, basis: str, fees: Fees | None = None,
    ) -> dict[str, Any] | None:
        oid = int(order_id)
        row = self._working.get(oid)
        if row is None:
            return None
        charged = fees if fees is not None else for_fill(str(row["side"]), float(row["qty"]), float(price))
        self.rollover(ts)
        self._append({
            "type": EVENT_FILLED, "ts": float(ts), "order_id": oid, "price": float(price),
            "basis": basis, "fees": charged.as_dict(), "source": row.get("order_source"),
            "bot_id": row.get("bot_id"),
        })
        return dict(self._closed[-1])

    def unwind_to(self, ts: float) -> int:
        """Drop every event after ``ts`` (it never happened) and re-derive; returns the count dropped."""
        keep = [e for e in self.events if float(e["ts"]) <= float(ts) + _EPS]
        dropped, next_id = len(self.events) - len(keep), self._next_id
        self.events = keep
        self._derive()
        self._next_id = max(self._next_id, next_id)  # an unwound order's id is never handed out again (QA R14)
        return dropped

    def mark(self, symbol: str, price: float) -> None:
        self._marks[symbol.upper()] = float(price)

    # ------------------------------------------------------------------- reads
    def mark_of(self, symbol: str, fallback: float | None = None) -> float | None:
        return self._marks.get(symbol.upper(), fallback)

    def held_qty(self, symbol: str) -> float:
        return float((self._positions.get(symbol.upper()) or {}).get("qty") or 0.0)

    def avg_cost(self, symbol: str) -> float:
        return float((self._positions.get(symbol.upper()) or {}).get("avg_cost") or 0.0)

    def held_symbols(self) -> list[str]:
        return [s for s, p in self._positions.items() if abs(float(p.get("qty") or 0)) > _EPS]

    def position_rows(self) -> list[dict[str, Any]]:
        """Rows in the shape ``/api/ibkr/positions`` serves today."""
        out: list[dict[str, Any]] = []
        for sym, pos in self._positions.items():
            qty = float(pos.get("qty") or 0)
            if abs(qty) < _EPS:
                continue
            avg = float(pos.get("avg_cost") or 0)
            mark = self._marks.get(sym, avg)
            out.append({
                "symbol": sym, "qty": qty, "avg_cost": avg, "market_price": mark,
                "market_value": round(qty * mark, 4),
                "unrealized_pnl": round((mark - avg) * qty, 4),
                "realized_pnl": round(float(pos.get("realized") or 0), 4),
            })
        return out

    def unrealized_pnl(self) -> float:
        return sum(float(r["unrealized_pnl"]) for r in self.position_rows())

    def gross_position_value(self) -> float:
        return sum(abs(float(r["market_value"])) for r in self.position_rows())

    def net_liquidation(self) -> float:
        return self.cash + sum(float(r["market_value"]) for r in self.position_rows())

    def buying_power(self) -> float:
        return margin.buying_power(self.net_liquidation(), self.gross_position_value())

    def can_afford(self, symbol: str, side: str, qty: float, price: float) -> tuple[bool, float, float]:
        return margin.check(
            side, qty, price, self.held_qty(symbol), self.net_liquidation(), self.gross_position_value(),
        )

    def working_orders(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._working.values()]

    def working_row(self, order_id: int) -> dict[str, Any] | None:
        row = self._working.get(int(order_id))
        return dict(row) if row is not None else None

    def working_symbols(self) -> list[str]:
        return sorted({str(r["symbol"]) for r in self._working.values()})

    def closed_orders(self, limit: int | None = None) -> list[dict[str, Any]]:
        rows = [dict(r) for r in reversed(self._closed)]
        return rows[: max(1, int(limit))] if limit is not None else rows

    def order_row(self, order_id: int) -> dict[str, Any] | None:
        row = self.working_row(order_id)
        if row is not None:
            return row
        for closed in reversed(self._closed):
            if int(closed["order_id"]) == int(order_id):
                return dict(closed)
        return None

    def _today(self, event: dict[str, Any]) -> bool:
        return float(event["ts"]) >= self.day_started_ts - _EPS

    def fills_today(self) -> int:
        return sum(1 for e in self.events if e["type"] == EVENT_FILLED and self._today(e))

    def commissions_today(self) -> float:
        """Every fee charged today -- commission plus the sell-side pass-throughs."""
        return sum(
            Fees.from_dict(e.get("fees")).total
            for e in self.events if e["type"] == EVENT_FILLED and self._today(e)
        )

    def day_pnl(self) -> float:
        return self.net_liquidation() - self.day_start_equity

    def realized_today(self) -> float:
        """Realized P&L (net of fees) since the practice-day boundary (QA W3)."""
        return self.realized - self.realized_at_day_start

    def last_event_ts(self) -> float:
        return float(self.events[-1].get("wall_ts", self.events[-1]["ts"])) if self.events else self.created_ts

    def snapshot(self, venue: str, account_id: str | None = None, *, replay_key: Any = None) -> dict[str, Any]:
        """Exactly the ADR 020 contract fields for ``GET /api/practice/account``."""
        out: dict[str, Any] = {
            "venue": venue,
            "account_id": account_id or ACCOUNT_IDS.get(venue),
            "starting_cash": round(self.starting_cash, 2),
            "cash": round(self.cash, 2),
            "buying_power": round(self.buying_power(), 2),
            "net_liquidation": round(self.net_liquidation(), 2),
            "gross_position_value": round(self.gross_position_value(), 2),
            "realized_pnl": round(self.realized, 2),
            "unrealized_pnl": round(self.unrealized_pnl(), 2),
            "day_pnl": round(self.day_pnl(), 2),
            "realized_today": round(self.realized_today(), 2),
            "day_started_et": iso_et(self.day_started_ts),
            "commissions_today": round(self.commissions_today(), 2),
            "positions": [
                {
                    "symbol": r["symbol"], "qty": r["qty"], "avg_cost": r["avg_cost"],
                    "mark": r["market_price"], "unrealized": r["unrealized_pnl"],
                }
                for r in self.position_rows()
            ],
            "working": self.working_orders(),
            "fills_today": self.fills_today(),
            "schema_version": PRACTICE_LEDGER_SCHEMA_VERSION,
            "updated_at": iso_utc(self.last_event_ts()),
        }
        if venue == PRACTICE_VENUE_SIM:
            out["replay_key"] = list(replay_key) if isinstance(replay_key, (list, tuple)) else replay_key
        return out
