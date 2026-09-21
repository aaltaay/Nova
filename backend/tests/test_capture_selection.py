"""Capture selection I/O cannot publish over a newer capture/history intent."""
import json
import threading
from datetime import datetime
from unittest.mock import Mock

import pytest

from sim import capture_player as player, feed, history_playback, replay, session_clock
from sim import history_store

DAY = "2026-09-18"
TS = datetime.fromisoformat(DAY + "T10:00:00-04:00").timestamp()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_CAPTURE_DIR", str(tmp_path / "capture"))
    monkeypatch.setenv("NOVA_SIM_HISTORY_DIR", str(tmp_path / "history"))
    replay.reset_for_tests()
    session_clock.reset_for_tests()
    for symbol, price in (("AAA", 10), ("BBB", 20)):
        root = tmp_path / "capture" / DAY / symbol
        root.mkdir(parents=True)
        (root / "prints.jsonl").write_text(json.dumps(dict(ts=TS, symbol=symbol, price=price, size=1)))
    yield tmp_path
    replay.reset_for_tests()
    session_clock.reset_for_tests()


def block_read(monkeypatch, symbol):
    entered, release = threading.Event(), threading.Event()
    original = player._read_jsonl
    def blocked(path, diagnostics=None):
        if path.parent.name == symbol and path.name == "prints.jsonl":
            entered.set()
            assert release.wait(5), "capture read was not released"
        return original(path, diagnostics)
    monkeypatch.setattr(player, "_read_jsonl", blocked)
    return entered, release


def run_thread(operation, *, name=None):
    errors = []
    def work():
        try:
            operation()
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=work, daemon=True, name=name)
    thread.start()
    return thread, errors


def finish(thread, errors, release):
    release.set()
    thread.join(5)
    assert not thread.is_alive(), "selection deadlocked"
    assert errors == []


def test_complete_snapshot_stays_visible_until_new_load_is_ready(monkeypatch):
    assert player.load(DAY, "AAA")["ok"]
    old = player.snapshot()
    entered, release = block_read(monkeypatch, "BBB")
    thread, errors = run_thread(lambda: player.load(DAY, "BBB"))
    try:
        assert entered.wait(5)
        assert player.quote_at(TS)["last"] == 10
        assert player.snapshot() is old
    finally:
        finish(thread, errors, release)
    assert player.quote_at(TS)["last"] == 20
    assert old.symbol == "AAA" and old.prints[0]["price"] == 10


def test_latest_capture_selection_wins_and_loading_never_fabricates_a_market(monkeypatch):
    from ibkr import tape_stream
    entered, release = block_read(monkeypatch, "AAA")
    tape = Mock()
    monkeypatch.setattr(tape_stream, "_push_queue", tape)
    thread, errors = run_thread(lambda: replay.set_replay(DAY, "AAA"))
    try:
        assert entered.wait(5)
        assert not replay.status_payload()["replay_ok"]
        assert feed.tick() == {}
        tape.assert_not_called()
        from sim import market
        assert market.quote("AAA") is None and market.book() == {}
        assert market.ticker_snapshot("AAA") == {}
        assert replay.set_replay(DAY, "BBB")["replay_symbol"] == "BBB"
    finally:
        finish(thread, errors, release)
    assert replay.status_payload()["replay_symbol"] == "BBB"
    assert player.loaded_key() == DAY + "|BBB"


def test_historical_selection_invalidates_pending_capture_without_deadlock(monkeypatch):
    entered, release = block_read(monkeypatch, "AAA")
    thread, errors = run_thread(lambda: replay.set_replay(DAY, "AAA"))
    try:
        assert entered.wait(5)
        spec = history_store.window("BBB", DAY, "09:30", "10:30")
        history_playback.select(spec)
    finally:
        finish(thread, errors, release)
    result = replay.status_payload()
    assert result["replay_source"] == "historical" and result["replay_symbol"] == "BBB"
    assert not player.is_loaded()
    assert session_clock.status_payload()["session_date"] == DAY


def test_clear_invalidates_pending_capture_and_failure_cannot_erase_newer_selection(isolated, monkeypatch):
    bad = isolated / "capture" / DAY / "AAA" / "prints.jsonl"
    bad.write_text("{broken")
    entered, release = block_read(monkeypatch, "AAA")
    thread, errors = run_thread(lambda: replay.set_replay(DAY, "AAA"))
    try:
        assert entered.wait(5)
        replay.set_replay(None, None)
        replay.set_replay(DAY, "BBB")
    finally:
        finish(thread, errors, release)
    assert replay.status_payload()["replay_ok"]
    assert player.loaded_key() == DAY + "|BBB"



