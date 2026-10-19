"""The unified Nova MCP server: data-tool parity, per-tool locks, and causal review charts."""
from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import os
import queue
import socket
import sys
import threading
import time
import urllib.error
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
    assert kept and max(row["high"] for row in kept) == 10
    assert causal.levels(kept, [], DAY, as_of)["hod"] == 10
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
    assert points[0]["t"] == "2026-09-18T04:00:00-04:00"


def test_the_session_daily_candle_is_the_cut_minutes():
    minutes = causal.closed_bars(_session_minutes(), "1m", causal.as_of_dt(DAY, "10:00"))
    dailies = [
        {"date": "2026-09-17", "open": 1, "high": 6, "low": 0.5, "close": 5.5, "volume": 10},
        {"date": DAY, "open": 100, "high": 200, "low": 1, "close": 150, "volume": 999},
        {"date": "2026-09-19", "open": 9, "high": 9, "low": 9, "close": 9, "volume": 1},
    ]
    series = causal.daily_series(dailies, minutes, DAY)
    assert [row["t"] for row in series] == ["2026-09-17", DAY]
    assert series[-1]["h"] == 10
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
    assert body["levels"]["hod"] == 10
    assert body["timeframes"]["1d"]["bars"][-1]["h"] == 10
    assert "2026-09-19" not in {row["t"] for row in body["timeframes"]["1d"]["bars"]}
    assert all(row["t"] < "2026-09-18T10:00" for row in body["timeframes"]["5m"]["bars"])


def test_nine_symbols_return_urls_without_loading(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("review data was loaded")

    monkeypatch.setattr(review_load, "load_review", boom)
    causal.chart_pages(SYMBOLS, DAY, ["1m", "5m", "1d"], "interactive", base="http://127.0.0.1:5173")
    samples = []
    answer = None
    for _ in range(5):
        started = time.perf_counter()
        answer = causal.chart_pages(SYMBOLS, DAY, ["1m", "5m", "1d"], "interactive", base="http://127.0.0.1:5173")
        samples.append(time.perf_counter() - started)
    assert sorted(samples)[len(samples) // 2] < 0.05
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
        assert response.status == 200 and body["ok"] is True and body["levels"]["hod"] == 10
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


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _shoot(url, dest, seen):
    seen.append(url)
    dest.write_bytes(PNG)
    return {"ok": True, "path": str(dest), "sha256": "abc", "bytes": len(PNG), "png": PNG}


def test_png_output_screenshots_the_review_url(tmp_path):
    seen = []
    answer = causal.chart_pages(["IMCC"], DAY, "1m", "png", base="http://127.0.0.1:5173")
    done = review_warm.attach_images(answer, review_warm.ReviewShots(shoot=lambda url, dest: _shoot(url, dest, seen)), tmp_path)
    assert done["loaded"] is True
    assert {item["symbol"] for item in done["images"]} == {"IMCC"}
    raw = Path(done["images"][0]["path"]).read_bytes()
    assert raw.startswith(b"\x89PNG\r\n\x1a\n") and len(raw) >= 64
    assert done["images"][0]["png"].startswith(b"\x89PNG\r\n\x1a\n")
    assert all("/review?" in url for url in seen)
    pair = causal.chart_pages(["IMCC", "REFR"], DAY, "5m", "png", base="http://127.0.0.1:5173")
    both = review_warm.attach_images(pair, review_warm.ReviewShots(shoot=lambda url, dest: _shoot(url, dest, [])), tmp_path)
    assert {item["symbol"] for item in both["images"]} == {"IMCC", "REFR", "gallery"}


def _schema_bits(schema: dict) -> dict:
    props = (schema or {}).get("properties") or {}
    kept = ("type", "default", "anyOf", "items", "enum")
    return {
        "required": list((schema or {}).get("required") or []),
        "props": {name: {key: prop[key] for key in kept if key in prop} for name, prop in props.items()},
    }


def test_data_tools_match_the_old_server():
    old = {tool.name: tool for tool in asyncio.run(data.create_server(data.DataService()).list_tools())}
    unified = {tool.name: tool for tool in asyncio.run(
        nova_mcp.create_server(data.DataService(), http=False, warm=False).list_tools())}
    assert set(old) <= set(unified)
    chart_tools = {"nova_historical_chart", "nova_historical_chart_gallery", "nova_trade_charts"}
    assert chart_tools <= set(unified)
    for name, tool in old.items():
        match = unified[name]
        assert " ".join(tool.description.split()) == " ".join(match.description.split())
        assert _schema_bits(tool.inputSchema) == _schema_bits(match.inputSchema)
    for name in chart_tools:
        notes = unified[name].annotations
        assert notes is not None
        assert notes.readOnlyHint is False
        assert notes.idempotentHint is False
        assert notes.destructiveHint is False


def test_a_10s_bar_waits_until_it_closes_and_nan_ohlc_is_dropped():
    rows = [
        {"time_et": datetime(2026, 9, 18, 9, 59, 50, tzinfo=ET), "open": 4, "high": 4, "low": 4, "close": 4, "volume": 1},
        {"time_et": datetime(2026, 9, 18, 10, 0, 0, tzinfo=ET), "open": 80, "high": 80, "low": 80, "close": 80, "volume": 1},
        {"time_et": datetime(2026, 9, 18, 9, 30, 0, tzinfo=ET), "open": float("nan"), "high": float("nan"),
         "low": float("nan"), "close": float("nan"), "volume": 9},
    ]
    kept = causal.closed_bars(rows, "10s", causal.as_of_dt(DAY, "10:00"))
    wired = causal.wire_bars(kept, "10s")
    assert [row["h"] for row in wired] == [4]
    json.dumps({"bars": wired}, allow_nan=False)


def test_review_errors_use_http_status_and_cors_is_the_desk_origin():
    def bars(_symbol, _day, _tf):
        return _session_minutes()

    def boom(*_args, **_kwargs):
        raise RuntimeError("reader failed")

    ok = review_http.serve(0, bars_reader=bars, daily_reader=lambda *_a: [],
                           allowed_origins=("http://127.0.0.1:5173",))
    bad = review_http.serve(0, bars_reader=boom, daily_reader=lambda *_a: [])
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (ok, bad)]
    for thread in threads:
        thread.start()
    try:
        port = ok.server_address[1]
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/nope")
            raise AssertionError("unknown path should be 404")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        evil = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/review?symbol=IMCC&date={DAY}&tf=1m&as_of=10:00",
            headers={"Origin": "http://evil.test"},
        )
        with urllib.request.urlopen(evil) as response:
            assert response.status == 200
            assert response.headers.get("Access-Control-Allow-Origin") is None
        desk = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/review?symbol=IMCC&date={DAY}&tf=1m&as_of=10:00",
            headers={"Origin": "http://127.0.0.1:5173"},
        )
        with urllib.request.urlopen(desk) as response:
            assert response.headers.get("Access-Control-Allow-Origin") == "http://127.0.0.1:5173"
            raw = response.read()
        assert b"NaN" not in raw
        json.loads(raw.decode())
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/review?symbol=&date={DAY}")
            raise AssertionError("empty symbol should be 400")
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{bad.server_address[1]}/api/review?symbol=IMCC&date={DAY}&tf=1m")
            raise AssertionError("a broken reader should be 500")
        except urllib.error.HTTPError as exc:
            assert exc.code == 500
    finally:
        ok.shutdown()
        bad.shutdown()


