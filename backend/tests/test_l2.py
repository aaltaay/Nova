"""Unit tests for the Level 2 recorder, tape features, and outcome labeling
(Phase F). No live IB Gateway -- IBKR calls are mocked. Both the l2 and
journal SQLite files are isolated to tmp_path per test."""
import asyncio
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import journal.db as journal_db
import l2.db as l2_db
import l2.features as features
import l2.recorder as recorder
from ibkr import client as ibkr_client_mod
from ibkr import depth as depth_mod


@pytest.fixture(autouse=True)
def isolated_dbs(tmp_path, monkeypatch):
    monkeypatch.setattr(l2_db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(journal_db, "cache_dir", lambda: tmp_path)
    l2_db.init_db()
    journal_db.init_db()
    import l2.batch as l2_batch
    import l2.tape as l2_tape
    l2_batch.clear_queues_for_tests()
    l2_tape.clear_watched_for_tests()
    yield
    l2_batch.clear_queues_for_tests()
    l2_tape.clear_watched_for_tests()


@pytest.fixture(autouse=True)
def reset_recorder_state():
    recorder._active_recordings.clear()
    yield
    recorder._active_recordings.clear()


def _book(bid_size, ask_size, bid_price=5.0, ask_price=5.05):
    return {
        "bids": [{"price": bid_price, "size": bid_size, "side": "bid"}] if bid_size else [],
        "asks": [{"price": ask_price, "size": ask_size, "side": "ask"}] if ask_size else [],
        "l1_fallback": False,
    }


class TestFeatures:
    def test_bid_ask_imbalance_positive_when_bids_heavier(self):
        book = _book(bid_size=900, ask_size=100)
        assert features.bid_ask_imbalance(book) == pytest.approx(0.8)

    def test_bid_ask_imbalance_none_when_both_empty(self):
        assert features.bid_ask_imbalance(_book(0, 0)) is None

    def test_spread_computation(self):
        book = _book(100, 100, bid_price=5.00, ask_price=5.07)
        assert features.spread(book) == pytest.approx(0.07)

    def test_spread_none_when_missing_side(self):
        assert features.spread(_book(0, 100)) is None

    def test_is_ask_stacked_true_when_ask_dominates(self):
        book = _book(bid_size=100, ask_size=200)  # 2x >= L2_ASK_STACKED_RATIO (1.5)
        assert features.is_ask_stacked(book) is True
        assert features.is_bid_heavy(book) is False

    def test_is_bid_heavy_true_when_bid_dominates(self):
        book = _book(bid_size=200, ask_size=100)
        assert features.is_bid_heavy(book) is True
        assert features.is_ask_stacked(book) is False

    def test_neither_flag_when_roughly_balanced(self):
        book = _book(bid_size=100, ask_size=110)
        assert features.is_ask_stacked(book) is False
        assert features.is_bid_heavy(book) is False

    def test_drying_up_true_when_bid_drops_enough(self):
        window = [_book(bid_size=1000, ask_size=100), _book(bid_size=600, ask_size=100)]
        assert features.is_buying_pressure_drying_up(window) is True  # 40% drop >= 30% threshold

    def test_drying_up_false_with_insufficient_history(self):
        assert features.is_buying_pressure_drying_up([_book(1000, 100)]) is False

    def test_drying_up_false_when_bid_holds(self):
        window = [_book(bid_size=1000, ask_size=100), _book(bid_size=950, ask_size=100)]
        assert features.is_buying_pressure_drying_up(window) is False

    def test_compute_feature_series_shape(self):
        snapshots = [_book(1000, 100), _book(600, 100), _book(300, 100)]
        series = features.compute_feature_series(snapshots)
        assert len(series) == 3
        assert all("drying_up" in f for f in series)
        assert series[-1]["drying_up"] is True


class TestStore:
    def test_record_and_get_snapshots(self):
        from l2.store import get_snapshots, record_snapshot

        record_snapshot("AAPL:100.0", "AAPL", "gap_and_go", 100.0, 101.0, _book(500, 100))
        record_snapshot("AAPL:100.0", "AAPL", "gap_and_go", 100.0, 103.0, _book(400, 100))

        rows = get_snapshots("AAPL:100.0")
        assert len(rows) == 2
        assert rows[0]["ts"] == 101.0
        assert rows[0]["bids"][0]["size"] == 500
        assert rows[1]["bids"][0]["size"] == 400

    def test_get_recording_ids_groups_by_recording(self):
        from l2.store import get_recording_ids, record_snapshot

        record_snapshot("AAPL:100.0", "AAPL", "gap_and_go", 100.0, 101.0, _book(500, 100))
        record_snapshot("AAPL:100.0", "AAPL", "gap_and_go", 100.0, 103.0, _book(400, 100))
        record_snapshot("MSFT:200.0", "MSFT", "bull_flag", 200.0, 201.0, _book(300, 50))

        recordings = {r["recording_id"]: r for r in get_recording_ids()}
        assert recordings["AAPL:100.0"]["snapshot_count"] == 2
        assert recordings["MSFT:200.0"]["snapshot_count"] == 1
        assert recordings["MSFT:200.0"]["symbol"] == "MSFT"


class TestRecorder:
    def test_on_signal_skips_when_not_connected(self, monkeypatch):
        monkeypatch.setattr(ibkr_client_mod, "is_connected", lambda: False)
        called = []
        monkeypatch.setattr(depth_mod, "subscribe", lambda s: called.append(s))
        asyncio.run(recorder.on_signal("AAPL", "gap_and_go", time.time()))
        assert called == []

    def test_on_signal_skips_when_already_recording(self, monkeypatch):
        monkeypatch.setattr(ibkr_client_mod, "is_connected", lambda: True)
        recorder._active_recordings.add("AAPL")
        called = []
        monkeypatch.setattr(depth_mod, "subscribe", lambda s: called.append(s))
        asyncio.run(recorder.on_signal("AAPL", "gap_and_go", time.time()))
        assert called == []

    def test_on_signal_skips_when_subscribe_fails(self, monkeypatch):
        monkeypatch.setattr(ibkr_client_mod, "is_connected", lambda: True)
        monkeypatch.setattr(
            depth_mod, "subscribe",
            lambda s: {"ok": False, "error": "Symbol cap reached", "symbols": []},
        )
        asyncio.run(recorder.on_signal("AAPL", "gap_and_go", time.time()))
        assert "AAPL" not in recorder._active_recordings

    @pytest.mark.parametrize("window_sec,interval_sec", [(0.05, 0.01)])
    def test_record_window_writes_snapshots_and_releases_self_subscription(
        self, monkeypatch, window_sec, interval_sec
    ):
        monkeypatch.setattr(recorder, "L2_RECORD_WINDOW_SEC", window_sec)
        monkeypatch.setattr(recorder, "L2_SNAPSHOT_INTERVAL_SEC", interval_sec)
        monkeypatch.setattr(depth_mod, "current_book", lambda s: _book(500, 100))
        unsubscribed = []
        monkeypatch.setattr(depth_mod, "unsubscribe", lambda s: unsubscribed.append(s))

        from l2 import sessions as sessions_mod
        session_id = sessions_mod.start_session("AAPL", "signal", setup="gap_and_go", signal_ts=100.0)
        asyncio.run(recorder._record_window(
            "AAPL", "gap_and_go", 100.0, release_subscription=True, session_id=session_id,
        ))

        from l2.store import get_snapshots
        rows = get_snapshots("AAPL:100.0")
        assert len(rows) >= 1
        assert unsubscribed == ["AAPL"]
        assert "AAPL" not in recorder._active_recordings

    def test_record_window_does_not_unsubscribe_when_shared(self, monkeypatch):
        monkeypatch.setattr(recorder, "L2_RECORD_WINDOW_SEC", 0.02)
        monkeypatch.setattr(recorder, "L2_SNAPSHOT_INTERVAL_SEC", 0.01)
        monkeypatch.setattr(depth_mod, "current_book", lambda s: _book(500, 100))
        unsubscribed = []
        monkeypatch.setattr(depth_mod, "unsubscribe", lambda s: unsubscribed.append(s))

        from l2 import sessions as sessions_mod
        session_id = sessions_mod.start_session("AAPL", "signal", setup="gap_and_go", signal_ts=100.0)
        asyncio.run(recorder._record_window(
            "AAPL", "gap_and_go", 100.0, release_subscription=False, session_id=session_id,
        ))

        assert unsubscribed == []


class TestLabeling:
    def test_matches_closest_trade_as_win(self):
        from journal.store import record_trade
        from l2.labeling import label_recordings
        from l2.store import record_snapshot

        signal_ts = 1000.0
        record_snapshot("AAPL:1000.0", "AAPL", "gap_and_go", signal_ts, signal_ts + 1, _book(500, 100))
        record_trade(
            symbol="AAPL", setup="gap_and_go", side="long", qty=100,
            entry_price=5.0, stop_price=4.9, target_price=5.2,
            exit_price=5.2, pnl=20.0, adherent=True, opened_ts=signal_ts + 5,
        )

        rows = label_recordings()
        assert len(rows) == 1
        assert rows[0]["outcome"] == "win"
        assert rows[0]["pnl"] == 20.0
        assert len(rows[0]["feature_series"]) == 1

    def test_marks_loss_for_negative_pnl(self):
        from journal.store import record_trade
        from l2.labeling import label_recordings
        from l2.store import record_snapshot

        signal_ts = 1000.0
        record_snapshot("AAPL:1000.0", "AAPL", "gap_and_go", signal_ts, signal_ts + 1, _book(100, 500))
        record_trade(
            symbol="AAPL", setup="gap_and_go", side="long", qty=100,
            entry_price=5.0, stop_price=4.9, target_price=5.2,
            exit_price=4.9, pnl=-10.0, adherent=True, opened_ts=signal_ts + 5,
        )

        rows = label_recordings()
        assert rows[0]["outcome"] == "loss"

    def test_unlabeled_when_no_matching_trade(self):
        from l2.labeling import label_recordings
        from l2.store import record_snapshot

        record_snapshot("AAPL:1000.0", "AAPL", "gap_and_go", 1000.0, 1001.0, _book(500, 100))

        rows = label_recordings()
        assert rows[0]["outcome"] == "unlabeled"
        assert rows[0]["pnl"] is None

    def test_respects_match_tolerance_window(self):
        from journal.store import record_trade
        from l2.labeling import label_recordings
        from l2.store import record_snapshot

        signal_ts = 1000.0
        record_snapshot("AAPL:1000.0", "AAPL", "gap_and_go", signal_ts, signal_ts + 1, _book(500, 100))
        # Trade opened far outside L2_LABEL_MATCH_TOLERANCE_SEC (600s) later -- should not match.
        record_trade(
            symbol="AAPL", setup="gap_and_go", side="long", qty=100,
            entry_price=5.0, stop_price=4.9, target_price=5.2,
            exit_price=5.2, pnl=20.0, adherent=True, opened_ts=signal_ts + 10_000,
        )

        rows = label_recordings()
        assert rows[0]["outcome"] == "unlabeled"

    def test_mock_trades_excluded_by_default(self):
        from journal.store import record_trade
        from l2.labeling import label_recordings
        from l2.store import record_snapshot

        signal_ts = 1000.0
        record_snapshot("AAPL:1000.0", "AAPL", "gap_and_go", signal_ts, signal_ts + 1, _book(500, 100))
        record_trade(
            symbol="AAPL", setup="gap_and_go", side="long", qty=100,
            entry_price=5.0, stop_price=4.9, target_price=5.2,
            exit_price=5.2, pnl=20.0, adherent=True, opened_ts=signal_ts + 5,
            is_mock=True,
        )

        assert label_recordings()[0]["outcome"] == "unlabeled"
        assert label_recordings(include_mock=True)[0]["outcome"] == "win"
