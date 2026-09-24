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
from sale_conditions import row_sets_price


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


def tick(symbol="AAPL", price=42.25, at=datetime(2026, 9, 18, 14, 30, tzinfo=timezone.utc)):
    ticker = SimpleNamespace(
        tickByTicks=[
            SimpleNamespace(
                time=at,
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
    for field in ("symbol", "ts", "price", "size", "exchange", "conditions", "unreported", "source", "receive_ts"):
        assert captured[field] == rows[0][field]
    assert rows[0]["session_id"] == "session-a"
    assert captured["source"] == "ibkr"
    # ib_async stamps a print with its arrival at Nova, never IBKR's time (#563).
    assert captured["ts_source"] == "receive"
    assert captured["exchange_ts"] is None  # this tick did not pass the wrapper override
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


def test_print_without_an_exchange_time_is_recorded_as_stamped_on_arrival():
    """A substituted arrival time must never read as the exchange's own."""
    mode.set_capture_mode(True, symbol="AAPL")
    untimed = SimpleNamespace(tickByTicks=[SimpleNamespace(
        time=None, price=42.30, size=3, exchange="NASDAQ", specialConditions="")])
    tape_stream._on_tape_update(untimed, "AAPL")
    directory = Path(recorder.status()["dir"])
    mode.set_capture_mode(False)
    assert [row["ts_source"] for row in rows(directory, "prints")] == ["receive"]


def test_a_recorded_print_keeps_ibkrs_second_beside_its_arrival_time():
    """#563: ib_async's own wrapper, decoder and registry feed the Session Record row."""
    from ib_async import IB, Stock
    from ibkr import tape_exchange_time

    arrived = datetime(2026, 9, 18, 14, 30, 2, 400_000, tzinfo=timezone.utc)
    ibkr_second = int(datetime(2026, 9, 18, 14, 30, 1, tzinfo=timezone.utc).timestamp())
    ib = IB()
    ib.client.getReqId = lambda: 7
    ib.client.reqTickByTickData = lambda *_args: None
    contract = Stock("AAPL", "SMART", "USD")
    contract.conId = 265598
    ticker = ib.reqTickByTickData(contract, "AllLast")
    assert tape_exchange_time.install(ib)
    ib.wrapper.lastTime = arrived
    ib.client.decoder.tickByTick(["99", "7", "2", str(ibkr_second), "42.25", "7", "0", "NASDAQ", "T"])

    mode.set_capture_mode(True, symbol="AAPL")
    tape_stream._on_tape_update(ticker, "AAPL")
    mode.set_capture_mode(False)  # drains accepted rows into the print's own (event) day
    [row] = rows(Path(recorder.status()["dir"]), "prints")
    assert row["ts"] == arrived.timestamp()  # rows stay in arrival order, like the books
    assert row["ts_source"] == "receive"
    assert row["exchange_ts"] == ibkr_second


def test_invalid_producer_timestamp_is_diagnosed_by_the_recorder():
    """The bridge must not raise first, or the row is lost as a generic failure."""
    mode.set_capture_mode(True, symbol="AAPL")
    bridge_ibkr._write_print(dict(symbol="AAPL", ts=None, price=1.0, size=1, source="ibkr"))
    assert recorder.status()["fidelity"]["invalid_timestamp_rows"] == 1
    mode.set_capture_mode(False)


def test_empty_segment_fails_manifest_with_ibkr_provenance():
    """Empty recordings are never presented as successful (#315)."""
    mode.set_capture_mode(True, symbol="AAPL")
    directory = Path(recorder.status()["dir"])
    mode.set_capture_mode(False)
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["status"] == "failed"
    assert "No IBKR prints" in manifest["error"]
    assert manifest["source"] == "ibkr"
    assert "No IBKR prints" in mode.status_payload()["error"]


def test_former_sim_symbol_gets_no_admission_bypass(tmp_path):
    """SIM1 is gone: it is refused like any symbol without an AllLast producer."""
    result = mode.set_capture_mode(True, symbol="SIM1")
    assert result["capture"] is False and "subscribed" in result["error"]
    assert not recorder.is_recording()
    assert not list(tmp_path.rglob("manifest.json"))


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
    assert row["unreported"] is None  # unknown, never "reported"
    assert row_sets_price(row)  # judged by its (absent) conditions, as before


def test_the_archive_keeps_ibkrs_unreported_flag_for_practice_fills():
    """#511: a print IBKR flags unreported sets no price even with no listed code."""
    tape.watch_symbol("AAPL", "session-a")
    at = datetime(2026, 9, 18, 14, 30, tzinfo=timezone.utc)
    ticker = SimpleNamespace(tickByTicks=[
        SimpleNamespace(time=at, price=42.25, size=100, exchange="NASDAQ", specialConditions="@ T"),
        SimpleNamespace(time=at, price=40.10, size=100, exchange="FINRA", specialConditions="",
                        tickAttribLast=SimpleNamespace(unreported=True)),
        SimpleNamespace(time=at, price=40.20, size=100, exchange="FINRA", specialConditions="4 W"),
    ])
    tape_stream._on_tape_update(ticker, "AAPL")
    fanout.l2_sink.queue.join()
    rows = tape.get_trades_in_range("AAPL", 0, 2_000_000_000)
    assert [(r["price"], r["unreported"]) for r in rows] == [(42.25, False), (40.10, True), (40.20, False)]
    assert [row_sets_price(r) for r in rows] == [True, False, False]


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
    monkeypatch.setattr(bridge_ibkr, "CAPTURE_PRINT_BATCH_MAX", 1)  # one print, one job
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
    from tests.depth_ticks import depth_ticker

    on_update_book(depth_ticker(bids=bids, asks=asks), symbol)


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


def test_replay_books_never_enter_a_live_capture():
    """`state.push_book` is shared with the capture replay (sim/feed, sim/market).

    Hooking the capture bridge there recorded non-IBKR books (then the SIM1
    tape, now replayed captures) into a live IBKR capture on a different clock,
    which tripped the recorder's timestamp-regression stop and ended the
    recording. Caught end to end against a running API, not by a unit test, so
    it is pinned here.
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
    # Stamped on the recorder's own Eastern day. The shared tick() is dated
    # 2026-09-18, and a print from another day rotates the segment -- which stops
    # a segment with no prints and records "No IBKR prints received". That is a
    # day-boundary behaviour, not what this test is about, and whether the test
    # saw it depended on the capture worker beating the assertion (flaky: it
    # failed 5 of 6 isolated runs on master).
    tick(at=datetime.now(timezone.utc))
    for i in range(worker.CAPTURE_PENDING_BATCHES * 2):
        push_depth(bids=((42.20 + i / 1000, 300),))
    worker.transition(lambda: None)  # drain accepted batches: no thread-timing race
    assert recorder.status()["error"] is None  # backlog never filled
    health = bridge_ibkr.book_health("AAPL")
    mode.set_capture_mode(False)
    directory = Path(recorder.status()["dir"])

    assert health["books_coalesced"] > 0
    assert len(rows(directory, "quotes")) < worker.CAPTURE_PENDING_BATCHES


class _Clock:
    """The bridge's wall clock, stepped by hand (ADR 031 book batching)."""

    def __init__(self, start):
        self.now = start

    def time(self):
        return self.now


def test_every_book_inside_the_flood_bound_is_recorded_in_batches(monkeypatch):
    import time as _time

    clock = _Clock(_time.time())
    monkeypatch.setattr(bridge_ibkr, "time", clock)
    submits = []
    real_submit = worker.submit
    monkeypatch.setattr(worker, "submit", lambda fn, *a, **kw: submits.append(fn.__name__) or real_submit(fn, *a, **kw))
    mode.set_capture_mode(True, symbol="AAPL")
    tick(at=datetime.now(timezone.utc))
    for i in range(30):  # 20 books a second: under CAPTURE_L2_MAX_HZ, none held back
        clock.now += 0.05
        push_depth(bids=((42.20 + i / 1000, 300),))
    mode.set_capture_mode(False)
    directory = Path(recorder.status()["dir"])
    fidelity = json.loads((directory / "manifest.json").read_text())["fidelity"]

    assert len(rows(directory, "l2")) == 30
    assert all("coalesced_before" not in row for row in rows(directory, "l2"))
    assert fidelity["l2_coalesced"] == 0 and fidelity["l2_offered"] == 30
    assert submits.count("_write_books") < 30  # batched, not one job per book


def test_the_manifest_counts_every_book_the_bridge_held_back(monkeypatch):
    import time as _time

    clock = _Clock(_time.time())
    monkeypatch.setattr(bridge_ibkr, "time", clock)
    mode.set_capture_mode(True, symbol="AAPL")
    tick(at=datetime.now(timezone.utc))
    push_depth(bids=((42.20, 300),))  # written
    for i in range(5):  # a burst over the bound: each held book is replaced by the next
        clock.now += 0.001
        push_depth(bids=((42.21 + i / 1000, 300),))
    clock.now += 1.0
    push_depth(bids=((42.40, 300),))  # written; the last held book was never written
    health = bridge_ibkr.book_health("AAPL")
    mode.set_capture_mode(False)
    directory = Path(recorder.status()["dir"])
    fidelity = json.loads((directory / "manifest.json").read_text())["fidelity"]

    assert [row["bids"][0]["price"] for row in rows(directory, "l2")] == [42.20, 42.40]
    assert health["books_coalesced"] == 5
    assert fidelity["l2_coalesced"] == 5 and fidelity["l2_offered"] == 7


def test_stop_writes_the_held_book(monkeypatch):
    import time as _time

    clock = _Clock(_time.time())
    monkeypatch.setattr(bridge_ibkr, "time", clock)
    mode.set_capture_mode(True, symbol="AAPL")
    tick(at=datetime.now(timezone.utc))
    push_depth(bids=((42.20, 300),))
    clock.now += 0.001
    push_depth(bids=((42.25, 300),))  # held: inside the flood bound
    mode.set_capture_mode(False)
    directory = Path(recorder.status()["dir"])
    fidelity = json.loads((directory / "manifest.json").read_text())["fidelity"]

    assert [row["bids"][0]["price"] for row in rows(directory, "l2")] == [42.20, 42.25]
    assert fidelity["l2_coalesced"] == 0


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


def test_quote_rows_carry_ibkrs_tick9_close_from_the_l1_line(monkeypatch):
    """The replay reads the recorded prior close before anything else (#542).

    Record's own tape and depth lines carry no close; the symbol's L1 line does,
    once IBKR sends tick 9 (NaN until then, and no line at all records null).
    """
    from ibkr import ticks

    lines = {"AAPL": SimpleNamespace(close=41.87)}
    monkeypatch.setattr(ticks, "get_ticker", lambda symbol: lines.get(symbol))
    mode.set_capture_mode(True, symbol="AAPL")
    tick()
    push_depth(bids=((42.20, 300),))
    lines["AAPL"] = SimpleNamespace(close=float("nan"))
    push_depth(bids=((42.21, 300),))  # coalesced, then flushed by the stop
    mode.set_capture_mode(False)
    directory = Path(recorder.status()["dir"])

    assert [row["prev_close"] for row in rows(directory, "quotes")] == [41.87, None]


def test_depth_is_claimed_once_a_real_book_arrives():
    mode.set_capture_mode(True, symbol="AAPL")
    tick()
    push_depth()
    health = bridge_ibkr.book_health("AAPL")
    status = mode.status_payload()
    mode.set_capture_mode(False)

    assert (health["observed"], health["depth"], health["l1_fallback"]) == (True, True, False)
    assert "warning" not in status
