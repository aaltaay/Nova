"""Brain memory store -- schema, isolation, last-N."""
from __future__ import annotations

import json

import pytest

from constants_sensors import SENSOR_MEMORY_FILENAME, SENSOR_MEMORY_SCHEMA_VERSION
from paths import cache_dir
from sensors import memory_store


def setup_function() -> None:
    memory_store.reset_for_tests()


def test_append_and_filter_by_symbol():
    memory_store.append_decision(symbol="aapl", decision="go", confidence=0.7)
    memory_store.append_decision(symbol="MSFT", decision="no-go", confidence=0.2)
    rows = memory_store.list_decisions("AAPL")
    assert len(rows) == 1
    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["decision"] == "go"
    path = cache_dir() / SENSOR_MEMORY_FILENAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SENSOR_MEMORY_SCHEMA_VERSION
    assert str(path).find(".cache") == -1 or "nova_cache" in str(path) or "nova_pytest" in str(path)


def test_unknown_schema_refuses_loud(tmp_path, monkeypatch):
    memory_store.reset_for_tests()
    path = cache_dir() / SENSOR_MEMORY_FILENAME
    path.write_text(json.dumps({"schema_version": 99, "decisions": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        memory_store.list_decisions("AAPL")


def test_rejects_unknown_decision():
    with pytest.raises(ValueError, match="decision"):
        memory_store.append_decision(symbol="AAPL", decision="maybe", confidence=0.5)
