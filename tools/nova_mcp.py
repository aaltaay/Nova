#!/usr/bin/env python3
"""One Nova MCP server: the data front door and the desk review charts.

Data tools keep the names, arguments, units and as-of rules of ``nova_data_mcp``.
Chart tools return ``/review`` links, a PNG of that same page, or both. Interactive
links do not load bars; the page loads them when it opens. A long data read takes
only its own lock, so a fast read is not stuck behind it.

  py -3 tools/nova_mcp.py [--output-root DIR] [--review-base URL] [--review-port N]
                          [--no-review-http] [--no-warm-shots]

``tools/nova_data_mcp.py`` starts this same server. ``tools/nova_chart_mcp.py`` stays
the candle-gateway exporter.
"""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path
from typing import Any

import nova_data_mcp as data
import nova_review_causal as causal
import nova_review_http as review_http
import nova_review_warm as review_warm

_TOOL_LOCKS: dict[str, threading.Lock] = {}
_TOOL_LOCKS_GUARD = threading.Lock()


def call_per_tool(fn, *args, **kwargs) -> dict[str, Any]:
    """One lock per tool name. A slow ``status`` does not block ``movers_search``."""
    name = getattr(fn, "__name__", "tool")
    with _TOOL_LOCKS_GUARD:
        lock = _TOOL_LOCKS.setdefault(name, threading.Lock())
    with lock:
        return data.invoke(fn, *args, **kwargs)


def _with_images(answer: dict[str, Any], shots: review_warm.ReviewShots | None, directory: Path) -> dict[str, Any]:
    if not answer.get("ok") or answer.get("output") == "interactive":
        return answer
    if shots is None:
        return {"ok": False, "error": {"code": "REVIEW_SHOT_UNAVAILABLE", "detail": "warm renderer was not started"}}
    return review_warm.attach_images(answer, shots, directory)


def create_server(service: data.DataService, *, review_base: str = "http://127.0.0.1:5173",
                  shots: review_warm.ReviewShots | None = None):
    import anyio
    from mcp.types import ToolAnnotations

    server = data.create_server(service, run_sync=call_per_tool, server_name="nova")
    reads = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    directory = service.output_root / "review-shots"

    async def run(fn, *args):
        return await anyio.to_thread.run_sync(lambda: data.invoke(fn, *args))

    def historical(symbol: str, date: str, tf: str = "1m,5m,1d", output: str = "interactive",
                   as_of: str | None = None) -> dict[str, Any]:
        answer = causal.chart_pages([symbol], date, tf, output, base=review_base, as_of=as_of)
        return _with_images(answer, shots, directory)

    def gallery(symbols: list[str] | str, date: str, tf: str = "1m,5m,1d", output: str = "interactive",
                as_of: str | None = None) -> dict[str, Any]:
        answer = causal.chart_pages(symbols, date, tf, output, base=review_base, as_of=as_of)
        return _with_images(answer, shots, directory)

    def trade_body(rows: list[dict[str, Any]], output: str = "interactive") -> dict[str, Any]:
        answer = causal.trade_pages(rows, output, base=review_base)
        return _with_images(answer, shots, directory)

    @server.tool(name="nova_historical_chart", annotations=reads)
    async def nova_historical_chart(symbol: str, date: str, tf: str = "1m,5m,1d", output: str = "interactive",
                                    as_of: str | None = None) -> dict:
        """One desk review chart. output: interactive (default, /review URLs only) | png | both.

        tf is 1m, 5m, 10s, 1d (default 1m,5m,1d). as_of is HH:MM ET (default 16:00). Interactive
        does not load bars. png is a screenshot of that same /review page. The answer also
        includes a one-symbol gallery URL."""
        return await run(historical, symbol, date, tf, output, as_of)

    @server.tool(name="nova_historical_chart_gallery", annotations=reads)
    async def nova_historical_chart_gallery(symbols: list[str], date: str, tf: str = "1m,5m,1d",
                                            output: str = "interactive", as_of: str | None = None) -> dict:
        """1 to 9 desk review charts for one date. output: interactive | png | both.

        interactive returns every symbol URL and one gallery URL in one call, without loading
        bars. Each page loads its own data when opened. png screenshots those same pages."""
        return await run(gallery, symbols, date, tf, output, as_of)

    @server.tool(name="nova_trade_charts", annotations=reads)
    async def nova_trade_charts(trades: list[dict], output: str = "interactive") -> dict:
        """Review links for the symbol/date pairs in trades (max 9). output: interactive | png | both.

        Marked sub-minute candle-gateway PNGs stay on tools/nova_chart_mcp.py. Here each pair
        opens the desk /review page. A gallery URL is included when every trade shares a date."""
        return await run(trade_body, trades, output)

    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nova data and desk-chart MCP server")
    parser.add_argument("--output-root", type=Path, default=data.DEFAULT_OUTPUT,
                        help="where output_name tables and review PNGs are written")
    parser.add_argument("--review-base", default="http://127.0.0.1:5173",
                        help="origin of the desk, used in /review URLs")
    parser.add_argument("--review-port", type=int, default=8765, help="loopback port for /api/review")
    parser.add_argument("--no-review-http", action="store_true", help="do not listen for /api/review")
    parser.add_argument("--no-warm-shots", action="store_true", help="do not keep a browser for PNGs")
    args = parser.parse_args(argv)
    if not args.no_review_http:
        try:
            review_http.serve_background(args.review_port)
            print(f"nova-review: http://127.0.0.1:{args.review_port}/api/review", file=sys.stderr)
        except OSError as exc:
            print(f"nova-review: HTTP did not start: {exc}", file=sys.stderr)
    shots = None
    if not args.no_warm_shots:
        shots = review_warm.ReviewShots()
        ready = shots.start()
        if not ready.get("ok"):
            detail = ready.get("error")
            print(f"nova-review: screenshots unavailable: {detail}", file=sys.stderr)
            shots = None
    data.preload()
    create_server(data.DataService(args.output_root), review_base=args.review_base.rstrip("/"), shots=shots).run(
        transport="stdio")
    if shots is not None:
        shots.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
