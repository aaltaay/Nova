"""Approve meets your order size limit (ADR 064): said at Approve, and again by the door at the trigger.

The plan box's Approve is your own order (source ``manual``, origin ``approve``), so Paper's Max shares and Max
risk at stop read it. Refusing at Approve says it now, not hours later; a limit lowered after the approval is
the door's to refuse at the trigger, and the approval says why. The real door and the practice broker run on
Paper against ``test_stock_mode``'s fake live market (153 shares at 10.02, stop 9.89: $19.89 at risk).
"""
from __future__ import annotations

from execution.size_limit import settings
from stock_mode import runner, store
from tests.bot_helpers import headers
from tests.test_stock_mode import (  # noqa: F401 -- fixtures
    SYM,
    api_key,
    approve_body,
    client,
    lane,
    paper,
    put,
    tick,
    trigger,
)


def _approve(p):
    return client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(p.key))


def test_approve_refuses_a_plan_over_your_limit_in_its_words(paper, monkeypatch):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    put(paper, "you", "nova")
    settings.update({"paper": {"max_shares": 100}})
    r = _approve(paper)
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "ORDER_SIZE_LIMIT_SHARES"
    assert r.json()["detail"]["error"].startswith("Paper allows at most 100 shares per order; this order is 153")
    assert store.approval(SYM) is None
    settings.update({"paper": {"max_shares": None, "max_risk_usd": 19}})
    risky = _approve(paper)
    assert risky.status_code == 409 and risky.json()["detail"]["reason"] == "ORDER_SIZE_LIMIT_RISK"
    assert "this order risks $19.89 (153 shares x $0.13" in risky.json()["detail"]["error"]
    settings.update({"paper": {"max_risk_usd": 20}})
    assert _approve(paper).status_code == 200 and store.approval(SYM)["state"] == "waiting"


def test_a_limit_lowered_after_the_approval_is_refused_at_the_trigger_and_said(paper, monkeypatch):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    put(paper, "you", "nova")
    assert _approve(paper).status_code == 200
    settings.update({"paper": {"max_shares": 100}})
    runner.submit(trigger())
    tick(paper)
    approval = store.approval(SYM)
    assert approval["state"] == "withdrawn"
    assert "the bracket was refused: Paper allows at most 100 shares per order" in approval["reason"]
    assert store.trade("paper", SYM) is None
