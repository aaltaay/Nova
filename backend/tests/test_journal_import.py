"""Reports file import -- CSV/JSON facts only; never invent P/L."""
from pathlib import Path

import pytest

import journal.db as db

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "journal_import"


@pytest.fixture(autouse=True)
def isolated_journal_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "cache_dir", lambda: tmp_path)
    db.init_db()
    yield


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class TestParseImport:
    def test_csv_fixture_keeps_supplied_pnl_and_commission(self):
        from journal.calendar import et_date_from_ts
        from journal.import_parse import parse_import_bytes

        parsed = parse_import_bytes("valid_trades.csv", _read("valid_trades.csv"))
        assert parsed["ok"] is True
        assert parsed["source"] == "csv"
        trade = parsed["trades"][0]
        assert trade["symbol"] == "IMP"
        assert trade["qty"] == 100
        assert trade["pnl"] == 48.0
        assert trade["commission"] == 2.0
        assert et_date_from_ts(trade["closed_ts"]).isoformat() == "2026-03-15"

    def test_json_fixture_matches_csv_facts(self):
        from journal.import_parse import parse_import_bytes

        parsed = parse_import_bytes("valid_trades.json", _read("valid_trades.json"))
        assert parsed["ok"] is True
        assert parsed["source"] == "json"
        trade = parsed["trades"][0]
        assert trade["pnl"] == 48.0
        assert trade["commission"] == 2.0
        assert trade["tags"] == ["import", "sample"]

    def test_missing_pnl_is_skipped_not_computed(self):
        from journal.import_parse import parse_import_bytes

        parsed = parse_import_bytes("missing_facts.csv", _read("missing_facts.csv"))
        assert parsed["ok"] is True
        assert len(parsed["trades"]) == 1
        assert parsed["trades"][0]["symbol"] == "OK"
        assert parsed["trades"][0]["pnl"] == 2.0
        reasons = " ".join(parsed["skipped"])
        assert "missing" in reasons
        assert "pnl" in reasons or "exit" in reasons or "side" in reasons
        assert any("SKIP" in r or "row 0" in r for r in parsed["skipped"])

    def test_does_not_invent_pnl_from_prices(self):
        from journal.import_parse import normalize_trade_row

        trade, reason = normalize_trade_row(
            {
                "symbol": "FAKE",
                "side": "long",
                "qty": 10,
                "entry_price": 2.0,
                "exit_price": 3.0,
                "closed_at": "2026-03-15",
            },
            0,
        )
        assert trade is None
        assert reason is not None
        assert "pnl" in reason or "missing" in reason

    def test_flex_xml_is_rejected(self):
        from journal.import_parse import parse_import_bytes

        parsed = parse_import_bytes("flex.xml", b"<FlexQueryResponse/>")
        assert parsed["ok"] is False
        assert "Flex" in parsed["error"] or "XML" in parsed["error"]


class TestApplyImport:
    def test_apply_writes_journal_and_calendar(self):
        from journal.calendar import build_year_calendar
        from journal.import_apply import import_uploaded_file
        from journal.store import get_closed_trades

        result = import_uploaded_file("valid_trades.csv", _read("valid_trades.csv"))
        assert result["ok"] is True
        assert result["imported"] == 1
        trades = get_closed_trades()
        assert len(trades) == 1
        assert trades[0]["pnl"] == 48.0
        assert trades[0]["commission"] == 2.0
        year = build_year_calendar(trades, 2026)
        assert year["year_trade_count"] == 1
        assert year["year_pnl"] == 48.0

    def test_reimport_is_idempotent(self):
        from journal.import_apply import import_uploaded_file
        from journal.store import get_closed_trades

        first = import_uploaded_file("valid_trades.json", _read("valid_trades.json"))
        second = import_uploaded_file("valid_trades.json", _read("valid_trades.json"))
        assert first["imported"] == 1
        assert second["imported"] == 0
        assert second["duplicates"] == 1
        assert len(get_closed_trades()) == 1


class TestImportRoute:
    def test_upload_csv_then_calendar(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        res = client.post(
            "/api/journal/import",
            json={
                "filename": "valid_trades.csv",
                "content": _read("valid_trades.csv").decode("utf-8"),
            },
        )
        assert res.status_code == 200
        assert res.json()["imported"] == 1

        cal = client.get("/api/journal/calendar?year=2026")
        assert cal.status_code == 200
        body = cal.json()
        assert body["year_trade_count"] == 1
        assert body["year_pnl"] == 48.0

        trades = client.get("/api/journal/trades")
        assert trades.status_code == 200
        assert trades.json()["trades"][0]["symbol"] == "IMP"

    def test_all_skipped_is_loud_400(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        only_bad = (
            b"symbol,side,qty,entry_price,exit_price,pnl,closed_at\n"
            b"BAD,long,10,1.00,1.10,,2026-03-15\n"
        )
        res = client.post(
            "/api/journal/import",
            json={"filename": "bad.csv", "content": only_bad.decode("utf-8")},
        )
        assert res.status_code == 400
        detail = res.json()["detail"]
        assert detail["imported"] == 0
        assert "required fact" in detail["error"] or detail["skipped"] >= 1
