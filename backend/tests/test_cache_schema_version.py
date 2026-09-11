"""D-017: dated snapshots and named persist files stamp / refuse schema_version."""
from __future__ import annotations

import json
from unittest.mock import patch

import cache
from cache_schema import (
    ALERTS_CHANNELS_SCHEMA_VERSION,
    GAPPERS_SCHEMA_VERSION,
    HOD_MOMO_BLOCKLIST_SCHEMA_VERSION,
    accept_schema,
)


def test_gapper_snapshot_stamps_schema_and_refuses_unknown(tmp_path, caplog):
    with patch("cache._CACHE_DIR", str(tmp_path)), patch("cache._today_et", return_value="2026-09-11"):
        cache.save_gapper_snapshot([{"symbol": "AAA", "price": 1, "prev_close": 1}], 1.0)
        path = tmp_path / "gappers-2026-09-11.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == GAPPERS_SCHEMA_VERSION
        rows, ts = cache.load_gapper_snapshot()
        assert rows and rows[0]["symbol"] == "AAA"
        assert ts == 1.0

        payload["schema_version"] = 99
        path.write_text(json.dumps(payload), encoding="utf-8")
        empty, empty_ts = cache.load_gapper_snapshot()
        assert empty == []
        assert empty_ts == 0.0
    assert "unknown schema_version" in caplog.text


def test_legacy_gapper_file_without_version_still_loads(tmp_path):
    path = tmp_path / "gappers-2026-09-11.json"
    path.write_text(
        json.dumps({"date": "2026-09-11", "ts": 2.0, "gappers": [{"symbol": "LEG"}]}),
        encoding="utf-8",
    )
    with patch("cache._CACHE_DIR", str(tmp_path)), patch("cache._today_et", return_value="2026-09-11"):
        rows, ts = cache.load_gapper_snapshot()
    assert rows[0]["symbol"] == "LEG"
    assert ts == 2.0


def test_blocklist_stamps_and_refuses_unknown(tmp_path, caplog):
    path = tmp_path / "hod-momo-blocklist.json"
    with patch.object(cache, "HOD_MOMO_BLOCKLIST_FILE", str(path)), patch.object(cache, "_CACHE_DIR", str(tmp_path)):
        cache.save_hod_momo_blocklist(["BAD"])
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == HOD_MOMO_BLOCKLIST_SCHEMA_VERSION
        assert cache.load_hod_momo_blocklist() == ["BAD"]
        payload["schema_version"] = 77
        path.write_text(json.dumps(payload), encoding="utf-8")
        assert cache.load_hod_momo_blocklist() == []
    assert "unknown schema_version" in caplog.text


def test_accept_schema_legacy_missing_version():
    assert accept_schema({"rows": []}, 1, name="x") == {"rows": []}


def test_alerts_channels_schema_constant_is_int():
    assert ALERTS_CHANNELS_SCHEMA_VERSION == 1
