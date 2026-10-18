"""The momentum-research tools of the nova-data MCP server (ADR 059): finding stock-days, daily bars and the market
around a day, one stock-day's stats, minute order flow, halts, catalysts and symbols.

Split from ``tools/nova_data_mcp.py`` along the tool-set seam: that file owns the server, the answer shape and the
first fourteen tools; this one owns these eight (``ResearchTools`` bodies, ``register`` their MCP descriptions).
Same contract: read-only on the data, a table answer holds 200 rows inline, ``output_name`` writes a new file.
"""
from __future__ import annotations

from typing import Any

PRELOAD = ("market_reads.stock_days", "market_reads.daily", "market_reads.stats", "market_reads.order_flow",
           "market_reads.halts", "market_reads.catalysts", "market_reads.symbols", "pyarrow.parquet",
           "day_movers.floats", "day_movers.store")


class ResearchTools:
    """Tool bodies; the host class gives ``output_path`` and ``answer`` (``nova_data_mcp.table_answer``)."""

    def find_stock_days(self, filters: dict[str, Any], symbol: str | None = None, kinds: list[str] | None = None,
                        splits: str = "exclude_likely", float_max: float | None = None,
                        float_basis: str = "sec_outstanding", float_unknown: str = "exclude",
                        catalyst: list[str] | None = None, halted: bool | None = None, cursor: str | None = None,
                        page_size: int = 200, output_name: str | None = None) -> dict[str, Any]:
        from market_reads import stock_days
        out = self.output_path(output_name)
        frame = stock_days.find_stock_days(filters=filters, symbol=symbol, kinds=kinds, splits=splits,
                                           float_max=float_max, float_basis=float_basis, float_unknown=float_unknown,
                                           catalyst=catalyst, halted=halted, cursor=cursor, page_size=page_size,
                                           to_file=out is not None)
        answer = self.answer(frame, out)
        answer["next_cursor"] = frame.attrs.get("next_cursor")
        return answer

    def daily_bars(self, symbol: str, date_from: str, date_to: str, adjust: bool = False,
                   as_of: str | None = None, output_name: str | None = None) -> dict[str, Any]:
        from market_reads import daily
        out = self.output_path(output_name)
        return self.answer(daily.daily_bars(symbol, date_from, date_to, adjust, as_of), out)

    def market_context(self, day: str, symbols: list[str] | None = None) -> dict[str, Any]:
        from market_reads import daily
        args = {"symbols": tuple(symbols)} if symbols else {}
        return {"ok": True, **self.json_safe(daily.market_context(day, **args))}

    def stock_day_stats(self, symbol: str, day: str, rvol_days: int = 20, spread: bool = True) -> dict[str, Any]:
        from market_reads import stats       # takes its own heavy-read slot
        return {"ok": True, **self.json_safe(stats.stock_day_stats(symbol, day, rvol_days, spread))}

    def order_flow(self, symbol: str, day: str, start: str | None = None, end: str | None = None,
                   bucket: str = "1m", output_name: str | None = None) -> dict[str, Any]:
        from market_reads import order_flow
        out = self.output_path(output_name)
        return self.answer(order_flow.order_flow(symbol, day, start, end, bucket), out)

    def halts(self, symbol: str | None = None, day: str | None = None, date_from: str | None = None,
              date_to: str | None = None, source: str | None = None) -> dict[str, Any]:
        from market_reads import halts
        return self.answer(halts.halts(symbol, day, date_from, date_to, source))

    def catalysts(self, symbol: str, date_from: str | None = None, date_to: str | None = None,
                  at: str | None = None, sources: list[str] | None = None, limit: int | None = None) -> dict:
        from market_reads import catalysts
        answer = self.answer(catalysts.items(symbol, date_from, date_to, at, sources, limit))
        verdicts = catalysts.verdicts(symbol=symbol, date_from=date_from, date_to=date_to)
        answer["verdicts"] = self.answer(verdicts)["data"]
        answer["verdicts_meta"] = self.json_safe(dict(verdicts.attrs))
        return answer

    def symbols(self, query: str | None = None, ticker: str | None = None, day: str | None = None,
                active: bool | None = None, types: list[str] | None = None, limit: int = 50) -> dict[str, Any]:
        from market_reads import symbols
        if ticker:
            return {"ok": True, **self.json_safe(symbols.symbol(ticker, day))}
        return self.answer(symbols.search(query, active=active, types=types, limit=limit))


