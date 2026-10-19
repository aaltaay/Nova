"""The unified Nova MCP server: data-tool parity, per-tool locks, and causal review charts."""
from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import nova_data_mcp as data  # noqa: E402
import nova_mcp  # noqa: E402
import nova_review_causal as causal  # noqa: E402
import nova_review_http as review_http  # noqa: E402
import nova_review_load as review_load  # noqa: E402
import nova_review_warm as review_warm  # noqa: E402

ET = causal.ET
DAY = "2026-09-18"
SYMBOLS = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]


def _minute(hour: int, minute: int, high: float, volume: float = 100) -> dict:
    return {"time_et": datetime(2026, 9, 18, hour, minute, tzinfo=ET), "open": 9, "high": high, "low": 8,
            "close": 9, "volume": volume}


def _session_minutes() -> list[dict]:
    rows = []
    clock = datetime(2026, 9, 18, 9, 0, tzinfo=ET)
    end = datetime(2026, 9, 18, 10, 30, tzinfo=ET)
    while clock <= end:
        high = 50.0 if clock.hour == 10 and clock.minute == 15 else 10.0
        rows.append(_minute(clock.hour, clock.minute, high))
        clock += timedelta(minutes=1)
    return rows


def test_a_bar_that_is_still_open_cannot_move_the_high():
    minutes = _session_minutes()
    as_of = causal.as_of_dt(DAY, "10:00")
    kept = causal.closed_bars(minutes, "1m", as_of)
    assert kept and max(row["high"] for row in kept) < 50
    assert causal.levels(kept, [], DAY, as_of)["hod"] < 50
    five = [_minute(9, 55, 12)]
    assert causal.closed_bars(five, "5m", causal.as_of_dt(DAY, "09:58")) == []
    assert len(causal.closed_bars(five, "5m", causal.as_of_dt(DAY, "10:00"))) == 1
    early = causal.levels(causal.closed_bars(minutes, "1m", causal.as_of_dt(DAY, "09:34")), [], DAY,
                          causal.as_of_dt(DAY, "09:34"))
    assert early["opening_range_high"] is None


def test_session_vwap_starts_at_4_and_ignores_the_bar_before_it():
    rows = [
        _minute(3, 50, 1, volume=10000),
        {"time_et": datetime(2026, 9, 18, 4, 0, tzinfo=ET), "open": 10, "high": 10, "low": 10, "close": 10, "volume": 100},
        {"time_et": datetime(2026, 9, 18, 4, 1, tzinfo=ET), "open": 13, "high": 13, "low": 13, "close": 13, "volume": 100},
    ]
    points = causal.session_vwap(rows)
    assert points[0]["value"] == pytest.approx(10)
    assert points[1]["value"] == pytest.approx(11.5)
    assert points[0]["t"].endswith("04:00:00-04:00") or "04:00:00" in points[0]["t"]


def test_the_session_daily_candle_is_the_cut_minutes():
    minutes = causal.closed_bars(_session_minutes(), "1m", causal.as_of_dt(DAY, "10:00"))
    dailies = [
        {"date": "2026-09-17", "open": 1, "high": 6, "low": 0.5, "close": 5.5, "volume": 10},
        {"date": DAY, "open": 100, "high": 200, "low": 1, "close": 150, "volume": 999},
        {"date": "2026-09-19", "open": 9, "high": 9, "low": 9, "close": 9, "volume": 1},
    ]
    series = causal.daily_series(dailies, minutes, DAY)
    assert [row["t"] for row in series] == ["2026-09-17", DAY]
    assert series[-1]["h"] < 50
    assert causal.levels(minutes, dailies, DAY, causal.as_of_dt(DAY, "10:00"))["prior_close"] == 5.5


def test_loader_levels_cannot_see_the_later_spike():
    def bars(_symbol, _day, tf):
        if tf == "5m":
            return [_minute(9, 55, 12), _minute(10, 10, 50)]
        return _session_minutes()

    def daily(_symbol, _start, _end):
        return [
            {"date": "2026-09-17", "open": 1, "high": 6, "low": 0.5, "close": 5.5, "volume": 10},
            {"date": DAY, "open": 100, "high": 200, "low": 1, "close": 150, "volume": 999},
        ]

    body = review_load.load_review("imcc", DAY, ["1m", "5m", "1d"], "10:00", bars_reader=bars, daily_reader=daily)
    assert body["lookahead"] is False
    assert body["levels"]["hod"] < 50
    assert body["timeframes"]["1d"]["bars"][-1]["h"] < 50
    assert "2026-09-19" not in {row["t"] for row in body["timeframes"]["1d"]["bars"]}
    assert all(row["t"] < "2026-09-18T10:00" for row in body["timeframes"]["5m"]["bars"])


