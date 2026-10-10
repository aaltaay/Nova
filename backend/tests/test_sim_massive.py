"""The Sim replays the operator's Massive flat files (ADR 046).

Small files in Massive's own format (one gzip CSV per dataset per day, every ticker,
sorted by ticker, quoted commas in the conditions) under a temporary root.
"""
from __future__ import annotations

import csv
import gzip
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sim import (
    broker, feed, history_playback as playback, history_routes, history_store, massive_days, massive_files,
    massive_import, massive_read, massive_store, mode, practice, replay, session_clock as clock,
)

ET = ZoneInfo("America/New_York")
DAY = "2026-09-18"
TRADES = "ticker,conditions,correction,exchange,id,participant_timestamp,price,sequence_number,sip_timestamp,size,tape,trf_id,trf_timestamp"
QUOTES = ("ticker,ask_exchange,ask_price,ask_size,bid_exchange,bid_price,bid_size,conditions,indicators,"
          "participant_timestamp,sequence_number,sip_timestamp,tape,trf_timestamp")
MINUTES = "ticker,volume,open,close,high,low,window_start,transactions"


def _sec(hms: str) -> int:
    return int(datetime.fromisoformat(f"{DAY}T{hms}").replace(tzinfo=ET).timestamp())


def _ns(hms: str, frac_ms: int = 0) -> int:
    return _sec(hms) * 10**9 + frac_ms * 10**6


def _conds(value: str) -> str:
    return f'"{value}"' if "," in value else value


def _trade(ticker, hms, ms, price, size, conds="", corr=0, ex=12, seq=1):
    ns = _ns(hms, ms)
    return f"{ticker},{_conds(conds)},{corr},{ex},{seq},{ns},{price},{seq},{ns},{size},3,0,0"


def _quote(ticker, hms, ms, bid, bsz, ask, asz, bx=12, ax=12):
    ns = _ns(hms, ms)
    return f"{ticker},{ax},{ask},{asz},{bx},{bid},{bsz},1,1,{ns},1,{ns},3,0"


def _minute(ticker, hms, o, c, h, low, v):
    return f"{ticker},{v},{o},{c},{h},{low},{_ns(hms)},12"


def _write(root, dataset, header, lines, *, newline_at_end=True):
    path = root / dataset / DAY[:4] / DAY[5:7] / f"{DAY}.csv.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="") as fh:
        fh.write(header + "\n" + "\n".join(lines) + ("\n" if newline_at_end else ""))
    return path


IMCC_TRADES = [
    _trade("IMCC", "09:29:59", 500, 9.90, 100, seq=1),             # before the window
    _trade("IMCC", "09:30:00", 100, 10.00, 100, seq=2),            # sets the price
    _trade("IMCC", "09:30:00", 200, 9.50, 10, "37", seq=3),        # odd lot: shown, never the last
    _trade("IMCC", "09:30:00", 300, 10.05, 200, "14,41", seq=4),   # quoted commas, sets the price
    _trade("IMCC", "09:30:01", 0, 10.10, 100, corr=8, seq=5),      # later cancelled: shown, sets nothing
    _trade("IMCC", "09:30:01", 500, 10.10, 100, corr=10, seq=6),   # the cancel record: not a trade
    _trade("IMCC", "09:30:02", 0, 10.02, 100, seq=7),
]
IMCC_QUOTES = [
    _quote("IMCC", "09:29:59", 0, 9.98, 500, 10.00, 300),           # stands at the window's open
    _quote("IMCC", "09:30:00", 150, 9.99, 400, 10.05, 200),
    _quote("IMCC", "09:30:00", 250, 0, 0, 10.05, 200),              # an empty bid side
    _quote("IMCC", "09:30:01", 200, 10.00, 100, 10.02, 100),
]


