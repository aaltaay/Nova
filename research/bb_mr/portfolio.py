"""Portfolio, Basket, Cash Reservation, Risk Controls, and Ledger Reconciliation.

maintainer: one-concern the shared account's cash-reservation, basket-state, and ledger reconciliation invariant must live in one place

Implements Section 5 of the specification:
- Shared $25,000 cash account (no borrowing or leverage).
- Basket creation freezes account equity E0 for that basket's entry sizing (2% E0) and loss budget (-0.5% E0).
- Up to `max_entries` (default 5) per basket, max 10% E0 committed entry capital per basket.
- Max 5 simultaneously held stocks; max 50% aggregate gross exposure for new purchases.
- Reserved cash for pending entry orders so simultaneous signals cannot double-spend cash.
- Normal exit when executable bid >= latest completed target band AND net basket liquidation P&L > 0.
- Basket loss stop (-0.5% E0) and Account daily loss stop (-3.0% of start-of-day equity).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from research.bb_mr.config import AccountParams, ExecutionParams, StrategyParams
from research.bb_mr.execution import (
    BarQuote,
    compute_fill_fees,
    execute_order_on_bar,
    is_regular_hours,
    max_shares_for_budget,
)


@dataclass
class EntryLeg:
    entry_num: int
    shares: int
    fill_price: float
    fees: float
    signal_bar_index: int
    signal_date: str
    signal_minute: int
    fill_date: str
    fill_minute: int


@dataclass
class PendingOrder:
    order_id: int
    ticker: str
    side: str                       # "BUY" or "SELL"
    shares: int
    submitted_date: str
    submitted_minute: int
    eligible_after_minute: int      # earliest minute_close on submitted_date when order can fill
    reason: str
    signal_bar_index: int = -1
    reserved_cash: float = 0.0
    frozen_e0: float = 0.0
    limit_collar_price: float | None = None


@dataclass
class Basket:
    basket_id: int
    ticker: str
    frozen_e0: float
    created_date: str
    created_minute: int
    entries: list[EntryLeg] = field(default_factory=list)
    total_shares: int = 0
    initial_peak_shares: int = 0
    committed_cost: float = 0.0     # sum of entry shares * entry fill_price (for all entries ever filled in basket)
    remaining_cost_basis: float = 0.0
    opening_fees: float = 0.0
    exit_proceeds: float = 0.0
    exit_fees: float = 0.0
    dividends_received: float = 0.0
    last_signal_bar_index: int = -999_999
    last_mark_bid: float = 0.0
    last_mark_mid: float = 0.0
    liquidation_pending: bool = False
    liquidation_reason: str | None = None
    max_favorable_excursion_usd: float = 0.0
    max_adverse_excursion_usd: float = 0.0
    _max_bid_seen: float = -1.0
    _min_bid_seen: float = 1e18

    @property
    def num_entries(self) -> int:
        return len(self.entries)

    @property
    def avg_entry_price(self) -> float:
        total_in = sum(e.shares for e in self.entries)
        return self.committed_cost / total_in if total_in > 0 else 0.0

    def estimated_net_liquidation_pnl(self, bid_price: float, exec_params: ExecutionParams) -> float:
        """Net P&L of the entire basket if remaining `total_shares` are sold at `bid_price` now."""
        est_close_fee = compute_fill_fees("SELL", self.total_shares, bid_price, exec_params).total if self.total_shares > 0 else 0.0
        gross_out = self.exit_proceeds + self.total_shares * bid_price + self.dividends_received
        total_fees = self.opening_fees + self.exit_fees + est_close_fee
        return gross_out - self.committed_cost - total_fees

    def update_excursions(self, bid_price: float, exec_params: ExecutionParams) -> float:
        if bid_price > self._max_bid_seen or bid_price < self._min_bid_seen:
            net_pnl = self.estimated_net_liquidation_pnl(bid_price, exec_params)
            if bid_price > self._max_bid_seen:
                self._max_bid_seen = bid_price
            if bid_price < self._min_bid_seen:
                self._min_bid_seen = bid_price
            if net_pnl > self.max_favorable_excursion_usd:
                self.max_favorable_excursion_usd = net_pnl
            if net_pnl < self.max_adverse_excursion_usd:
                self.max_adverse_excursion_usd = net_pnl
            return net_pnl
        return 0.0


class PortfolioAccount:
    """Shared multi-stock simulated account with cash reservation, baskets, and full ledgers."""

    def __init__(
        self,
        account_params: AccountParams,
        strategy_params: StrategyParams,
        exec_params: ExecutionParams,
    ) -> None:
        self.acc = account_params
        self.strat = strategy_params
        self.exec = exec_params

        self.cash: float = float(account_params.start_equity)
        self.realized_pnl: float = 0.0
        self.total_fees_paid: float = 0.0
        self.day_start_equity: float = float(account_params.start_equity)
        self.daily_loss_halted: bool = False
        self.current_date: str | None = None

        self.baskets: dict[str, Basket] = {}
        self.pending_orders: list[PendingOrder] = []
        self._next_order_id: int = 1
        self._next_basket_id: int = 1

        # Complete audit ledgers
        self.signal_ledger: list[dict[str, Any]] = []
        self.rejected_ledger: list[dict[str, Any]] = []
        self.order_ledger: list[dict[str, Any]] = []
        self.fill_ledger: list[dict[str, Any]] = []
        self.basket_ledger: list[dict[str, Any]] = []
        self.daily_ledger: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ valuation
    def reserved_buy_cash(self) -> float:
        return sum(o.reserved_cash for o in self.pending_orders if o.side == "BUY")

    def available_cash(self) -> float:
        return max(0.0, self.cash - self.reserved_buy_cash())

    def gross_position_value(self, use_bid: bool = True) -> float:
        return sum(
            b.total_shares * (b.last_mark_bid if use_bid and b.last_mark_bid > 0 else b.last_mark_mid)
            for b in self.baskets.values()
            if b.total_shares > 0
        )

    def marked_equity(self, use_bid: bool = True) -> float:
        """Account Net Liquidation Equity (cash + marked value of open holdings)."""
        return self.cash + self.gross_position_value(use_bid=use_bid)

    def account_balance(self) -> float:
        """Account Balance (cash + remaining cost basis of open holdings, excluding floating unrealized P&L)."""
        return self.cash + sum(b.remaining_cost_basis for b in self.baskets.values() if b.total_shares > 0)

    def active_stock_count(self) -> int:
        held = {t for t, b in self.baskets.items() if b.total_shares > 0}
        pending_buy = {o.ticker for o in self.pending_orders if o.side == "BUY"}
        return len(held | pending_buy)

    def has_pending_order(self, ticker: str, side: str | None = None) -> bool:
        for o in self.pending_orders:
            if o.ticker == ticker and (side is None or o.side == side):
                return True
        return False

    # ------------------------------------------------------------------ lifecycle
    def start_trading_day(self, session_date: str) -> None:
        self.current_date = session_date
        self.day_start_equity = self.marked_equity(use_bid=True)
        self.daily_loss_halted = False

    def mark_symbol(self, ticker: str, bar: BarQuote) -> None:
        b = self.baskets.get(ticker)
        if b is None or bar.halted or bar.volume <= 0:
            return
        b.last_mark_bid = bar.close_bid
        b.last_mark_mid = bar.close
        if b.total_shares > 0:
            b.update_excursions(bar.close_bid, self.exec)

    # ------------------------------------------------------------------ risk monitoring
    def check_risk_triggers(self, session_date: str, minute_close: int) -> None:
        """Evaluate account daily loss stop and per-basket loss budget at every replay event."""
        equity_now = self.marked_equity(use_bid=True)
        daily_pnl = equity_now - self.day_start_equity
        if not self.daily_loss_halted and daily_pnl <= -self.acc.daily_loss_pct * self.day_start_equity - 1e-9:
            self.daily_loss_halted = True
            # Cancel all pending BUY entry orders and release reserved cash
            kept: list[PendingOrder] = []
            for o in self.pending_orders:
                if o.side == "BUY":
                    self.order_ledger.append({
                        "order_id": o.order_id, "ticker": o.ticker, "side": "BUY", "shares": o.shares,
                        "status": "cancelled", "reason": "daily_loss_stop_cancel",
                        "date": session_date, "minute": minute_close,
                    })
                else:
                    kept.append(o)
            self.pending_orders = kept
            # Request immediate liquidation of all open holdings
            for ticker, b in list(self.baskets.items()):
                if b.total_shares > 0 and not b.liquidation_pending:
                    self.request_liquidation(ticker, session_date, minute_close, "daily_loss_stop")
            return

        # Per-basket loss budget (-0.5% of frozen E0)
        for ticker, b in list(self.baskets.items()):
            if b.total_shares <= 0 or b.liquidation_pending:
                continue
            bid = b.last_mark_bid if b.last_mark_bid > 0 else b.last_mark_mid
            if bid <= 0:
                continue
            gross_est = b.exit_proceeds + b.total_shares * bid + b.dividends_received - b.committed_cost - b.opening_fees - b.exit_fees
            if gross_est > -self.acc.basket_loss_pct_e0 * b.frozen_e0 + 25.0:
                continue
            net_pnl = b.estimated_net_liquidation_pnl(bid, self.exec)
            if net_pnl <= -self.acc.basket_loss_pct_e0 * b.frozen_e0 - 1e-9:
                self.request_liquidation(ticker, session_date, minute_close, "basket_stop")

    # ------------------------------------------------------------------ exits & entries
    def check_normal_exit(
        self,
        ticker: str,
        session_date: str,
        minute_close: int,
        latest_upper: float | None,
        latest_middle: float | None,
    ) -> bool:
        b = self.baskets.get(ticker)
        if b is None or b.total_shares <= 0 or b.liquidation_pending:
            return False
        target_band = latest_middle if self.strat.exit_band == "middle" else latest_upper
        if target_band is None or b.last_mark_bid <= 0:
            return False
        if b.last_mark_bid + 1e-9 < target_band:
            return False
        net_pnl = b.estimated_net_liquidation_pnl(b.last_mark_bid, self.exec)
        if self.strat.require_profit_on_exit and net_pnl <= 0.0:
            return False
        self.request_liquidation(ticker, session_date, minute_close, f"normal_{self.strat.exit_band}_band")
        return True

    def request_liquidation(self, ticker: str, session_date: str, minute_close: int, reason: str) -> None:
        b = self.baskets.get(ticker)
        if b is None or b.total_shares <= 0 or b.liquidation_pending:
            return
        # Cancel any pending BUY for this ticker
        self.pending_orders = [o for o in self.pending_orders if not (o.ticker == ticker and o.side == "BUY")]
        b.liquidation_pending = True
        b.liquidation_reason = reason
        oid = self._next_order_id
        self._next_order_id += 1
        order = PendingOrder(
            order_id=oid,
            ticker=ticker,
            side="SELL",
            shares=b.total_shares,
            submitted_date=session_date,
            submitted_minute=minute_close,
            eligible_after_minute=minute_close + self.exec.latency_bars,
            reason=reason,
        )
        self.pending_orders.append(order)
        self.order_ledger.append({
            "order_id": oid, "ticker": ticker, "side": "SELL", "shares": b.total_shares,
            "status": "submitted", "reason": reason, "date": session_date, "minute": minute_close,
        })

    def evaluate_entry_signal(
        self,
        ticker: str,
        session_date: str,
        minute_close: int,
        signal_bar_index: int,
        ref_ask_price: float,
        trailing_avg_vol: float | None,
        universe_eligible: bool,
        priority_metric: float,
    ) -> bool:
        """Check all portfolio, spacing, cash, and exposure gates for a completed lower-band rejection signal."""
        self.signal_ledger.append({
            "date": session_date, "minute": minute_close, "ticker": ticker,
            "signal_bar_index": signal_bar_index, "ref_ask": round(ref_ask_price, 4),
            "priority_metric": round(priority_metric, 2),
        })
        b = self.baskets.get(ticker)
        is_addition = b is not None and b.total_shares > 0

        if not universe_eligible:
            self._reject(session_date, minute_close, ticker, signal_bar_index, "not_in_active_universe")
            return False
        if self.daily_loss_halted:
            self._reject(session_date, minute_close, ticker, signal_bar_index, "daily_loss_halted")
            return False
        if ref_ask_price <= 0:
            self._reject(session_date, minute_close, ticker, signal_bar_index, "invalid_quote")
            return False
        if self.has_pending_order(ticker):
            self._reject(session_date, minute_close, ticker, signal_bar_index, "order_already_pending")
            return False
        if b is not None and b.liquidation_pending:
            self._reject(session_date, minute_close, ticker, signal_bar_index, "liquidation_pending")
            return False

        if is_addition:
            assert b is not None
            if b.num_entries >= self.strat.max_entries:
                self._reject(session_date, minute_close, ticker, signal_bar_index, "max_entries_reached")
                return False
            if signal_bar_index - b.last_signal_bar_index < self.strat.spacing:
                self._reject(session_date, minute_close, ticker, signal_bar_index, "spacing_not_satisfied")
                return False
            e0 = b.frozen_e0
            entry_num = b.num_entries + 1
            remaining_basket_cap = max(0.0, self.acc.max_committed_pct_e0 * e0 - b.committed_cost)
        else:
            if self.active_stock_count() >= self.acc.max_simultaneous_stocks:
                self._reject(session_date, minute_close, ticker, signal_bar_index, "max_simultaneous_stocks")
                return False
            e0 = self.acc.start_equity if self.acc.fixed_dollar_sizing else self.marked_equity(use_bid=True)
            entry_num = 1
            remaining_basket_cap = self.acc.max_committed_pct_e0 * e0

        equity_now = self.acc.start_equity if self.acc.fixed_dollar_sizing else self.marked_equity(use_bid=True)
        current_committed_exposure = self.gross_position_value(use_bid=False) + self.reserved_buy_cash()
        remaining_gross_cap = max(0.0, self.acc.max_gross_exposure_pct * equity_now - current_committed_exposure)
        if remaining_gross_cap < ref_ask_price:
            self._reject(session_date, minute_close, ticker, signal_bar_index, "max_gross_exposure_cap")
            return False

        target_alloc = self.acc.entry_alloc_pct_e0 * e0 * (self.strat.multiplier ** (entry_num - 1))
        budget = min(target_alloc, remaining_basket_cap, remaining_gross_cap, self.available_cash())
        shares, reject_reason = max_shares_for_budget(budget, ref_ask_price, self.exec, trailing_avg_vol)
        if shares < 1:
            self._reject(session_date, minute_close, ticker, signal_bar_index, reject_reason or "insufficient_shares")
            return False

        est_fee = compute_fill_fees("BUY", shares, ref_ask_price, self.exec).total
        collar = (
            round(ref_ask_price * (1.0 + self.exec.ext_limit_collar_pct), 4)
            if not is_regular_hours(minute_close)
            else None
        )
        reserved = shares * (collar if collar is not None else ref_ask_price) + est_fee
        if reserved > self.available_cash() + 1e-9:
            shares, reject_reason = max_shares_for_budget(
                self.available_cash(), collar or ref_ask_price, self.exec, trailing_avg_vol
            )
            if shares < 1:
                self._reject(session_date, minute_close, ticker, signal_bar_index, "insufficient_cash_for_collar")
                return False
            est_fee = compute_fill_fees("BUY", shares, collar or ref_ask_price, self.exec).total
            reserved = shares * (collar or ref_ask_price) + est_fee

        oid = self._next_order_id
        self._next_order_id += 1
        order = PendingOrder(
            order_id=oid,
            ticker=ticker,
            side="BUY",
            shares=shares,
            submitted_date=session_date,
            submitted_minute=minute_close,
            eligible_after_minute=minute_close + self.exec.latency_bars,
            reason=f"entry_{entry_num}",
            signal_bar_index=signal_bar_index,
            reserved_cash=reserved,
            frozen_e0=e0,
            limit_collar_price=collar,
        )
        self.pending_orders.append(order)
        self.order_ledger.append({
            "order_id": oid, "ticker": ticker, "side": "BUY", "shares": shares,
            "status": "submitted", "reason": order.reason, "date": session_date, "minute": minute_close,
            "reserved_cash": round(reserved, 2), "collar": collar,
        })
        return True

    def _reject(self, session_date: str, minute_close: int, ticker: str, signal_bar_index: int, reason: str) -> None:
        self.rejected_ledger.append({
            "date": session_date, "minute": minute_close, "ticker": ticker,
            "signal_bar_index": signal_bar_index, "reason": reason,
        })

    # ------------------------------------------------------------------ order execution
    def process_pending_orders_for_bar(self, ticker: str, bar: BarQuote) -> None:
        """Attempt to fill pending orders for `ticker` that have reached their eligible execution bar."""
        if not self.pending_orders:
            return
        remaining_orders: list[PendingOrder] = []
        for o in self.pending_orders:
            if o.ticker != ticker:
                remaining_orders.append(o)
                continue
            # Must be strictly at or after eligible_after_minute on submitted_date, or on a later date
            if bar.session_date == o.submitted_date and bar.minute_close < o.eligible_after_minute:
                remaining_orders.append(o)
                continue

            if o.side == "BUY":
                res = execute_order_on_bar("BUY", o.shares, bar, self.exec, limit_collar_price=o.limit_collar_price)
                if res.filled_shares > 0:
                    cost = res.filled_shares * res.fill_price + res.fees.total
                    if cost <= self.cash + 1e-9:
                        self._apply_buy_fill(o, bar, res.filled_shares, res.fill_price, res.fees.total, res.status)
                    else:
                        self.order_ledger.append({
                            "order_id": o.order_id, "ticker": ticker, "side": "BUY", "shares": o.shares,
                            "status": "cancelled", "reason": "cash_exhausted_at_fill",
                            "date": bar.session_date, "minute": bar.minute_close,
                        })
                else:
                    self.order_ledger.append({
                        "order_id": o.order_id, "ticker": ticker, "side": "BUY", "shares": o.shares,
                        "status": "expired", "reason": res.reason or res.status,
                        "date": bar.session_date, "minute": bar.minute_close,
                    })
            else:
                b = self.baskets.get(ticker)
                if b is None or b.total_shares <= 0:
                    continue
                sell_qty = min(o.shares, b.total_shares)
                res = execute_order_on_bar("SELL", sell_qty, bar, self.exec)
                if res.filled_shares > 0:
                    self._apply_sell_fill(o, b, bar, res.filled_shares, res.fill_price, res.fees.total, res.status)
                if b.total_shares > 0:
                    o.shares = b.total_shares
                    remaining_orders.append(o)
        self.pending_orders = remaining_orders

    def _apply_buy_fill(
        self, o: PendingOrder, bar: BarQuote, shares: int, price: float, fee_total: float, status: str
    ) -> None:
        self.cash -= shares * price + fee_total
        self.total_fees_paid += fee_total
        b = self.baskets.get(o.ticker)
        if b is None or b.total_shares == 0:
            b = Basket(
                basket_id=self._next_basket_id,
                ticker=o.ticker,
                frozen_e0=o.frozen_e0,
                created_date=bar.session_date,
                created_minute=bar.minute_close,
                last_mark_bid=bar.close_bid,
                last_mark_mid=bar.close,
            )
            self._next_basket_id += 1
            self.baskets[o.ticker] = b

        leg = EntryLeg(
            entry_num=b.num_entries + 1,
            shares=shares,
            fill_price=price,
            fees=fee_total,
            signal_bar_index=o.signal_bar_index,
            signal_date=o.submitted_date,
            signal_minute=o.submitted_minute,
            fill_date=bar.session_date,
            fill_minute=bar.minute_close,
        )
        b.entries.append(leg)
        b.total_shares += shares
        b.initial_peak_shares = max(b.initial_peak_shares, b.total_shares)
        b.committed_cost += shares * price
        b.remaining_cost_basis += shares * price
        b.opening_fees += fee_total
        b.last_signal_bar_index = o.signal_bar_index
        b.last_mark_bid = bar.close_bid
        b.last_mark_mid = bar.close
        b._max_bid_seen = -1.0
        b._min_bid_seen = 1e18
        b.update_excursions(bar.close_bid, self.exec)

        self.fill_ledger.append({
            "order_id": o.order_id, "basket_id": b.basket_id, "ticker": o.ticker, "side": "BUY",
            "entry_num": leg.entry_num, "shares": shares, "price": round(price, 4),
            "fees": round(fee_total, 4), "status": status, "reason": o.reason,
            "date": bar.session_date, "minute": bar.minute_close,
        })

    def _apply_sell_fill(
        self, o: PendingOrder, b: Basket, bar: BarQuote, shares: int, price: float, fee_total: float, status: str
    ) -> None:
        proceeds = shares * price
        # Proportional cost basis closed by this partial or full fill
        frac = shares / b.total_shares if b.total_shares > 0 else 1.0
        cost_closed = b.remaining_cost_basis * frac
        b.remaining_cost_basis = max(0.0, b.remaining_cost_basis - cost_closed)
        b.total_shares -= shares
        b.exit_proceeds += proceeds
        b.exit_fees += fee_total
        self.cash += proceeds - fee_total
        self.total_fees_paid += fee_total

        self.fill_ledger.append({
            "order_id": o.order_id, "basket_id": b.basket_id, "ticker": o.ticker, "side": "SELL",
            "entry_num": b.num_entries, "shares": shares, "price": round(price, 4),
            "fees": round(fee_total, 4), "status": status, "reason": o.reason,
            "date": bar.session_date, "minute": bar.minute_close,
        })

        if b.total_shares == 0:
            b.remaining_cost_basis = 0.0
            b.liquidation_pending = False
            net_pnl = b.exit_proceeds + b.dividends_received - b.committed_cost - b.opening_fees - b.exit_fees
            # Opening fees were already subtracted from cash at entry; net realized P&L adds the basket's net result
            self.realized_pnl += net_pnl
            self.basket_ledger.append({
                "basket_id": b.basket_id,
                "ticker": b.ticker,
                "opened_date": b.created_date,
                "opened_minute": b.created_minute,
                "closed_date": bar.session_date,
                "closed_minute": bar.minute_close,
                "frozen_e0": round(b.frozen_e0, 2),
                "entries": b.num_entries,
                "peak_shares": b.initial_peak_shares,
                "avg_entry_price": round(b.avg_entry_price, 4),
                "last_exit_price": round(price, 4),
                "committed_cost": round(b.committed_cost, 2),
                "exit_proceeds": round(b.exit_proceeds, 2),
                "dividends": round(b.dividends_received, 2),
                "total_fees": round(b.opening_fees + b.exit_fees, 4),
                "net_pnl": round(net_pnl, 4),
                "return_on_e0_pct": round(100.0 * net_pnl / b.frozen_e0, 4) if b.frozen_e0 > 0 else 0.0,
                "mfe_usd": round(b.max_favorable_excursion_usd, 4),
                "mae_usd": round(b.max_adverse_excursion_usd, 4),
                "exit_reason": o.reason,
            })
            del self.baskets[o.ticker]

    # ------------------------------------------------------------------ corporate actions (overnight swing)
    def apply_overnight_split(self, ticker: str, split_from: float, split_to: float, session_date: str) -> None:
        """Adjust an open overnight basket when a stock split or reverse split executes on `session_date`."""
        b = self.baskets.get(ticker)
        if b is None or b.total_shares <= 0 or split_from <= 0 or split_to <= 0:
            return
        ratio = split_to / split_from  # e.g. 2-for-1: split_from=1, split_to=2 -> ratio=2.0
        exact_shares = b.total_shares * ratio
        whole_shares = int(exact_shares)
        frac_shares = exact_shares - whole_shares
        adj_mark = b.last_mark_mid / ratio if b.last_mark_mid > 0 else b.avg_entry_price / ratio
        b.last_mark_mid = adj_mark
        b.last_mark_bid = b.last_mark_bid / ratio if b.last_mark_bid > 0 else adj_mark
        if frac_shares > 1e-9:
            # Cash-in-lieu of fractional shares after a reverse split
            cil = frac_shares * adj_mark
            self.cash += cil
            b.exit_proceeds += cil
        b.total_shares = whole_shares
        if b.total_shares == 0:
            # Position completely cashed out by reverse split into < 1 share
            net_pnl = b.exit_proceeds + b.dividends_received - b.committed_cost - b.opening_fees - b.exit_fees
            self.realized_pnl += net_pnl
            self.basket_ledger.append({
                "basket_id": b.basket_id, "ticker": b.ticker, "opened_date": b.created_date,
                "opened_minute": b.created_minute, "closed_date": session_date, "closed_minute": 570,
                "frozen_e0": round(b.frozen_e0, 2), "entries": b.num_entries,
                "peak_shares": b.initial_peak_shares, "avg_entry_price": round(b.avg_entry_price, 4),
                "last_exit_price": round(adj_mark, 4), "committed_cost": round(b.committed_cost, 2),
                "exit_proceeds": round(b.exit_proceeds, 2), "dividends": round(b.dividends_received, 2),
                "total_fees": round(b.opening_fees + b.exit_fees, 4), "net_pnl": round(net_pnl, 4),
                "return_on_e0_pct": round(100.0 * net_pnl / b.frozen_e0, 4),
                "mfe_usd": round(b.max_favorable_excursion_usd, 4),
                "mae_usd": round(b.max_adverse_excursion_usd, 4), "exit_reason": "reverse_split_cash_in_lieu",
            })
            del self.baskets[ticker]

    def apply_overnight_dividend(self, ticker: str, cash_per_share: float, session_date: str) -> None:
        """Credit cash dividend on `ex_dividend_date` for shares held overnight into `session_date`."""
        b = self.baskets.get(ticker)
        if b is None or b.total_shares <= 0 or cash_per_share <= 0:
            return
        div_cash = b.total_shares * cash_per_share
        self.cash += div_cash
        b.dividends_received += div_cash

    def reconcile(self) -> dict[str, Any]:
        """Reconcile cash, open cost basis, partial exit proceeds, and realized P&L against starting equity."""
        open_cost_net = sum(
            b.committed_cost + b.opening_fees + b.exit_fees - b.exit_proceeds - b.dividends_received
            for b in self.baskets.values()
            if b.total_shares > 0
        )
        expected_cash = self.acc.start_equity + self.realized_pnl - open_cost_net
        diff = abs(self.cash - expected_cash)
        return {
            "ok": diff < 1e-5,
            "cash": round(self.cash, 6),
            "expected_cash": round(expected_cash, 6),
            "diff": round(diff, 9),
            "realized_pnl": round(self.realized_pnl, 6),
            "open_baskets": len(self.baskets),
            "marked_equity": round(self.marked_equity(use_bid=True), 6),
            "account_balance": round(self.account_balance(), 6),
        }
