"""AllLast producer -> independent real JSONL/SQLite sinks; no broker needed."""

import asyncio
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from capture import bridge_ibkr, mode, recorder, worker
from ibkr import tape_recording as fanout, tape_stream
from l2 import db, tape


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_CAPTURE_DIR", str(tmp_path / "capture"))
    mode.set_capture_mode(False)
    recorder.reset_for_tests()
    mode.reset_for_tests()
    tape.clear_watched_for_tests()
    fanout._last.clear()
    fanout._errors.clear()
    fanout.dispatch_errors.clear()
    monkeypatch.setattr(fanout, "l2_sink", fanout.Sink(fanout._write_l2))
    monkeypatch.setattr(tape_stream, "_tickers", {"AAPL": {}})
    monkeypatch.setattr(tape_stream._client, "get_ib", lambda: object())
    monkeypatch.setattr(tape_stream._depth, "current_book", lambda _: None)
    # Existing archive tests own that independent sink; keep these files isolated.
    from archive import write_queue, bar_builder
    from ibkr import tape_10sec

    monkeypatch.setattr(write_queue, "enqueue_tape_print", lambda **kw: None)
    monkeypatch.setattr(bar_builder, "on_tape_print", lambda **kw: None)
    monkeypatch.setattr(tape_10sec, "on_print", lambda *a: None)
    db.init_db()
    yield
    mode.set_capture_mode(False)
    fanout.l2_sink.queue.join()
    fanout.l2_sink.close()
    tape.clear_watched_for_tests()
    fanout._last.clear()
    fanout._errors.clear()
    fanout.dispatch_errors.clear()


def tick(symbol="AAPL", price=42.25):
    ticker = SimpleNamespace(
        tickByTicks=[
            SimpleNamespace(
                time=datetime(2026, 9, 18, 14, 30, tzinfo=timezone.utc),
                price=price,
                size=7,
                exchange="NASDAQ",
                specialConditions="T",
            )
        ]
    )
    tape_stream._on_tape_update(ticker, symbol)


def test_callback_persists_identical_provenance_to_both_sinks():
    tape.watch_symbol("AAPL", "session-a")
    started = mode.set_capture_mode(True, symbol="AAPL")
    assert started["capture"]
    assert "error" not in started  # pending first print is not a failed command
    assert not mode.status_payload()["healthy"]  # waiting is not healthy
    tick("MSFT", 9)  # wrong symbol must not enter this capture or L2 watch
    tick()
    mode.set_capture_mode(False)  # drains accepted capture rows
    directory = Path(recorder.status()["dir"])
    assert directory.parent.name == "2026-09-18"  # event date, not the test wall date
    fanout.l2_sink.queue.join()
    captured = json.loads((directory / "prints.jsonl").read_text())
    rows = tape.get_trades_in_range("AAPL", 0, 2_000_000_000)
    assert len(rows) == 1
    for field in ("symbol", "ts", "price", "size", "exchange", "conditions", "source", "receive_ts"):
        assert captured[field] == rows[0][field]
    assert rows[0]["session_id"] == "session-a"
    assert captured["source"] == "ibkr"
    assert (directory / "quotes.jsonl").stat().st_size == 0
    assert (directory / "l2.jsonl").stat().st_size == 0
    assert json.loads((directory / "manifest.json").read_text())["counts"]["prints"] == 1


def test_admission_rejects_wrong_disconnected_and_rejected_producer(monkeypatch, tmp_path):
    assert "subscribed" in mode.set_capture_mode(True, symbol="MSFT")["error"]
    fanout.rejected("AAPL", "market data permission denied")
    assert "permission" in mode.set_capture_mode(True, symbol="AAPL")["error"]
    fanout.subscribed("AAPL")
    monkeypatch.setattr(tape_stream._client, "get_ib", lambda: None)
    assert "connected" in mode.set_capture_mode(True, symbol="AAPL")["error"]
    assert not list(tmp_path.rglob("manifest.json"))


def test_empty_segment_fails_manifest_and_sim_provenance_is_truthful():
    mode.set_capture_mode(True, symbol="AAPL")
    directory = Path(recorder.status()["dir"])
    mode.set_capture_mode(False)
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["status"] == "failed"
    assert "No IBKR prints" in manifest["error"]
    mode.set_capture_mode(True, symbol="SIM1")
    directory = Path(recorder.status()["dir"])
    mode.set_capture_mode(False)
    assert json.loads((directory / "manifest.json").read_text())["source"] == "sim"


