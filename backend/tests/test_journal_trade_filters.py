"""The journal's trade list filters (``GET /api/journal/trades``): by symbol, setup, tag, the plan flag and the ET
day a trade opened, with the limit counting matches -- the operator's trades narrowed by the facts the journal
already stores, never fetched whole and filtered by hand."""
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import journal.db as db

ET = ZoneInfo("America/New_York")


def ts(stamp: str) -> float:
    return datetime.fromisoformat(stamp).replace(tzinfo=ET).timestamp()


@pytest.fixture(autouse=True)
def journal(tmp_path, monkeypatch):
    from journal.store import record_trade
    monkeypatch.setattr(db, "cache_dir", lambda: tmp_path)
    db.init_db()
    trades = [("AAA", "gap_and_go", True, "2026-10-01 09:35", ["gap", "Morning"]),
              ("BBB", "bull_flag", False, "2026-10-01 23:30", ["flag"]),             # still Oct 1 in ET
              ("aaa", "Gap_And_Go", None, "2026-10-02 10:00", ["gap"]),
              ("CCC", "abcd", True, "2026-10-03 11:00", [])]
    for symbol, setup, adherent, opened, tags in trades:
        record_trade(symbol, setup, "long", 100, 10.0, 9.8, 10.4, 10.4, 40.0, adherent,
                     opened_ts=ts(opened), closed_ts=ts(opened) + 60, tags=tags)
    yield


def symbols(**filters) -> list[str]:
    from journal.store import get_trades
    return [t["symbol"] for t in get_trades(**filters)]


def test_symbol_and_setup_match_exactly_in_any_case():
    assert symbols(symbol="aaa") == ["aaa", "AAA"]                          # newest first
    assert symbols(setup="GAP_AND_GO") == ["aaa", "AAA"]


def test_a_tag_is_one_of_the_trades_tags_and_the_limit_counts_matches():
    assert symbols(tag="morning") == ["AAA"]
    assert symbols(tag="gap", limit=1) == ["aaa"]


def test_the_plan_flag_and_the_et_day_the_trade_opened():
    assert symbols(adherent=True) == ["CCC", "AAA"]
    assert symbols(adherent=False) == ["BBB"]                               # no flag matches neither
    assert symbols(date_from="2026-10-01", date_to="2026-10-01") == ["BBB", "AAA"]
    assert symbols(date_from="2026-10-02") == ["CCC", "aaa"]


def test_the_route_echoes_its_filters_and_refuses_a_bad_day():
    from fastapi.testclient import TestClient

    from main import app
    with TestClient(app) as client:
        answer = client.get("/api/journal/trades", params={"tag": "gap", "adherent": "true"}).json()
        assert answer["filters"] == {"tag": "gap", "adherent": True}
        assert [t["symbol"] for t in answer["trades"]] == ["AAA"]
        assert client.get("/api/journal/trades", params={"date_from": "10/01/2026"}).status_code == 400
