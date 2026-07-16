"""Tests for backtest engine + routes — seeds tmp cold day when needed."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive.capture as capture
import archive.compact as compact
import archive.db as archive_db
from backtest.engine import run_backtest
from constants import ARCHIVE_SOURCE_IBKR
from main import app

client = TestClient(app)

_SESSION_DATE = "2026-07-11"
_BASE_TS = 1_720_086_400.0  # distinct from archive route tests


@pytest.fixture(autouse=True)
def isolated_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(compact, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    capture.clear_l2_stub_for_tests()
    yield tmp_path


def _seed_day() -> None:
    for i in range(30):
        px = 5.0 + i * 0.03
        capture.record_bar(
            symbol="BTST",
            ts=_BASE_TS + i * 60,
            open_=px,
            high=px + 0.15,
            low=px - 0.08,
            close=px + 0.05,
            volume=80_000 + i * 500,
            source=ARCHIVE_SOURCE_IBKR,
            timeframe="1m",
            session_date=_SESSION_DATE,
        )
    compact.compact_day(_SESSION_DATE)


class TestBacktestEngine:
    def test_run_no_crash_and_honesty_flags(self, tmp_path):
        _seed_day()
        result = run_backtest(_SESSION_DATE, setup="all", symbols=["BTST"], cold_dir=compact.cold_root(tmp_path))
        assert result["ok"] is True
        assert result["honesty"]["bar_resolution"] == "1m"
        assert result["honesty"]["spread_modeled"] is False
        assert result["honesty"]["hindsight"] is False
        assert "metrics" in result
        assert result["metrics"]["trade_count"] >= 0

    def test_missing_day_returns_error(self, tmp_path):
        result = run_backtest("1999-01-01", cold_dir=compact.cold_root(tmp_path))
        assert result["ok"] is False
        assert "missing cold day" in result["error"]


class TestBacktestRoutes:
    def test_health(self):
        res = client.get("/api/backtest/health")
        assert res.status_code == 200
        body = res.json()
        assert body["scorer"] == "nova-native"
        assert body["vectorbt_required"] is False
        assert "cold_day_count" in body

    def test_days_after_seed(self):
        _seed_day()
        res = client.get("/api/backtest/days")
        assert res.status_code == 200
        assert _SESSION_DATE in res.json()["days"]

    def test_run_post(self):
        _seed_day()
        res = client.post(
            "/api/backtest/run",
            json={"session_date": _SESSION_DATE, "setup": "gap_and_go", "symbols": ["BTST"]},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["honesty"]["hindsight"] is False
        assert body["setup"] == "gap_and_go"

    def test_run_bad_setup_400(self):
        res = client.post(
            "/api/backtest/run",
            json={"session_date": _SESSION_DATE, "setup": "nope"},
        )
        assert res.status_code == 400

    def test_run_missing_day_404(self):
        res = client.post(
            "/api/backtest/run",
            json={"session_date": "1999-01-01", "setup": "all"},
        )
        assert res.status_code == 404