def test_blocked_capture_does_not_block_l2_viewer_or_event_loop(monkeypatch):
    entered, release, l2_done = threading.Event(), threading.Event(), threading.Event()
    original = recorder.record_print

    def blocked(payload):
        entered.set()
        assert release.wait(5)
        return original(payload)

    monkeypatch.setattr(recorder, "record_print", blocked)

    def write_l2(payload):
        fanout._write_l2(payload)
        l2_done.set()

    monkeypatch.setattr(fanout, "l2_sink", fanout.Sink(write_l2))
    mode.set_capture_mode(True, symbol="AAPL")
    tape.watch_symbol("AAPL")

    async def run():
        q = tape_stream.open_viewer_queue("AAPL")
        try:
            tick()
            assert await asyncio.to_thread(entered.wait, 5)
            assert await asyncio.to_thread(l2_done.wait, 5)
            assert q.get_nowait()["price"] == 42.25
            heartbeat = asyncio.Event()
            asyncio.get_running_loop().call_soon(heartbeat.set)
            await asyncio.wait_for(heartbeat.wait(), 1)
        finally:
            release.set()
            tape_stream.close_viewer_queue("AAPL", q)

    asyncio.run(run())


def test_l2_overflow_is_sticky_and_capture_continues(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def blocked(payload):
        entered.set()
        assert release.wait(5)

    sink = fanout.Sink(blocked, capacity=1)
    monkeypatch.setattr(fanout, "l2_sink", sink)
    tape.watch_symbol("AAPL")
    mode.set_capture_mode(True, symbol="AAPL")
    try:
        tick()
        assert entered.wait(5)
        tick()
        tick()
        assert "backlog full" in tape.health()["writer"]["error"]
        assert not tape.health()["healthy"]
    finally:
        release.set()
    mode.set_capture_mode(False)
    assert recorder.status()["counts"]["prints"] == 3


def test_sink_failure_is_visible_and_payload_is_immutable(monkeypatch):
    def fail(payload):
        payload["price"] = 0

    sink = fanout.Sink(fail)
    monkeypatch.setattr(fanout, "l2_sink", sink)
    tape.watch_symbol("AAPL")
    tick()
    sink.queue.join()
    assert "write failed" in tape.health()["writer"]["error"]
    assert not sink.submit({"price": 4})


def test_disconnect_and_staleness_are_loud(monkeypatch):
    mode.set_capture_mode(True, symbol="AAPL")
    tick()
    worker.transition(lambda: None)  # drain
    assert mode.status_payload()["healthy"]
    fanout._last["AAPL"] = 1
    assert "stale" in mode.status_payload()["error"]
    monkeypatch.setattr(tape_stream._client, "get_ib", lambda: None)
    assert "connected" in mode.status_payload()["error"]


def test_nonfinite_prices_never_reach_recorders():
    mode.set_capture_mode(True, symbol="AAPL")
    for price in (float("nan"), float("inf"), 0, -1):
        tick(price=price)
    mode.set_capture_mode(False)
    assert recorder.status()["counts"]["prints"] == 0


def test_schema_upgrade_and_past_missing_tape_audit():
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO l2_snapshots (recording_id,symbol,setup,signal_ts,ts,bids_json,asks_json) VALUES ('old','AAPL','depth',1,1,'[]','[]')"
    )
    conn.commit()
    conn.close()
    db.init_db()  # repeated migration is safe
    assert tape.audit_coverage()["sessions_without_tape"] == 1
    tape.watch_symbol("AAPL")
    tape.on_trade_print("AAPL", 2, 1, ts=1)
    assert tape.audit_coverage()["sessions_without_tape"] == 0


def test_legacy_schema_migrates_without_losing_existing_rows():
    conn = db.get_connection()
    conn.execute("DROP TABLE tape_trades")
    conn.execute(
        "CREATE TABLE tape_trades (id INTEGER PRIMARY KEY, symbol TEXT, ts REAL, price REAL, size REAL, exchange TEXT, source TEXT, session_id TEXT)"
    )
    conn.execute("INSERT INTO tape_trades VALUES (1,'AAPL',1,2,3,'X','ibkr','old')")
    conn.commit()
    conn.close()
    db.init_db()
    db.init_db()
    row = tape.get_trades_in_range("AAPL", 0, 2)[0]
    assert row["price"] == 2
    assert row["conditions"] is None
    assert row["receive_ts"] is None


