"""Regression tests for cache.py error visibility (Phase 11)."""
from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest

import cache


def test_atomic_write_logs_temp_cleanup_failure(tmp_path, caplog):
    target = tmp_path / "gappers-2026-07-16.json"
    with patch("cache._CACHE_DIR", str(tmp_path)):
        with patch("cache.os.replace", side_effect=OSError("disk full")):
            with patch("cache.os.unlink", side_effect=OSError("missing")):
                with caplog.at_level(logging.DEBUG, logger="cache"):
                    with pytest.raises(OSError, match="disk full"):
                        cache._atomic_write(str(target), {"date": "2026-07-16"})
    assert any("temp file cleanup failed" in r.message for r in caplog.records)


def test_load_hod_momo_highs_ignores_stale_prior_day_file(tmp_path):
    """A genuinely new trading day must still start fresh, even though the
    prior day's highs file is still sitting on disk (see PROBLEM_LOG
    2026-07-23 — highs persistence)."""
    stale = tmp_path / "hod-momo-highs-2026-07-22.json"
    stale.write_text(
        json.dumps({"date": "2026-07-22", "session_highs": {"OLD": 1.0}}),
        encoding="utf-8",
    )
    with patch("cache._CACHE_DIR", str(tmp_path)):
        with patch("cache._today_et", return_value="2026-07-23"):
            assert cache.load_hod_momo_highs() == {}


def test_save_then_load_hod_momo_highs_round_trips(tmp_path):
    with patch("cache._CACHE_DIR", str(tmp_path)):
        with patch("cache._today_et", return_value="2026-07-23"):
            cache.save_hod_momo_highs({"session_highs": {"WLDS": 3.21}})
            loaded = cache.load_hod_momo_highs()
    assert loaded["session_highs"] == {"WLDS": 3.21}
    assert loaded["date"] == "2026-07-23"


def test_cleanup_old_snapshots_logs_delete_failure(tmp_path, caplog):
    stale = tmp_path / "gappers-2020-01-01.json"
    stale.write_text(json.dumps({"date": "2020-01-01", "gappers": []}), encoding="utf-8")
    with patch("cache._CACHE_DIR", str(tmp_path)):
        with patch("cache.os.unlink", side_effect=OSError("permission denied")):
            with caplog.at_level(logging.WARNING, logger="cache"):
                cache.cleanup_old_snapshots(retention_days=1)
    assert any("failed to delete expired snapshot" in r.message for r in caplog.records)
    assert stale.exists()
