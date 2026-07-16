"""Unit tests for the Nova OS append-only event store -- no network, no orders."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nova_os.events_db as events_db


@pytest.fixture(autouse=True)
def isolated_events_db(tmp_path, monkeypatch):
    """Point the event log at a throwaway SQLite file per test so tests never
    touch the real backend/.cache/nova_os_events.db."""
    monkeypatch.setattr(events_db, "cache_dir", lambda: tmp_path)
    events_db.init_db()
    yield


class TestRecordReceipt:
    def test_record_and_read_back(self):
        from nova_os.events import KIND_DECISION, get_events, record_receipt

        receipt = record_receipt(
            kind=KIND_DECISION,
            symbol="AAPL",
            decision="NO_BUY",
            action="declined",
            mode="signal",
            reason_codes=["PILLAR_FLOAT_FAIL"],
            would_execute=False,
            executed=False,
            payload={"note": "float too big"},
        )
        assert receipt["id"] >= 1
        assert receipt["policy_version"]

        rows = get_events()
        assert len(rows) == 1
        row = rows[0]
        assert row["symbol"] == "AAPL"
        assert row["decision"] == "NO_BUY"
        assert row["action"] == "declined"
        assert row["reason_codes"] == ["PILLAR_FLOAT_FAIL"]
        assert row["would_execute"] is False
        assert row["executed"] is False
        assert row["payload"] == {"note": "float too big"}

    def test_events_newest_first(self):
        from nova_os.events import KIND_SYSTEM, get_events, record_receipt

        record_receipt(kind=KIND_SYSTEM, symbol="AAA")
        record_receipt(kind=KIND_SYSTEM, symbol="BBB")
        rows = get_events()
        assert [r["symbol"] for r in rows] == ["BBB", "AAA"]

    def test_filter_by_symbol_and_kind(self):
        from nova_os.events import KIND_ACTION, KIND_DECISION, get_events, record_receipt

        record_receipt(kind=KIND_DECISION, symbol="AAA", decision="BUY")
        record_receipt(kind=KIND_ACTION, symbol="AAA", action="executed_paper", executed=True)
        record_receipt(kind=KIND_ACTION, symbol="BBB", action="displayed")

        assert len(get_events(symbol="AAA")) == 2
        assert len(get_events(kind=KIND_ACTION)) == 2
        both = get_events(symbol="AAA", kind=KIND_ACTION)
        assert len(both) == 1
        assert both[0]["action"] == "executed_paper"
        assert both[0]["executed"] is True

    def test_limit(self):
        from nova_os.events import KIND_SYSTEM, get_events, record_receipt

        for i in range(5):
            record_receipt(kind=KIND_SYSTEM, symbol=f"S{i}")
        assert len(get_events(limit=2)) == 2


class TestFailClosed:
    def test_unknown_decision_rejected(self):
        from nova_os.events import KIND_DECISION, record_receipt

        with pytest.raises(ValueError):
            record_receipt(kind=KIND_DECISION, decision="SELL")

    def test_unknown_action_rejected(self):
        from nova_os.events import KIND_ACTION, record_receipt

        with pytest.raises(ValueError):
            record_receipt(kind=KIND_ACTION, action="nuke")

    def test_unknown_mode_rejected(self):
        from nova_os.events import KIND_DECISION, record_receipt

        with pytest.raises(ValueError):
            record_receipt(kind=KIND_DECISION, mode="yolo")

    def test_unknown_reason_code_rejected(self):
        from nova_os.events import KIND_DECISION, record_receipt

        with pytest.raises(ValueError):
            record_receipt(kind=KIND_DECISION, reason_codes=["PILLARS_PASS", "MADE_UP"])

    def test_bad_write_does_not_persist(self):
        from nova_os.events import KIND_DECISION, get_events, record_receipt

        with pytest.raises(ValueError):
            record_receipt(kind=KIND_DECISION, decision="SELL")
        assert get_events() == []


class TestAlertHookVisibility:
    def test_record_receipt_succeeds_when_alerts_import_missing(self, monkeypatch):
        from nova_os.events import KIND_SYSTEM, record_receipt

        import builtins

        real_import = builtins.__import__

        def _block_alerts(name, *args, **kwargs):
            if name == "alerts.hooks" or name.startswith("alerts."):
                raise ImportError("alerts unavailable in test")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _block_alerts)
        receipt = record_receipt(kind=KIND_SYSTEM, symbol="ZZZ")
        assert receipt["symbol"] == "ZZZ"
