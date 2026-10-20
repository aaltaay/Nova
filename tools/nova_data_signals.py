"""The signal tools of the nova-data MCP server (ADR 059): the Trader's Signals panel for every in-play stock-day since
2016, minute by minute, and a test of any mix of its signals -- read from the signal table
(``research/market_reads/signals_store.py``; built by ``research/signals/build_signals.py``).

Split from ``tools/nova_data_rvol.py`` along the tool-set seam: that file owns the relative-volume tools; this one
owns these four (``SignalTools`` bodies, ``register`` their MCP descriptions). Same contract: read-only on the data,
a table answer holds 200 rows inline, ``output_name`` writes a new file with every row.
"""
from __future__ import annotations

from typing import Any

PRELOAD = ("duckdb", "market_reads.signals", "market_reads.signal_outcomes", "market_reads.signal_registry",
           "market_reads.signals_store")


class SignalTools:
    """Tool bodies; the host class gives ``output_path``, ``answer`` and ``json_safe`` (``nova_data_mcp``)."""

    def signal_catalog(self) -> dict[str, Any]:
        from market_reads import signal_registry, signals_store
        return {"ok": True, "signals": signal_registry.catalog(), "not_rebuilt": signal_registry.NOT_REBUILT,
                "table": signals_store.status(), "rules": signals_store.RULES}

    def _rows(self, frame, out) -> dict[str, Any]:
        if out is not None:
            frame.to_parquet(out, index=False) if out.suffix == ".parquet" else frame.to_csv(out, index=False)
        answer = self.answer(frame)
        answer.update(rows=len(frame), truncated=len(frame) > len(answer["data"]), out=str(out) if out else None)
        return answer

    def signal_series(self, symbol: str, day: str, signals: list[str] | None = None,
                      output_name: str | None = None) -> dict[str, Any]:
        from market_reads import signals as reads
        out = self.output_path(output_name)
        return self._rows(reads.series(symbol, day, signals), out)

    def signal_scan(self, day: str, at: str, when: list[dict[str, Any]] | None = None,
                    output_name: str | None = None) -> dict[str, Any]:
        from market_reads import signals as reads
        out = self.output_path(output_name)
        return self._rows(reads.scan(day, at, when), out)

    def signal_test(self, when: list[dict[str, Any]], filters: dict[str, Any], window_from: str = "04:00",
                    window_to: str = "16:00", fresh: bool = False, up_pct: float = 20.0, down_pct: float = 20.0,
                    horizon: str = "close", days: int | None = None, group_by: str = "year", control: bool = True,
                    seed: int = 1, output_name: str | None = None) -> dict[str, Any]:
        from market_reads import signal_outcomes
        out = self.output_path(output_name)
        answer = signal_outcomes.test(when=when, filters=filters, window_from=window_from, window_to=window_to,
                                      fresh=fresh, up_pct=up_pct, down_pct=down_pct, horizon=horizon, days=days,
                                      group_by=group_by, control=control, seed=seed, to_file=out)
        return {"ok": True, **self.json_safe(answer), "out": str(out) if out else None}


def register(server, service, run, reads, writes_file) -> None:
    """The four tools on ``server`` (``run`` executes a body off the event loop)."""

    @server.tool(annotations=reads)
    async def signal_catalog() -> dict:
        """Every signal of the Trader's Signals panel the signal table holds, for signal_test / signal_scan: its
        name, group (in_play, setups, front, float, halts, tape), kind (state ok | warn | bad | info | unknown,
        label with its values, number, bool), the desk rule that writes it, and how far back it reaches (most from
        2016; boards, catalysts, halts, HOD Momo and the tape only partly). not_rebuilt names what has no history
        (borrow, HOD Momo's gate decisions, the Level 2 book walk). table: days built."""
        return await run(service.signal_catalog)

    @server.tool(annotations=writes_file)
    async def signal_series(symbol: str, day: str, signals: list[str] | None = None,
                            output_name: str | None = None) -> dict:
        """One in-play stock-day's signals minute by minute (time_et the minute's start; each value as of its end),
        from in_play_et (the first minute it was in play: a bar 10%+ over the prior close, or 5x its relative
        volume, with 50,000+ shares) through 15:59. signals: names from signal_catalog (default all). 200 rows
        inline; output_name writes every row."""
        return await run(service.signal_series, symbol, day, signals, output_name)

    @server.tool(annotations=writes_file)
    async def signal_scan(day: str, at: str, when: list[dict] | None = None, output_name: str | None = None) -> dict:
        """Every stock in play by at (ET HH:MM: the minute before it, as of its end) on day, with every signal --
        or only those meeting when (a list, all must hold: {"signal": "setup_first_pullback", "is": "triggered"},
        {"signal": "pillars_n", "min": 4}, {"signal": "front", "is": ["Front side", "Mixed"]}). Highest relative
        volume first."""
        return await run(service.signal_scan, day, at, when, output_name)

    @server.tool(annotations=writes_file)
    async def signal_test(when: list[dict], filters: dict, window_from: str = "04:00", window_to: str = "16:00",
                          fresh: bool = False, up_pct: float = 20.0, down_pct: float = 20.0, horizon: str = "close",
                          days: int | None = None, group_by: str = "year", control: bool = True, seed: int = 1,
                          output_name: str | None = None) -> dict:
        """Test a mix of the Trader's signals: the first minute in [window_from, window_to) ET each in-play
        stock-day met every condition of when (a list: {"signal", "is": value | [values]} or {"signal", "min"?,
        "max"?}; names and values from signal_catalog), entered at that minute's end at its price -- did a bar's
        high reach +up_pct% or a low -down_pct% first? fresh=true leaves out stock-days where it all held before the
        window. horizon close (before 16:00) | session (before 20:00) | days (days=1-20). filters: date_from,
        date_to (or symbol), price_min / price_max (prior close). Answers rvol_outcomes' shape: summary per
        group_by (year | hour | none) plus all -- entries, up, down, same_bar, same_day, neither, p_up, p_down,
        medians -- and a control (on by default): per entry one stock-day in play by the same minute of the same
        date where the mix had not held, scored the same way. meta.coverage names conditions on partly covered
        signals. output_name writes every scored entry."""
        return await run(service.signal_test, when, filters, window_from, window_to, fresh, up_pct, down_pct,
                         horizon, days, group_by, control, seed, output_name)
