"""LLM decide pack -- L2+Activate live fire. No live IBKR or paid LLM."""
from __future__ import annotations

import pytest

from bot.autonomy import apply_patch
from bot.errors import BotError
from bot.packs import assert_pack_can_fire, catalog, normalize_pack
from bot.persist import load_session
from bot.proposals import submit
from bot.session import get_session
from constants_bot import (
    BOT_PACK_LLM_DECIDE,
    BOT_REASON_LLM_CAP,
    BOT_REASON_L1_NO_FIRE,
)
from tests.bot_helpers import ready_l2


def test_catalog_includes_llm_decide_description():
    rows = {row["id"]: row for row in catalog()}
    assert BOT_PACK_LLM_DECIDE in rows
    assert rows[BOT_PACK_LLM_DECIDE]["status"] == "live"
    desc = rows[BOT_PACK_LLM_DECIDE]["description"]
    assert "L2" in desc
    assert "Activate" in desc
    assert "LLM_LIVE_FIRE" not in desc
    assert "stub" not in rows["quote-spike"]["description"].lower()
    assert rows["quote-spike"]["status"] == "live"
    assert normalize_pack(BOT_PACK_LLM_DECIDE) == BOT_PACK_LLM_DECIDE


def test_llm_pack_can_fire_without_hidden_flag():
    assert_pack_can_fire(BOT_PACK_LLM_DECIDE)


def test_session_exposes_llm_caps_and_configured_false(monkeypatch):
    monkeypatch.delenv("NOVA_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    view = get_session()
    assert view["llm"]["live_fire"] is False
    assert view["llm"]["configured"] is False
    assert view["llm"]["call_cap"] == 10
    apply_patch({"llm": {"call_cap": 4, "usd_cap": 1.25}}, desk=True)
    view = get_session()
    assert view["llm"]["call_cap"] == 4
    assert view["llm"]["usd_cap"] == 1.25


def test_openrouter_key_alone_configures_llm(monkeypatch):
    from bot.llm_guard import llm_base_url, llm_configured, llm_model_id
    from constants_bot import BOT_LLM_DEFAULT_MODEL, BOT_LLM_OPENROUTER_BASE_URL

    monkeypatch.delenv("NOVA_LLM_API_KEY", raising=False)
    monkeypatch.delenv("NOVA_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("NOVA_LLM_MODEL", raising=False)
    monkeypatch.delenv("NOVA_BRAIN_MODEL", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    assert llm_configured() is True
    assert llm_base_url() == BOT_LLM_OPENROUTER_BASE_URL
    assert llm_model_id() == BOT_LLM_DEFAULT_MODEL


def test_session_llm_live_fire_follows_activate(monkeypatch):
    monkeypatch.setenv("NOVA_LLM_API_KEY", "test-key")
    monkeypatch.setenv("NOVA_LLM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("NOVA_LLM_MODEL", "test-model")
    ready_l2(brain="brain-1", heartbeat=True)
    apply_patch({"active_pack": BOT_PACK_LLM_DECIDE}, desk=True)
    view = get_session()
    assert view["llm"]["configured"] is True
    assert view["llm"]["live_fire"] is True
    assert view["live_fire_ready"] is True


def test_llm_spend_fail_closed_on_cap(monkeypatch):
    from bot.llm_guard import assert_and_charge

    monkeypatch.setenv("NOVA_LLM_API_KEY", "test-key")
    monkeypatch.setenv("NOVA_LLM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("NOVA_LLM_MODEL", "test-model")
    apply_patch({"llm": {"call_cap": 1, "usd_cap": 0.05}}, desk=True)
    assert_and_charge(0.02)
    with pytest.raises(BotError) as exc:
        assert_and_charge(0.02)
    assert exc.value.reason == BOT_REASON_LLM_CAP
    assert load_session()["llm"]["calls_used"] == 1


def test_llm_pack_may_propose_at_l2():
    ready_l2(brain="brain-1", heartbeat=True)
    apply_patch({"active_pack": BOT_PACK_LLM_DECIDE}, desk=True)
    item = submit(
        {
            "symbol": "ABCD",
            "side": "BUY",
            "kind": "buy_market",
            "reason": "model resume setup",
            "confidence": 0.6,
        },
        brain_session_id="brain-1",
    )
    assert item["symbol"] == "ABCD"
    assert item["preset_qty"] == 1
    assert item.get("qty") is None


def test_other_packs_still_refuse_l2_proposals():
    ready_l2(brain="brain-1", heartbeat=True)
    with pytest.raises(BotError) as exc:
        submit(
            {
                "symbol": "ABCD",
                "side": "BUY",
                "kind": "buy_market",
                "reason": "halt pack proposes at L1 only",
            },
            brain_session_id="brain-1",
        )
    assert exc.value.reason == BOT_REASON_L1_NO_FIRE
