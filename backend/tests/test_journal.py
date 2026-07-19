"""Unit tests for the journal DB, store, and metrics -- no network, no orders."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import journal.db as db


@pytest.fixture(autouse=True)
def isolated_journal_db(tmp_path, monkeypatch):
    """Point the journal at a throwaway SQLite file per test so tests never
    touch the real backend/.cache/journal.db."""
    monkeypatch.setattr(db, "cache_dir", lambda: tmp_path)
    db.init_db()
    yield


class TestSignals:
    def test_record_and_get_signal(self):
        from journal.store import get_signals, record_signal

        record_signal(
            symbol="AAPL",
            setup="gap_and_go",
            entry_price=10.0,
            stop_price=9.8,
            target_price=10.4,
            payload={"would_execute": False, "notes": "test signal"},
        )
        rows = get_signals()
        assert len(rows) == 1
        assert rows[0]["symbol"] == "AAPL"
        assert rows[0]["setup"] == "gap_and_go"
        assert rows[0]["entry_price"] == 10.0

    def test_signals_ordered_newest_first(self):
        from journal.store import get_signals, record_signal

        record_signal("AAA", "abcd", 1, 0.9, 1.2, {})
        record_signal("BBB", "bull_flag", 2, 1.9, 2.2, {})
        rows = get_signals()
        assert [r["symbol"] for r in rows] == ["BBB", "AAA"]

    def test_signals_limit(self):
        from journal.store import get_signals, record_signal

        for i in range(5):
            record_signal(f"SYM{i}", "gap_and_go", 1, 0.9, 1.2, {})
        rows = get_signals(limit=2)
        assert len(rows) == 2


class TestTrades:
    def test_record_and_get_trade(self):
        from journal.store import get_trades, record_trade

        record_trade(
            symbol="MSFT",
            setup="gap_and_go",
            side="long",
            qty=100,
            entry_price=10.0,
            stop_price=9.8,
            target_price=10.4,
            exit_price=10.4,
            pnl=40.0,
            adherent=True,
        )
        rows = get_trades()
        assert len(rows) == 1
        assert rows[0]["symbol"] == "MSFT"
        assert rows[0]["pnl"] == 40.0
        assert rows[0]["adherent"] == 1
        assert rows[0]["is_mock"] == 0

    def test_get_closed_trades_excludes_open_trades(self):
        from journal.store import get_closed_trades, record_trade

        record_trade("AAA", "abcd", "long", 100, 5.0, 4.9, 5.2, None, None, None)
        record_trade("BBB", "abcd", "long", 100, 5.0, 4.9, 5.2, 5.2, 20.0, True)
        closed = get_closed_trades()
        assert len(closed) == 1
        assert closed[0]["symbol"] == "BBB"


class TestMockTrades:
    def test_mock_trades_excluded_by_default(self):
        from journal.store import get_closed_trades, get_trades, record_trade

        record_trade("REAL", "gap_and_go", "long", 100, 5.0, 4.9, 5.2, 5.2, 20.0, True, is_mock=False)
        record_trade("FAKE", "gap_and_go", "long", 100, 5.0, 4.9, 5.2, 5.2, 20.0, True, is_mock=True)

        assert [t["symbol"] for t in get_trades()] == ["REAL"]
        assert [t["symbol"] for t in get_closed_trades()] == ["REAL"]

    def test_mock_trades_included_when_requested(self):
        from journal.store import get_closed_trades, get_trades, record_trade

        record_trade("REAL", "gap_and_go", "long", 100, 5.0, 4.9, 5.2, 5.2, 20.0, True, is_mock=False)
        record_trade("FAKE", "gap_and_go", "long", 100, 5.0, 4.9, 5.2, 5.2, 20.0, True, is_mock=True)

        assert {t["symbol"] for t in get_trades(include_mock=True)} == {"REAL", "FAKE"}
        assert {t["symbol"] for t in get_closed_trades(include_mock=True)} == {"REAL", "FAKE"}

    def test_clear_mock_trades_only_removes_mock_rows(self):
        from journal.store import clear_mock_trades, get_trades, record_trade

        record_trade("REAL", "gap_and_go", "long", 100, 5.0, 4.9, 5.2, 5.2, 20.0, True, is_mock=False)
        record_trade("FAKE", "gap_and_go", "long", 100, 5.0, 4.9, 5.2, 5.2, 20.0, True, is_mock=True)

        removed = clear_mock_trades()
        assert removed == 1
        assert [t["symbol"] for t in get_trades(include_mock=True)] == ["REAL"]

    def test_seed_mock_trades_is_idempotent_and_tagged(self):
        from journal.mock_data import _MOCK_TRADES, seed_mock_trades
        from journal.store import get_trades

        n1 = seed_mock_trades()
        n2 = seed_mock_trades()  # re-running must not duplicate rows
        assert n1 == n2 == len(_MOCK_TRADES)

        rows = get_trades(include_mock=True)
        assert len(rows) == len(_MOCK_TRADES)
        assert all(r["is_mock"] == 1 for r in rows)

    def test_migration_adds_is_mock_column_to_pre_existing_table(self):
        """Simulates a journal.db created before is_mock existed -- init_db()
        must ALTER the column in without losing existing rows."""
        conn = db.get_connection()
        conn.executescript(
            """
            DROP TABLE IF EXISTS trades;
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opened_ts REAL NOT NULL,
                closed_ts REAL,
                symbol TEXT NOT NULL,
                setup TEXT,
                side TEXT NOT NULL,
                qty INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                stop_price REAL,
                target_price REAL,
                pnl REAL,
                adherent INTEGER,
                notes TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO trades (opened_ts, symbol, side, qty, entry_price) VALUES (1.0, 'OLD', 'long', 100, 5.0)"
        )
        conn.commit()
        conn.close()

        db.init_db()  # should ALTER TABLE ADD COLUMN is_mock without dropping OLD's row

        from journal.store import get_trades
        rows = get_trades(include_mock=True)
        assert len(rows) == 1
        assert rows[0]["symbol"] == "OLD"
        assert rows[0]["is_mock"] == 0


