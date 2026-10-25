#!/usr/bin/env python3
"""One Nova MCP server: the data front door and one desk chart tool.

Data tools keep the names, arguments, units and as-of rules of ``nova_data_mcp``.
``nova_chart`` returns review links and PNG image blocks. The links do not load
bars. A long data read takes only its own lock, so a fast read is not stuck behind it.

The review engine (one listener, one Chromium) stays off until a chart call needs
it. A later MCP process attaches to the engine that is already up.

  py -3 tools/nova_mcp.py [--output-root DIR] [--review-base URL] [--review-port N]
                          [--review-http] [--no-review-http] [--no-warm-shots]

``NOVA_REVIEW_BASE`` overrides the link origin. Unset, the link uses the engine,
which serves ``/review``. ``NOVA_REVIEW_PORT`` (default 18765) is the engine. ``NOVA_REVIEW_HTTP=1`` starts
the engine at process start. ``tools/nova_data_mcp.py`` starts this same server.
``tools/nova_chart_mcp.py`` stays the candle-gateway exporter.
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
import threading
import uuid
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import nova_data_mcp as data
import nova_review_causal as causal
import nova_review_http as review_http
import nova_review_warm as review_warm

_TOOL_LOCKS: dict[str, threading.Lock] = {}
_TOOL_LOCKS_GUARD = threading.Lock()
DEFAULT_REVIEW_BASE = "http://127.0.0.1:5173"
DEFAULT_REVIEW_PORT = review_http.DEFAULT_PORT


def default_review_base() -> str:
    """Empty means the chart link uses the review engine's own origin."""
    raw = os.environ.get("NOVA_REVIEW_BASE")
    if raw is None or not raw.strip():
        return ""
    return raw.strip().rstrip("/")


def default_review_port() -> int:
    raw = os.environ.get("NOVA_REVIEW_PORT", str(DEFAULT_REVIEW_PORT))
    try:
        port = int(raw)
    except ValueError:
        return DEFAULT_REVIEW_PORT
    return port if 0 < port < 65536 else DEFAULT_REVIEW_PORT


def call_per_tool(fn, *args, **kwargs) -> dict[str, Any]:
    """One lock per tool name. A slow ``status`` does not block ``movers_search``."""
    name = getattr(fn, "__name__", "tool")
    with _TOOL_LOCKS_GUARD:
        lock = _TOOL_LOCKS.setdefault(name, threading.Lock())
    with lock:
        return data.invoke(fn, *args, **kwargs)


CHART_ARGUMENTS = frozenset({"symbols", "date", "as_of"})
TIMEFRAMES = ["10s", "1m", "5m", "1d"]
INSTRUCTIONS = (
    "For a chart, call nova_chart with symbols (1 to 9 tickers), date (YYYY-MM-DD) and optional as_of "
    "(HH:MM ET, default 16:00). Post the tool's chat_message text verbatim. "
    "Do not pass tf, output, symbol or trades."
)


