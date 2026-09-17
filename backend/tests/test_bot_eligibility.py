"""Allowlist AND live Trader focus."""
from __future__ import annotations

import pytest

from bot.eligibility import add_symbol, assert_symbol_eligible, eligible_symbols, remove_symbol
from bot.errors import BotError
from bot.packs import assert_pack_can_fire, catalog, normalize_pack
from bot.persist import default_session
from constants_bot import BOT_REASON_PACK_STUB, BOT_REASON_SYMBOL_BLOCKED


def test_eligible_is_intersection():
    row = {"symbol_allowlist": ["aaa", "BBB"], "trader_live": ["bbb", "CCC"]}
    assert eligible_symbols(row) == ["BBB"]


def test_empty_allowlist_fail_closed():
    with pytest.raises(BotError) as exc:
        assert_symbol_eligible("ABCD", {"symbol_allowlist": [], "trader_live": ["ABCD"]})
    assert exc.value.reason == BOT_REASON_SYMBOL_BLOCKED


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
    assert persist.load_session()["schema_version"] == 2


def test_pack_catalog_marks_stubs():
    ids = {row["id"]: row["status"] for row in catalog()}
    assert ids["halt-luld"] == "live"
    assert ids["quote-spike"] == "stub"
    assert ids["volume"] == "stub"
    assert normalize_pack(None) == "halt-luld"
    with pytest.raises(BotError) as exc:
        assert_pack_can_fire("volume")
    assert exc.value.reason == BOT_REASON_PACK_STUB