def test_capture_alignment_and_historical_publication_cannot_invert_locks(monkeypatch):
    capture_locked, history_locked = threading.Event(), threading.Event()
    original_align, original_clear = replay._align_clock, replay.clear_capture
    def align(date, info):
        capture_locked.set()
        assert history_locked.wait(5), "history did not reach publication"
        return original_align(date, info)
    def clear():
        if threading.current_thread().name == "history-select":
            history_locked.set()
        return original_clear()
    monkeypatch.setattr(replay, "_align_clock", align)
    monkeypatch.setattr(replay, "clear_capture", clear)
    capture_thread, capture_errors = run_thread(lambda: replay.set_replay(DAY, "AAA"), name="capture-select")
    assert capture_locked.wait(5)
    spec = history_store.window("BBB", DAY, "09:30", "10:30")
    history_thread, history_errors = run_thread(lambda: history_playback.select(spec), name="history-select")
    capture_thread.join(5)
    history_thread.join(5)
    alive = capture_thread.is_alive() or history_thread.is_alive()
    if alive:
        # A failing lock-order regression must not wedge fixture cleanup/CI.
        replay._selection_lock = threading.RLock()
        history_playback._lock = threading.RLock()
    assert not alive, "capture clock fanout inverted capture/history locks"
    assert capture_errors == history_errors == []
    result = replay.status_payload()
    assert result["replay_source"] == "historical" and result["replay_symbol"] == "BBB"
    assert not player.is_loaded()
    assert session_clock.status_payload()["session_open_et"].startswith(DAY + "T09:30")


def test_quote_and_ticker_reads_pin_one_snapshot_across_a_concurrent_switch(monkeypatch):
    from sim import market
    original_quote = player.quote_at
    def switch_after_snapshot(asof=None, *, state=None):
        player.load(DAY, "BBB")
        return original_quote(TS, state=state)
    replay.set_replay(DAY, "AAA")
    monkeypatch.setattr(player, "quote_at", switch_after_snapshot)
    quote = market.quote("AAA")
    assert quote["symbol"] == "AAA" and quote["last"] == 10
    replay.set_replay(DAY, "AAA")
    monkeypatch.setattr(session_clock, "now_et", lambda: datetime.fromtimestamp(TS, session_clock.ET))
    ticker = market.ticker_snapshot("AAA")
    assert ticker["latest_trade"]["price"] == 10
    assert player.snapshot().symbol == "BBB"


def test_superseded_capture_generation_cannot_reseed_tape(monkeypatch):
    from sim import market
    from ibkr import tape_stream
    replay.set_replay(DAY, "AAA")
    generation = replay._generation
    replay.set_replay(DAY, "BBB")
    emit = Mock()
    monkeypatch.setattr(tape_stream, "_push_queue", emit)
    market.rebuild_for_scrub(expected_capture_generation=generation)
    emit.assert_not_called()



def test_initial_capture_intent_is_atomic_with_historical_publication(monkeypatch):
    registering, permit_registration = threading.Event(), threading.Event()
    original_clear = replay.clear_capture
    def clear():
        if threading.current_thread().name == "capture-register":
            registering.set()
            assert permit_registration.wait(5)
        return original_clear()
    monkeypatch.setattr(replay, "clear_capture", clear)
    loading, permit_load = block_read(monkeypatch, "AAA")
    capture_thread, capture_errors = run_thread(lambda: replay.set_replay(DAY, "AAA"), name="capture-register")
    assert registering.wait(5)
    # Capture generation registration must still own history's transition lock.
    # Without that atomic boundary a newer history publication can slip into
    # the gap and then be overwritten by the older capture's clock alignment.
    held = not history_playback._lock.acquire(blocking=False)
    if not held:
        history_playback._lock.release()
    try:
        assert held
        spec = history_store.window("BBB", DAY, "09:30", "10:30")
        history_thread, history_errors = run_thread(lambda: history_playback.select(spec))
        permit_registration.set()
        assert loading.wait(5)
        history_thread.join(5)
        assert not history_thread.is_alive() and history_errors == []
    finally:
        permit_registration.set()
        finish(capture_thread, capture_errors, permit_load)
    result = replay.status_payload()
    assert result["replay_source"] == "historical" and result["replay_symbol"] == "BBB"
    assert not player.is_loaded()
    assert session_clock.status_payload()["session_open_et"].startswith(DAY + "T09:30")