def test_review_port_and_link_base_follow_the_environment(monkeypatch):
    monkeypatch.delenv("NOVA_REVIEW_PORT", raising=False)
    monkeypatch.delenv("NOVA_REVIEW_BASE", raising=False)
    assert nova_mcp.default_review_port() == 18765
    assert nova_mcp.default_review_base() == "http://127.0.0.1:5173"
    monkeypatch.setenv("NOVA_REVIEW_PORT", "19991")
    monkeypatch.setenv("NOVA_REVIEW_BASE", "http://127.0.0.1:4173")
    assert nova_mcp.default_review_port() == 19991
    assert nova_mcp.default_review_base() == "http://127.0.0.1:4173"


def test_a_taken_port_moves_to_a_free_one(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(review_http, "LEASE", tmp_path / "lease.json")
    monkeypatch.setattr(review_http, "LEASE_LOCK", tmp_path / "lease.lock")
    review_http.stop_owned()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    taken = sock.getsockname()[1]
    try:
        port, how = review_http.ensure_shared(taken)
        assert how == "moved" and port != taken
        assert review_http.health_ok(port)
        err = capsys.readouterr().err
        assert f"port {taken} is taken" in err and str(port) in err
    finally:
        review_http.stop_owned()
        sock.close()


def test_a_late_screenshot_reply_does_not_satisfy_the_next_request():
    lines: queue.Queue[str] = queue.Queue()
    lines.put(json.dumps({"id": "old", "ok": True, "which": "old"}))
    lines.put(json.dumps({"id": "new", "ok": True, "which": "new"}))
    body = review_warm.matching_reply(lines.get, "new", 1)
    assert body is not None and body["which"] == "new"


def test_old_review_shots_are_rotated(tmp_path):
    for index in range(30):
        path = tmp_path / f"review-x-{index}.png"
        path.write_bytes(b"x" * 20)
        stamp = index + 1
        os.utime(path, (stamp, stamp))
    review_warm.rotate_shots(tmp_path, keep=24, max_bytes=10**9)
    left = list(tmp_path.glob("review-*.png"))
    assert len(left) == 24
    assert not (tmp_path / "review-x-0.png").exists()


def test_review_load_finds_market_reads_without_the_data_server():
    research = str(Path(review_load.__file__).resolve().parents[1] / "research")
    sys.path[:] = [entry for entry in sys.path if entry != research]
    assert review_load.ensure_research_path() == research
    assert research in sys.path
    assert importlib.util.find_spec("market_reads") is not None


def test_png_tool_returns_an_image_block(tmp_path):
    def shoot(_url, dest):
        dest.write_bytes(PNG)
        return {"ok": True, "path": str(dest), "sha256": "abc", "bytes": len(PNG), "png": PNG}

    server = nova_mcp.create_server(
        data.DataService(tmp_path), http=False, warm=True,
        shots=review_warm.ReviewShots(shoot=shoot),
    )
    result = asyncio.run(server.call_tool("nova_historical_chart", {"symbol": "IMCC", "date": DAY, "output": "png"}))
    blocks = result[0] if isinstance(result, tuple) else result
    images = [block for block in blocks if getattr(block, "type", None) == "image"]
    assert len(images) == 1
    assert images[0].mimeType == "image/png"
    raw = base64.b64decode(images[0].data)
    assert raw.startswith(b"\x89PNG\r\n\x1a\n") and len(raw) >= 64