def register(server, service, run, reads, writes_file) -> None:
    """The eight tools on ``server`` (``run`` executes a body off the event loop; heavy ones one at a time)."""

    @server.tool(annotations=writes_file)
    async def find_stock_days(filters: dict, symbol: str | None = None, kinds: list[str] | None = None,
                              splits: str = "exclude_likely", float_max: float | None = None,
                              float_basis: str = "sec_outstanding", float_unknown: str = "exclude",
                              catalyst: list[str] | None = None, halted: bool | None = None,
                              cursor: str | None = None, page_size: int = 200,
                              output_name: str | None = None) -> dict:
        """Momentum stock-days in one call: movers rows (filters as movers_scan: date_from/date_to, price_min/max on
        the raw prior close, high_min ... in percent points; needs dates or a symbol) joined with what was known that
        day -- outstanding_* (SEC shares OUTSTANDING filed by the day, as of <=120 days, split-adjusted; NOT free
        float), enrichment_float (the desk's own float, 2026-07-28 on), catalyst_* (the backfill's verdict; null =
        unknown), halts / first_halt_et / halt_codes, pm_high / pm_volume and up10_et..up300_et (first ET minute
        each +N% printed). float_max filters float_basis: sec_outstanding (default) | enrichment | best; float_source
        labels each value; float_unknown exclude | include | only. catalyst e.g. ["catalyst"] or ["unknown"];
        halted true/false. Likely splits left out (splits=include keeps). Pages of page_size (<=5,000; with
        output_name <=100,000): pass next_cursor back as cursor."""
        return await run(service.find_stock_days, filters, symbol, kinds, splits, float_max, float_basis,
                         float_unknown, catalyst, halted, cursor, page_size, output_name)

    @server.tool(annotations=writes_file)
    async def daily_bars(symbol: str, date_from: str, date_to: str, adjust: bool = False, as_of: str | None = None,
                         output_name: str | None = None) -> dict:
        """Daily bars for a date range from the Massive day files (2016-01-04 on): open/high/low/close/volume,
        prev_close, change_pct / gap_pct / range_pct in percent points. Raw unless adjust=true (split-adjusted to
        as_of, default today, by the splits of the company that held the ticker each day). Day volume is the whole
        04:00-20:00 session; prices are regular hours."""
        return await run(service.daily_bars, symbol, date_from, date_to, adjust, as_of, output_name)

    @server.tool(annotations=reads)
    async def market_context(day: str, symbols: list[str] | None = None) -> dict:
        """The market around a day (default SPY, QQQ, IWM): each one's day change, gap, range, 5- and 20-session
        returns and close vs its 20-day average, plus a one-line summary. Nothing after the day is read."""
        return await run(service.market_context, day, symbols)

    @server.tool(annotations=reads)
    async def stock_day_stats(symbol: str, day: str, rvol_days: int = 20, spread: bool = True) -> dict:
        """One stock-day's numbers, computed from the Massive files: premarket volume/high/low and their times,
        first 5 and 30 minutes, regular session OHLC and the time of the high/low, VWAP (method stated), trade count
        and average trade size, median NBBO spread (cents and bps; window stated), relative volume by minute vs the
        prior rvol_days sessions, and daily rvol. Raw prices; units and methods in the answer's rules."""
        return await run(service.stock_day_stats, symbol, day, rvol_days, spread)

    @server.tool(annotations=writes_file)
    async def order_flow(symbol: str, day: str, start: str | None = None, end: str | None = None,
                         bucket: str = "1m", output_name: str | None = None) -> dict:
        """Who traded, per minute (trades_flow_v1, built from every trade; 2016 on): vol, dvol, off-exchange (dark
        pool / wholesaler, exchange 4) off_pct, retail buys / sells by the sub-penny rule (a lower bound) with
        retail_imbalance -1..1, midpoint, sweeps (sweep_pct), odd lots, big prints ($25k+) and blocks ($200k+),
        shares by venue. start/end ET HH:MM; bucket 1m | 5m | 15m | 30m | 60m | day; meta.day_total sums the
        window. Definitions: docs/massive-builders.md."""
        return await run(service.order_flow, symbol, day, start, end, bucket, output_name)

    @server.tool(annotations=reads)
    async def halts(symbol: str | None = None, day: str | None = None, date_from: str | None = None,
                    date_to: str | None = None, source: str | None = None) -> dict:
        """Trading halts (LULD pauses, news pending, ...) by symbol and/or day from Nova's halt log: one row per halt
        with start/end ET, duration, code and source. Needs a symbol or a day / date range; meta says the coverage."""
        return await run(service.halts, symbol, day, date_from, date_to, source)

    @server.tool(annotations=reads)
    async def catalysts(symbol: str, date_from: str | None = None, date_to: str | None = None, at: str | None = None,
                        sources: list[str] | None = None, limit: int | None = None) -> dict:
        """News items naming a stock in a window (data), plus the catalyst backfill's verdicts for its days
        (verdicts). at = 'YYYY-MM-DD HH:MM' ET keeps only items published by then (no look-ahead). Coverage: Massive
        news is nearly empty before 2021-04 and verdicts exist only for days the backfill covered -- a missing one
        is unknown, never no news."""
        return await run(service.catalysts, symbol, date_from, date_to, at, sources, limit)

    @server.tool(annotations=reads)
    async def symbols(query: str | None = None, ticker: str | None = None, day: str | None = None,
                      active: bool | None = None, types: list[str] | None = None, limit: int = 50) -> dict:
        """Find a stock: query matches a ticker prefix or a company name; active true/false; types e.g. ["CS"].
        With ticker: everything about it -- every company that used it and when, which one held it on day, a
        reused-ticker warning, and the company's other tickers (CIK history). Massive's list, latest dump."""
        return await run(service.symbols, query, ticker, day, active, types, limit)
