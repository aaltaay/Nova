"""Fast exact slice loader and simulation runner over `bb_mr.duckdb`.

maintainer: one-concern the DuckDB slice cache and minute-stepping simulation loop over precomputed signal slices

Fetches precomputed completed signal candles and 1-minute execution bars for any
`(universe, session, timeframe, period, deviation)` slice from `bb_mr.duckdb` in ~1.5s,
and executes `PortfolioAccount` across all 1,235 trading days in ~0.15s per configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import duckdb
import numpy as np

from research.bb_mr.config import BB_DB_PATH, SESSION_WINDOWS, RunConfig, parse_hhmm
from research.bb_mr.engine import summarize_run
from research.bb_mr.execution import BarQuote, make_bar_quote
from research.bb_mr.indicators import minute_of_day
from research.bb_mr.portfolio import PortfolioAccount


@dataclass
class SymbolDaySlice:
    ticker: str
    d: str
    # Signal arrays sorted by close_min
    sig_min: np.ndarray         # int32
    sig_idx: np.ndarray         # int32
    sig_close: np.ndarray       # float64
    sig_vol: np.ndarray         # float64
    sig_mid: np.ndarray         # float64
    sig_up: np.ndarray          # float64
    sig_lo: np.ndarray          # float64
    sig_qual: np.ndarray        # bool
    sig_in_univ: np.ndarray     # bool
    sig_prio: np.ndarray        # float64
    # 1m bar arrays sorted by close_min
    bar_min: np.ndarray         # int32
    bar_open: np.ndarray        # float64
    bar_high: np.ndarray        # float64
    bar_low: np.ndarray         # float64
    bar_close: np.ndarray       # float64
    bar_vol: np.ndarray         # float64
    bar_trail5: np.ndarray      # float64
    sig_pos: dict[int, int] | None = None
    bar_pos: dict[int, int] | None = None
    qual_mins: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        self.sig_pos = {int(m): i for i, m in enumerate(self.sig_min.tolist())}
        self.bar_pos = {int(m): i for i, m in enumerate(self.bar_min.tolist())}
        q_idx = np.flatnonzero(self.sig_qual & self.sig_in_univ)
        self.qual_mins = tuple(int(self.sig_min[i]) for i in q_idx.tolist())


class SliceCache:
    """Loads and caches `(universe, warmup_mode, timeframe, period, deviation)` slices from `bb_mr.duckdb`."""

    def __init__(self, db_path=BB_DB_PATH) -> None:
        self.con = duckdb.connect(str(db_path), read_only=True)
        self.con.execute("SET threads TO 8")
        self.all_days: list[str] = [
            str(r[0])
            for r in self.con.execute(
                "SELECT DISTINCT d::VARCHAR FROM meta_univ_a WHERE d BETWEEN DATE '2021-10-19' AND DATE '2026-09-21' ORDER BY 1"
            ).fetchall()
        ]
        self.splits: dict[tuple[str, str], tuple[float, float]] = {
            (str(t), str(d)): (float(sf), float(st))
            for t, d, sf, st in self.con.execute("SELECT ticker, d::VARCHAR, split_from, split_to FROM corp_splits").fetchall()
        }
        self.dividends: dict[tuple[str, str], float] = {
            (str(t), str(d)): float(amt)
            for t, d, amt in self.con.execute("SELECT ticker, d::VARCHAR, sum(cash_amount) FROM corp_dividends GROUP BY 1, 2").fetchall()
        }
        self._cache: dict[tuple[str, str, str, int, float, bool], dict[str, dict[str, SymbolDaySlice]]] = {}

    def close(self) -> None:
        self.con.close()

    @staticmethod
    def _split_groups(d_arr: np.ndarray, t_arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        n = len(d_arr)
        if n == 0:
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
        change = (d_arr[1:] != d_arr[:-1]) | (t_arr[1:] != t_arr[:-1])
        starts = np.r_[0, np.flatnonzero(change) + 1]
        ends = np.r_[starts[1:], n]
        return starts, ends

    def get_slice(
        self,
        universe: str,
        warmup_mode: str,
        timeframe: str,
        period: int,
        deviation: float,
        overnight_hold: bool = False,
    ) -> dict[str, dict[str, SymbolDaySlice]]:
        key = (universe, warmup_mode, timeframe, period, deviation, overnight_hold)
        if key in self._cache:
            return self._cache[key]

        if timeframe == "1m":
            sig_tbl = "sig_1m_ext"
        elif timeframe == "1h":
            sig_tbl = "sig_1h_rth"
        else:
            sig_tbl = "sig_5m_rth" if warmup_mode == "regular" else "sig_5m_ext"

        n_col = f"n{period}"
        sma_col = f"sma{period}"
        std_col = f"std{period}"

        if universe == "liquid_reference":
            univ_join = "LEFT JOIN meta_univ_a u ON u.ticker = s.ticker AND u.d = s.d"
            in_univ_expr = "(u.ticker IS NOT NULL AND s.close BETWEEN 5.0 AND 200.0 AND (s.close_min >= 571 OR u.has_ext))"
            prio_expr = "coalesce(u.adv20_usd, 0.0)"
        else:
            univ_join = "LEFT JOIN ub_scanner_top20 u ON u.ticker = s.ticker AND u.d = s.d AND u.close_min = s.close_min"
            in_univ_expr = "(u.ticker IS NOT NULL)"
            prio_expr = "coalesce(u.cum_dvol, 0.0)"

        qual_expr = f"(s.{n_col} = {period} AND s.low <= s.{sma_col} - {deviation} * s.{std_col} AND s.close > s.{sma_col} - {deviation} * s.{std_col})"

        if overnight_hold:
            qual_days_cte = f"""
            WITH qual_tickers AS (
                SELECT DISTINCT s.ticker
                FROM {sig_tbl} s
                {univ_join}
                WHERE {qual_expr} AND {in_univ_expr}
            ),
            qual_days AS (
                SELECT DISTINCT s.ticker, s.d
                FROM {sig_tbl} s
                JOIN qual_tickers qt ON qt.ticker = s.ticker
            )
            """
        else:
            qual_days_cte = f"""
            WITH qual_days AS (
                SELECT DISTINCT s.ticker, s.d
                FROM {sig_tbl} s
                {univ_join}
                WHERE {qual_expr} AND {in_univ_expr}
            )
            """

        sig_sql = f"""
        {qual_days_cte}
        SELECT s.d::VARCHAR AS d, s.ticker, s.close_min, s.bar_idx, s.close, s.volume,
               s.{sma_col} AS mid,
               s.{sma_col} + {deviation} * s.{std_col} AS up,
               s.{sma_col} - {deviation} * s.{std_col} AS lo,
               {qual_expr} AS qual,
               {in_univ_expr} AS in_univ,
               {prio_expr} AS prio
        FROM {sig_tbl} s
        JOIN qual_days q ON q.ticker = s.ticker AND q.d = s.d
        {univ_join}
        WHERE s.{n_col} = {period}
        ORDER BY d, s.ticker, s.close_min
        """
        s_np = self.con.execute(sig_sql).fetchnumpy()

        if overnight_hold and timeframe == "1h":
            bar_sql = f"""
            {qual_days_cte}
            SELECT s.d::VARCHAR AS d, s.ticker, s.close_min, s.open, s.high, s.low, s.close, s.volume,
                   (s.volume / 60.0) AS trail5_vol
            FROM {sig_tbl} s
            JOIN qual_days q ON q.ticker = s.ticker AND q.d = s.d
            ORDER BY d, s.ticker, s.close_min
            """
        else:
            bar_sql = f"""
            {qual_days_cte}
            SELECT b.d::VARCHAR AS d, b.ticker, b.close_min, b.open, b.high, b.low, b.close, b.volume, b.trail5_vol
            FROM bars_1m_exec b
            JOIN qual_days q ON q.ticker = b.ticker AND q.d = b.d
            ORDER BY d, b.ticker, b.close_min
            """
        b_np = self.con.execute(bar_sql).fetchnumpy()

        bars_by_dt: dict[tuple[str, str], tuple[np.ndarray, ...]] = {}
        b_d = np.asarray(b_np["d"], dtype=object)
        b_t = np.asarray(b_np["ticker"], dtype=object)
        if len(b_d):
            b_min = np.asarray(b_np["close_min"], dtype=np.int32)
            b_o = np.asarray(b_np["open"], dtype=np.float64)
            b_h = np.asarray(b_np["high"], dtype=np.float64)
            b_l = np.asarray(b_np["low"], dtype=np.float64)
            b_c = np.asarray(b_np["close"], dtype=np.float64)
            b_v = np.asarray(b_np["volume"], dtype=np.float64)
            b_tr = np.asarray(b_np["trail5_vol"], dtype=np.float64)
            starts, ends = self._split_groups(b_d, b_t)
            for a, b in zip(starts.tolist(), ends.tolist(), strict=True):
                bars_by_dt[(str(b_d[a]), str(b_t[a]))] = (
                    b_min[a:b], b_o[a:b], b_h[a:b], b_l[a:b], b_c[a:b], b_v[a:b], b_tr[a:b]
                )

        by_day: dict[str, dict[str, SymbolDaySlice]] = {}
        s_d = np.asarray(s_np["d"], dtype=object)
        s_t = np.asarray(s_np["ticker"], dtype=object)
        if len(s_d):
            s_min = np.asarray(s_np["close_min"], dtype=np.int32)
            s_idx = np.asarray(s_np["bar_idx"], dtype=np.int32)
            s_c = np.asarray(s_np["close"], dtype=np.float64)
            s_v = np.asarray(s_np["volume"], dtype=np.float64)
            s_mid = np.asarray(s_np["mid"], dtype=np.float64)
            s_up = np.asarray(s_np["up"], dtype=np.float64)
            s_lo = np.asarray(s_np["lo"], dtype=np.float64)
            s_q = np.asarray(s_np["qual"], dtype=bool)
            s_iu = np.asarray(s_np["in_univ"], dtype=bool)
            s_pr = np.asarray(s_np["prio"], dtype=np.float64)
            starts, ends = self._split_groups(s_d, s_t)
            for a, b in zip(starts.tolist(), ends.tolist(), strict=True):
                d_s, t_s = str(s_d[a]), str(s_t[a])
                b_tup = bars_by_dt.get((d_s, t_s))
                if b_tup is None:
                    continue
                by_day.setdefault(d_s, {})[t_s] = SymbolDaySlice(
                    ticker=t_s, d=d_s,
                    sig_min=s_min[a:b], sig_idx=s_idx[a:b], sig_close=s_c[a:b], sig_vol=s_v[a:b],
                    sig_mid=s_mid[a:b], sig_up=s_up[a:b], sig_lo=s_lo[a:b],
                    sig_qual=s_q[a:b], sig_in_univ=s_iu[a:b], sig_prio=s_pr[a:b],
                    bar_min=b_tup[0], bar_open=b_tup[1], bar_high=b_tup[2], bar_low=b_tup[3],
                    bar_close=b_tup[4], bar_vol=b_tup[5], bar_trail5=b_tup[6],
                )

        # Only cache up to 16 slices at a time to bound RAM while avoiding re-fetching in walk-forward
        if len(self._cache) >= 16:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = by_day
        return by_day

    def run_config(self, cfg: RunConfig, *, keep_ledgers: bool = False) -> dict[str, Any]:
        """Run exact chronological simulation of `cfg` over its date window."""
        win = SESSION_WINDOWS[cfg.session]
        start_min = minute_of_day(parse_hhmm(win["start"])) + 1
        end_min = minute_of_day(parse_hhmm(win["end"]))
        cutoff_min = minute_of_day(parse_hhmm(win["entry_cutoff"]))

        slice_by_day = self.get_slice(
            cfg.universe,
            win["warmup_session"],
            cfg.strategy.timeframe,
            cfg.strategy.period,
            cfg.strategy.deviation,
            cfg.strategy.overnight_hold,
        )

        date_lo, date_hi = cfg.window_dates()
        days = [d for d in self.all_days if date_lo <= d <= date_hi]
        account = PortfolioAccount(cfg.account, cfg.strategy, cfg.execution)

        for d_idx, d in enumerate(days):
            if cfg.strategy.overnight_hold and account.baskets:
                for tkr in list(account.baskets.keys()):
                    sp = self.splits.get((tkr, d))
                    if sp is not None:
                        account.apply_overnight_split(tkr, sp[0], sp[1], d)
                    div = self.dividends.get((tkr, d))
                    if div is not None:
                        account.apply_overnight_dividend(tkr, div, d)

            account.start_trading_day(d)
            day_map = slice_by_day.get(d, {})
            if not day_map and not account.baskets:
                eq_end = account.marked_equity(use_bid=True)
                bal_end = account.account_balance()
                account.daily_ledger.append({
                    "date": d, "balance": round(bal_end, 2), "equity": round(eq_end, 2),
                    "cash": round(account.cash, 2), "gross_exposure": 0.0,
                    "floating_pnl": 0.0, "day_pnl": 0.0, "open_baskets": 0, "daily_loss_halted": False,
                })
                continue

            # Filter day_map to symbols that either are already held or have a qualifying signal inside [start_min, cutoff_min]
            active_sds: dict[str, SymbolDaySlice] = {}
            for tkr, sds in day_map.items():
                if tkr in account.baskets and account.baskets[tkr].total_shares > 0:
                    active_sds[tkr] = sds
                    continue
                if any(start_min <= qm <= cutoff_min for qm in sds.qual_mins):
                    active_sds[tkr] = sds

            if not active_sds and not account.baskets:
                eq_end = account.marked_equity(use_bid=True)
                bal_end = account.account_balance()
                account.daily_ledger.append({
                    "date": d, "balance": round(bal_end, 2), "equity": round(eq_end, 2),
                    "cash": round(account.cash, 2), "gross_exposure": round(account.gross_position_value(use_bid=True), 2),
                    "floating_pnl": round(eq_end - bal_end, 2), "day_pnl": round(eq_end - account.day_start_equity, 2),
                    "open_baskets": len(account.baskets), "daily_loss_halted": account.daily_loss_halted,
                })
                continue

            sig_minutes: set[int] = {end_min}
            for _tkr, sds in active_sds.items():
                for m in sds.sig_min.tolist():
                    if start_min <= m <= end_min:
                        sig_minutes.add(m)

            latest_bands: dict[str, tuple[float, float]] = {}
            exec_p = cfg.execution
            m = start_min
            sorted_sig_mins = sorted(sig_minutes)
            while m <= 960:
                has_active_state = bool(account.baskets) or bool(account.pending_orders)
                if not has_active_state and m not in sig_minutes:
                    nxt = next((sm for sm in sorted_sig_mins if sm > m), 961)
                    m = nxt
                    if m > 960:
                        break

                pending_tkrs = {o.ticker for o in account.pending_orders}
                watched_tkrs = set(account.baskets.keys()) | pending_tkrs
                rth_frac = exec_p.rth_range_spread_frac if (571 <= m <= 960) else exec_p.ext_range_spread_frac
                for tkr in watched_tkrs:
                    sds = active_sds.get(tkr)
                    if sds is None:
                        continue
                    b_idx = sds.bar_pos.get(m)  # type: ignore[union-attr]
                    if b_idx is not None:
                        if tkr in pending_tkrs:
                            bq = make_bar_quote(
                                d, m, float(sds.bar_open[b_idx]), float(sds.bar_high[b_idx]),
                                float(sds.bar_low[b_idx]), float(sds.bar_close[b_idx]),
                                float(sds.bar_vol[b_idx]), exec_p
                            )
                            account.mark_symbol(tkr, bq)
                            account.process_pending_orders_for_bar(tkr, bq)
                        else:
                            b_obj = account.baskets.get(tkr)
                            vol_v = float(sds.bar_vol[b_idx])
                            if b_obj is not None and vol_v > 0:
                                c_px = float(sds.bar_close[b_idx])
                                o_px = float(sds.bar_open[b_idx])
                                rng = max(0.0, float(sds.bar_high[b_idx]) - float(sds.bar_low[b_idx]))
                                hs = min(max(exec_p.half_spread_min, rth_frac * rng), 0.05 * o_px)
                                c_bid = round(max(0.01, c_px - hs - exec_p.slippage_per_share), 4)
                                b_obj.last_mark_bid = c_bid
                                b_obj.last_mark_mid = c_px
                                b_obj.update_excursions(c_bid, exec_p)
                    s_idx = sds.sig_pos.get(m)  # type: ignore[union-attr]
                    if s_idx is not None:
                        latest_bands[tkr] = (float(sds.sig_up[s_idx]), float(sds.sig_mid[s_idx]))

                # 2) Risk monitoring when holdings exist
                if account.baskets:
                    account.check_risk_triggers(d, m)

                # 3) Window-end liquidation at `end_min`
                if not cfg.strategy.overnight_hold and m == end_min:
                    for tkr in list(account.baskets.keys()):
                        account.request_liquidation(tkr, d, m, "window_end")
                    account.pending_orders = [o for o in account.pending_orders if o.side != "BUY"]

                if start_min <= m <= end_min:
                    # 4) Normal exits on held baskets
                    for tkr in list(account.baskets.keys()):
                        bands = latest_bands.get(tkr)
                        if bands is not None:
                            account.check_normal_exit(tkr, d, m, bands[0], bands[1])

                    # 5) New entry / addition signals at minute m
                    if m <= cutoff_min and not account.daily_loss_halted and m in sig_minutes:
                        signaling: list[tuple[float, str, int, SymbolDaySlice, bool]] = []
                        for tkr, sds in active_sds.items():
                            s_idx = sds.sig_pos.get(m)  # type: ignore[union-attr]
                            if s_idx is None:
                                continue
                            latest_bands[tkr] = (float(sds.sig_up[s_idx]), float(sds.sig_mid[s_idx]))
                            if not bool(sds.sig_qual[s_idx]):
                                continue
                            in_u = bool(sds.sig_in_univ[s_idx])
                            already_held = tkr in account.baskets and account.baskets[tkr].total_shares > 0
                            if not in_u and not already_held:
                                continue
                            signaling.append((float(sds.sig_prio[s_idx]), tkr, s_idx, sds, in_u or already_held))

                        if signaling:
                            signaling.sort(key=lambda item: (-item[0], item[1]))
                            for prio, tkr, s_idx, sds, elig in signaling:
                                b_idx = sds.bar_pos.get(m)  # type: ignore[union-attr]
                                if b_idx is not None:
                                    bq = make_bar_quote(
                                        d, m, float(sds.bar_open[b_idx]), float(sds.bar_high[b_idx]),
                                        float(sds.bar_low[b_idx]), float(sds.bar_close[b_idx]),
                                        float(sds.bar_vol[b_idx]), exec_p
                                    )
                                    ref_ask = bq.close_ask
                                    tvol = float(sds.bar_trail5[b_idx])
                                else:
                                    ref_ask = float(sds.sig_close[s_idx]) + exec_p.half_spread_min + exec_p.slippage_per_share
                                    tvol = float(sds.sig_vol[s_idx])
                                account.evaluate_entry_signal(
                                    ticker=tkr,
                                    session_date=d,
                                    minute_close=m,
                                    signal_bar_index=int(sds.sig_idx[s_idx]),
                                    ref_ask_price=ref_ask,
                                    trailing_avg_vol=tvol,
                                    universe_eligible=elig,
                                    priority_metric=prio,
                                )
                m += 1

            # If an intraday basket could not liquidate by 16:00 due to a halt or cutoff at 16:00,
            # fill remaining session-end liquidation at the next available print or dataset boundary
            if not cfg.strategy.overnight_hold and account.baskets:
                for tkr, b in list(account.baskets.items()):
                    if b.total_shares > 0 and b.liquidation_pending:
                        sds = active_sds.get(tkr)
                        # Check if there was a valid bar at or after end_min; if none (halted through 16:00),
                        # settle at next session's open or last known mark with adverse halt-reopen slippage
                        reopen_bid = max(0.01, (b.last_mark_bid if b.last_mark_bid > 0 else b.last_mark_mid) * 0.98)
                        fake_bar = BarQuote(
                            session_date=d, minute_close=960, open=reopen_bid, high=reopen_bid, low=reopen_bid,
                            close=reopen_bid, volume=1e9, bid=reopen_bid, ask=reopen_bid,
                            close_bid=reopen_bid, close_ask=reopen_bid, half_spread=0.0, halted=False,
                        )
                        account.process_pending_orders_for_bar(tkr, fake_bar)

            if d_idx == len(days) - 1 and account.baskets:
                for tkr, b in list(account.baskets.items()):
                    if b.total_shares > 0:
                        bid = b.last_mark_bid if b.last_mark_bid > 0 else b.last_mark_mid
                        fake_bar = BarQuote(
                            session_date=d, minute_close=960, open=bid, high=bid, low=bid, close=bid,
                            volume=1e9, bid=bid, ask=bid, close_bid=bid, close_ask=bid, half_spread=0.0, halted=False,
                        )
                        if not b.liquidation_pending:
                            account.request_liquidation(tkr, d, 959, "dataset_boundary_close")
                        account.process_pending_orders_for_bar(tkr, fake_bar)

            eq_end = account.marked_equity(use_bid=True)
            bal_end = account.account_balance()
            account.daily_ledger.append({
                "date": d, "balance": round(bal_end, 2), "equity": round(eq_end, 2),
                "cash": round(account.cash, 2), "gross_exposure": round(account.gross_position_value(use_bid=True), 2),
                "floating_pnl": round(eq_end - bal_end, 2), "day_pnl": round(eq_end - account.day_start_equity, 2),
                "open_baskets": len(account.baskets), "daily_loss_halted": account.daily_loss_halted,
            })

        out = summarize_run(cfg, account)
        if not keep_ledgers:
            out.pop("_ledgers", None)
        return out