def desk_reachable(base: str) -> bool:
    try:
        with urlopen(base.rstrip("/") + "/review", timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


class Charts:
    """Attaches to the shared review engine on every chart call. No cached origin."""

    def __init__(self, *, base: str, port: int, http: bool, warm: bool,
                 shots: review_warm.ReviewShots | None, directory: Path):
        self.base = base.rstrip("/")
        self.port = port
        self.http = http
        self.warm = warm
        self.shots = shots
        self.directory = directory

    def api_origin(self) -> str | None:
        if not self.http:
            return None
        import nova_review_engine as engine
        return f"http://127.0.0.1:{engine.ensure_engine(self.port)}"

    def origins(self) -> tuple[str, str | None]:
        """Link origin, and the ``api`` query when the page is not the engine."""
        engine_origin = self.api_origin() if self.http else None
        base = (self.base or engine_origin or DEFAULT_REVIEW_BASE).rstrip("/")
        if engine_origin and base == engine_origin.rstrip("/"):
            return base, None
        return base, engine_origin

    def _shoot_one(self, url: str, symbol: str, fields: dict[str, Any]) -> dict[str, Any]:
        self.directory.mkdir(parents=True, exist_ok=True)
        dest = self.directory / f"review-{symbol}-{uuid.uuid4().hex[:8]}.png"
        if self.shots is not None:
            return self.shots.shoot(url, dest)
        import nova_review_engine as engine
        base = self.base.rstrip("/")
        if base and not desk_reachable(base):
            return {"ok": False, "error": {"code": "REVIEW_DESK_UNREACHABLE", "detail": base}}
        try:
            port = engine.ensure_engine(self.port)
        except OSError as exc:
            return {"ok": False, "error": {"code": "REVIEW_ENGINE_UNAVAILABLE", "detail": str(exc)}}
        if not base:
            base = f"http://127.0.0.1:{port}"
            if not desk_reachable(base):
                return {"ok": False, "error": {"code": "REVIEW_DESK_UNREACHABLE", "detail": base}}
        shot = engine.request_shot(port, fields, uuid.uuid4().hex)
        png = shot.get("png")
        if shot.get("ok") and isinstance(png, (bytes, bytearray)):
            try:
                dest.write_bytes(bytes(png))
            except OSError:
                return {"ok": False, "error": {"code": "REVIEW_SHOT_FAILED", "detail": "could not store the preview"}}
        return shot

    def previews(self, links: list[dict[str, str]], gallery: str, *, date: str,
                 as_of: str) -> tuple[list[dict[str, Any]], str | None]:
        if not self.warm:
            return [], "REVIEW_SHOT_UNAVAILABLE"
        pages: list[dict[str, Any]] = [
            {"symbol": item["symbol"], "url": item["url"],
             "fields": {"symbol": item["symbol"], "date": date, "as_of": as_of}}
            for item in links
        ]
        if len(links) > 1:
            pages.append({
                "symbol": "gallery",
                "url": gallery,
                "fields": {
                    "symbols": [item["symbol"] for item in links],
                    "date": date,
                    "as_of": as_of,
                    "gtf": "5m",
                },
            })
        images = []
        for page in pages:
            shot = self._shoot_one(page["url"], page["symbol"], page["fields"])
            if not shot.get("ok"):
                code = (shot.get("error") or {}).get("code") or "REVIEW_SHOT_FAILED"
                return images, str(code)
            png = shot.get("png")
            if not isinstance(png, (bytes, bytearray)) or not png:
                return images, "REVIEW_SHOT_FAILED"
            images.append({
                "symbol": page["symbol"],
                "sha256": shot.get("sha256") or "",
                "bytes": int(shot.get("bytes") or len(png)),
                "png": bytes(png),
            })
        return images, None


def _result(message: str, structured: dict[str, Any], images: list[dict[str, Any]]):
    from mcp.types import CallToolResult, ImageContent, TextContent

    content: list[Any] = [TextContent(type="text", text=message)]
    for image in images:
        content.append(ImageContent(
            type="image",
            data=base64.b64encode(image["png"]).decode("ascii"),
            mimeType="image/png",
        ))
    return CallToolResult(content=content, structuredContent=structured, isError=False)


def _guard_unknown(tool) -> None:
    from mcp.types import CallToolResult, TextContent

    original = tool.run
    allowed = CHART_ARGUMENTS

    async def run(arguments, context=None, convert_result=False):
        unknown = [name for name in (arguments or {}) if name not in allowed]
        if unknown:
            return CallToolResult(
                isError=True,
                content=[TextContent(type="text", text=f"UNKNOWN_ARGUMENT {unknown[0]}")],
            )
        return await original(arguments, context=context, convert_result=convert_result)

    object.__setattr__(tool, "run", run)
    tool.parameters["additionalProperties"] = False


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
    server._mcp_server.instructions = INSTRUCTIONS
    writes = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

    def build(symbols: list[str], date: str, as_of: str) -> Any:
        try:
            base, api = charts.origins()
            engine_note = None
        except OSError as exc:
            base = charts.base or DEFAULT_REVIEW_BASE
            api = None
            engine_note = str(exc)
        try:
            linked = causal.chart_links(symbols, date, as_of, base=base, api=api)
        except ValueError as exc:
            try:
                clock = causal.check_clock(as_of or "16:00")
            except ValueError:
                clock = "16:00"
            try:
                day = causal.parse_day(str(date)).isoformat()
            except ValueError:
                day = "0000-00-00"
            message = causal.chat_message(date=day, as_of=clock, links=[])
            return _result(message, {
                "ok": False,
                "chat_message": message,
                "date": day,
                "as_of": clock,
                "timeframes": TIMEFRAMES,
                "links": [],
                "gallery_url": "",
                "images": [],
                "error": {"code": "BAD_REQUEST", "detail": str(exc)},
            }, [])
        preview = engine_note and "REVIEW_ENGINE_UNAVAILABLE"
        images: list[dict[str, Any]] = []
        if charts.warm and preview is None:
            images, failed = charts.previews(
                linked["links"], linked["gallery_url"], date=linked["date"], as_of=linked["as_of"],
            )
            preview = failed
        elif not charts.warm:
            preview = "REVIEW_SHOT_UNAVAILABLE"
        message = causal.chat_message(
            date=linked["date"],
            as_of=linked["as_of"],
            links=linked["links"],
            gallery_url_text=linked["gallery_url"],
            preview_code=preview,
        )
        shown = images if preview is None else []
        body = {
            "ok": preview is None,
            "chat_message": message,
            "date": linked["date"],
            "as_of": linked["as_of"],
            "timeframes": TIMEFRAMES,
            "links": linked["links"],
            "gallery_url": linked["gallery_url"],
            "images": [{"symbol": image["symbol"], "sha256": image["sha256"], "bytes": image["bytes"]} for image in shown],
        }
        if preview:
            body["error"] = {"code": preview, "detail": preview}
        return _result(message, body, shown)

    @server.tool(name="nova_chart", annotations=writes)
    async def nova_chart(symbols: list[str], date: str, as_of: str = "16:00"):
        """Desk charts for 1 to 9 symbols on one date. Post chat_message verbatim.

        symbols: tickers. date: YYYY-MM-DD. as_of: HH:MM Eastern, default 16:00.
        Timeframes are fixed: 10s, 1m, 5m, 1d, full session 04:00 to 16:00 ET.
        One link per symbol, plus a gallery link. PNG previews are image blocks.
        Volume: the 10s 16:00 bar holds the closing cross, the 1m bar does not. The date's 1d candle is its minute
        bars to as_of (no closing cross or after-hours, high may be premarket); prior 1d candles are official day bars,
        so the last candle's volume sits under the day bar's even at 16:00."""
        return await anyio.to_thread.run_sync(lambda: build(symbols, date, as_of))

    _guard_unknown(server._tool_manager.get_tool("nova_chart"))

    @server.prompt(name="chart_request")
    def chart_request(symbols: str, date: str, as_of: str = "16:00") -> str:
        """Call nova_chart and post its chat_message verbatim."""
        return (
            f"Call nova_chart with symbols {symbols}, date {date}, as_of {as_of}. "
            "Post the tool result chat_message verbatim. Do not pass any other argument."
        )

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
            import nova_review_engine as engine
            engine.ensure_engine(port)
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
