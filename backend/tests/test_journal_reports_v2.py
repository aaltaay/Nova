"""Phase F Reports v2 — tags, R-multiples, drawdown analytics."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import journal.db as db


@pytest.fixture(autouse=True)
def isolated_journal_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "cache_dir", lambda: tmp_path)
    db.init_db()
    yield


def _seed_tagged_trades():
    from journal.store import record_trade

    # Win: risk = |10-9.8|*100 = 20, R = 40/20 = 2.0
    record_trade(
        "AAA", "gap_and_go", "long", 100, 10.0, 9.8, 10.4, 10.4, 40.0, True,
        opened_ts=1000.0, closed_ts=1100.0, tags=["gap", "morning"],
    )
    # Loss: risk = 20, R = -10/20 = -0.5
    record_trade(
        "BBB", "bull_flag", "long", 100, 10.0, 9.8, 10.4, 9.8, -10.0, True,
        opened_ts=1200.0, closed_ts=1300.0, tags=["flag"],
    )
    # No stop — skipped for R
    record_trade(
        "CCC", "abcd", "long", 50, 5.0, None, 5.5, 5.5, 25.0, True,
        opened_ts=1400.0, closed_ts=1500.0, tags=["gap"],
    )


class TestTagPerformance:
    def test_tag_performance_shapes(self):
        from journal.store import get_closed_trades
        from journal.tags import tag_performance

        _seed_tagged_trades()
        rows = tag_performance(get_closed_trades())
        by_tag = {r["tag"]: r for r in rows}

        assert "gap" in by_tag
        gap = by_tag["gap"]
        assert gap["count"] == 2
        assert gap["wins"] == 2
        assert gap["pnl"] == 65.0
        assert gap["win_rate_pct"] == 100.0

        assert by_tag["flag"]["count"] == 1
        assert by_tag["flag"]["losses"] == 1
        assert by_tag["flag"]["win_rate_pct"] == 0.0


class TestRMultiples:
    def test_r_multiples_and_expectancy(self):
        from journal.r_multiples import compute_r_multiples
        from journal.store import get_closed_trades

        _seed_tagged_trades()
        result = compute_r_multiples(get_closed_trades())

        assert result["trade_count"] == 3
        assert result["scored_count"] == 2
        assert result["skipped_no_stop"] == 1
        assert result["expectancy_r"] == 0.75  # (2.0 + -0.5) / 2
        assert result["avg_win_r"] == 2.0
        assert result["avg_loss_r"] == -0.5

        scored = [t for t in result["trades"] if t["r_multiple"] is not None]
        assert len(scored) == 2


class TestDrawdown:
    def test_drawdown_curve_and_max(self):
        from journal.drawdown import compute_drawdown
        from journal.store import get_closed_trades

        _seed_tagged_trades()
        result = compute_drawdown(get_closed_trades())

        assert result["trade_count"] == 3
        assert result["final_equity"] == 55.0
        assert result["peak_equity"] == 55.0
        assert result["max_drawdown"] == 10.0
        assert len(result["curve"]) == 3
        assert result["curve"][-1]["equity"] == 55.0


class TestStoreTags:
    def test_record_and_update_tags(self):
        from journal.store import get_trade_by_id, record_trade, update_trade_tags

        trade_id = record_trade(
            "ZZZ", "gap_and_go", "long", 100, 5.0, 4.9, 5.2, 5.2, 10.0, True, tags=["a"],
        )
        row = get_trade_by_id(trade_id)
        assert row is not None
        assert row["tags"] == ["a"]

        updated = update_trade_tags(trade_id, ["x", "y"])
        assert updated is not None
        assert updated["tags"] == ["x", "y"]

    def test_tags_migration_on_legacy_table(self):
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
                notes TEXT,
                is_mock INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.execute(
            "INSERT INTO trades (opened_ts, symbol, side, qty, entry_price, pnl, is_mock) "
            "VALUES (1.0, 'OLD', 'long', 100, 5.0, 10.0, 0)"
        )
        conn.commit()
        conn.close()

        db.init_db()
        from journal.store import get_closed_trades, update_trade_tags

        rows = get_closed_trades()
        assert len(rows) == 1
        assert rows[0]["tags"] == []
        update_trade_tags(rows[0]["id"], ["legacy"])
        assert get_closed_trades()[0]["tags"] == ["legacy"]


class TestReportsV2Routes:
    """HTTP smoke for Phase F journal analytics + IBKR import honesty."""

    def test_tags_r_drawdown_endpoints(self):
        from fastapi.testclient import TestClient
        from main import app

        _seed_tagged_trades()
        client = TestClient(app)

        tags = client.get("/api/journal/tags")
        assert tags.status_code == 200
        assert tags.json()["count"] >= 1
        assert any(row["tag"] == "gap" for row in tags.json()["tags"])

        r_mult = client.get("/api/journal/r-multiples")
        assert r_mult.status_code == 200
        body = r_mult.json()
        assert body["scored_count"] == 2
        assert body["skipped_no_stop"] == 1

        dd = client.get("/api/journal/drawdown")
        assert dd.status_code == 200
        assert dd.json()["max_drawdown"] == 10.0

    def test_update_trade_tags_route(self):
        from fastapi.testclient import TestClient
        from journal.store import record_trade
        from main import app

        trade_id = record_trade(
            "TAG", "gap_and_go", "long", 10, 1.0, 0.9, 1.2, 1.2, 1.0, True, tags=["old"],
        )
        client = TestClient(app)
        res = client.post(f"/api/journal/trades/{trade_id}/tags", json={"tags": ["new", "a"]})
        assert res.status_code == 200
        assert res.json()["trade"]["tags"] == ["new", "a"]

    def test_ibkr_import_empty_is_loud_503(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        res = client.post("/api/journal/import/ibkr", json={})
        assert res.status_code == 503
        detail = res.json()["detail"]
        assert "Gateway" in detail or "JSON" in detail

    def test_ibkr_import_json_trades(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        res = client.post(
            "/api/journal/import/ibkr",
            json={
                "trades": [
                    {
                        "symbol": "IMP",
                        "qty": 10,
                        "entry_price": 2.0,
                        "exit_price": 2.5,
                        "pnl": 5.0,
                        "tags": ["import"],
                    }
                ]
            },
        )
        assert res.status_code == 200
        assert res.json()["imported"] == 1
