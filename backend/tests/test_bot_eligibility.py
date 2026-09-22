"""Symbol gates: Eyes see allowlist AND live Trader focus; fire needs allowlist AND a held depth line."""
from __future__ import annotations

import pytest

from bot.eligibility import (
    add_symbol,
    assert_depth_line,
    assert_symbol_can_fire,
    assert_symbol_eligible,
    eligible_symbols,
    holds_depth_line,
    remove_symbol,
)
from bot.errors import BotError
from bot.packs import assert_pack_can_fire, catalog, normalize_pack
from bot.persist import default_session
from constants_bot import (
    BOT_NO_DEPTH_LINE_HINT,
    BOT_REASON_NO_DEPTH_LINE,
    BOT_REASON_SYMBOL_BLOCKED,
)
from ibkr.depth import state as depth_state
from tests.bot_helpers import hold_depth_line


def test_eligible_is_intersection():
    row = {"symbol_allowlist": ["aaa", "BBB"], "trader_live": ["bbb", "CCC"]}
    assert eligible_symbols(row) == ["BBB"]


def test_empty_allowlist_fail_closed():
    with pytest.raises(BotError) as exc:
        assert_symbol_eligible("ABCD", {"symbol_allowlist": [], "trader_live": ["ABCD"]})
    assert exc.value.reason == BOT_REASON_SYMBOL_BLOCKED


# ── fire gate: allowlist AND a depth line the backend holds (ADR 020) ────────

def test_fire_gate_refuses_a_symbol_with_no_depth_line():
    """The UI said the tab is live; the backend holds no line -- the line is the fact."""
    row = {"symbol_allowlist": ["ABCD"], "trader_live": ["ABCD"]}
    assert holds_depth_line("ABCD") is False
    with pytest.raises(BotError) as exc:
        assert_symbol_can_fire("abcd", row)
    assert exc.value.status_code == 409
    assert exc.value.reason == BOT_REASON_NO_DEPTH_LINE
    assert BOT_NO_DEPTH_LINE_HINT in exc.value.message
    assert "open its Level 2 or record it" in exc.value.message


def test_fire_gate_passes_when_a_trader_level_2_holds_the_line():
    hold_depth_line("ABCD")
    row = {"symbol_allowlist": ["ABCD"], "trader_live": []}  # no UI report needed
    assert holds_depth_line("ABCD") is True
    assert assert_symbol_can_fire("abcd", row) == "ABCD"


def test_fire_gate_counts_a_session_record_line(monkeypatch):
    """Session Record holds a real IBKR line without any Trader tab (``is_live``)."""
    monkeypatch.setattr(depth_state, "is_subscribed", lambda sym: False)
    monkeypatch.setattr(depth_state, "is_live", lambda sym: sym == "RECD")
    assert holds_depth_line("RECD") is True
    assert assert_symbol_can_fire("RECD", {"symbol_allowlist": ["RECD"]}) == "RECD"
    assert holds_depth_line("OTHR") is False


def test_fire_gate_keeps_the_allowlist_fail_closed_even_with_a_line():
    hold_depth_line("ABCD")
    with pytest.raises(BotError) as exc:
        assert_symbol_can_fire("ABCD", {"symbol_allowlist": [], "trader_live": ["ABCD"]})
    assert exc.value.reason == BOT_REASON_SYMBOL_BLOCKED


def test_fire_gate_checks_the_allowlist_before_the_line():
    with pytest.raises(BotError) as exc:
        assert_symbol_can_fire("ZZZZ", {"symbol_allowlist": ["ABCD"]})
    assert exc.value.reason == BOT_REASON_SYMBOL_BLOCKED


def test_depth_line_gate_fails_closed_when_the_depth_module_cannot_answer(monkeypatch):
    def boom(_sym):
        raise RuntimeError("depth state unavailable")

    monkeypatch.setattr(depth_state, "is_subscribed", boom)
    assert holds_depth_line("ABCD") is False
    with pytest.raises(BotError) as exc:
        assert_depth_line("ABCD")
    assert exc.value.reason == BOT_REASON_NO_DEPTH_LINE


def test_depth_line_gate_requires_a_symbol():
    with pytest.raises(BotError) as exc:
        assert_depth_line("  ")
    assert exc.value.status_code == 400
    assert holds_depth_line("") is False


def test_add_remove_round_trip():
    row = default_session()
    add_symbol(row, "abcd")
    add_symbol(row, "ABCD")
    assert row["symbol_allowlist"] == ["ABCD"]
    remove_symbol(row, "abcd")
    assert row["symbol_allowlist"] == []


def test_schema_1_file_gains_v2_defaults():
    import json

    from bot import persist

    persist.reset_for_tests()
    persist._session_path().write_text(
        json.dumps({"schema_version": 1, "level": 0, "armed": False}),
        encoding="utf-8",
    )
    persist._session = None
    loaded = persist.load_session()
    assert loaded["symbol_allowlist"] == []
    assert loaded["active_pack"] == "halt-luld"
    assert loaded.get("desk_arm_token") is None
    persist.save_session(loaded)
    from constants_bot import BOT_SCHEMA_VERSION

    assert persist.load_session()["schema_version"] == BOT_SCHEMA_VERSION
    assert loaded["llm"]["call_cap"] == 10


def test_pack_catalog_marks_stubs():
    ids = {row["id"]: row["status"] for row in catalog()}
    assert ids["halt-luld"] == "live"
    assert ids["llm-decide"] == "live"
    assert ids["quote-spike"] == "live"
    assert ids["volume"] == "live"
    assert normalize_pack(None) == "halt-luld"
    assert_pack_can_fire("volume")
