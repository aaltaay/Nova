"""The practice broker on both venues: live fills, resting fills, buying power, persistence."""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from constants_practice import (
    PRACTICE_BUYING_POWER_CODE,
    PRACTICE_NO_LIVE_PRINT_CODE,
    PRACTICE_NO_LIVE_PRINT_REASON,
)
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests
from sim.fill_model import Reference

NOW = 1_700_000_000.0  # 2023-11-14, a wall clock the Paper venue could actually show


class FakeLive:
    """A MarketReference standing in for the live feed: IMCC quoted, everything else dark."""

    def __init__(self) -> None:
        self.ref = Reference(10.0, 9.98, 10.02, live=True)
        self.now = NOW
        self.prints: list[tuple[float, float]] = []
        self.dark = False

    def reference(self, symbol: str) -> Reference:
        return self.ref if symbol == "IMCC" and not self.dark else Reference(None, live=True)

    def admission(self, symbol: str):
        if symbol == "IMCC" and not self.dark:
            return True, "OK", None
        return False, PRACTICE_NO_LIVE_PRINT_REASON, PRACTICE_NO_LIVE_PRINT_CODE

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return [(ts, px) for ts, px in self.prints if after_ts < ts <= through_ts]

    def now_ts(self) -> float:
        return self.now


@pytest.fixture
def paper(monkeypatch):
    reset_for_tests()
    fake = FakeLive()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: fake)
    yield SimpleNamespace(broker=for_venue("paper"), ref=fake)
    reset_for_tests()


def test_for_venue_hands_out_one_broker_per_venue_and_refuses_the_rest(paper) -> None:
    assert for_venue("paper") is paper.broker and paper.broker.account_id == "NOVA-PAPER"
    sim = for_venue("sim")
    assert sim is for_venue(" SIM ") and sim.account_id == "NOVA-SIM" and sim.persist_path is None
    assert paper.broker.persist_path.endswith("practice-paper.json")
    with pytest.raises(ValueError):
        for_venue("live")


def test_a_paper_market_buy_fills_at_the_live_ask_with_fees_and_attribution(paper) -> None:
    raw = paper.broker.place("imcc", "BUY", 100, "MKT", source="bot", bot_id="alpha")
    assert (raw["ok"], raw["broker_status"], raw["mode"]) == (True, "Filled", "paper")
    row = paper.broker.closed_orders()[0]
    assert (row["avg_fill_price"], row["fill_basis"], row["fill_estimated"]) == (10.02, "live_quote", True)
    assert (row["source"], row["order_source"], row["bot_id"]) == ("nova", "bot", "alpha")
    assert (row["account_id"], row["venue"], row["commission"]) == ("NOVA-PAPER", "paper", 1.0)
    summary = paper.broker.account_summary()
    assert summary["TotalCashValue"] == pytest.approx(100_000 - 1_002 - 1.0)
    assert (summary["mode"], summary["sim"], summary["practice"], summary["AccountType"]) == (
        "paper", False, True, "PAPER",
    )
    assert summary["connected"] is True and summary["account_id"] == "NOVA-PAPER"
    assert paper.broker.positions()[0]["qty"] == 100


def test_paper_persists_every_change_and_the_next_process_reloads_it(paper) -> None:
    paper.broker.place("IMCC", "BUY", 100, "MKT")
    path = paper.broker.persist_path
    assert os.path.exists(path)
    reset_for_tests()
    again = for_venue("paper")
    assert again is not paper.broker
    assert again.positions()[0]["qty"] == 100 and again.closed_orders()[0]["order_id"] == 1
    assert again.snapshot()["account_id"] == "NOVA-PAPER"


def test_a_resting_limit_fills_on_a_later_live_print_as_print_cross(paper) -> None:
    raw = paper.broker.place("IMCC", "BUY", 10, "LMT", limit_price=9.5)
    assert raw["broker_status"] == "Submitted" and paper.broker.working_symbols() == ["IMCC"]
    assert paper.broker.try_fill_working("IMCC", [(NOW, 9.4)]) == []  # not after placement
    filled = paper.broker.try_fill_working("IMCC", [(NOW + 1, 9.4)])
    assert [(r["avg_fill_price"], r["fill_basis"]) for r in filled] == [(9.5, "print_cross")]
    assert paper.broker.working_symbols() == [] and paper.broker.positions()[0]["market_price"] == 10.0


