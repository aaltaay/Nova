#!/usr/bin/env python3
"""One Nova MCP server: the data front door and the desk review charts.

Data tools keep the names, arguments, units and as-of rules of ``nova_data_mcp``.
Chart tools return ``/review`` links, a PNG of that same page, or both. Interactive
links do not load bars; the page loads them when it opens. A long data read takes
only its own lock, so a fast read is not stuck behind it.

The review HTTP listener and Chromium stay off until a chart call needs them.
Chromium starts on the first ``png`` or ``both`` call. HTTP is one shared
listener: a second process attaches to the one already up.

  py -3 tools/nova_mcp.py [--output-root DIR] [--review-base URL] [--review-port N]
                          [--review-http] [--no-review-http] [--no-warm-shots]

``NOVA_REVIEW_BASE`` (default ``http://127.0.0.1:5173``) is the link origin.
``NOVA_REVIEW_PORT`` (default 18765) is the review listener. ``NOVA_REVIEW_HTTP=1``
starts that listener at process start, for opening ``/review`` before any chart call.
``tools/nova_data_mcp.py`` starts this same server. ``tools/nova_chart_mcp.py`` stays
the candle-gateway exporter.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import nova_data_mcp as data
import nova_review_causal as causal
import nova_review_http as review_http
import nova_review_warm as review_warm

_TOOL_LOCKS: dict[str, threading.Lock] = {}
_TOOL_LOCKS_GUARD = threading.Lock()
DEFAULT_REVIEW_BASE = "http://127.0.0.1:5173"
DEFAULT_REVIEW_PORT = review_http.DEFAULT_PORT


def default_review_base() -> str:
    return os.environ.get("NOVA_REVIEW_BASE", DEFAULT_REVIEW_BASE).rstrip("/")


def default_review_port() -> int:
    raw = os.environ.get("NOVA_REVIEW_PORT", str(DEFAULT_REVIEW_PORT))
    try:
        port = int(raw)
    except ValueError:
        return DEFAULT_REVIEW_PORT
    return port if 0 < port < 65536 else DEFAULT_REVIEW_PORT


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}"


def call_per_tool(fn, *args, **kwargs) -> dict[str, Any]:
    """One lock per tool name. A slow ``status`` does not block ``movers_search``."""
    name = getattr(fn, "__name__", "tool")
    with _TOOL_LOCKS_GUARD:
        lock = _TOOL_LOCKS.setdefault(name, threading.Lock())
    with lock:
        return data.invoke(fn, *args, **kwargs)


def tool_result(answer: dict[str, Any]) -> list[Any]:
    """Text JSON plus one MCP image block per PNG. The JSON keeps the path; the block is the pixels."""
    from mcp.server.fastmcp import Image

    images = []
    clean = []
    for image in answer.get("images") or []:
        png = image.get("png")
        clean.append({key: value for key, value in image.items() if key != "png"})
        if isinstance(png, (bytes, bytearray)) and png:
            images.append(Image(data=bytes(png), format="png"))
    body = dict(answer)
    if answer.get("images") is not None:
        body["images"] = clean
    return [body, *images]


class Charts:
    """Lazy review HTTP and a browser that starts on the first PNG."""

    def __init__(self, *, base: str, port: int, http: bool, warm: bool,
                 shots: review_warm.ReviewShots | None, directory: Path):
        self.base = base.rstrip("/")
        self.port = port
        self.http = http
        self.warm = warm
        self.shots = shots
        self.directory = directory
        self._api: str | None = None

    def api_origin(self) -> str | None:
        if not self.http:
            return None
        if self._api:
            return self._api
        origins = tuple(item for item in (origin_of(self.base),) if item)
        port, _how = review_http.ensure_shared(self.port, allowed_origins=origins)
        self._api = f"http://127.0.0.1:{port}"
        return self._api

    def renderer(self) -> review_warm.ReviewShots | None:
        if not self.warm:
            return None
        if self.shots is None:
            self.shots = review_warm.ReviewShots()
        return self.shots

    def finish(self, answer: dict[str, Any]) -> Any:
        if not answer.get("ok") or answer.get("output") == "interactive":
            return answer
        shots = self.renderer()
        if shots is None:
            return {"ok": False, "error": {"code": "REVIEW_SHOT_UNAVAILABLE", "detail": "warm renderer was not started"}}
        done = review_warm.attach_images(answer, shots, self.directory)
        if not done.get("ok") or not done.get("images"):
            return done
        return tool_result(done)


def create_server(service: data.DataService, *, review_base: str | None = None, review_port: int | None = None,
                  http: bool = True, warm: bool = True, shots: review_warm.ReviewShots | None = None):
    import anyio
    from mcp.types import ToolAnnotations

    charts = Charts(
        base=review_base or default_review_base(),
        port=default_review_port() if review_port is None else review_port,
        http=http,
        warm=warm,
        shots=shots,
        directory=service.output_root / "review-shots",
    )
    server = data.create_server(service, run_sync=call_per_tool, server_name="nova")
    # png and both write a file, so the tool is not read-only and not idempotent.
    writes = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

    async def run(fn, *args):
        return await anyio.to_thread.run_sync(lambda: data.invoke(fn, *args))

    def historical(symbol: str, date: str, tf: str = "1m,5m,1d", output: str = "interactive",
                   as_of: str | None = None) -> Any:
        answer = causal.chart_pages([symbol], date, tf, output, base=charts.base, as_of=as_of, api=charts.api_origin())
        return charts.finish(answer)

    def gallery(symbols: list[str] | str, date: str, tf: str = "1m,5m,1d", output: str = "interactive",
                as_of: str | None = None) -> Any:
        answer = causal.chart_pages(symbols, date, tf, output, base=charts.base, as_of=as_of, api=charts.api_origin())
        return charts.finish(answer)

    def trade_body(rows: list[dict[str, Any]], output: str = "interactive") -> Any:
        answer = causal.trade_pages(rows, output, base=charts.base, api=charts.api_origin())
        return charts.finish(answer)

    @server.tool(name="nova_historical_chart", annotations=writes)
    async def nova_historical_chart(symbol: str, date: str, tf: str = "1m,5m,1d", output: str = "interactive",
                                    as_of: str | None = None):
        """One desk review chart. output: interactive (default, /review URLs only) | png | both.

        tf is 1m, 5m, 10s, 1d (default 1m,5m,1d). as_of is HH:MM ET (default 16:00). Interactive
        does not load bars. png is a screenshot of that same /review page, returned as an image
        block. The answer also includes a one-symbol gallery URL. A gallery picture is taken
        only when the call has more than one symbol."""
        return await run(historical, symbol, date, tf, output, as_of)

    @server.tool(name="nova_historical_chart_gallery", annotations=writes)
    async def nova_historical_chart_gallery(symbols: list[str], date: str, tf: str = "1m,5m,1d",
                                            output: str = "interactive", as_of: str | None = None):
        """1 to 9 desk review charts for one date. output: interactive | png | both.

        interactive returns every symbol URL and one gallery URL in one call, without loading
        bars. Each page loads its own data when opened. png screenshots those pages and returns
        image blocks. The gallery page is screenshotted only for more than one symbol."""
        return await run(gallery, symbols, date, tf, output, as_of)

    @server.tool(name="nova_trade_charts", annotations=writes)
    async def nova_trade_charts(trades: list[dict], output: str = "interactive"):
        """Review links for the symbol/date pairs in trades (max 9). output: interactive | png | both.

        Marked sub-minute candle-gateway PNGs stay on tools/nova_chart_mcp.py. Here each pair
        opens the desk /review page. A gallery URL is included when every trade shares a date.
        png returns image blocks. The gallery picture is taken only when there is more than one pair."""
        return await run(trade_body, trades, output)

    return server


def _want_http_now(argv_flag: bool) -> bool:
    return argv_flag or os.environ.get("NOVA_REVIEW_HTTP") == "1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nova data and desk-chart MCP server")
    parser.add_argument("--output-root", type=Path, default=data.DEFAULT_OUTPUT,
                        help="where output_name tables and review PNGs are written")
    parser.add_argument("--review-base", default=None,
                        help="origin of the desk, used in /review URLs (env NOVA_REVIEW_BASE)")
    parser.add_argument("--review-port", type=int, default=None,
                        help=f"loopback port for /api/review (default {DEFAULT_REVIEW_PORT}, env NOVA_REVIEW_PORT)")
    parser.add_argument("--review-http", action="store_true",
                        help="start the shared review listener now (also NOVA_REVIEW_HTTP=1)")
    parser.add_argument("--no-review-http", action="store_true",
                        help="never listen for /api/review; the page uses whatever is already proxied")
    parser.add_argument("--no-warm-shots", action="store_true", help="do not launch a browser for PNGs")
    args = parser.parse_args(argv)
    base = (args.review_base or default_review_base()).rstrip("/")
    port = default_review_port() if args.review_port is None else args.review_port
    http = not args.no_review_http
    if http and _want_http_now(args.review_http):
        try:
            review_http.ensure_shared(port, allowed_origins=tuple(item for item in (origin_of(base),) if item))
        except OSError as exc:
            print(f"nova-review: HTTP did not start: {exc}", file=sys.stderr)
            return 1
    service = data.DataService(args.output_root)
    data.preload()
    server = create_server(service, review_base=base, review_port=port, http=http, warm=not args.no_warm_shots)
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