def test_nine_symbols_return_urls_without_loading(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("review data was loaded")

    monkeypatch.setattr(review_load, "load_review", boom)
    started = time.perf_counter()
    answer = causal.chart_pages(SYMBOLS, DAY, ["1m", "5m", "1d"], "interactive", base="http://127.0.0.1:5173")
    assert time.perf_counter() - started < 0.5
    assert answer["ok"] is True and answer["loaded"] is False and answer["lazy"] is True
    assert len(answer["urls"]["symbols"]) == 9
    assert "symbols=" in answer["urls"]["gallery"]
    assert all(item["url"].startswith("http://127.0.0.1:5173/review?symbol=") for item in answer["urls"]["symbols"])


def test_review_http_serves_the_cut_payload():
    def bars(_symbol, _day, tf):
        return [_minute(9, 55, 12)] if tf == "5m" else _session_minutes()

    httpd = review_http.serve(0, bars_reader=bars, daily_reader=lambda *_a: [])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/review?symbol=IMCC&date={DAY}&tf=1m&as_of=10:00") as response:
            body = json.loads(response.read().decode())
        assert body["ok"] is True and body["levels"]["hod"] < 50
    finally:
        httpd.shutdown()


def test_a_fast_tool_is_not_stuck_behind_a_slow_one():
    started, release = threading.Event(), threading.Event()

    def status():
        started.set()
        release.wait(5)
        return {"ok": True, "which": "status"}

    def movers_search(_params):
        return {"ok": True, "which": "movers"}

    slow = threading.Thread(target=nova_mcp.call_per_tool, args=(status,))
    slow.start()
    assert started.wait(2)
    began = time.perf_counter()
    answer = nova_mcp.call_per_tool(movers_search, {})
    assert answer["which"] == "movers" and time.perf_counter() - began < 0.5
    release.set()
    slow.join(5)


def test_the_unified_runner_does_not_take_the_data_servers_global_lock():
    held = threading.Event()

    def grab():
        data._HEAVY_ONE_AT_A_TIME.acquire()
        held.set()
        time.sleep(0.4)
        data._HEAVY_ONE_AT_A_TIME.release()

    worker = threading.Thread(target=grab)
    worker.start()
    assert held.wait(1)
    began = time.perf_counter()
    assert nova_mcp.call_per_tool(lambda: {"ok": True})["ok"] is True
    assert time.perf_counter() - began < 0.3
    worker.join(2)


def test_png_output_screenshots_the_review_url(tmp_path):
    seen = []

    def shoot(url, dest):
        seen.append(url)
        dest.write_bytes(b"\x89PNG\r\n\x1a\n")
        return {"ok": True, "path": str(dest), "sha256": "abc", "bytes": 8}

    answer = causal.chart_pages(["IMCC"], DAY, "1m", "png", base="http://127.0.0.1:5173")
    done = review_warm.attach_images(answer, review_warm.ReviewShots(shoot=shoot), tmp_path)
    assert done["loaded"] is True
    assert {item["symbol"] for item in done["images"]} == {"IMCC", "gallery"}
    assert all("/review?" in url for url in seen)


def test_data_tools_match_the_old_server():
    pytest.importorskip("mcp")
    old = {tool.name: tool for tool in asyncio.run(data.create_server(data.DataService()).list_tools())}
    unified = {tool.name: tool for tool in asyncio.run(nova_mcp.create_server(data.DataService()).list_tools())}
    assert set(old) <= set(unified)
    assert {"nova_historical_chart", "nova_historical_chart_gallery", "nova_trade_charts"} <= set(unified)
    for name, tool in old.items():
        match = unified[name]
        assert " ".join(tool.description.split()) == " ".join(match.description.split())
        assert set((tool.inputSchema or {}).get("properties") or {}) == set((match.inputSchema or {}).get("properties") or {})
