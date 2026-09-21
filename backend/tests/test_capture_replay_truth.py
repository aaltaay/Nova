"""Capture selection truth and recorded-event isolation (#317)."""
import json
from datetime import datetime
from unittest.mock import Mock

import pytest

from capture import sessions
from sim import capture_player as player, feed, replay, session_clock as clock

DAY = "2026-09-18"
TS = datetime.fromisoformat("2026-09-18T10:00:00-04:00").timestamp()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    replay.reset_for_tests()
    clock.reset_for_tests()
    monkeypatch.setattr(player, "capture_root", lambda: tmp_path)
    monkeypatch.setattr(sessions, "capture_root", lambda: tmp_path)
    yield
    replay.reset_for_tests()
    clock.reset_for_tests()


def capture(tmp_path, symbol="IMCC", prints=None, quotes=None):
    root = tmp_path / DAY / symbol
    root.mkdir(parents=True, exist_ok=True)
    for name, rows in [("prints", prints), ("quotes", quotes)]:
        if rows is not None:
            (root / f"{name}.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return root


def print_row(**changes):
    return {"ts": TS, "symbol": "IMCC", "price": 12.5, "size": 7, **changes}


def mute_feed(monkeypatch):
    """Record every tape/broadcast/fill the feed attempts."""
    from ibkr import tape_stream
    tape, broadcast, fills = Mock(), Mock(), Mock(return_value=[])
    monkeypatch.setattr(tape_stream, "_push_queue", tape)
    monkeypatch.setattr(feed, "_broadcast_capture", broadcast)
    monkeypatch.setattr(feed, "match_practice_fills", fills)
    return tape, broadcast, fills


def test_missing_selection_exposes_persistent_failure_and_blocks_ticks(monkeypatch):
    tape, broadcast, fills = mute_feed(monkeypatch)
    result = replay.set_replay(DAY, "NOPE")
    assert result["replay_source"] == "none"
    assert result["replay_date"] is result["replay_symbol"] is None
    assert result["replay_ok"] is False and result["replay_error"]
    assert not replay.is_capture_replay() and not player.is_loaded()
    assert replay.status_payload()["replay_error"] == result["replay_error"]
    assert feed.tick() == {}
    # Blocked outright: not even practice fills run until a source is selected.
    tape.assert_not_called()
    broadcast.assert_not_called()
    fills.assert_not_called()


@pytest.mark.parametrize("kind", ["empty", "l2", "bars", "corrupt", "invalid_price", "wrong_symbol"])
def test_unusable_capture_is_refused(tmp_path, kind):
    root = capture(tmp_path)
    if kind == "l2":
        (root / "l2.jsonl").write_text(json.dumps({"ts": TS, "bids": []}), encoding="utf-8")
    elif kind == "bars":
        (root / "bars_1m.jsonl").write_text(json.dumps({"ts": TS, "close": 12}), encoding="utf-8")
    elif kind == "corrupt":
        (root / "prints.jsonl").write_text('null\n[]\n{torn\n', encoding="utf-8")
    elif kind == "invalid_price":
        capture(tmp_path, prints=[print_row(price=0), print_row(price=float("nan"))])
    elif kind == "wrong_symbol":
        capture(tmp_path, prints=[print_row(symbol="OTHER")])
    result = replay.set_replay(DAY, "IMCC")
    assert result["replay_ok"] is False
    assert result["replay_source"] == "none"
    assert "no usable" in result["replay_error"]
    assert not player.is_loaded()


def test_read_error_clears_previous_capture_and_can_retry(tmp_path, monkeypatch):
    capture(tmp_path, prints=[print_row()])
    assert replay.set_replay(DAY, "IMCC")["replay_ok"]
    with monkeypatch.context() as patch:
        patch.setattr(player, "_read_jsonl", Mock(side_effect=OSError("disk unavailable")))
        failed = replay.set_replay(DAY, "IMCC")
    assert failed["replay_ok"] is False and not player.is_loaded()
    assert replay.set_replay(DAY, "IMCC")["replay_source"] == "capture"
    assert replay.status_payload()["replay_error"] is None


def test_quotes_only_is_usable_and_does_not_invent_prints(tmp_path, monkeypatch):
    capture(tmp_path, quotes=[dict(ts=TS, symbol="IMCC", last=12.5, bid=12.4, ask=12.6)])
    result = replay.set_replay(DAY, "IMCC")
    assert result["replay_ok"] and result["replay_load"]["first_ts"] == TS
    monkeypatch.setattr(clock, "now_et", lambda: datetime.fromtimestamp(TS + 1, clock.ET))
    tape, broadcast, _fills = mute_feed(monkeypatch)
    assert feed.tick() == {}
    assert player.recent_prints() == []
    assert player.quote_at()["last"] == 12.5
    tape.assert_not_called()
    broadcast.assert_not_called()


def test_valid_rows_survive_torn_tail_with_warning(tmp_path, caplog):
    root = capture(tmp_path, prints=[print_row()])
    with (root / "prints.jsonl").open("a", encoding="utf-8") as out:
        out.write('{"ts":')
    assert replay.set_replay(DAY, "IMCC")["replay_ok"]
    assert "unparseable" in caplog.text
    assert player.prints_since(TS - 1, TS + 1) == [print_row()]


def test_capture_feed_uses_recorded_symbol_and_no_gap_or_fabricated_book(tmp_path, monkeypatch):
    from ibkr import tape_stream
    from ibkr.depth import state
    capture(tmp_path, prints=[print_row()])
    replay.set_replay(DAY, "IMCC")
    monkeypatch.setattr(clock, "now_et", lambda: datetime.fromtimestamp(TS + 1, clock.ET))
    player.seek_emit_cursor(TS)
    tape, books, broadcast = Mock(), Mock(), Mock()
    monkeypatch.setattr(tape_stream, "_push_queue", tape)
    monkeypatch.setattr(state, "push_book", books)
    monkeypatch.setattr(feed, "_broadcast_capture", broadcast)
    payload = feed.tick()
    assert payload["symbol"] == "IMCC" and payload["price"] == 12.5
    tape.assert_called_once_with("IMCC", payload)
    broadcast.assert_called_once_with(payload)
    books.assert_not_called()
    assert feed.tick() == {}  # no GAP trade in a quiet interval
    assert tape.call_count == 1 and broadcast.call_count == 1


def test_runtime_capture_failure_does_not_fall_through(tmp_path, monkeypatch):
    capture(tmp_path, prints=[print_row()])
    replay.set_replay(DAY, "IMCC")
    monkeypatch.setattr(player, "prints_since", Mock(side_effect=ValueError("broken data")))
    tape, broadcast, fills = mute_feed(monkeypatch)
    assert feed.tick() == {} and feed.tick() == {}
    assert replay.status_payload()["replay_ok"] is False
    assert "playback failed" in replay.status_payload()["replay_error"]
    assert not replay.is_capture_replay()
    tape.assert_not_called()
    broadcast.assert_not_called()
    fills.assert_not_called()


def test_clearing_a_failed_selection_acknowledges_it_and_idles(monkeypatch):
    """With nothing loaded the feed prints nothing; there is no SIM1 to resume (#315)."""
    tape, broadcast, fills = mute_feed(monkeypatch)
    replay.set_replay(DAY, "NOPE")
    assert feed.tick() == {}
    fills.assert_not_called()  # a failed selection still blocks ticks
    result = replay.set_replay(None, None)
    assert result["replay_ok"] and result["replay_error"] is None
    assert result["replay_source"] == "none"
    assert feed.tick() == {}
    fills.assert_called_once_with()  # idle, not blocked
    tape.assert_not_called()
    broadcast.assert_not_called()


def test_idle_feed_never_fills_practice_orders(monkeypatch):
    fill = Mock(side_effect=AssertionError("filled with nothing loaded"))
    monkeypatch.setattr(feed._broker, "try_fill_working", fill)
    assert replay.status_payload()["replay_source"] == "none"
    assert feed.tick() == {} and feed.tick() == {}
    assert feed.match_practice_fills() == []


@pytest.mark.parametrize("manifest", [{"counts": {"prints": 999}}, [], None, {"counts": {"prints": "invalid"}}])
def test_listing_uses_files_not_stale_or_corrupt_counts(tmp_path, manifest):
    root = capture(tmp_path, symbol="EMPTY")
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    # L2 bytes ensure malformed-manifest directories remain visible for diagnosis.
    (root / "l2.jsonl").write_text('{}\n', encoding="utf-8")
    row = sessions.list_sessions()["tickers_by_day"][DAY][0]
    assert row["empty"] and not row["usable"] and row["unavailable_reason"]


def test_listing_recognizes_partial_print_and_quote_only_sessions(tmp_path):
    capture(tmp_path, prints=[print_row()])
    capture(tmp_path, symbol="QUOTE", quotes=[dict(ts=TS, last=10)])
    rows = sessions.list_sessions()["tickers_by_day"][DAY]
    assert len(rows) == 2
    assert all(row["usable"] and not row["empty"] for row in rows)
    assert rows[0]["prints"] == -1  # Partial capture with no finalized manifest.


def test_http_failure_and_clock_poll_share_replay_error():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sim.routes import router
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        selected = client.post('/api/sim/replay', json={"date": DAY, "symbol": "NOPE"})
        assert selected.status_code == 200
        assert selected.json()["replay_ok"] is False
        status = client.get('/api/sim/clock').json()
        assert status["replay_error"] == selected.json()["replay_error"]
        assert status["replay_source"] == "none"


def test_quiet_capture_can_refresh_recorded_book_without_fabricating_trade(tmp_path, monkeypatch):
    from ibkr import tape_stream
    from ibkr.depth import state
    root = capture(tmp_path, quotes=[dict(ts=TS, symbol="IMCC", last=12.5)])
    recorded = dict(ts=TS, symbol="IMCC", bids=[dict(price=12.4, size=10)], asks=[])
    (root / "l2.jsonl").write_text(json.dumps(recorded) + '\n', encoding='utf-8')
    replay.set_replay(DAY, "IMCC")
    monkeypatch.setattr(clock, "now_et", lambda: datetime.fromtimestamp(TS + 1, clock.ET))
    tape, books = Mock(), Mock()
    monkeypatch.setattr(tape_stream, "_push_queue", tape)
    monkeypatch.setattr(state, "push_book", books)
    assert feed.tick() == {}
    tape.assert_not_called()
    books.assert_called_once_with("IMCC", {**recorded, "source": "capture"})
