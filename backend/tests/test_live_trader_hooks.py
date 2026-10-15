"""Where the Live Trader bot meets the rest of Nova (ADR 055): Paper's quote, the door, the Bot switch, its files.

- Paper fills a stock with no Level 2 at IBKR's Level 1 bid and ask (decision 7);
- the door lets a ``live_trader`` close or cancel name Paper, never Live;
- a host's key counts as a strategy On for the Bot switch on Paper, and the operator's OFF sells the bot's shares;
- the settings and the book refuse a file they cannot read, loud, and never overwrite it.
"""
from __future__ import annotations

import json

import pytest

from bot import activation, switch
from bot.live_trader import book as lt_book
from bot.live_trader import settings as lt_settings
from bot.live_trader import watcher
from bot.live_trader.constants_live_trader import LT_BOOK_FILE, LT_SETTINGS_FILE
from bot.live_trader.settings import SettingsError
from constants_bot import BOT_REASON_NO_SETUP_AT_STRATEGY
from execution import venue_door
from execution.models import ExecutionCommand
from practice import reference as practice_reference
from sim.mode import reset_for_tests as reset_venue, set_venue


@pytest.fixture(autouse=True)
def _clean():
    lt_settings.reset_for_tests()
    lt_book.reset_for_tests()
    watcher.reset_for_tests()
    reset_venue()
    yield
    lt_settings.reset_for_tests()
    lt_book.reset_for_tests()
    watcher.reset_for_tests()
    reset_venue()


# -- Paper's quote with no Level 2 -----------------------------------------------------------------
def _l1(monkeypatch, *, fresh: bool, bid=9.98, ask=10.02, book=None):
    from ibkr import ticks
    from ibkr.depth import state as depth_state

    monkeypatch.setattr(ticks, "is_fresh", lambda sym, sec: fresh)
    monkeypatch.setattr(ticks, "bid_ask", lambda sym: (bid, ask))
    monkeypatch.setattr(depth_state, "current_book", lambda sym: book)
    monkeypatch.setattr(practice_reference.LiveReference, "fresh_last", lambda self, sym: 10.0)


def test_paper_takes_the_level_1_bid_and_ask_when_no_book_holds_them(monkeypatch):
    _l1(monkeypatch, fresh=True)
    ref = practice_reference.LiveReference().reference("XYZ")
    assert (ref.last, ref.bid, ref.ask) == (10.0, 9.98, 10.02)


def test_paper_keeps_the_books_sides_and_fills_only_a_missing_one(monkeypatch):
    _l1(monkeypatch, fresh=True, book={"bids": [{"price": 9.99}], "asks": []})
    ref = practice_reference.LiveReference().reference("XYZ")
    assert (ref.bid, ref.ask) == (9.99, 10.02)


def test_a_stale_level_1_line_gives_no_quote(monkeypatch):
    _l1(monkeypatch, fresh=False)
    ref = practice_reference.LiveReference().reference("XYZ")
    assert (ref.bid, ref.ask) == (None, None)


# -- the door ----------------------------------------------------------------------------------------
def _close(target: str, **over) -> ExecutionCommand:
    base = {"operation": "place", "idempotency_key": "k", "source": "flatten", "symbol": "XYZ", "side": "SELL",
            "qty": 4.0, "order_type": "MKT", "target_venue": target, "origin": "live_trader"}
    base.update(over)
    return ExecutionCommand(**base)


def test_a_live_trader_close_may_name_paper_but_never_live(monkeypatch):
    monkeypatch.setattr(venue_door, "ibkr_connected", lambda: True)
    assert venue_door.target_refusal(_close("paper")) is None
    assert venue_door.target_refusal(ExecutionCommand(
        operation="cancel", idempotency_key="c", source="cancel_working", order_id=7, target_venue="paper",
        origin="live_trader")) is None
    why = venue_door.target_refusal(_close("live"))
    assert why is not None and "trades Paper only" in why
    assert venue_door.target_refusal(_close("paper", source="bot", side="BUY")) is not None


