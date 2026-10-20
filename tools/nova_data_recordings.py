"""The recorded-session tools of the nova-data MCP server (ADR 059, #1064): Nova's own IBKR recordings -- Level 2 at a
moment and the prints in a window -- read through ``research/market_reads/recordings.py``.

The third tool set, split from ``tools/nova_data_mcp.py`` along the same seam as ``nova_data_research.py`` (the host
class gives ``output_path`` / ``answer`` / ``json_safe``). Read-only on the stores, which are the live desk's: a read
never writes, creates a store or waits on a writer, and takes one heavy-read slot (so a call here is a heavy tool of
the server, one at a time per process). Shapes: ``architecture/schema/agent-desk.md``.
"""
from __future__ import annotations

from typing import Any

PRELOAD = ("market_reads.recordings",)


class RecordingTools:
    """Tool bodies; the host class gives ``output_path``, ``answer`` and ``json_safe``."""

    def recorded_depth(self, symbol: str, day: str, at: str, source: str = "auto",
                       max_age_sec: float = 60.0) -> dict[str, Any]:
        from market_reads import recordings
        return {"ok": True, **self.json_safe(recordings.depth(symbol, day, at, source, max_age_sec))}

    def recorded_tape(self, symbol: str, day: str, start: str | None = None, end: str | None = None,
                      source: str = "auto", limit: int = 200_000, output_name: str | None = None) -> dict[str, Any]:
        from market_reads import recordings
        out = self.output_path(output_name)
        return self.answer(recordings.tape(symbol, day, start, end, source, limit), out)


def register(server, service, run, reads, writes_file) -> None:
    """The two tools on ``server`` (``run`` executes a body off the event loop; heavy ones one at a time)."""

    @server.tool(annotations=reads)
    async def recorded_depth(symbol: str, day: str, at: str, source: str = "auto", max_age_sec: float = 60.0) -> dict:
        """Nova's own recorded Level 2 book (what the desk's IBKR depth line showed) for a symbol at ET `at`
        (HH:MM or HH:MM:SS) on `day`: the newest book at or before that moment, never after, no older than
        max_age_sec (default 60, up to 3600), best price first with size per level, best_bid / best_ask / spread /
        mid. source: auto (the newer of the two stores) | capture (a Session Record: only symbols the operator or
        auto-record recorded, 2026-09-19 on, never read across a gap in the recording) | l2_db (the desk's depth
        samples). `tried` shows each store's answer; `coverage` states what each recording holds and lost (recorded
        stretches, gaps and why, books IBKR sent that the recording did not keep, sampling sessions). covered=false
        with a reason and recorded_days when nothing was recorded then: not "the book was empty". Times are ET on
        Nova's receive clock. Massive has no Level 2; this is Nova's own recording."""
        return await run(service.recorded_depth, symbol, day, at, source, max_age_sec)

    @server.tool(annotations=writes_file)
    async def recorded_tape(symbol: str, day: str, start: str | None = None, end: str | None = None,
                            source: str = "auto", limit: int = 200_000, output_name: str | None = None) -> dict:
        """Nova's own recorded Time & Sales prints for a symbol on `day`, ET start (inclusive) to end (exclusive),
        default the whole ET day, oldest first: time_et, ts (epoch seconds when Nova RECEIVED the print), receive_ts,
        exchange_ts (IBKR's own whole second, Session Records only), price, size, exchange, conditions, unreported,
        sets_price (may the print move a candle), side (ask | bid | between | unknown) / bid / ask (the desk's own
        judgement against the book it held at receipt; unknown when no usable book, never inferred), source. source: auto (a Session Record when one exists,
        else the archive) | capture | archive (every print the desk's tape line saw, 2026-07-15 on, any symbol).
        meta.coverage says what the recording holds and lost (a Session Record: stretches, gaps, tape losses; the
        archive: first / last print and that it marks no gap of its own); a Session Record's gaps may hold prints the
        archive has. limit up to 1,000,000 rows (meta.capped); inline answers hold 200, output_name (new
        .parquet/.csv) for all."""
        return await run(service.recorded_tape, symbol, day, start, end, source, limit, output_name)
