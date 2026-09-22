"""GET /api/practice/account and POST /api/practice/reset answer the ADR 020 contract."""
from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from practice import broker as practice_broker
from practice.routes import router
from sim.fill_model import Reference

CONTRACT = {
    "venue", "account_id", "starting_cash", "cash", "buying_power", "net_liquidation",
    "gross_position_value", "realized_pnl", "unrealized_pnl", "day_pnl", "realized_today", "day_started_et",
    "commissions_today", "positions", "working", "fills_today", "schema_version", "updated_at",
}


class DarkLive:
    """A live reference with nothing quoted -- the routes only need an account, not a fill."""

    def reference(self, symbol: str) -> Reference:
        return Reference(None, live=True)

    def admission(self, symbol: str):
        return False, "dark", "PRACTICE_NO_LIVE_PRINT"

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return 1_700_000_000.0


@pytest.fixture
def client(monkeypatch):
    practice_broker.reset_for_tests()
    monkeypatch.setattr(practice_broker, "LiveReference", DarkLive)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as test_client:
        yield test_client
    practice_broker.reset_for_tests()


def test_account_answers_the_contract_for_both_venues(client) -> None:
    sim = client.get("/api/practice/account", params={"venue": "sim"})
    assert sim.status_code == 200
    assert set(sim.json()) == CONTRACT | {"replay_key"}
    assert (sim.json()["venue"], sim.json()["account_id"]) == ("sim", "NOVA-SIM")
    paper = client.get("/api/practice/account", params={"venue": "Paper"})
    assert paper.status_code == 200
    body = paper.json()
    assert set(body) == CONTRACT
    assert (body["venue"], body["account_id"], body["starting_cash"]) == ("paper", "NOVA-PAPER", 100_000)
    assert body["cash"] == 100_000 and body["buying_power"] == 400_000 and body["positions"] == []


def test_an_unknown_venue_is_a_400_and_a_missing_one_a_422(client) -> None:
    assert client.get("/api/practice/account", params={"venue": "live"}).status_code == 400
    assert client.get("/api/practice/account").status_code == 422
    assert client.post("/api/practice/reset", json={"venue": "ibkr"}).status_code == 400


def test_reset_paper_returns_the_new_account_and_archives_the_old_ledger(client) -> None:
    first = client.post("/api/practice/reset", json={"venue": "paper", "starting_cash": 50_000})
    assert first.status_code == 200
    assert (first.json()["cash"], first.json()["starting_cash"], first.json()["archived"]) == (50_000, 50_000, None)
    second = client.post("/api/practice/reset", json={"venue": "paper"})
    assert second.status_code == 200
    archived = second.json()["archived"]
    assert archived and os.path.basename(archived).startswith("practice-paper-") and os.path.exists(archived)
    assert second.json()["starting_cash"] == 100_000
    assert client.get("/api/practice/account", params={"venue": "paper"}).json()["cash"] == 100_000


def test_reset_sim_starts_over_without_an_archive(client) -> None:
    out = client.post("/api/practice/reset", json={"venue": "sim", "starting_cash": 25_000})
    assert out.status_code == 200
    assert (out.json()["account_id"], out.json()["cash"], out.json()["archived"]) == ("NOVA-SIM", 25_000, None)


def test_reset_refuses_a_non_positive_starting_cash(client) -> None:
    assert client.post("/api/practice/reset", json={"venue": "paper", "starting_cash": 0}).status_code == 422
    assert client.post("/api/practice/reset", json={"venue": "paper", "starting_cash": -1}).status_code == 422