# -- the Bot switch --------------------------------------------------------------------------------
def test_a_host_key_counts_as_a_strategy_on_paper_only():
    set_venue("paper")
    row = {"level": 2, "setup_levels": {}}
    assert activation.refusal(row, padlock_rule=False).reason == BOT_REASON_NO_SETUP_AT_STRATEGY
    lt_settings.patch_host("ALPHA", {"key": True})
    assert activation.refusal(row, padlock_rule=False) is None
    assert activation.live_trader_keys("sim") == []


def test_the_operators_off_asks_the_bot_to_sell_and_on_keeps(monkeypatch):
    asked: list[str] = []
    monkeypatch.setattr(watcher, "holds_positions", lambda: True)
    monkeypatch.setattr(watcher, "request_sell_all", lambda reason="bot_off": asked.append(reason))
    monkeypatch.setattr(watcher, "cancel_sell_all", lambda: asked.append("kept"))
    set_venue("sim")
    switch._live_trader(on=False)                 # Sim's switch: the Paper bot's shares are not its own
    assert asked == []
    set_venue("paper")
    switch._live_trader(on=False)
    switch._live_trader(on=True)
    assert asked == ["bot_off", "kept"]


# -- the files ----------------------------------------------------------------------------------------
def test_settings_default_to_the_operators_answers_and_check_every_field():
    st = lt_settings.of("ALPHA")
    assert (st["key"], st["step_usd"], st["allowance_usd"], st["adds"], st["sides"], st["short_stop_pct"],
            st["take_open"], st["entry"], st["exit"]) == (False, 500.0, 2500.0, 2, "both", 5.0, True, "nova", "nova")
    before, after = lt_settings.patch_host("alpha", {"key": True, "adds": None})
    assert before["key"] is False and after["key"] is True and after["adds"] is None
    for bad in ({"step_usd": 5}, {"adds": 3}, {"sides": "short"}, {"entry": "bot"}, {"nope": 1}):
        with pytest.raises(SettingsError) as exc:
            lt_settings.patch_host("ALPHA", bad)
        assert exc.value.code == "LIVE_TRADER_INVALID"
    with pytest.raises(SettingsError):
        lt_settings.patch_sell_all("16:30")
    assert lt_settings.patch_sell_all("15:30") == ("15:55", "15:30")


def test_an_unknown_settings_version_is_refused_loud_and_never_overwritten(tmp_path):
    from paths import cache_dir

    path = cache_dir() / LT_SETTINGS_FILE
    path.write_text(json.dumps({"schema_version": 99, "hosts": {"ALPHA": {"key": True}}}), encoding="utf-8")
    assert lt_settings.of("ALPHA")["key"] is False and "schema_version 99" in lt_settings.error()
    with pytest.raises(SettingsError) as exc:
        lt_settings.patch_host("ALPHA", {"key": True})
    assert exc.value.status == 409
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 99


def test_a_book_from_another_day_is_sold_and_an_unknown_one_refused():
    from paths import cache_dir

    path = cache_dir() / LT_BOOK_FILE
    path.write_text(json.dumps({"schema_version": 1, "day": "2026-10-06", "closed": [],
                                "positions": [{"id": "ALPHA|long|XYZ", "host": "ALPHA", "row_id": "r", "symbol": "XYZ",
                                               "side": "long", "qty": 4.0, "cost_usd": 400.0, "steps": 1,
                                               "adds_followed": 0, "opened_ts": 1.0, "state": "open", "order": None,
                                               "stop_order_ids": [], "fills": [], "exit_fills": [], "close": None}]}),
                    encoding="utf-8")
    stale = lt_book.roll_day("2026-10-07")
    assert [p["symbol"] for p in stale] == ["XYZ"]
    assert lt_book.roll_day("2026-10-07") == []
    lt_book.reset_for_tests()
    path.write_text(json.dumps({"schema_version": 7}), encoding="utf-8")
    assert "schema_version 7" in lt_book.error()
