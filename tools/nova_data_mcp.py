#!/usr/bin/env python3
"""Nova's historical data front door over MCP (ADR 059): every agent -- Cursor, Claude, Codex -- reads the operator's
Massive files, Nova's stores, Massive's reference dump and SEC's bulk files through these tools, never its own reader.

Read-only on the data. The one thing a tool writes is a table an agent asked for by ``output_name`` (a new .parquet
or .csv under ``--output-root``); everything else answers inline, at most ``INLINE_ROWS`` rows, with ``rows`` saying
how many matched. Heavy reads take a slot shared by every process on the PC (``research/market_reads/slots.py``).
Start with ``data_catalog``: what each dataset is, its history, its as-of rule and its units.

  py -3 tools/nova_data_mcp.py [--output-root DIR]      (stdio; registered in .cursor/mcp.json and .mcp.json)
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "research") not in sys.path:
    sys.path.insert(0, str(REPO / "research"))
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

import nova_data_research as research  # noqa: E402  (the second tool set: stock-days, stats, flow, halts ...)

INLINE_ROWS = 200
OUTPUT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,100}\.(parquet|csv)$")
DEFAULT_OUTPUT = Path(tempfile.gettempdir()) / "nova-data-mcp"
# Light reads run beside anything: no index build, no file written, no first-use DuckDB open (#1067). Every other tool
# is heavy: one at a time per process here, and the PC-wide heavy-read slots bound them across processes.
LIGHT_TOOLS = frozenset({"catalog", "symbols", "halts", "catalysts", "sec_filings"})
_HEAVY_ONE_AT_A_TIME = threading.Lock()


class PrintsToStderr(io.TextIOBase):
    """``sys.stdout`` while tools run: every print goes to stderr from any thread, and ``buffer`` stays the real
    stdout, which the stdio transport captured when it started and writes the protocol to. Installed once, so calls
    that overlap never swap ``sys.stdout`` under each other."""

    def __init__(self, real):
        self._real = real

    @property
    def buffer(self):
        return self._real.buffer

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        return sys.stderr.write(text)

    def flush(self) -> None:
        sys.stderr.flush()


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def table_answer(frame, out: Path | None = None, inline: int = INLINE_ROWS) -> dict[str, Any]:
    """A DataFrame as an answer: ``rows`` matched, ``columns``, the first ``inline`` rows, and the file when asked."""
    meta = {k: v for k, v in getattr(frame, "attrs", {}).items() if k != "file"}
    if out is not None:
        frame.to_parquet(out, index=False) if out.suffix == ".parquet" else frame.to_csv(out, index=False)
    head = json.loads(frame.head(inline).to_json(orient="records", date_format="iso")) if len(frame) else []
    return {"ok": True, "meta": _json_safe(meta), "rows": int(len(frame)), "columns": [str(c) for c in frame.columns],
            "data": head, "truncated": len(frame) > inline, "out": str(out) if out else None}


class DataService(research.ResearchTools):
    """The tools' bodies, callable without the MCP SDK (tests drive this class)."""

    answer = staticmethod(table_answer)
    json_safe = staticmethod(_json_safe)

    def __init__(self, output_root: Path = DEFAULT_OUTPUT):
        self.output_root = Path(output_root)

    def output_path(self, output_name: str | None) -> Path | None:
        if not output_name:
            return None
        if not OUTPUT_NAME.match(output_name):
            raise ValueError("output_name must be a plain new file name ending .parquet or .csv")
        self.output_root.mkdir(parents=True, exist_ok=True)
        path = self.output_root / output_name
        if path.exists():
            raise FileExistsError(f"{path} exists: pick a new output_name")
        return path

    def catalog(self) -> dict[str, Any]:
        from market_reads import catalog
        return {"ok": True, "datasets": list(catalog.CATALOG), "not_here": list(catalog.NOT_HERE)}

    def status(self) -> dict[str, Any]:
        from market_reads import inventory
        return {"ok": True, **_json_safe(inventory.status())}

    def stock_day(self, kind: str, symbol: str, day: str, start: str | None = None, end: str | None = None,
                  tf: str = "1m", adjust: bool = False, output_name: str | None = None) -> dict[str, Any]:
        from market_reads import reads, slots, splits
        out = self.output_path(output_name)
        with slots.heavy(f"{kind} {symbol} {day}"):
            if kind == "bars":
                frame = reads.bars(symbol, day, tf, start, end)
            elif kind in ("trades", "quotes"):
                frame = getattr(reads, kind)(symbol, day, start, end)
            else:
                raise ValueError("kind must be trades, quotes or bars")
        if adjust:
            frame = splits.adjust(frame, symbol, day)
        return table_answer(frame, out)

    def movers_search(self, params: dict[str, Any]) -> dict[str, Any]:
        from market_reads import reads
        return {"ok": True, **_json_safe(reads.movers(**params))}

    def movers_scan(self, filters: dict[str, Any], symbol: str | None = None, kinds: list[str] | None = None,
                    columns: list[str] | None = None, limit: int | None = None, splits: str = "exclude_likely",
                    output_name: str | None = None) -> dict[str, Any]:
        from market_reads import scan
        out = self.output_path(output_name)
        return table_answer(scan.movers_scan(symbol=symbol, kinds=kinds, columns=columns, limit=limit, splits=splits,
                                             **filters), out)

    def board(self, day: str, at: str, list_name: str = "gainers", source: str | None = None) -> dict[str, Any]:
        from market_reads import reads
        frame = reads.board(day, at, list_name, source)
        answer = table_answer(frame)
        answer.update(covered=frame.attrs.get("covered") is not False and bool(frame.attrs.get("board")),
                      gap=_json_safe(frame.attrs.get("gap")))
        if frame.attrs.get("note"):
            answer["note"] = frame.attrs["note"]
        return answer

    def splits(self, symbol: str, day: str | None = None, cik: str | None = None) -> dict[str, Any]:
        from market_reads import splits
        answer = table_answer(splits.table(symbol, cik=cik))
        if day:
            answer["price_factor"] = splits.factor(symbol, day, cik=cik)
        return answer

    def financials(self, symbol: str, statement: str = "balance_sheets", as_of: str | None = None,
                   timeframe: str | None = None, cik: str | None = None) -> dict[str, Any]:
        from market_reads import reference
        return table_answer(reference.financials(symbol, statement, as_of, timeframe, cik))

    def sec_shares(self, symbol: str, day: str | None = None, max_age_days: int | None = None,
                   cik: str | None = None) -> dict[str, Any]:
        from market_reads import sec
        if day:
            return {"ok": True, **_json_safe(sec.shares_as_of(symbol, day, max_age_days, cik))}
        return table_answer(sec.facts(symbol, cik=cik))

    def sec_filings(self, symbol: str, as_of: str | None = None, forms: list[str] | None = None,
                    cik: str | None = None) -> dict[str, Any]:
        from market_reads import sec
        return table_answer(sec.filings(symbol, as_of, forms, cik))

    def float_latest(self, symbol: str | None = None) -> dict[str, Any]:
        from market_reads import reference
        return table_answer(reference.float_latest(symbol))

    def ipos(self, symbol: str | None = None, date_from: str | None = None, date_to: str | None = None) -> dict:
        from market_reads import reference
        return table_answer(reference.ipos(symbol, date_from, date_to))

    def ticker_details(self, symbol: str) -> dict[str, Any]:
        from market_reads import reference
        return table_answer(reference.ticker_details(symbol))

    def short_interest(self, symbol: str, day: str, at: str = "09:30") -> dict[str, Any]:
        from market_reads import reference
        return {"ok": True, **_json_safe(reference.short_interest(symbol, day, at))}