def test_delayed_l2_row_retains_original_session(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def blocked(payload):
        entered.set()
        assert release.wait(5)
        fanout._write_l2(payload)

    monkeypatch.setattr(fanout, "l2_sink", fanout.Sink(blocked))
    tape.watch_symbol("AAPL", "old")
    try:
        tick()
        assert entered.wait(5)
        tape.unwatch_symbol("AAPL")
        tape.watch_symbol("AAPL", "new")
    finally:
        release.set()
    fanout.l2_sink.queue.join()
    assert tape.get_trades_in_range("AAPL", 0, 2_000_000_000)[0]["session_id"] == "old"
    assert not tape.health()["symbols"]["AAPL"]["healthy"]


def test_capture_overflow_does_not_stop_l2(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = recorder.record_print

    def blocked(payload):
        entered.set()
        assert release.wait(5)
        return original(payload)

    monkeypatch.setattr(recorder, "record_print", blocked)
    monkeypatch.setattr(worker, "CAPTURE_PENDING_BATCHES", 1)
    mode.set_capture_mode(True, symbol="AAPL")
    tape.watch_symbol("AAPL")
    try:
        tick()
        assert entered.wait(5)
        tick()
        assert "backlog full" in mode.status_payload()["error"]
    finally:
        release.set()
    mode.set_capture_mode(False)
    fanout.l2_sink.queue.join()
    assert len(tape.get_trades_in_range("AAPL", 0, 2_000_000_000)) == 2
    assert fanout.l2_sink.status()["error"] is None


def test_shutdown_drains_accepted_rows_and_closes_ingress():
    rows = []
    sink = fanout.Sink(rows.append)
    assert sink.submit({"price": 1})
    assert sink.submit({"price": 2})
    sink.close()
    assert [row["price"] for row in rows] == [1, 2]
    assert not sink.thread.is_alive()
    assert not sink.submit({"price": 3})


# --- D-064: quote / Level 2 capture for a real IBKR symbol -------------------


def push_depth(symbol="AAPL", bids=((42.20, 300),), asks=((42.30, 400),)):
    """Drive the real ib_async depth handler, not the shared broadcast channel."""
    from ibkr.depth.handlers import on_update_book

    def level(price, size):
        return SimpleNamespace(price=price, size=size, marketMaker="ARCA")

    ticker = SimpleNamespace(domBids=[level(p, s) for p, s in bids],
                             domAsks=[level(p, s) for p, s in asks])
    on_update_book(ticker, symbol)


def push_l1(symbol="AAPL", bid=42.20, bid_size=300, ask=42.30, ask_size=400):
    from ibkr.depth.handlers import on_update_ticker

    on_update_ticker(
        SimpleNamespace(bid=bid, bidSize=bid_size, ask=ask, askSize=ask_size), symbol)


def rows(directory, name):
    text = (Path(directory) / (name + ".jsonl")).read_text().strip()
    return [json.loads(line) for line in text.splitlines() if line]


@pytest.fixture(autouse=True)
def book_bridge_reset():
    from ibkr.depth import state as depth_state

    bridge_ibkr.reset_for_tests()
    depth_state.reset_all()  # the handlers write _subscriptions; do not leak it
    yield
    bridge_ibkr.reset_for_tests()
    depth_state.reset_all()


def test_sim_and_replay_books_never_enter_a_live_capture():
    """`state.push_book` is shared with sim/feed and sim/market.

    Hooking the capture bridge there recorded SIM and replay books into a live
    IBKR capture, stamped with wall clock while the sim bridge stamps sim
    session time -- which tripped the recorder's timestamp-regression stop and
    ended the recording. Caught end to end against a running API, not by a
    unit test, so it is pinned here.
    """
    from ibkr.depth import state as depth_state

    mode.set_capture_mode(True, symbol="AAPL")
    tick()
    depth_state.push_book("AAPL", {
        "bids": [{"price": 1.0, "size": 1}], "asks": [], "l1_fallback": False})
    mode.set_capture_mode(False)
    directory = Path(recorder.status()["dir"])

    assert (directory / "quotes.jsonl").stat().st_size == 0
    assert (directory / "l2.jsonl").stat().st_size == 0
    assert recorder.status()["fidelity"]["timestamp_regressions"] == 0


def test_depth_book_records_quote_and_l2_with_ibkr_provenance():
    mode.set_capture_mode(True, symbol="AAPL")
    tick()
    push_depth()
    mode.set_capture_mode(False)  # drains, rotating onto the print event date
    directory = Path(recorder.status()["dir"])

    quote = rows(directory, "quotes")[0]
    assert (quote["bid"], quote["bid_size"]) == (42.20, 300.0)
    assert (quote["ask"], quote["ask_size"]) == (42.30, 400.0)
    assert quote["source"] == "ibkr"
    depth_row = rows(directory, "l2")[0]
    assert depth_row["bids"] == [{"price": 42.20, "size": 300.0}]
    assert depth_row["asks"] == [{"price": 42.30, "size": 400.0}]
    assert depth_row["source"] == "ibkr"
    counts = json.loads((directory / "manifest.json").read_text())["counts"]
    assert counts["quotes"] == 1 and counts["l2"] == 1


def test_l1_fallback_book_records_a_quote_but_never_claims_depth():
    mode.set_capture_mode(True, symbol="AAPL")
    tick()
    push_l1()
    mode.set_capture_mode(False)
    directory = Path(recorder.status()["dir"])

    assert rows(directory, "quotes")[0]["bid"] == 42.20
    assert (directory / "l2.jsonl").stat().st_size == 0


def test_book_for_another_symbol_and_empty_books_are_never_recorded():
    mode.set_capture_mode(True, symbol="AAPL")
    tick()
    push_depth("MSFT")  # not the recorded symbol
    push_depth("AAPL", bids=(), asks=())  # empty book -- nothing observed yet
    mode.set_capture_mode(False)
    directory = Path(recorder.status()["dir"])

    assert (directory / "quotes.jsonl").stat().st_size == 0
    assert (directory / "l2.jsonl").stat().st_size == 0


def test_fast_books_coalesce_before_the_worker_backlog_can_stop_the_session():
    mode.set_capture_mode(True, symbol="AAPL")
    tick()
    for i in range(worker.CAPTURE_PENDING_BATCHES * 2):
        push_depth(bids=((42.20 + i / 1000, 300),))
    assert recorder.status()["error"] is None  # backlog never filled
    health = bridge_ibkr.book_health("AAPL")
    mode.set_capture_mode(False)
    directory = Path(recorder.status()["dir"])

    assert health["books_coalesced"] > 0
    assert len(rows(directory, "quotes")) < worker.CAPTURE_PENDING_BATCHES


def test_status_warns_when_the_recorded_symbol_has_no_depth_line():
    mode.set_capture_mode(True, symbol="AAPL")
    tick()
    status = mode.status_payload()
    mode.set_capture_mode(False)

    assert status["book"]["subscribed"] is False
    assert "quotes and Level 2 do not" in status["warning"]


# --- Codex review on #415 -------------------------------------------------


def test_the_newest_coalesced_book_is_kept_not_dropped():
    """A burst that then goes quiet must not leave a stale book recorded.

    The first coalescer dropped everything after the first update in an
    interval, so books at t and t+0.01 recorded only t -- and if nothing
    followed, the capture held a stale book forever. Fidelity.offer_l2 keeps a
    pending snapshot for exactly this reason; the bridge now does too.
    """
    mode.set_capture_mode(True, symbol="AAPL")
    tick()
    push_depth(bids=((42.20, 300),))   # enqueued immediately
    push_depth(bids=((42.99, 900),))   # inside the interval -> held, not dropped
    assert bridge_ibkr._pending_book.get("AAPL") is not None
    mode.set_capture_mode(False)       # flushes the pending book
    directory = Path(recorder.status()["dir"])

    prices = [row["bids"][0]["price"] for row in rows(directory, "l2")]
    assert 42.99 in prices, f"newest book was dropped: {prices}"


def test_depth_is_not_claimed_before_a_book_has_been_seen():
    """A reserved slot makes is_subscribed true while the book is still empty."""
    from ibkr.depth import state as depth_state

    mode.set_capture_mode(True, symbol="AAPL")
    tick()
    depth_state.reserve_slot("AAPL")  # subscribed, but nothing received yet
    health = bridge_ibkr.book_health("AAPL")
    status = mode.status_payload()
    mode.set_capture_mode(False)

    assert health["subscribed"] is True
    assert health["observed"] is False
    assert health["depth"] is False, "claimed depth before any book arrived"
    assert "not recording" in status["warning"]


def test_depth_is_claimed_once_a_real_book_arrives():
    mode.set_capture_mode(True, symbol="AAPL")
    tick()
    push_depth()
    health = bridge_ibkr.book_health("AAPL")
    status = mode.status_payload()
    mode.set_capture_mode(False)

    assert (health["observed"], health["depth"], health["l1_fallback"]) == (True, True, False)
    assert "warning" not in status
