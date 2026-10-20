"""The relative-volume tools of the nova-data MCP server (#1100, ADR 059): every stock-day's relative volume at a
clock time, the first minute it crossed a line, and what came next -- read from the relative-volume table
(``research/market_reads/rvol_store.py``; built by ``research/rvol/build_rvol.py``).

Split from ``tools/nova_data_research.py`` along the tool-set seam: that file owns the momentum-research tools; this
one owns these three (``RvolTools`` bodies, ``register`` their MCP descriptions). Same contract: read-only on the data,
a table answer holds 200 rows inline, ``output_name`` writes a new file with every row.
"""
from __future__ import annotations

from typing import Any

PRELOAD = ("duckdb", "market_reads.rvol", "market_reads.rvol_outcomes", "market_reads.rvol_store")


class RvolTools:
    """Tool bodies; the host class gives ``output_path``, ``answer`` and ``json_safe`` (``nova_data_mcp``)."""

    def _table(self, frame, out) -> dict[str, Any]:
        answer = self.answer(frame)
        rows = int(frame.attrs.get("rows", len(frame)))
        answer.update(rows=rows, truncated=rows > len(answer["data"]), out=str(out) if out else None)
        return answer

    def rvol_scan(self, at: str, filters: dict[str, Any], measure: str = "cumulative", kinds: list[str] | None = None,
                  splits: str = "exclude_likely", min_base_sessions: int = 20, sort: str | None = None,
                  limit: int | None = None, output_name: str | None = None) -> dict[str, Any]:
        from market_reads import rvol
        out = self.output_path(output_name)
        frame = rvol.scan(at, filters=filters, measure=measure, kinds=kinds, splits=splits,
                          min_base_sessions=min_base_sessions, sort=sort, limit=limit, to_file=out)
        return self._table(frame, out)

    def rvol_triggers(self, rvol_min: float, filters: dict[str, Any], measure: str = "cumulative",
                      window_from: str = "04:00", window_to: str = "16:00", kinds: list[str] | None = None,
                      splits: str = "exclude_likely", min_base_sessions: int = 20, fresh: bool = False,
                      limit: int | None = None, output_name: str | None = None) -> dict[str, Any]:
        from market_reads import rvol
        out = self.output_path(output_name)
        frame = rvol.triggers(rvol_min, measure=measure, window_from=window_from, window_to=window_to,
                              filters=filters, kinds=kinds, splits=splits, min_base_sessions=min_base_sessions,
                              fresh=fresh, limit=limit, to_file=out)
        return self._table(frame, out)

    def rvol_outcomes(self, filters: dict[str, Any], at: str | None = None, trigger: dict[str, Any] | None = None,
                      up_pct: float = 50.0, down_pct: float = 50.0, horizon: str = "close", days: int | None = None,
                      group_by: str | None = None, buckets: list[float] | None = None, measure: str = "cumulative",
                      kinds: list[str] | None = None, splits: str = "exclude_likely", min_base_sessions: int = 20,
                      control: bool = True, seed: int = 1, output_name: str | None = None) -> dict[str, Any]:
        from market_reads import rvol_outcomes
        out = self.output_path(output_name)
        answer = rvol_outcomes.outcomes(filters=filters, at=at, trigger=trigger, up_pct=up_pct, down_pct=down_pct,
                                        horizon=horizon, days=days, group_by=group_by, buckets=buckets,
                                        measure=measure, kinds=kinds, splits=splits,
                                        min_base_sessions=min_base_sessions, control=control, seed=seed, to_file=out)
        return {"ok": True, **self.json_safe(answer), "out": str(out) if out else None}


