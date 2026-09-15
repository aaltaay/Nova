"""Advise service: free reopen, force refresh, missing key, safety."""
from __future__ import annotations

import pytest

from advise import book, pool, safety, service
from advise.estimate import call_count, estimate
from advise.result_parse import parse_judge, ticket_for_stance
from constants_advise import ADVISE_GRAPH_VERSION, advise_model_id


@pytest.fixture
def advise_iso(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ADVISE_STUB", raising=False)
    pool.reset_for_tests()
    book.init_db()
    return tmp_path


def test_estimate_scales_with_depth():
    shallow = estimate("aapl", 1)
    deep = estimate("AAPL", 5)
    assert shallow["llm_calls"] == call_count(1)
    assert deep["llm_calls"] > shallow["llm_calls"]
    assert deep["est_usd"] > 0
    assert "not auto-trading" in deep["disclaimer"]


def test_reopen_complete_is_free(advise_iso, monkeypatch):
    monkeypatch.setattr(service, "session_key_et", lambda: "2026-09-15")
    run = book.create_run(
        symbol="AAPL",
        model=advise_model_id(),
        graph_version=ADVISE_GRAPH_VERSION,
        depth=2,
        session_date="2026-09-15",
    )
    book.set_result(run["id"], {"stance": "HOLD", "reasons": ["x"], "risks": ["y"]})
    book.update_status(run["id"], "complete", finished=True)

    async def _boom(_run_id):
        raise AssertionError("worker must not start on book reopen")

    monkeypatch.setattr(pool, "enqueue", _boom)
    opened = service.latest("aapl", 2)
    assert opened["from_book"] is True
    assert opened["id"] == run["id"]


@pytest.mark.asyncio
async def test_start_without_key_refuses_spend(advise_iso):
    with pytest.raises(service.AdviseError, match="OPENROUTER_API_KEY"):
        await service.start_run("AAPL", 2, force_refresh=True)


@pytest.mark.asyncio
async def test_start_reuses_todays_complete(advise_iso, monkeypatch):
    monkeypatch.setattr(service, "session_key_et", lambda: "2026-09-15")
    run = book.create_run(
        symbol="MSFT",
        model=advise_model_id(),
        graph_version=ADVISE_GRAPH_VERSION,
        depth=2,
        session_date="2026-09-15",
    )
    book.update_status(run["id"], "complete", finished=True)

    async def _boom(_run_id):
        raise AssertionError("cache hit must not enqueue")

    monkeypatch.setattr(pool, "enqueue", _boom)
    again = await service.start_run("MSFT", 2, force_refresh=False)
    assert again["id"] == run["id"]
    assert again["from_book"] is True


def test_ticket_prefill_does_not_place():
    long_t = ticket_for_stance("AAPL", "LONG", 50)
    assert long_t == {
        "symbol": "AAPL",
        "side": "BUY",
        "order_type": "MKT",
        "quantity_value": "50",
        "limit_price": "",
        "places": False,
    }
    assert ticket_for_stance("AAPL", "HOLD", None) is None
    parsed = parse_judge("NVDA", '{"stance":"SHORT","reasons":["r"],"risks":["k"],"qty_hint":10}')
    assert parsed["ticket"]["side"] == "SELL"
    assert parsed["ticket"]["places"] is False


def test_advise_sources_never_import_ibkr():
    assert safety.forbidden_hits() == []
