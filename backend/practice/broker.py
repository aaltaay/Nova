"""The practice broker: one ledger, one market reference, no IBKR (ADR 020).

``for_venue("sim")`` trades the loaded replay (``ReplayReference``) on a
scratch ledger; ``for_venue("paper")`` trades the live feed (``LiveReference``)
on the persistent Paper ledger under the operator cache. Fills follow
``sim.fill_model`` and are always estimates (``fill_estimated`` +
``fill_basis``); buying power is enforced at admission and again when a
resting order fills (the order is cancelled ``PRACTICE_BUYING_POWER`` if power
ran out); every row keeps ``source: "nova"`` (the blotter's ownership key) and
adds ``order_source`` (the ADR 007 command source) and ``bot_id``. Per-order
rules -- a DAY order expires at its session close, a SELL is only ever
risk-reducing -- live in ``practice.order_rules`` (operator decisions,
2026-09-21). ``sim.broker`` is a facade over the Sim instance.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from constants_practice import (
    PRACTICE_ACCOUNT_ID_PAPER,
    PRACTICE_ACCOUNT_ID_SIM,
    PRACTICE_ACCOUNT_TYPE_PAPER,
    PRACTICE_ACCOUNT_TYPE_SIM,
    PRACTICE_BUYING_POWER_CODE,
    PRACTICE_BUYING_POWER_REASON,
    PRACTICE_NO_SHORTS_CODE,
    PRACTICE_NO_SHORTS_REASON,
    PRACTICE_STARTING_CASH,
    PRACTICE_TIF_INVALID_CODE,
    PRACTICE_VENUE_PAPER,
    PRACTICE_VENUE_SIM,
)
from constants_sim import SIM_ORDER_TYPE_CODE
from practice import order_rules
from practice.fees import for_fill
from practice.ledger import Ledger, iso_utc
from practice.reference import LiveReference, MarketReference, ReplayReference
from practice.watch import notify_watch
from sim import fill_model

logger = logging.getLogger(__name__)

ORDER_TYPE_REASON = "Practice orders support MKT, LMT and STP"
_EPS = 1e-9


class PracticeBroker:
    def __init__(
        self,
        reference: MarketReference,
        ledger: Ledger,
        account_id: str,
        *,
        venue: str,
        persist_path: str | None = None,
    ) -> None:
        self.reference = reference
        self.ledger = ledger
        self.account_id = account_id
        self.venue = venue
        self.persist_path = persist_path

    # ---------------------------------------------------------------- orders
    def place(
        self,
        symbol: str,
        side: str,
        qty: float,
        order_type: str = "MKT",
        limit_price: float | None = None,
        stop_price: float | None = None,
        outside_rth: bool = False,
        order_id: int | None = None,
        protective: bool = False,
        source: str = "manual",
        bot_id: str | None = None,
        tif: str | None = None,
        short_entry: bool = False,
    ) -> dict[str, Any]:
        """Place a practice order against the venue's reference.

        ``protective`` (flatten / kill) may close a held position whose
        reference is gone: a MKT order then fills at the last known mark, so
        the practice desk can always get flat (ADR 018). ``tif`` is DAY (the
        default; expires at the session close) or GTC. An opening short --
        a SELL beyond the held quantity, or ``short_entry`` -- is refused on
        every source (``practice.order_rules``).
        """
        del outside_rth  # practice orders are always live; there is no session gate
        sym = (symbol or "").strip().upper()
        side_u = (side or "").upper()
        typ = (order_type or "MKT").upper()
        qty_f = float(qty)
        if typ not in fill_model.SUPPORTED_ORDER_TYPES:
            return self._refused(ORDER_TYPE_REASON, SIM_ORDER_TYPE_CODE)
        tif_u = order_rules.normalize_tif(tif)
        if tif_u is None:
            return self._refused(order_rules.TIF_REASON, PRACTICE_TIF_INVALID_CODE)
        ok, reason, code = self.reference.admission(sym)
        at_mark = not ok and protective and typ == "MKT" and self._closes_position(sym, side_u, qty_f)
        if not ok and not at_mark:
            return self._refused(reason, code)
        # Admission first, then the no-shorts rule -- the same order as the
        # execution door (execution/practice_checks.py), so both gates answer alike.
        if order_rules.opening_short(self.ledger.held_qty(sym), side_u, qty_f, short_entry):
            return self._refused(PRACTICE_NO_SHORTS_REASON, PRACTICE_NO_SHORTS_CODE)
        ref = None if at_mark else self.reference.reference(sym)
        now = self.reference.now_ts()
        self.ledger.rollover(now)
        power_price = self._admission_price(typ, side_u, limit_price, stop_price, ref)
        if power_price is not None:
            afford, needed, available = self.ledger.can_afford(sym, side_u, qty_f, power_price)
            if not afford:
                return self._refused(
                    f"{PRACTICE_BUYING_POWER_REASON} (needs {needed:,.2f}, has {available:,.2f})",
                    PRACTICE_BUYING_POWER_CODE,
                )
        oid = int(order_id) if order_id is not None else self.ledger.alloc_id()
        row = self._row(oid, sym, side_u, qty_f, typ, limit_price, stop_price, now, source, bot_id, tif_u)
        self.ledger.place(row, ts=now, source=source, bot_id=bot_id)
        if at_mark:
            mark = self.ledger.mark_of(sym, self.ledger.avg_cost(sym))
            self._settle(oid, now, fill_model.Fill(float(mark), fill_model.BASIS_LAST_MARK))
        else:
            fill = fill_model.at_placement(side_u, typ, ref, limit=row["limit_price"], stop=row["stop_price"])
            if fill is not None:
                self._settle(oid, now, fill)
        self._commit()
        current = self.ledger.order_row(oid) or row
        return {
            "ok": True, "order_id": oid, "error": None, "mode": self.venue,
            "nova_placed_at": row["nova_placed_at"], "broker_status": current["status"],
        }

    def cancel(self, order_id: int, *, source: str = "manual", bot_id: str | None = None) -> dict[str, Any]:
        row = self.ledger.cancel(int(order_id), ts=self.reference.now_ts(), source=source, bot_id=bot_id)
        if row is None:
            return {"ok": False, "error": f"order {order_id} not open", "verified_gone": True}
        self._commit()
        return {"ok": True, "error": None, "verified_gone": True, "mode": self.venue}

    def replace(
        self, order_id: int, limit_price: float | None = None, stop_price: float | None = None,
    ) -> dict[str, Any]:
        now = self.reference.now_ts()
        row = self.ledger.replace(int(order_id), ts=now, limit_price=limit_price, stop_price=stop_price)
        if row is None:
            return {"ok": False, "error": f"order {order_id} not open"}
        fill = fill_model.at_placement(
            row["side"], row["order_type"], self.reference.reference(row["symbol"]),
            limit=row.get("limit_price"), stop=row.get("stop_price"),
        )
        if fill is not None:
            self._settle(int(order_id), now, fill)
        self._commit()
        current = self.ledger.order_row(int(order_id)) or row
        return {
            "ok": True, "order_id": int(order_id), "error": None, "mode": self.venue,
            "nova_placed_at": row.get("submitted_at"), "broker_status": current.get("status"),
        }

    def try_fill_working(self, symbol: str, prints: list[tuple[float, float]]) -> list[dict[str, Any]]:
        """Match resting orders for ``symbol`` against later prints, oldest first."""
        sym = (symbol or "").strip().upper()
        filled: list[dict[str, Any]] = []
        for ts, price in prints:
            self.ledger.mark(sym, price)
            for row in self.ledger.working_orders():
                if row["symbol"] != sym or float(ts) <= float(row.get("placed_ts") or 0):
                    continue
                if order_rules.print_after_expiry(row, float(ts)):
                    continue  # a DAY order's session closed before this print
                fill = fill_model.on_print(
                    row["side"], row["order_type"], float(price),
                    limit=row.get("limit_price"), stop=row.get("stop_price"),
                )
                if fill is None:
                    continue
                closed = self._settle(int(row["order_id"]), float(ts), fill)
                if closed is not None and closed.get("status") == "Filled":
                    filled.append(closed)
        if prints:
            self._commit()
        return filled

    def expire_due(self, now: float | None = None) -> list[dict[str, Any]]:
        """Expire every DAY order whose session has closed (``PRACTICE_TIF_EXPIRED``); returns the rows."""
        now_ts = float(now) if now is not None else float(self.reference.now_ts())
        expired = order_rules.expire_due(self.ledger, now_ts)
        for row in expired:
            notify_watch(int(row["order_id"]), row)
        if expired:
            self._commit()
        return expired

    # ----------------------------------------------------------------- reads
    def working_symbols(self) -> list[str]:
        return self.ledger.working_symbols()

    def working_orders(self) -> list[dict[str, Any]]:
        return self.ledger.working_orders()

    open_orders = working_orders

    def closed_orders(self, limit: int | None = None) -> list[dict[str, Any]]:
        return self.ledger.closed_orders(limit)

    def positions(self) -> list[dict[str, Any]]:
        self._refresh_marks()
        return self.ledger.position_rows()

    def account_summary(self) -> dict[str, Any]:
        """The shape ``/api/ibkr/account`` serves today, from the practice ledger."""
        self._refresh_marks()
        ledger = self.ledger
        sim = self.venue == PRACTICE_VENUE_SIM
        return {
            "connected": True, "mode": self.venue, "sim": sim, "practice": True,
            "pending": False, "account_id": self.account_id,
            "NetLiquidation": round(ledger.net_liquidation(), 2),
            "TotalCashValue": round(ledger.cash, 2),
            "BuyingPower": round(ledger.buying_power(), 2),
            "UnrealizedPnL": round(ledger.unrealized_pnl(), 2),
            "RealizedPnL": round(ledger.realized, 2),
            "GrossPositionValue": round(ledger.gross_position_value(), 2),
            "account_class": "margin",
            "AccountType": PRACTICE_ACCOUNT_TYPE_SIM if sim else PRACTICE_ACCOUNT_TYPE_PAPER,
        }

    def snapshot(self) -> dict[str, Any]:
        self._refresh_marks()
        if self.ledger.rollover(self.reference.now_ts()):
            self._commit()
        key_fn = getattr(self.reference, "replay_key", None)
        replay_key = key_fn() if callable(key_fn) else None
        return self.ledger.snapshot(self.venue, self.account_id, replay_key=replay_key)

    # ------------------------------------------------------------- lifecycle
    def rollover(self) -> bool:
        rolled = self.ledger.rollover(self.reference.now_ts())
        if rolled:
            self._commit()
        return rolled

    def unwind_to(self, ts: float) -> int:
        dropped = self.ledger.unwind_to(ts)
        if dropped:
            self._commit()
        return dropped

    def reset(self, starting_cash: float | None = None) -> dict[str, Any]:
        """A fresh account. Paper archives the old ledger first, never deletes it."""
        cash = float(starting_cash) if starting_cash is not None else PRACTICE_STARTING_CASH
        if not cash > 0:
            raise ValueError("starting_cash must be positive")
        archived = None
        if self.persist_path:
            from practice import persist

            archived = persist.archive(self.persist_path)
        self.ledger = Ledger(cash, created_ts=self.reference.now_ts())
        self._commit()
        logger.info("PRACTICE %s: account reset to %.2f (archived=%s)", self.venue, cash, archived)
        return {**self.snapshot(), "archived": archived}

    # --------------------------------------------------------------- helpers
    def _refused(self, error: str, code: str | None) -> dict[str, Any]:
        return {"ok": False, "order_id": None, "error": error, "mode": self.venue, "reason_code": code}

    def _closes_position(self, symbol: str, side: str, qty: float) -> bool:
        held = self.ledger.held_qty(symbol)
        if side == "SELL":
            return held > _EPS and qty <= held + _EPS
        return held < -_EPS and qty <= -held + _EPS

    @staticmethod
    def _admission_price(
        typ: str, side: str, limit_price: float | None, stop_price: float | None, ref: fill_model.Reference | None,
    ) -> float | None:
        """What an opening order is charged against buying power at admission."""
        if typ == "LMT" and limit_price is not None:
            return float(limit_price)
        if typ == "STP" and stop_price is not None:
            return float(stop_price)
        if ref is None:
            return None
        quoted = ref.ask if side == "BUY" else ref.bid
        touch = quoted if quoted is not None else ref.last
        return float(touch) if touch is not None else None

    def _row(
        self, oid: int, sym: str, side: str, qty: float, typ: str, limit_price: float | None,
        stop_price: float | None, now: float, source: str, bot_id: str | None, tif: str,
    ) -> dict[str, Any]:
        wall = iso_utc(time.time())
        return {
            "order_id": oid, "perm_id": oid, "symbol": sym, "side": side, "qty": qty,
            "filled_qty": 0.0, "remaining_qty": qty, "order_type": typ,
            "limit_price": float(limit_price) if limit_price is not None else None,
            "stop_price": float(stop_price) if stop_price is not None else None,
            "avg_fill_price": None, "outside_rth": True, "status": "Submitted",
            "submitted_at": wall, "updated_at": wall, "filled_at": None, "held_until": None,
            "commission": 0.0, "fees": None, "source": "nova", "order_source": source,
            "bot_id": bot_id, "mode": self.venue, "venue": self.venue,
            "account_id": self.account_id, "nova_placed_at": wall, "placed_ts": float(now),
            "fill_estimated": True, "fill_basis": None,
            "tif": tif, "expires_ts": order_rules.expiry_ts(tif, self.reference, now),
        }

    def _settle(self, oid: int, ts: float, fill: fill_model.Fill) -> dict[str, Any] | None:
        """Fill a working order, or cancel it when buying power ran out since admission."""
        row = self.ledger.working_row(oid)
        if row is None:
            return None
        ok, needed, available = self.ledger.can_afford(row["symbol"], row["side"], float(row["qty"]), fill.price)
        if not ok:
            reason = f"{PRACTICE_BUYING_POWER_REASON} at the fill (needs {needed:,.2f}, has {available:,.2f})"
            logger.warning("PRACTICE %s: order %s cancelled -- %s", self.venue, oid, reason)
            closed = self.ledger.cancel(oid, ts=ts, reason=reason, code=PRACTICE_BUYING_POWER_CODE, source="venue")
        else:
            fees = for_fill(row["side"], float(row["qty"]), fill.price)
            closed = self.ledger.fill(oid, ts=ts, price=fill.price, basis=fill.basis, fees=fees)
        if closed is not None:
            notify_watch(oid, closed)
        return closed

    def _refresh_marks(self) -> None:
        for sym in self.ledger.held_symbols():
            try:
                last = self.reference.reference(sym).last
            except Exception:
                logger.debug("PRACTICE %s: mark refresh failed for %s", self.venue, sym, exc_info=True)
                continue
            if last is not None:
                self.ledger.mark(sym, last)

    def _commit(self) -> None:
        if not self.persist_path:
            return
        from practice import persist

        try:
            persist.save(self.ledger, self.persist_path)
        except Exception:
            logger.exception("PRACTICE %s: could not persist the ledger to %s", self.venue, self.persist_path)


# ------------------------------------------------------------------ venues
_brokers: dict[str, PracticeBroker] = {}


def _paper_ledger(path: str, now: float) -> Ledger:
    from practice import persist

    try:
        ledger = persist.load(path)
    except persist.LedgerSchemaError as exc:
        archived = persist.archive(path)
        logger.exception(
            "PRACTICE paper: refusing %s (%s); archived as %s, starting a fresh account", path, exc, archived,
        )
        ledger = None
    return ledger if ledger is not None else Ledger(PRACTICE_STARTING_CASH, created_ts=now)


def for_venue(venue: str) -> PracticeBroker:
    """The venue's broker: ``sim`` (scratch, replay) or ``paper`` (persistent, live feed)."""
    key = (venue or "").strip().lower()
    broker = _brokers.get(key)
    if broker is not None:
        return broker
    if key == PRACTICE_VENUE_SIM:
        ref: MarketReference = ReplayReference()
        broker = PracticeBroker(
            ref, Ledger(PRACTICE_STARTING_CASH, created_ts=ref.now_ts()), PRACTICE_ACCOUNT_ID_SIM, venue=key,
        )
    elif key == PRACTICE_VENUE_PAPER:
        from practice import persist

        path = persist.paper_ledger_path()
        ref = LiveReference()
        broker = PracticeBroker(
            ref, _paper_ledger(path, ref.now_ts()), PRACTICE_ACCOUNT_ID_PAPER, venue=key, persist_path=path,
        )
    else:
        raise ValueError(f"unknown practice venue {venue!r}")
    _brokers[key] = broker
    return broker


def reset_for_tests(venue: str | None = None) -> None:
    if venue is None:
        _brokers.clear()
    else:
        _brokers.pop((venue or "").strip().lower(), None)