def register(server, service, run, reads, writes_file) -> None:
    """The three tools on ``server`` (``run`` executes a body off the event loop)."""

    @server.tool(annotations=writes_file)
    async def rvol_scan(at: str, filters: dict, measure: str = "cumulative", kinds: list[str] | None = None,
                        splits: str = "exclude_likely", min_base_sessions: int = 20, sort: str | None = None,
                        limit: int | None = None, output_name: str | None = None) -> dict:
        """Relative volume of every common stock on every day, as of one ET clock time (at HH:MM: bars starting
        before it), from the relative-volume table (2016 on). Each row: date, symbol, kind, prev_close, price /
        price_et (the last bar's close and start), change_pct, volume (since 04:00), base_volume, rvol, volume_5m,
        base_5m, rvol_5m, day_avg_volume, rvol_daily, base_sessions, day_avg_sessions, split. filters: date_from,
        date_to (or symbol), price_min / price_max (prior close, $), rvol_min / rvol_max (on measure), volume_min
        (shares by at), change_min / change_max (percent points). measure: cumulative (volume since 04:00 / the
        prior sessions' mean to the same minute) | five_minute (the last 5 minutes / the same 5 minutes before) |
        daily_rate (volume since 04:00 / the mean whole-session volume of up to 50 sessions: the Five Pillars' "5x
        the 50-day average"). kinds default
        ["CS", "ADRC"] (also "unknown"); likely reverse splits left out (splits=include keeps); a measure needs
        min_base_sessions prior sessions (default 20). Sorted by the measure, largest first; 200 rows inline, rows
        counts all; output_name (new .parquet/.csv) for every row."""
        return await run(service.rvol_scan, at, filters, measure, kinds, splits, min_base_sessions, sort, limit,
                         output_name)

    @server.tool(annotations=writes_file)
    async def rvol_triggers(rvol_min: float, filters: dict, measure: str = "cumulative", window_from: str = "04:00",
                            window_to: str = "16:00", kinds: list[str] | None = None, splits: str = "exclude_likely",
                            min_base_sessions: int = 20, fresh: bool = False, limit: int | None = None,
                            output_name: str | None = None) -> dict:
        """The first minute each stock-day's relative volume reached rvol_min (5 = five times its baseline) inside
        [window_from, window_to) ET, with every filter holding at that bar -- e.g. the 6-7 AM surge. Rows: date,
        symbol, kind, prev_close, trigger_et (the bar's start), entry_et (its end: the first moment it is known),
        price (its close), change_pct, volume, base_volume, rvol, volume_5m, base_5m, rvol_5m, day_avg_volume,
        rvol_daily, above_before (already over the line before the window opened, so the window's first bar
        triggered; fresh=true leaves those out), base_sessions, split. filters: date_from, date_to (or symbol), price_min / price_max (prior
        close), volume_min (shares since 04:00 at the bar), change_min / change_max (percent points at the bar).
        measure: cumulative (volume since 04:00 / the prior sessions' mean to the same minute) | five_minute (the
        last 5 minutes / the same 5 minutes before) | daily_rate (volume since 04:00 / the mean whole-session volume
        of up to 50 sessions). Oldest day first; 200 inline, rows counts all."""
        return await run(service.rvol_triggers, rvol_min, filters, measure, window_from, window_to, kinds, splits,
                         min_base_sessions, fresh, limit, output_name)

    @server.tool(annotations=writes_file)
    async def rvol_outcomes(filters: dict, at: str | None = None, trigger: dict | None = None, up_pct: float = 50.0,
                            down_pct: float = 50.0, horizon: str = "close", days: int | None = None,
                            group_by: str | None = None, buckets: list[float] | None = None,
                            measure: str = "cumulative", kinds: list[str] | None = None,
                            splits: str = "exclude_likely", min_base_sessions: int = 20, control: bool = True,
                            seed: int = 1, output_name: str | None = None) -> dict:
        """What came next: from every stock-day at clock time at (rvol_scan's rows) or from the first minute it
        crossed a line (trigger = {"rvol_min": 10, "measure"?, "window_from"?, "window_to"?, "fresh"?}; filters as
        rvol_triggers), did a bar's high reach +up_pct% or a low reach -down_pct% of the entry price first? The entry
        price is the close of the last bar before the entry clock; only later bars are read. horizon: close (before
        16:00) | session (before 20:00) | days (days=1-20: then the next sessions' high / low on the entry's share
        basis). Outcomes up | down | same_bar (both in one minute: order unknown, never guessed) | same_day | neither.
        summary per group_by (rvol buckets on measure -- buckets edges, default 0,1,2,3,5,10,20,50,100,1000 -- or
        year | hour | none) plus all: entries, counts, p_up, p_down, p_up_resolved, median max up / down %, median
        and mean end %, median minutes to each line. Trigger entries get a control (on by default): one stock-day
        per trigger from the same date and universe that had not crossed the line by then, scored from the same
        clock. meta.left_out counts what was dropped. output_name writes every scored entry."""
        return await run(service.rvol_outcomes, filters, at, trigger, up_pct, down_pct, horizon, days, group_by,
                         buckets, measure, kinds, splits, min_base_sessions, control, seed, output_name)
