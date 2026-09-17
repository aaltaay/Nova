"""Small-cap filters: shares, BP, working block, offsets, TTL."""
from __future__ import annotations

import time

import pytest

from bot.autonomy import apply_patch
from bot.errors import BotError
from bot.persist import load_session
from bot.risk import (
    assert_bp_budget,
    assert_kind,
    assert_no_working_buy,
    drop_working,
    open_plus_working_usd,
    remember_working,
    resolve_offset,
    resolve_percent,
    resolve_shares,
)
from bot.ttl import due_working
from constants_bot import (
    BOT_DEFAULT_ASK_OFFSET_USD,
    BOT_DEFAULT_BID_EXIT_OFFSET_USD,
    BOT_REASON_BP_BUDGET,
    BOT_REASON_FREE_FORM_QTY,
    BOT_REASON_KIND_BLOCKED,
    BOT_REASON_WORKING_BLOCK,
)


@pytest.fixture
def l2_row():
    apply_patch({"level": 2}, desk=True)
    return load_session()


def test_free_form_qty_refused(l2_row):
    with pytest.raises(BotError) as exc:
        resolve_shares("buy_market", {"qty": 3}, l2_row)
    assert exc.value.reason == BOT_REASON_FREE_FORM_QTY
    with pytest.raises(BotError) as exc:
        resolve_shares("buy_market", {"shares": 2}, l2_row)
    assert exc.value.reason == BOT_REASON_FREE_FORM_QTY
    assert resolve_shares("buy_market", {}, l2_row) == 1


def test_model_dump_none_qty_is_not_free_form(l2_row):
    assert resolve_shares("buy_market", {"qty": None, "shares": None}, l2_row) == 1


def test_percent_and_offset_presets(l2_row):
    assert resolve_percent({}) == 50
    assert resolve_percent({"percent": None}) == 50
    assert resolve_percent({"percent": 25}) == 25
    with pytest.raises(BotError) as exc:
        resolve_percent({"percent": 33})
    assert exc.value.reason == BOT_REASON_FREE_FORM_QTY
    assert resolve_offset("buy_limit_ask_offset", {}) == BOT_DEFAULT_ASK_OFFSET_USD
    assert resolve_offset("buy_limit_ask_offset", {"offset_dollars": None}) == BOT_DEFAULT_ASK_OFFSET_USD
    assert resolve_offset("sell_limit_bid_offset", {}) == BOT_DEFAULT_BID_EXIT_OFFSET_USD
    with pytest.raises(BotError) as exc:
        resolve_offset("buy_limit_ask_offset", {"offset_dollars": 0.2})
    assert exc.value.reason == BOT_REASON_FREE_FORM_QTY


def test_later_kinds_blocked(l2_row):
    with pytest.raises(BotError) as exc:
        assert_kind("cancel_and_exit", l2_row)
    assert exc.value.reason == BOT_REASON_KIND_BLOCKED


def test_working_buy_blocks_new_buy(l2_row):
    remember_working(
        order_id=7,
        symbol="ABCD",
        side="BUY",
        qty=1,
        price=2.0,
        kind="buy_limit_ask_offset",
        ttl_sec=3,
    )
    row = load_session()
    with pytest.raises(BotError) as exc:
        assert_no_working_buy("buy_market", row)
    assert exc.value.reason == BOT_REASON_WORKING_BLOCK
    assert_no_working_buy("exit_pos", row)
    drop_working(7)
    assert_no_working_buy("buy_market", load_session())


def test_bp_budget_open_plus_working(monkeypatch, l2_row):
    monkeypatch.setattr("bot.risk.last_quote", lambda _s: {"price": 10.0})
    monkeypatch.setattr("bot.risk.top_of_book", lambda _s: (9.9, 10.1))
    row = load_session()
    row["bot_qty"] = {"ABCD": 4}  # $40 open
    with pytest.raises(BotError) as exc:
        assert_bp_budget("buy_market", "ABCD", 2, 10.0, row)  # +$20
    assert exc.value.reason == BOT_REASON_BP_BUDGET
    assert_bp_budget("buy_market", "ABCD", 1, 10.0, row)  # +$10 = $50
    row["working"] = [{"side": "BUY", "qty": 1, "price": 10.0}]
    assert open_plus_working_usd(row) == 50.0
    with pytest.raises(BotError) as exc:
        assert_bp_budget("buy_market", "EFGH", 1, 1.0, row)
    assert exc.value.reason == BOT_REASON_BP_BUDGET
    row["bot_qty"] = {"ABCD": -4}
    row["working"] = []
    assert open_plus_working_usd(row) == 0.0


def test_ttl_due_working():
    remember_working(
        order_id=9,
        symbol="ZZZ",
        side="SELL",
        qty=1,
        price=1.0,
        kind="sell_limit_ask_offset",
        ttl_sec=1,
    )
    row = load_session()
    row["working"][0]["expire_ts"] = time.time() - 1
    from bot.persist import save_session

    save_session(row)
    due = due_working()
    assert len(due) == 1
    assert due[0]["order_id"] == 9