def call(fn, *args, **kwargs) -> dict[str, Any]:
    """Run one tool body: its prints go to stderr (stdout carries the protocol) and an error is an answer. A heavy
    body waits for the process's heavy lock; a light one (``LIGHT_TOOLS``) does not."""
    if not isinstance(sys.stdout, PrintsToStderr):
        sys.stdout = PrintsToStderr(sys.stdout)
    light = getattr(fn, "__name__", "") in LIGHT_TOOLS
    with contextlib.nullcontext() if light else _HEAVY_ONE_AT_A_TIME:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # maintainer: allow-swallow a failed read is returned to the agent as its answer
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def create_server(service: DataService):
    import anyio
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    server = FastMCP("nova-data", log_level="WARNING")
    reads = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    writes_file = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False,
                                  openWorldHint=False)

    async def run(fn, *args, **kwargs):
        return await anyio.to_thread.run_sync(lambda: call(fn, *args, **kwargs))

    @server.tool(annotations=reads)
    async def data_catalog() -> dict:
        """Start here: every dataset (trades, quotes, bars, daily bars, movers index, stock-day finder, boards,
        order flow, halts, catalysts, symbols, splits, financials, SEC shares and filings, float, IPOs, ticker
        details, short interest) with its source, history, as-of rule, units and the tool that reads it, plus what
        is NOT available."""
        return await run(service.catalog)

    @server.tool(annotations=reads)
    async def data_status() -> dict:
        """What is on disk: each Massive dataset's days and indexed share, the movers index and past-day boards."""
        return await run(service.status)

    @server.tool(annotations=writes_file)
    async def stock_day(kind: str, symbol: str, day: str, start: str | None = None, end: str | None = None,
                        tf: str = "1m", adjust: bool = False, output_name: str | None = None) -> dict:
        """One stock-day from the Massive files. kind: trades | quotes (NBBO, Level 1) | bars (tf 1m/5m/15m/1h from
        the minute file, 1s/10s built from trades; daily bars are not a stock-day read). day YYYY-MM-DD; start/end ET
        HH:MM (end exclusive). Volume: minute bars are Massive's (its SIP volume rules); seconds bars count every trade
        except cancel/error records, so they can sum higher (GME 2021-01-27 09:30: 185,567 vs 179,397). Raw prices
        unless adjust=true (today's split terms). Inline answers hold 200 rows; output_name (new .parquet/.csv) for all."""
        return await run(service.stock_day, kind, symbol, day, start, end, tf, adjust, output_name)

    @server.tool(annotations=reads)
    async def movers_search(params: dict) -> dict:
        """The agent movers endpoint (at most 500 rows): params like {"date_from": "2021-01-01", "high_min": 100,
        "price_max": 20, "float_max": 10000000, "sort": "high", "limit": 50}. Percents in points. float_max is SEC
        shares OUTSTANDING filed by the day (not free float; insiders and locked-up shares are inside it).
        splits: exclude_likely (default) | include | only_suspects."""
        return await run(service.movers_search, params)

    @server.tool(annotations=writes_file)
    async def movers_scan(filters: dict, symbol: str | None = None, kinds: list[str] | None = None,
                          columns: list[str] | None = None, limit: int | None = None, splits: str = "exclude_likely",
                          output_name: str | None = None) -> dict:
        """Bulk day movers rows for research, past the 500-row cap. filters: date_from, date_to, price_min, price_max
        (prior close, raw $), high_min/high_max, low_*, close_*, gap_* (percent points: 50 = +50%), volume_min,
        dollar_volume_min. Needs date_from/date_to, a symbol or a limit; without a limit at most 100,000 rows
        (meta.capped says more matched; limit up to 1,000,000). splits: exclude_likely (default, the same rule as
        movers_search) | include | only_suspects; each row has split. Returned *_pct are percent points."""
        return await run(service.movers_scan, filters, symbol, kinds, columns, limit, splits, output_name)

    @server.tool(annotations=reads)
    async def board(day: str, at: str, list_name: str = "gainers", source: str | None = None) -> dict:
        """A past day's Scanner list at ET HH:MM as the Sim plays it back (recorded, else rebuilt): list_name
        gainers | losers | gappers | afterhours | large_cap. change_pct / gap_pct are percent points (45.6 = +45.6%),
        like the movers tools. Boards cover 1,752 of 2,713 sessions: a day without one answers covered=false with
        gap and note (0 rows then means no board, not no movers)."""
        return await run(service.board, day, at, list_name, source)

    @server.tool(annotations=reads)
    async def splits(symbol: str, day: str | None = None, cik: str | None = None) -> dict:
        """A stock's splits (Massive + SEC-confirmed); with day, the factor that puts that day's raw prices in
        today's terms (shares divide by it), counting only the splits of the company that held the ticker that day.
        A ticker two companies used shows holder_cik per split and meta.ticker; cik picks one company."""
        return await run(service.splits, symbol, day, cik)

    @server.tool(annotations=reads)
    async def financials(symbol: str, statement: str = "balance_sheets", as_of: str | None = None,
                         timeframe: str | None = None, cik: str | None = None) -> dict:
        """Massive financial statements as filed: statement balance_sheets | income_statements |
        cash_flow_statements; as_of YYYY-MM-DD keeps only filings on or before it (no look-ahead). Balance-sheet
        common_stock/treasury_stock are dollars, not shares. A reused ticker reads the company that held it on as_of
        (meta.ticker names it; an unsettled day errors with the candidate CIKs -- pass cik)."""
        return await run(service.financials, symbol, statement, as_of, timeframe, cik)

    @server.tool(annotations=reads)
    async def sec_shares(symbol: str, day: str | None = None, max_age_days: int | None = None,
                         cik: str | None = None) -> dict:
        """SEC share counts. With day: what filings said by that day -- outstanding (split-adjusted to the day),
        issued, treasury, 10-K public float in USD, and filer kind (domestic / foreign). Without day: every fact.
        The company is the one that held the ticker on day (ticker says who and whether the ticker was reused)."""
        return await run(service.sec_shares, symbol, day, max_age_days, cik)

    @server.tool(annotations=reads)
    async def sec_filings(symbol: str, as_of: str | None = None, forms: list[str] | None = None,
                          cik: str | None = None) -> dict:
        """A company's SEC filings filed by as_of: forms e.g. ["4", "SC 13D", "SCHEDULE 13G", "424B4", "8-K",
        "10-Q", "20-F"]. Lists filings, not their contents. A reused ticker reads the company that held it on as_of."""
        return await run(service.sec_filings, symbol, as_of, forms, cik)

    @server.tool(annotations=reads)
    async def float_latest(symbol: str | None = None) -> dict:
        """Massive's free float today (excludes insiders, 5%+ holders, locked-up shares). Latest only: never a past
        day's float."""
        return await run(service.float_latest, symbol)

    @server.tool(annotations=reads)
    async def ipos(symbol: str | None = None, date_from: str | None = None, date_to: str | None = None) -> dict:
        """IPOs by listing date (no lockup terms)."""
        return await run(service.ipos, symbol, date_from, date_to)

    @server.tool(annotations=reads)
    async def ticker_details(symbol: str) -> dict:
        """Ticker details as of the reference dump (name, CIK, exchange, SIC, list date, share class shares)."""
        return await run(service.ticker_details, symbol)

    @server.tool(annotations=reads)
    async def short_interest(symbol: str, day: str, at: str = "09:30") -> dict:
        """FINRA short interest as published by day at ET HH:MM (a settlement counts only after its publish lag)."""
        return await run(service.short_interest, symbol, day, at)

    research.register(server, service, run, reads, writes_file)
    return server


PRELOAD = ("numpy", "pandas", "pyarrow", "market_reads.reads", "market_reads.splits", "market_reads.reference",
           "market_reads.sec", "market_reads.tickers", "market_reads.scan", "market_reads.inventory",
           "market_reads.catalog", "day_movers.query",
           "agent_desk.movers_read", "leaderboard.playback", "move_reason.short_interest", *research.PRELOAD)


def preload() -> list[str]:
    """Import every read's modules on the main thread before stdio starts. On Windows the transport's pending read
    on the stdin pipe blocks other calls on that handle, and numpy's first import from a worker thread hung there
    (2026-10-18). Returns the modules that failed (named on stderr; their tools answer the error)."""
    import importlib
    failed = []
    with contextlib.redirect_stdout(sys.stderr):
        for name in PRELOAD:
            try:
                importlib.import_module(name)
            except Exception as exc:  # maintainer: allow-swallow a missing optional reader leaves only its tools failing
                failed.append(name)
                print(f"nova-data: preload {name} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    return failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT,
                        help="where tables asked for by output_name are written")
    args = parser.parse_args(argv)
    preload()
    create_server(DataService(args.output_root)).run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
