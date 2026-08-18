"""News catalyst dated-JSON snapshot."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cache
import news_catalyst_persist as persist


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(cache, "_today_et", lambda: "2026-08-17")
    monkeypatch.setattr(persist, "_today_et", lambda: "2026-08-17")
    yield


def test_save_and_load_news_catalyst_snapshot():
    rows = [{"symbol": "IVF", "catalyst_headline": "FDA"}]
    persist.save_news_catalyst_snapshot(rows, 1_700_000_000.0)
    loaded, ts = persist.load_news_catalyst_snapshot()
    assert loaded == rows
    assert ts == 1_700_000_000.0
    path = Path(cache._CACHE_DIR) / "news-catalysts-2026-08-17.json"
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["date"] == "2026-08-17"