class TestMetrics:
    def test_empty_journal_reports_no_data_honestly(self):
        from journal.metrics import compute_metrics

        result = compute_metrics()
        assert result["includes_mock_data"] is False
        assert result["total_closed_trades"] == 0
        assert result["win_rate_pct"] is None
        assert result["profit_loss_ratio"] is None
        assert result["go_no_go"]["overall_go"] is False
        assert result["go_no_go"]["criteria"]["min_sample_size"]["met"] is False
        assert result["go_no_go"]["criteria"]["profit_loss_ratio"]["met"] is None

    def test_metrics_compute_win_rate_and_ratio(self):
        from journal.store import record_trade

        record_trade("AAA", "gap_and_go", "long", 100, 5.0, 4.9, 5.2, 5.2, 20.0, True)
        record_trade("BBB", "gap_and_go", "long", 100, 5.0, 4.9, 5.2, 4.9, -10.0, True)

        from journal.metrics import compute_metrics

        result = compute_metrics()
        assert result["total_closed_trades"] == 2
        assert result["win_rate_pct"] == 50.0
        assert result["avg_win_dollars"] == 20.0
        assert result["avg_loss_dollars"] == 10.0
        assert result["profit_loss_ratio"] == 2.0
        assert result["adherence_pct"] == 100.0

    def test_go_no_go_requires_full_sample_and_ratio_and_adherence(self):
        from journal.store import record_trade

        record_trade("AAA", "gap_and_go", "long", 100, 5.0, 4.9, 5.2, 5.2, 20.0, True)
        record_trade("BBB", "gap_and_go", "long", 100, 5.0, 4.9, 5.2, 4.9, -10.0, False)

        from journal.metrics import compute_metrics

        result = compute_metrics()
        criteria = result["go_no_go"]["criteria"]
        assert criteria["profit_loss_ratio"]["met"] is True
        assert criteria["adherence"]["met"] is False  # one non-adherent trade
        assert criteria["min_sample_size"]["met"] is False  # only 2 of 50 required
        assert result["go_no_go"]["overall_go"] is False

    def test_mock_trades_never_leak_into_default_metrics(self):
        from journal.metrics import compute_metrics
        from journal.mock_data import seed_mock_trades

        seed_mock_trades()
        real_metrics = compute_metrics()
        assert real_metrics["total_closed_trades"] == 0
        assert real_metrics["includes_mock_data"] is False

        demo_metrics = compute_metrics(include_mock=True)
        assert demo_metrics["total_closed_trades"] > 0
        assert demo_metrics["includes_mock_data"] is True
