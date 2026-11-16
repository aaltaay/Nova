"""The AI traders' switches, limits and door (ADR 072 batch 3, ``architecture/schema/traders.md``)."""
from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from traders import door, limits, switches

ET = ZoneInfo("America/New_York")


def at(clock: str, day: str = "2026-11-13") -> float:
    return datetime.fromisoformat(f"{day}T{clock}").replace(tzinfo=ET).timestamp()


@pytest.fixture
def paper_desk(monkeypatch):
    from sim import mode

    monkeypatch.setattr(mode, "venue", lambda: "paper")


def test_every_switch_reads_off_with_no_file_and_on_within_its_day(paper_desk) -> None:
    state, error = switches.current(at("10:00"))
    assert state == {"claude": {"on": False, "at": None, "by": None}, "brain": {"on": False, "at": None, "by": None}}
    assert error is None
    switches.set_switch("brain", True, "you", at("10:00"))
    assert switches.is_on("brain", at("15:00")) and not switches.is_on("claude", at("15:00"))
    assert switches.is_on("brain", at("03:59", "2026-11-14"))      # Saturday 03:59 still belongs to Friday


def test_the_desk_day_rolling_over_writes_every_switch_off(paper_desk) -> None:
    switches.set_switch("claude", True, "you", at("10:00"))
    assert not switches.is_on("claude", at("04:01", "2026-11-16"))  # Monday's desk day
    saved = json.loads(switches.path().read_text(encoding="utf-8"))
    assert saved["day"] == "2026-11-16" and saved["switches"]["claude"]["on"] is False


def test_an_unknown_file_reads_off_and_says_why(paper_desk) -> None:
    switches.path().parent.mkdir(parents=True, exist_ok=True)
    switches.path().write_text(json.dumps({"schema_version": 9, "day": "2026-11-13", "switches": {}}), "utf-8")
    state, error = switches.current(at("10:00"))
    assert not state["claude"]["on"] and "version 9" in (error or "")


def test_on_is_refused_on_live_and_past_its_flat_by(monkeypatch) -> None:
    from sim import mode

    monkeypatch.setattr(mode, "venue", lambda: "live")
    assert switches.on_refusal("brain", at("10:00"))[0] == "TRADER_LIVE"
    monkeypatch.setattr(mode, "venue", lambda: "paper")
    assert switches.on_refusal("brain", at("10:00")) is None
    code, words = switches.on_refusal("brain", at("15:55"))
    assert code == "TRADER_PAST_FLAT_BY" and "15:55" in words


def test_the_limits_read_their_defaults_and_keep_only_values_within_their_rule() -> None:
    assert limits.of("claude") == {"max_shares": 1000, "risk_usd": 150, "budget_usd": 25_000, "flat_by": "15:55"}
    limits.path().parent.mkdir(parents=True, exist_ok=True)
    limits.path().write_text(json.dumps({"schema_version": 1, "traders": {
        "brain": {"budget_usd": 10_000, "max_shares": 0, "flat_by": "15:30"}}}), "utf-8")
    brain = limits.of("brain")
    assert (brain["budget_usd"], brain["max_shares"], brain["flat_by"]) == (10_000, 1000, "15:30")
    assert limits.problem("flat_by", "16:00") and limits.problem("risk_usd", 1.5)


def _cmd(origin: str | None, operation: str = "place", source: str = "bot") -> SimpleNamespace:
    return SimpleNamespace(origin=origin, operation=operation, source=source)


def test_the_door_refuses_a_switched_off_traders_new_order_but_never_a_cancel_or_a_close(paper_desk) -> None:
    assert "Claude is switched off" in door.refusal(_cmd("claude"))
    assert door.refusal(_cmd("claude", operation="cancel")) is None
    assert door.refusal(_cmd("claude", source="flatten")) is None   # Nova's protective sources always go
    assert door.refusal(_cmd(None, source="manual")) is None         # yours
    switches.set_switch("claude", True, "you")
    assert door.refusal(_cmd("claude")) is None


def test_a_stored_bots_trade_reads_as_the_book_it_is_now() -> None:
    from journal.split import book_of_trade, bot_of_trade, holders

    claude = {"owner": "bots", "bot": "claude"}
    lt = {"owner": "bots", "bot": "live_trader"}
    assert (book_of_trade(claude), bot_of_trade(claude)) == ("claude", None)
    assert (book_of_trade(lt), bot_of_trade(lt)) == ("earlier_bots", "live_trader")
    assert book_of_trade({"owner": None}) == "you"
    rows = holders([claude, lt, lt, {"owner": "you"}, {"owner": "brain"}])
    assert [(r["owner"], r["bot"], r["trade_count"]) for r in rows] == [
        ("you", None, 1), ("claude", None, 1), ("brain", None, 1), ("earlier_bots", "live_trader", 2)]