def test_an_opening_order_beyond_buying_power_is_refused(paper) -> None:
    raw = paper.broker.place("IMCC", "BUY", 50_000, "MKT")
    assert raw["ok"] is False and raw["reason_code"] == PRACTICE_BUYING_POWER_CODE
    assert paper.broker.positions() == [] and paper.broker.working_orders() == []


def test_a_reducing_sell_needs_no_buying_power(paper) -> None:
    paper.broker.reset(30_000)
    assert paper.broker.place("IMCC", "BUY", 10_000, "MKT")["broker_status"] == "Filled"
    assert paper.broker.account_summary()["BuyingPower"] < 100_000
    raw = paper.broker.place("IMCC", "SELL", 10_000, "MKT")
    assert raw["broker_status"] == "Filled" and paper.broker.positions() == []


def test_a_resting_fill_that_no_longer_fits_is_cancelled_with_the_buying_power_code(paper) -> None:
    paper.broker.reset(30_000)
    resting = paper.broker.place("IMCC", "BUY", 5_000, "LMT", limit_price=9.0)
    assert resting["broker_status"] == "Submitted"
    assert paper.broker.place("IMCC", "BUY", 10_000, "MKT")["broker_status"] == "Filled"
    assert paper.broker.try_fill_working("IMCC", [(NOW + 1, 8.9)]) == []
    cancelled = paper.broker.closed_orders()[0]
    assert cancelled["order_id"] == resting["order_id"]
    assert (cancelled["status"], cancelled["reason_code"]) == ("Cancelled", PRACTICE_BUYING_POWER_CODE)
    assert paper.broker.working_orders() == []


def test_protective_flatten_closes_at_the_last_mark_when_the_feed_is_dark(paper) -> None:
    paper.broker.place("IMCC", "BUY", 100, "MKT")
    paper.ref.dark = True
    assert paper.broker.place("IMCC", "SELL", 100, "MKT")["reason_code"] == PRACTICE_NO_LIVE_PRINT_CODE
    raw = paper.broker.place("IMCC", "SELL", 100, "MKT", protective=True, source="flatten")
    row = paper.broker.closed_orders()[0]
    assert raw["broker_status"] == "Filled" and (row["avg_fill_price"], row["fill_basis"]) == (10.02, "last_mark")
    assert paper.broker.positions() == []
    assert paper.broker.place("IMCC", "SELL", 1, "MKT", protective=True)["ok"] is False


def test_reset_archives_the_paper_ledger_and_starts_fresh(paper) -> None:
    paper.broker.place("IMCC", "BUY", 100, "MKT")
    out = paper.broker.reset(50_000)
    assert out["archived"] and os.path.exists(out["archived"]) and "practice-paper-" in out["archived"]
    assert (out["starting_cash"], out["cash"], out["positions"], out["fills_today"]) == (50_000, 50_000, [], 0)
    reset_for_tests()
    assert for_venue("paper").snapshot()["starting_cash"] == 50_000
    with pytest.raises(ValueError):
        paper.broker.reset(0)


def test_the_sim_broker_unwinds_time_and_names_its_replay(monkeypatch) -> None:
    from sim import practice

    clock = {"ts": 100.0}
    monkeypatch.setattr(practice, "playhead_ts", lambda: clock["ts"])
    monkeypatch.setattr(practice, "admission", lambda sym: (sym == "IMCC", "not loaded", None if sym == "IMCC" else "SIM_SYMBOL_MISMATCH"))
    monkeypatch.setattr(practice, "reference", lambda sym: Reference(10.0, 9.98, 10.02) if sym == "IMCC" else Reference(None))
    monkeypatch.setattr(practice, "loaded", lambda: practice.Loaded("historical", "IMCC", ("historical", "IMCC")))
    reset_for_tests()
    sim = for_venue("sim")
    assert sim.place("IMCC", "BUY", 1, "MKT")["broker_status"] == "Filled"
    clock["ts"] = 200.0
    assert sim.place("IMCC", "BUY", 1, "LMT", limit_price=9.0)["broker_status"] == "Submitted"
    assert sim.unwind_to(150.0) == 1
    assert sim.working_orders() == [] and sim.positions()[0]["qty"] == 1
    snap = sim.snapshot()
    assert (snap["venue"], snap["account_id"], snap["replay_key"]) == ("sim", "NOVA-SIM", ["historical", "IMCC"])
    assert sim.closed_orders()[0]["fill_basis"] == "quote"
    reset_for_tests()
