"""Today's hot list (ADR 043): the file, the 04:00 ET rollover, the auto feed, and HOD Momo's admission.

The routes and the Who trades tie-in are ``test_hot_list_routes.py``.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import hod_momo_active as active
import hot_list
from bot.audit import list_entries
from bot.persist import load_session, save_session
from constants_hot_list import HOT_LIST_CAP, HOT_LIST_UNREADABLE
from hot_list import auto, service, store
from hot_list.errors import HotListError
from stock_mode import store as stock_store
from tests.bot_helpers import on_practice

ET = ZoneInfo("America/New_York")


def et(day: int, hh: int, mm: int = 0, month: int = 9) -> float:
    return datetime(2026, month, day, hh, mm, tzinfo=ET).timestamp()


WED_0430 = et(30, 4, 30)       # 2026-09-30, a Wednesday: the trading day began at 04:00
WED_1000 = et(30, 10, 0)
TUE_1500 = et(29, 15, 0)


@pytest.fixture(autouse=True)
def fresh():
    service.reset_for_tests()
    auto.reset_for_tests()
    stock_store.reset_for_tests()
    yield
    service.reset_for_tests()
    auto.reset_for_tests()
    stock_store.reset_for_tests()


def entry(sym: str, how: str = "star", at: float = TUE_1500, **kw) -> dict:
    return {"symbol": sym, "how": how, "at": at, "board": kw.get("board"), "rank": kw.get("rank"),
            "change_pct": kw.get("change_pct")}


def doc_for(day: str, *symbols: str, **over) -> dict:
    doc = store.empty(day)
    doc["entries"] = [entry(s) for s in symbols]
    doc.update(over)
    return doc


def gainer(symbol: str, change: float, price: float = 5.0, volume: float = 500_000) -> dict:
    """A surfaced Gainers row: price over its prior close by ``change`` (a fraction)."""
    return {"symbol": symbol, "price": price, "prev_close": price / (1 + change), "volume": volume}


# -- the file -----------------------------------------------------------------------------------
def test_a_saved_list_reads_back_with_its_day_copy():
    day = store.trading_day(WED_1000)
    assert day == "2026-09-30" and store.trading_day(et(30, 3, 59)) == "2026-09-29"
    store.save(doc_for(day, "AISP", "lghl"))
    doc, error = store.read_raw()
    assert error is None and [e["symbol"] for e in doc["entries"]] == ["AISP", "LGHL"]
    assert hot_list.listed_symbols(WED_1000) == ["AISP", "LGHL"]
    assert hot_list.is_listed("aisp", WED_1000) and not hot_list.is_listed("ZZZZ", WED_1000)
    entries, why = hot_list.entries_on(day)
    assert why is None and [e["symbol"] for e in entries] == ["AISP", "LGHL"]
    copy = json.loads(store._day_path(day).read_text(encoding="utf-8"))
    assert copy["date"] == day and len(copy["entries"]) == 2
    assert hot_list.listed_symbols(et(1, 10, month=10)) == []          # the next day: nothing listed


def test_an_unknown_version_reads_empty_with_the_error_and_refuses_writes():
    store._path().write_text(json.dumps({"schema_version": 9, "date": "2026-09-30", "entries": []}), encoding="utf-8")
    doc, error = store.current(WED_1000)
    assert doc["entries"] == [] and "schema_version 9" in error
    assert not hot_list.is_listed("AISP", WED_1000)
    with pytest.raises(HotListError) as refused:
        service.star("AISP", by="operator", now=WED_1000)
    assert refused.value.reason == HOT_LIST_UNREADABLE
    assert json.loads(store._path().read_text(encoding="utf-8"))["schema_version"] == 9     # never overwritten


def test_an_unreadable_file_says_so():
    store._path().write_text("{not json", encoding="utf-8")
    doc, error = store.current(WED_1000)
    assert doc["entries"] == [] and "unreadable" in error


def test_a_day_from_a_request_is_never_made_into_a_path():
    entries, why = hot_list.entries_on("../../etc")
    assert entries is None and "not a day" in why
    with pytest.raises(ValueError):
        store._day_path("2026-09-30/../x")


def test_fields_out_of_shape_read_as_their_defaults():
    raw = {"schema_version": 1, "date": "2026-09-30", "auto_n": 7, "default": {"buy": "maybe"},
           "entries": [{"symbol": "aisp"}, "junk", {"symbol": ""}, {"symbol": "AISP"}, {"symbol": "lghl", "rank": 2}],
           "yesterday": ["ok", 5, None]}
    store._path().write_text(json.dumps(raw), encoding="utf-8")
    doc, error = store.read_raw()
    assert error is None and doc["auto_n"] == 5 and doc["default"] == {"buy": "you", "sell": "you"}
    assert [e["symbol"] for e in doc["entries"]] == ["AISP", "LGHL"] and doc["entries"][1]["rank"] == 2
    assert doc["yesterday"] == ["OK"]


# -- the 04:00 ET rollover ------------------------------------------------------------------------
def _session_with_lists(own: list[str], sim: list[str]) -> None:
    row = load_session()
    row["level_venue"] = "paper"
    row["symbol_allowlist"] = own
    row["venue_levels"] = {"sim": {"level": 0, "symbol_allowlist": sim}}
    save_session(row)


def test_the_rollover_keeps_the_day_moves_names_to_yesterday_and_clears_every_nova_buy():
    on_practice("paper")
    store.save(doc_for("2026-09-29", "AAA", "BBB", auto_n=10, default={"buy": "nova", "sell": "you"}))
    _session_with_lists(["AAA"], ["CCC"])
    stock_store.set_switch("DDD", {"buy": "nova", "sell": "you", "set_at": TUE_1500})
    stock_store.set_switch("EEE", {"buy": "you", "sell": "nova", "set_at": TUE_1500})
    stock_store.set_approval("EEE", {"setup_id": "x", "state": "waiting"})
    stock_store.set_approval("FFF", {"setup_id": "y", "state": "sent"})
    stock_store.set_trade({"venue": "paper", "symbol": "AAA", "kind": "auto_entry", "state": "holding",
                           "exits": "you", "sent_at": TUE_1500})

    fresh = service.today(WED_0430)

    assert fresh["date"] == "2026-09-30" and fresh["entries"] == [] and fresh["yesterday"] == ["AAA", "BBB"]
    assert fresh["auto_n"] == 10 and fresh["default"] == {"buy": "nova", "sell": "you"}
    old = json.loads(store._day_path("2026-09-29").read_text(encoding="utf-8"))
    assert [e["symbol"] for e in old["entries"]] == ["AAA", "BBB"]
    assert store._day_path("2026-09-30").exists()
    row = load_session()
    assert row["symbol_allowlist"] == [] and row["venue_levels"]["sim"]["symbol_allowlist"] == []
    assert stock_store.switches() == {} and stock_store.approval("EEE") is None
    assert stock_store.approval("FFF")["state"] == "sent"                      # a sent one belongs to a trade
    assert stock_store.trade("paper", "AAA")["state"] == "holding"              # trades keep their exits
    [line] = [r for r in list_entries(limit=50) if r["action"] == "hot_list"]
    assert line["inputs"]["event"] == "rollover" and line["inputs"]["from"] == "2026-09-29"
    cleared = {(c["venue"], c["symbol"], c["was"]) for c in line["inputs"]["cleared"]}
    assert cleared == {("paper", "AAA", "bot"), ("sim", "CCC", "bot"), ("paper", "DDD", "auto_entry"),
                       ("paper", "EEE", "approve")}
    assert "04:00" in (stock_store.event("DDD") or {}).get("text", "")

    stock_store.set_switch("GGG", {"buy": "nova", "sell": "you", "set_at": WED_0430})
    service.today(WED_1000)                                                    # the same day: nothing rolls
    assert "GGG" in stock_store.switches()


def test_a_day_with_no_names_keeps_the_last_names_for_bring_back():
    store.save(doc_for("2026-09-26", yesterday=["XYZ", "ABC"]))      # a Saturday that listed nothing
    assert service.today(WED_1000)["yesterday"] == ["XYZ", "ABC"]


def test_before_the_rollover_a_reader_sees_the_rolled_list_and_nothing_is_written():
    store.save(doc_for("2026-09-29", "AAA"))
    before = store._path().read_text(encoding="utf-8")
    doc, error = service.peek(WED_0430)
    assert error is None and doc["date"] == "2026-09-30" and doc["entries"] == [] and doc["yesterday"] == ["AAA"]
    assert store._path().read_text(encoding="utf-8") == before


def test_a_first_start_writes_today_and_clears_nothing():
    _session_with_lists(["AAA"], [])
    assert service.today(WED_1000)["entries"] == []
    assert load_session()["symbol_allowlist"] == ["AAA"]
    assert [r for r in list_entries(limit=20) if r["action"] == "hot_list"] == []


# -- the auto feed ---------------------------------------------------------------------------------
BOARD = [gainer("BIG", 0.80, price=12.0),            # over $10: the leaders rule keeps it out
         gainer("AAA", 0.60), gainer("BBB", 0.50), gainer("THIN", 0.45, volume=50_000),
         gainer("CCC", 0.40), gainer("DDD", 0.30), gainer("EEE", 0.20), gainer("FFF", 0.10)]


def test_pick_is_the_leaders_rule_top_n():
    picked = auto.pick(BOARD, now=WED_1000, n=3, listed=set(), room=20)
    assert [p["symbol"] for p in picked] == ["AAA", "BBB", "CCC"]
    assert [p["rank"] for p in picked] == [1, 2, 3]
    first = picked[0]
    assert first["how"] == "auto" and first["board"] == "gainers" and first["at"] == WED_1000
    assert first["change_pct"] == pytest.approx(0.60)


def test_pick_skips_a_listed_name_without_reaching_past_the_top_n():
    picked = auto.pick(BOARD, now=WED_1000, n=3, listed={"AAA"}, room=20)
    assert [p["symbol"] for p in picked] == ["BBB", "CCC"]
    assert auto.pick(BOARD, now=WED_1000, n=3, listed=set(), room=1)[0]["symbol"] == "AAA"
    assert auto.pick(BOARD, now=WED_1000, n=0, listed=set(), room=20) == []


def test_the_feed_adds_its_leaders_sticky_for_the_day(monkeypatch):
    board = {"rows": list(BOARD)}
    monkeypatch.setattr(auto, "live_gainers", lambda: (list(board["rows"]), None))
    assert asyncio.run(auto.tick(WED_1000)) == ["AAA", "BBB", "CCC", "DDD", "EEE"]
    board["rows"] = [gainer("NEW", 0.9), gainer("AAA", 0.1)]
    assert asyncio.run(auto.tick(WED_1000 + 30)) == ["NEW"]
    listed = hot_list.listed_symbols(WED_1000)
    assert listed == ["AAA", "BBB", "CCC", "DDD", "EEE", "NEW"]                 # nothing left the list
    doc, _ = store.read_raw()
    assert {e["how"] for e in doc["entries"]} == {"auto"} and doc["entries"][-1]["rank"] == 1
    assert auto.status()["error"] is None
    lines = [r["inputs"] for r in list_entries(limit=50) if r["action"] == "hot_list"]
    assert [i["symbol"] for i in lines if i["event"] == "auto"][-1] == "NEW"


def test_a_leader_you_took_off_is_not_added_back_that_day_even_after_a_restart(monkeypatch):
    monkeypatch.setattr(auto, "live_gainers", lambda: (list(BOARD), None))
    service.settings(auto_n=3, now=WED_1000)
    assert asyncio.run(auto.tick(WED_1000)) == ["AAA", "BBB", "CCC"]
    assert service.remove("AAA", now=WED_1000 + 10)
    assert asyncio.run(auto.tick(WED_1000 + 30)) == []                          # it still leads; it stays off
    auto.reset_for_tests()                                                     # a restart: memory is gone
    assert asyncio.run(auto.tick(WED_1000 + 60)) == []                          # the audit stream remembers
    assert "AAA" not in hot_list.listed_symbols(WED_1000)
    assert service.star("AAA", by="operator", now=WED_1000 + 90)               # a star still brings it back


def test_the_feed_never_passes_the_cap(monkeypatch):
    store.save(doc_for("2026-09-30", *[f"S{i:02d}" for i in range(HOT_LIST_CAP - 2)]))
    monkeypatch.setattr(auto, "live_gainers", lambda: (list(BOARD), None))
    assert asyncio.run(auto.tick(WED_1000)) == ["AAA", "BBB"]
    assert len(hot_list.listed_symbols(WED_1000)) == HOT_LIST_CAP
    assert asyncio.run(auto.tick(WED_1000 + 30)) == []


def test_the_feed_waits_for_its_window_and_stays_off_at_zero(monkeypatch):
    monkeypatch.setattr(auto, "live_gainers", lambda: (list(BOARD), None))
    assert asyncio.run(auto.tick(et(30, 6, 59))) == []                         # before 07:00
    assert asyncio.run(auto.tick(et(30, 16, 0))) == []                         # 16:00 closes it
    assert asyncio.run(auto.tick(et(27, 10, 0))) == []                         # a Sunday
    service.settings(auto_n=0, now=WED_1000)
    assert asyncio.run(auto.tick(WED_1000)) == [] and auto.status()["error"] is None
    assert "off" in auto.rule_text(0) and "top 5" in auto.rule_text(5)


def test_the_feed_says_why_when_the_board_is_not_live(monkeypatch):
    monkeypatch.setattr(auto, "live_gainers", lambda: ([], "the Gainers board is not live (frozen)"))
    assert asyncio.run(auto.tick(WED_1000)) == []
    assert "not live" in auto.status()["error"]


def test_the_feed_rolls_the_list_over_at_four():
    store.save(doc_for("2026-09-29", "AAA"))
    asyncio.run(auto.tick(WED_0430))
    doc, _ = store.read_raw()
    assert doc["date"] == "2026-09-30" and doc["yesterday"] == ["AAA"]


# -- HOD Momo's active set admits the list first ----------------------------------------------------
def test_listed_names_are_admitted_first_ahead_of_former_momo():
    active.clear_session_state()
    snap = active.build_active_set(
        gainer_rows=[{"symbol": "G1", "change_pct": 9.0}, {"symbol": "HOT2", "change_pct": 1.0}],
        priority_symbols=["F1", "HOT1"], hot_symbols=["hot1", "HOT2"], capacity=40)
    assert snap.active[:3] == ["HOT1", "HOT2", "F1"]
    assert snap.reasons["HOT1"] == "hot_list" and snap.reasons["HOT2"] == "hot_list"
    assert snap.reasons["F1"] == "former_momo" and "G1" in snap.active


def test_the_list_respects_the_active_sets_capacity():
    active.clear_session_state()
    snap = active.build_active_set(hot_symbols=["A", "B", "C", "D"], priority_symbols=["F1"], capacity=3)
    assert snap.active == ["A", "B", "C"] and set(snap.uncovered) >= {"D", "F1"}
    assert snap.reasons["D"] == "hot_list_over_reserved"


MOVERS = [{"symbol": f"M{i:02d}", "change_pct": 90 - i} for i in range(30)]


def test_twenty_listed_and_twenty_former_momo_still_leave_live_movers_twenty():
    active.clear_session_state()
    hot = [f"H{i:02d}" for i in range(20)]
    former = [f"F{i:02d}" for i in range(20)]
    snap = active.build_active_set(gainer_rows=MOVERS, priority_symbols=former, hot_symbols=hot, capacity=40)
    assert snap.active[:20] == hot and {snap.reasons[s] for s in hot} == {"hot_list"}
    assert [s for s in snap.active if s.startswith("M")] == [f"M{i:02d}" for i in range(20)]
    assert len(snap.active) == 40 and not any(s.startswith("F") for s in snap.active)
    assert {snap.reasons[s] for s in former} == {"former_momo_over_cap"} and set(former) <= set(snap.uncovered)


def test_a_21st_listed_name_gets_no_reserved_slot_and_says_why():
    active.clear_session_state()
    hot = [f"H{i:02d}" for i in range(21)]
    snap = active.build_active_set(gainer_rows=MOVERS, hot_symbols=hot, capacity=40)
    assert snap.active[:20] == hot[:20] and "H20" not in snap.active and "H20" in snap.uncovered
    assert snap.reasons["H20"] == "hot_list_over_reserved"
    assert len([s for s in snap.active if s.startswith("M")]) == 20            # the movers keep their 20
    from hot_list import following

    assert following.reason_not_followed("H20") == "HOD Momo's 20 reserved slots are full"


def test_a_listed_name_that_is_also_former_momo_takes_one_reserved_slot():
    active.clear_session_state()
    hot = [f"H{i:02d}" for i in range(10)] + ["BOTH"]
    former = ["BOTH"] + [f"F{i:02d}" for i in range(15)]
    snap = active.build_active_set(gainer_rows=MOVERS, priority_symbols=former, hot_symbols=hot, capacity=40)
    assert snap.active.count("BOTH") == 1 and snap.reasons["BOTH"] == "hot_list"
    taken = [snap.reasons[s] for s in snap.active]
    assert taken.count("hot_list") == 11 and taken.count("former_momo") == 9   # 20 reserved slots in all
    assert taken.count("top_gainer") == 20
    assert [s for s in former[1:] if s not in snap.active] == [f"F{i:02d}" for i in range(9, 15)]


def test_a_listed_name_ibkr_cannot_stream_says_so_and_leaves_its_slot():
    from hot_list import following

    active.clear_session_state()
    active.note_l1_subscribe_failed(["BAD"], cooldown_sec=600.0)
    snap = active.build_active_set(hot_symbols=["BAD", "GOOD"], priority_symbols=["F1"], capacity=40)
    assert snap.active == ["GOOD", "F1"] and snap.reasons["BAD"] == "hot_list_l1_blocked"
    assert following.reason_not_followed("BAD") == following.L1_BLOCKED


def test_the_bridge_reads_todays_list_when_it_rebuilds_the_set():
    import ibkr_bridge

    active.clear_session_state()
    store.save(doc_for(store.trading_day(), "ZHOT", "YHOT"))
    assert ibkr_bridge.refresh_hod_active_set()[:2] == ["ZHOT", "YHOT"]
    assert active.get_priority_reason("ZHOT") == "hot_list"