@pytest.fixture
def root(tmp_path, monkeypatch):
    base = tmp_path / "massive"
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(base))
    monkeypatch.setenv("NOVA_SIM_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setattr(massive_import, "launch", massive_import._launch_thread)   # one test below runs the real process
    massive_days.reset_for_tests()
    _write(base, "trades_v1", TRADES, [_trade("IMBX", "09:30:00", 0, 1.0, 1)] + IMCC_TRADES
           + [_trade("IMCCW", "09:30:00", 0, 0.5, 1), _trade("IMCD", "09:30:00", 0, 2.0, 1)])
    _write(base, "quotes_v1", QUOTES, [_quote("IMBX", "09:30:00", 0, 0.9, 1, 1.1, 1)] + IMCC_QUOTES
           + [_quote("IMCD", "09:30:00", 0, 1.9, 1, 2.1, 1)])
    _write(base, "minute_aggs_v1", MINUTES, [_minute("IMCC", "09:29:00", 9.9, 9.9, 9.9, 9.9, 100),
                                             _minute("IMCC", "09:30:00", 10.0, 10.02, 10.10, 9.50, 1000),
                                             _minute("IMCC", "09:59:00", 10.01, 10.0, 10.01, 10.0, 5),   # ends at 10:00: in
                                             _minute("IMCC", "10:00:00", 10.2, 10.2, 10.2, 10.2, 5)])    # after the window
    yield base
    _reset()


def _reset():
    clock.reset_for_tests()
    playback.clear()
    replay.clear_capture()
    broker.reset_for_tests()
    feed.reset_for_tests()
    massive_days.reset_for_tests()


def _window():
    return history_store.window("IMCC", DAY, "09:30", "10:00")


def _imported():
    spec = massive_import.spec(_window())
    job = massive_store.save(dict(massive_store.new_job(spec), status="running"))
    return spec, massive_import.run(job["id"])


def _at(monkeypatch, hms: str, ms: int = 0):
    moment = datetime.fromtimestamp(_sec(hms) + ms / 1000, ET)
    monkeypatch.setattr(clock, "now_et", lambda: moment)


# ---- reading the files ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("chunk", [7, 64, 1 << 20])
def test_one_tickers_block_is_found_across_any_chunking(root, monkeypatch, chunk):
    monkeypatch.setattr(massive_files, "SIM_MASSIVE_READ_CHUNK", chunk)
    path = massive_files.day_file("trades_v1", DAY)
    rows = list(massive_files.rows(path, "IMCC", lambda r: r))
    assert [r["sequence_number"] for r in rows] == ["1", "2", "3", "4", "5", "6", "7"]
    assert rows[3]["conditions"] == "14,41"                                    # the quoted commas stay one field
    assert [r["ticker"] for r in massive_files.rows(path, "IMCD", lambda r: r)] == ["IMCD"]
    assert [r["ticker"] for r in massive_files.rows(path, "IMCCW", lambda r: r)] == ["IMCCW"]
    for absent in ("IMCB", "ZZZZ", "AAAA"):
        assert list(massive_files.rows(path, absent, lambda r: r)) == []


def test_the_last_line_without_a_newline_is_read(root, monkeypatch):
    _write(root, "trades_v1", TRADES, IMCC_TRADES, newline_at_end=False)
    monkeypatch.setattr(massive_files, "SIM_MASSIVE_READ_CHUNK", 16)
    rows = list(massive_files.rows(massive_files.day_file("trades_v1", DAY), "IMCC", lambda r: r))
    assert len(rows) == len(IMCC_TRADES)


def test_a_file_still_arriving_is_not_on_disk(root):
    part = root / "trades_v1" / "2026" / "09" / "2026-09-17.csv.gz.part"
    part.write_bytes(b"\x1f\x8b")
    assert massive_files.day_file("trades_v1", "2026-09-17") is None
    assert massive_files.files_for(DAY) == {"trades_v1": True, "quotes_v1": True, "minute_aggs_v1": True}


def test_which_prints_set_a_price():
    def trade(conds, corr=0):
        fields = next(csv.reader([_trade("X", "09:30:00", 0, 1.0, 1, conds, corr)]))
        return massive_files.trade(dict(zip(TRADES.split(","), fields, strict=True)), "X")
    assert trade("")["sets_price"] and trade("14,41")["sets_price"] and trade("12")["sets_price"]
    for volume_only in ("37", "10,37,41", "10,2,41", "53,35,41", "7,12,37", "15", "16"):
        assert trade(volume_only)["sets_price"] is False, volume_only
    assert trade("", corr=12)["sets_price"] is True
    for busted in (1, 7, 8):
        assert trade("", corr=busted)["sets_price"] is False
    assert trade("", corr=10) is None and trade("", corr=11) is None
    assert trade("")["exchange"] == "NASDAQ" and trade("")["unreported"] is False


# ---- importing a stock-day --------------------------------------------------------------------------------------
def test_an_import_of_a_window_keeps_the_whole_stock_day(root):
    """Amendment 2026-10-09: the files are read once per stock-day, so an import keeps the whole session when
    it fits a selection, whatever window asked; the window is only its focus."""
    window = _window()
    started = massive_import.begin(window)
    assert (started["start"], started["end"]) == ("04:00", "20:00")
    assert (started["focus_start"], started["focus_end"]) == ("09:30", "10:00")
    job = _wait_day(window)
    day = massive_import.day_spec(window)
    assert job["status"] == "complete" and job["quote_status"] == "complete" and job["capped"] is None
    assert (job["kept_start"], job["kept_end"]) == ("04:00", "20:00")
    assert job["ranges"] == [[day["start_ts"], day["end_ts"]]]
    assert job["count"] == 6 and job["bar_count"] == 4 and job["quote_count"] == 4 and job["volume"] == 500
    assert job["minutes_scope"] == "day"
    prints = massive_store.read_prints(job["id"], "IMCC")
    assert [p["sequence"] for p in prints] == [1, 2, 3, 4, 5, 7]                     # 09:29:59 too: the day
    assert [p["sets_price"] for p in prints] == [True, True, False, True, False, True]
    assert prints[1]["ts"] == _sec("09:30:00") + 0.1 and prints[1]["ns"] == _ns("09:30:00", 100)
    quotes = massive_store.read_quotes(job["id"])
    assert quotes[0][0] == _sec("09:29:59") and quotes[2][1] is None                  # an empty bid side
    assert [c["o"] for c in massive_store.read_candles(job["id"])] == [9.9, 10.0, 10.01, 10.2]
    assert massive_store.find(massive_import.spec(window)) is None                     # no import of the window itself


def _reads(monkeypatch) -> dict[str, int]:
    """How many times each day file is streamed."""
    real, seen = massive_files.rows, {}

    def counted(path, *args, **kwargs):
        seen[path.parts[-4]] = seen.get(path.parts[-4], 0) + 1
        return real(path, *args, **kwargs)
    monkeypatch.setattr(massive_files, "rows", counted)
    return seen


@pytest.mark.parametrize("cap, limit, count", [("prints", 5, 6), ("quotes", 3, 4)])
def test_a_day_over_a_cap_keeps_the_focus_window_from_the_same_read(root, monkeypatch, cap, limit, count):
    monkeypatch.setattr(massive_read, "SIM_HISTORY_MAX_SELECTION_PRINTS" if cap == "prints"
                        else "SIM_MASSIVE_MAX_SELECTION_QUOTES", limit)
    reads = _reads(monkeypatch)
    window = _window()
    massive_import.begin(window)
    job = _wait_day(window)
    assert reads == {"trades_v1": 1, "quotes_v1": 1, "minute_aggs_v1": 1}             # one read, never a second
    assert job["status"] == "complete" and job["capped"] == dict(what=cap, count=count, limit=limit)
    assert (job["kept_start"], job["kept_end"]) == ("09:30", "10:00")
    assert job["ranges"] == [[window["start_ts"], window["end_ts"]]]
    assert [p["sequence"] for p in massive_store.read_prints(job["id"], "IMCC")] == [2, 3, 4, 5, 7]
    quotes = massive_store.read_quotes(job["id"])
    assert quotes[0][0] == _sec("09:29:59") and len(quotes) == 4                     # the quote standing at 09:30 first
    assert job["bar_count"] == 4                                                      # the day's bars, always whole
    assert massive_import.held_spec(job)["start"] == "09:30"
    later = history_store.window("IMCC", DAY, "10:00", "11:00")
    assert massive_import.holds(job, window) and not massive_import.holds(job, later)
    assert massive_import.wants_import(later, massive_import.availability(DAY)) is True


def test_a_day_whose_quotes_are_not_on_disk_imports_again_when_they_arrive(root):
    quotes = massive_files.day_file("quotes_v1", DAY)
    held = quotes.read_bytes()
    quotes.unlink()
    window = _window()
    massive_import.begin(window)
    job = _wait_day(window)
    assert job["quote_status"] == "not_downloaded" and job["quote_count"] == 0 and job["count"] == 6
    quotes.write_bytes(held)
    assert massive_import.begin(window)["status"] == "running"
    assert _wait_day(window)["quote_status"] == "complete"


def _wait_day(window, timeout=20.0):
    return _wait_complete(massive_import.day_spec(window), timeout)


def _wait_complete(spec, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = massive_store.find(spec)
        if job and job["status"] in ("complete", "failed", "paused"):
            return job
        time.sleep(0.05)
    raise AssertionError("the import did not finish")


def test_a_window_over_the_selection_cap_is_refused_before_anything_is_written(root, monkeypatch):
    monkeypatch.setattr(massive_read, "SIM_HISTORY_MAX_SELECTION_PRINTS", 2)
    window = _window()
    massive_import.begin(window)
    job = _wait_day(window)                     # the day is over the cap, and so is the window asked for
    assert job["status"] == "failed" and job["error"] == "IMCC printed over 2 in this window, more than a replay holds; narrow the window"
    assert massive_store.read_prints(job["id"], "IMCC") == []


def test_a_paused_import_writes_nothing(root, monkeypatch):
    monkeypatch.setattr(massive_files, "SIM_MASSIVE_READ_CHUNK", 16)       # many chunks, so a reader is mid-file
    spec = massive_import.spec(_window())
    job = massive_store.save(dict(massive_store.new_job(spec), status="running"))
    stop = threading.Event()
    stop.set()
    massive_import._worker(job["id"], stop)
    assert massive_store.get(job["id"])["status"] == "paused"
    assert massive_store.read_prints(job["id"], "IMCC") == []


def test_one_reader_failing_ends_the_import_with_its_reason(root, monkeypatch):
    real = massive_files.quote

    def broken(row):
        raise OSError("disk read failed")
    monkeypatch.setattr(massive_files, "quote", broken)
    spec = massive_import.spec(_window())
    job = massive_store.save(dict(massive_store.new_job(spec), status="running"))
    massive_import._worker(job["id"], threading.Event())
    failed = massive_store.get(job["id"])
    assert failed["status"] == "failed" and failed["error"] == "disk read failed"
    monkeypatch.setattr(massive_files, "quote", real)


def test_the_desk_imports_in_its_own_process(root, monkeypatch):
    monkeypatch.setattr(massive_import, "launch", massive_import._launch_process)
    window = _window()
    started = massive_import.begin(window)
    assert started["status"] == "running" and massive_import.running_ids()
    job = _wait_day(window, timeout=60.0)
    assert job["status"] == "complete" and job["count"] == 6 and job["quote_status"] == "complete"
    assert massive_import.worker_command("x")[1:3] == ["-m", "sim.massive_worker"]


def test_pausing_ends_the_import_process_and_a_crash_says_so(root):
    import subprocess
    import sys

    def running_job(symbol):
        spec = massive_import.spec(history_store.window(symbol, DAY, "09:30", "10:00"))
        massive_store.save(dict(massive_store.new_job(spec), status="running"))
        return spec

    slow = running_job("IMBX")
    handle = massive_import._ProcessHandle(massive_store.job_id_for(slow),
                                           subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"]))
    massive_import._active[handle.job_id] = handle
    massive_import._watch(handle, None)
    massive_import.pause(handle.job_id)
    assert _wait_complete(slow)["status"] == "paused"
    assert handle.job_id not in massive_import._active

    crashed = running_job("IMCD")
    massive_import._watch(massive_import._ProcessHandle(massive_store.job_id_for(crashed),
                                                        subprocess.Popen([sys.executable, "-c", "raise SystemExit(3)"])), None)
    job = _wait_complete(crashed)
    assert job["status"] == "failed" and "exit code 3" in job["error"]


def test_a_day_with_no_trades_file_is_refused_with_the_reason(root):
    with pytest.raises(ValueError, match="not on disk"):
        massive_import.begin(history_store.window("IMCC", "2026-09-17", "09:30", "10:00"))


def test_a_running_import_no_one_advances_lists_as_interrupted(root):
    spec = massive_import.spec(_window())
    job = massive_store.save(dict(massive_store.new_job(spec), status="running"))
    assert massive_import.effective_status(job, now=job["updated"] + massive_import.STALE_AFTER_SEC + 1) == "interrupted"
    assert massive_import.effective_status(job, now=job["updated"] + 1) == "running"


# ---- replaying it -----------------------------------------------------------------------------------------------
def test_bid_ask_last_and_sides_never_read_ahead(root, monkeypatch):
    spec, _job = _imported()
    playback.select(spec)
    _at(monkeypatch, "09:30:00", 260)
    snap = playback.snapshot("IMCC")
    assert (snap["bid"], snap["ask"], snap["ask_size"]) == (None, 10.05, 200)       # the 09:30:00.250 quote
    assert snap["quote_source"] == "massive_nbbo" and snap["quote_status"] == "complete"
    assert snap["last"] == 10.00 and snap["volume"] == 100                           # the odd lot sets nothing
    tape = {p["sequence"]: p for p in snap["prints"]}
    assert set(tape) == {2, 3}
    assert (tape[2]["side"], tape[2]["ask"]) == ("ask", 10.00)                       # vs the quote at the open
    assert (tape[3]["side"], tape[3]["bid"]) == ("bid", 9.99)                        # vs 09:30:00.150, not .250
    assert tape[2]["side_source"] == "nbbo" and snap["sides_nbbo"] == 2 and snap["sides_recorded"] == 0
    _at(monkeypatch, "09:30:01", 300)
    snap = playback.snapshot("IMCC")
    assert (snap["bid"], snap["ask"]) == (10.00, 10.02)
    assert snap["last"] == 10.05 and snap["volume"] == 300                           # the busted trade sets nothing
    assert snap["depth"]["l1_fallback"] is True and snap["depth"]["source"] == "massive_nbbo"
    assert snap["depth"]["bids"][0]["price"] == 10.00 and snap["depth"]["asks"][0]["size"] == 100


def test_practice_orders_see_the_bid_and_ask(root, monkeypatch):
    spec, _job = _imported()
    playback.select(spec)
    _at(monkeypatch, "09:30:01", 300)
    ref = practice.reference("IMCC")
    assert (ref.last, ref.bid, ref.ask) == (10.05, 10.00, 10.02)


def test_a_print_meets_the_nbbo_that_stood_before_it_not_the_playheads(root, monkeypatch):
    """PR #786 review: the SSR fill rule reads the bid before each print, wherever the playhead is."""
    spec, _job = _imported()
    playback.select(spec)
    _at(monkeypatch, "09:30:02", 500)
    assert practice.reference("IMCC").bid == 10.00                                   # the playhead's
    assert practice.bid_at("IMCC", _sec("09:30:00") + 0.100) == 9.98                # the quote before 09:30:00.100
    assert practice.bid_at("IMCC", _sec("09:30:02")) == 10.00
    assert practice.bid_at("IMCC", _sec("09:30:00") + 0.300) is None                # an empty bid side then
    assert practice.bid_at("IMCD", _sec("09:30:02")) is None                        # not the window's symbol


def test_a_massive_window_draws_its_own_bars_never_the_ibkr_chart_store(root, monkeypatch):
    import bars_store

    def refused(*_a, **_k):
        raise AssertionError("the IBKR chart store must not stand in under a Massive tape")
    monkeypatch.setattr(bars_store, "read", refused)
    spec, _job = _imported()
    playback.select(spec)
    archive = playback._selection.candles.archive("IMCC", "1Min")
    # The day before the window is drawn from the files too; nothing past the window's end.
    assert [row["o"] for _ts, row in archive] == [9.9, 10.0, 10.01]


def test_the_day_before_the_window_is_drawn_never_past_the_playhead(root, monkeypatch):
    from sim import chart_replay

    spec, _job = _imported()
    playback.select(spec)
    early = playback.bars("IMCC", "1Min", 50, datetime.fromtimestamp(_sec("09:30:00") + 0.05, ET))
    assert [bar["o"] for bar in early] == [9.9]                  # 09:29, before the window; 09:30 not reached
    _at(monkeypatch, "09:30:00", 50)
    labelled = chart_replay.fetch_replay_bars("IMCC", "1Min", 50)
    assert labelled["source"] == "massive"


def test_an_import_without_the_days_bars_is_imported_again_once_they_are_on_disk(root):
    window = _window()
    massive_import.begin(window)
    job = _wait_day(window)
    massive_store.update(job["id"], minutes_scope=None)
    assert massive_import.wants_import(window, massive_import.availability(DAY)) is True
    massive_store.update(job["id"], minutes_scope="day")
    assert massive_import.wants_import(window, massive_import.availability(DAY)) is False
    elsewhere = history_store.window("IMCC", DAY, "06:45", "09:00")
    assert massive_import.wants_import(elsewhere, massive_import.availability(DAY)) is False   # the day holds it


def test_an_older_window_import_is_upgraded_to_its_stock_day(root):
    """An import of one window, made before stock-days: it keeps playing; the day's import, once it holds the
    window, drops it in the same transaction."""
    spec, older = _imported()
    other = massive_import.spec(history_store.window("IMCD", DAY, "09:30", "10:00"))     # another stock-day
    massive_store.save(dict(massive_store.new_job(other), status="failed"))
    assert massive_import.day_job(_window()) is None
    assert massive_import.wants_import(_window(), massive_import.availability(DAY)) is True
    selected = playback.select(spec)
    assert selected["trade_count"] == 5 and selected["job_id"] == older["id"]          # it still plays
    massive_import.begin(_window())
    day = _wait_day(_window())
    assert day["count"] == 6 and massive_store.get(older["id"]) is None
    assert massive_store.read_prints(older["id"], "IMCC") == []
    assert massive_store.find(other) is not None


def test_a_capped_day_keeps_an_older_import_of_the_window_asked_for(root, monkeypatch):
    spec, older = _imported()
    monkeypatch.setattr(massive_read, "SIM_HISTORY_MAX_SELECTION_PRINTS", 5)
    elsewhere = history_store.window("IMCC", DAY, "09:00", "09:30")
    massive_import.begin(elsewhere)
    day = _wait_day(elsewhere)
    assert day["capped"]["what"] == "prints" and (day["kept_start"], day["kept_end"]) == ("09:00", "09:30")
    assert massive_store.get(older["id"]) is not None                                   # outside what the day kept
    assert massive_import.wants_import(_window(), massive_import.availability(DAY)) is False


def test_gap_reads_the_windows_own_0930_bar_never_the_ibkr_chart_store(root, monkeypatch):
    import bars_store

    def refused(*_a, **_k):
        raise AssertionError("the IBKR chart store must not stand in under a Massive tape")
    monkeypatch.setattr(bars_store, "read", refused)
    window = history_store.window("IMCC", DAY, "09:45", "10:00")    # the window does not hold 09:30
    spec = massive_import.spec(window)
    job = massive_store.save(dict(massive_store.new_job(spec), status="running"))
    massive_import.run(job["id"])
    playback.select(spec)
    assert playback._selection.session_open == (_sec("09:30:00"), 10.0)


def test_a_window_before_its_import_completes_is_empty_not_ibkr(root):
    spec = massive_import.spec(_window())
    massive_store.save(dict(massive_store.new_job(spec), status="running"))
    selected = playback.select(spec)
    assert selected["download_status"] == "running" and selected["trade_count"] == 0
    assert selected["source"] == "massive"


# ---- the routes -------------------------------------------------------------------------------------------------
@pytest.fixture
def client(root, monkeypatch):
    monkeypatch.setattr(mode, "is_sim_mode", lambda: True)
    app = FastAPI()
    app.include_router(history_routes.router)
    return TestClient(app)


def test_auto_downloads_and_selects_from_massive_when_the_day_is_on_disk(client):
    body = dict(symbol="IMCC", date=DAY, start="09:30", end="10:00")
    job = client.post("/api/sim/history", json=body).json()
    assert job["source"] == "massive" and job["status"] in ("running", "complete")
    _wait_day(_window())
    listing = client.get("/api/sim/history").json()
    assert listing["massive"]["available"] is True and listing["massive"]["trade_days"] == 1
    assert [j["source"] for j in listing["jobs"]] == ["massive"] and listing["jobs"][0]["progress_pct"] == 100
    selected = client.post("/api/sim/history/select", json=body).json()
    assert selected["source"] == "massive" and selected["trade_count"] == 6 and selected["quote_status"] == "complete"
    assert (selected["start"], selected["end"]) == ("04:00", "20:00")                # what the import holds: the day
    snap = client.get("/api/sim/history/snapshot/IMCC").json()
    assert "bid" in snap and snap["quote_source"] == "massive_nbbo"


def test_selecting_a_day_on_disk_starts_its_import(client):
    body = dict(symbol="IMCC", date=DAY, start="09:30", end="10:00")
    selected = client.post("/api/sim/history/select", json=body).json()
    assert selected["source"] == "massive" and selected["download_status"] in ("running", "complete")
    assert (selected["start"], selected["end"]) == ("09:30", "10:00")                # empty until it lands
    assert selected["job_id"] == massive_store.job_id_for(massive_import.day_spec(_window()))
    assert _wait_day(_window())["status"] == "complete"
    again = client.post("/api/sim/history/select", json=body).json()
    assert again["trade_count"] == 6 and (again["start"], again["end"]) == ("04:00", "20:00")


def test_a_scrub_elsewhere_on_the_stock_day_plays_with_no_new_import(client, monkeypatch):
    """The WFF tab, 2026-10-09: a playhead moved from premarket to 10:05 started a second read of the same day."""
    reads = _reads(monkeypatch)
    early = dict(symbol="IMCC", date=DAY, start="06:45", end="09:00")
    client.post("/api/sim/history/select", json=early)
    first = _wait_day(_window())
    late = dict(symbol="IMCC", date=DAY, start="09:15", end="11:30")
    loaded = client.post("/api/sim/history/select", json=late).json()
    assert loaded["trade_count"] == 6 and (loaded["start"], loaded["end"]) == ("04:00", "20:00")
    assert client.post("/api/sim/history", json=late).json()["id"] == first["id"]       # a download answers the day
    assert reads == {"trades_v1": 1, "quotes_v1": 1, "minute_aggs_v1": 1}
    jobs = client.get("/api/sim/history").json()["jobs"]
    assert [(j["id"], j["started"]) for j in jobs] == [(first["id"], first["started"])]


def test_loading_from_the_files_keeps_the_playhead_where_it_was_placed(client):
    """Loading WFF's day moved the playhead from 10:05 to the window's 09:15; a placed playhead now stays."""
    clock.set_session_date(DAY)
    clock.scrub_to_second(_sec("10:05:00") - _sec("04:00:00"))
    body = dict(symbol="IMCC", date=DAY, start="09:15", end="11:30")
    client.post("/api/sim/history/select", json=body)
    _wait_day(_window())
    client.post("/api/sim/history/select", json=body)
    assert abs(clock.now_et().timestamp() - _sec("10:05:00")) < 5
    assert clock.status_payload()["session_open_et"].startswith(f"{DAY}T04:00")
    outside = dict(symbol="IMCC", date=DAY, start="12:00", end="13:00")                 # asked elsewhere: its start
    client.post("/api/sim/history/select", json=outside)
    assert abs(clock.now_et().timestamp() - _sec("12:00:00")) < 5


def test_loading_again_once_the_quotes_arrive_adds_them_while_the_window_keeps_playing(client, monkeypatch):
    quotes = massive_files.day_file("quotes_v1", DAY)
    held = quotes.read_bytes()
    quotes.unlink()
    body = dict(symbol="IMCC", date=DAY, start="09:30", end="10:00")
    spec = massive_import.day_spec(_window())
    client.post("/api/sim/history/select", json=body)
    _wait_complete(spec)
    first = client.post("/api/sim/history/select", json=body).json()
    assert first["trade_count"] == 6 and first["quote_status"] == "not_downloaded"
    quotes.write_bytes(held)
    gate = threading.Event()
    real_run = massive_import.run

    def held_run(job_id, stop=None):
        gate.wait(10)                                   # the re-import waits, so the window is read while it runs
        return real_run(job_id, stop)
    monkeypatch.setattr(massive_import, "run", held_run)
    during = client.post("/api/sim/history/select", json=body).json()
    assert during["download_status"] == "running" and during["trade_count"] == 6
    assert during["quote_status"] == "not_downloaded"
    gate.set()
    assert _wait_complete(spec)["quote_status"] == "complete"
    after = client.post("/api/sim/history/select", json=body).json()
    assert after["quote_status"] == "complete" and after["quote_count"] == 4 and after["download_status"] == "complete"
    assert massive_import.wants_import(_window(), massive_import.availability(DAY)) is False


def test_auto_puts_the_massive_files_over_a_window_already_downloaded_from_ibkr(client):
    """Operator, 2026-10-09: the files carry the whole tape and the bid and ask; an IBKR copy of the
    same hours no longer wins just because it was downloaded first."""
    window = _window()
    history_store.create(window, "trades")
    body = dict(symbol="IMCC", date=DAY, start="09:30", end="10:00")
    selected = client.post("/api/sim/history/select", json=body).json()
    assert selected["source"] == "massive"
    assert _wait_day(window)["status"] == "complete"
    again = client.post("/api/sim/history/select", json=body).json()
    assert again["source"] == "massive" and again["trade_count"] == 6 and again["quote_status"] == "complete"


def test_auto_plays_the_ibkr_download_when_the_files_import_of_it_failed(client):
    window = _window()
    history_store.create(window, "trades")
    spec = massive_import.day_spec(window)
    massive_store.save(dict(massive_store.new_job(spec), status="failed", error="Replay exceeds 500,000 prints"))
    selected = client.post("/api/sim/history/select",
                           json=dict(symbol="IMCC", date=DAY, start="09:30", end="10:00")).json()
    assert selected["source"] == "ibkr_historical"
    assert massive_store.find(spec)["status"] == "failed"          # not started again behind the download


def test_auto_keeps_an_ibkr_download_of_a_day_the_files_do_not_hold(client):
    window = history_store.window("IMCC", "2026-09-17", "09:30", "10:00")
    history_store.create(window, "trades")
    selected = client.post("/api/sim/history/select",
                           json=dict(symbol="IMCC", date="2026-09-17", start="09:30", end="10:00")).json()
    assert selected["source"] == "ibkr_historical"


def test_the_days_on_disk_are_listed_for_the_calendar(client):
    days = client.get("/api/sim/history/massive/days").json()
    assert days["available"] is True and days["days"] == [dict(date=DAY, trades=True, quotes=True, minute_aggs=True)]
    one = client.get(f"/api/sim/history/massive/{DAY}").json()
    assert one["available"] is True and one["quotes"] is True
    assert client.get("/api/sim/history/massive/2026-13-45").status_code == 422
    assert client.get("/api/sim/history/massive/2026-09-17").json()["available"] is False


def test_an_unreadable_import_store_is_stated_not_listed_as_empty(client, monkeypatch):
    import sqlite3

    def broken():
        raise sqlite3.DatabaseError("Unsupported Massive replay store version 9")
    monkeypatch.setattr(massive_store, "jobs", broken)
    listing = client.get("/api/sim/history").json()
    assert listing["jobs"] == [] and "cannot be read" in listing["massive"]["store_error"]
    assert "version 9" in listing["massive"]["store_error"]


def test_no_massive_folder_is_a_stated_absence(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path / "nowhere"))
    massive_days.reset_for_tests()
    summary = massive_days.summary()
    assert summary["available"] is False and "No Massive folder" in summary["reason"] and summary["trade_days"] == 0
