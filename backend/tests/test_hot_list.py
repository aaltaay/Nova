"""Today's hot list (ADR 044, amended 2026-10-06): the file, the 04:00 ET rollover, the auto feed, and HOD
Momo's admission -- the bot's stocks first when a caller names any (the bridge names none since the bots retired,
ADR 072), then the list.

The routes, and that the list never decides who trades a stock, are ``test_hot_list_routes.py``.
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
from constants_hot_list import HOT_LIST_AUTO_CAP, HOT_LIST_CAP, HOT_LIST_FULL, HOT_LIST_UNREADABLE
from hot_list import auto, service, store
from hot_list.errors import HotListError
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
    yield
    service.reset_for_tests()
    auto.reset_for_tests()


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
    assert error is None and doc["auto_n"] == 5 and "default" not in doc
    assert [e["symbol"] for e in doc["entries"]] == ["AISP", "LGHL"] and doc["entries"][1]["rank"] == 2
    assert doc["yesterday"] == ["OK"]


def test_a_file_from_before_drops_its_default_side_without_a_word(caplog):
    """A file written before 2026-10-06 carries ``default: {buy, sell}`` (the side a new name started on): it
    reads without it, says nothing (it is no fault of the file), and the next write leaves it out."""
    store.save(doc_for("2026-09-30", "AISP", default={"buy": "nova", "sell": "nova"}))
    assert "default" in json.loads(store._path().read_text(encoding="utf-8"))
    store.forget_cache_for_tests()
    with caplog.at_level("WARNING", logger="hot_list.store"):
        doc, error = store.read_raw()
    assert error is None and "default" not in doc and [e["symbol"] for e in doc["entries"]] == ["AISP"]
    assert not [r for r in caplog.records if "out of shape" in r.getMessage()]
    assert service.star("LGHL", by="operator", now=WED_1000)
    written = json.loads(store._path().read_text(encoding="utf-8"))
    assert "default" not in written and [e["symbol"] for e in written["entries"]] == ["AISP", "LGHL"]
    assert "default" not in service.today(WED_1000) and "default" not in store.roll(written, "2026-10-01")


# -- the 04:00 ET rollover ------------------------------------------------------------------------
def _session_with_lists(own: list[str], sim: list[str]) -> None:
    row = load_session()
    row["level_venue"] = "paper"
    row["symbol_allowlist"] = own
    row["venue_levels"] = {"sim": {"level": 0, "symbol_allowlist": sim}}
    save_session(row)


def test_the_rollover_keeps_the_day_moves_names_to_yesterday_and_touches_no_bot_list():
    """ADR 072: no bot buys, so the 04:00 rollover has nothing of the bot's to reset."""
    on_practice("paper")
    store.save(doc_for("2026-09-29", "AAA", "BBB", auto_n=10, default={"buy": "nova", "sell": "you"}))  # old file
    _session_with_lists(["AAA"], ["CCC"])

    fresh = service.today(WED_0430)

    assert fresh["date"] == "2026-09-30" and fresh["entries"] == [] and fresh["yesterday"] == ["AAA", "BBB"]
    assert fresh["auto_n"] == 10 and "default" not in fresh and "reset_error" not in fresh
    old = json.loads(store._day_path("2026-09-29").read_text(encoding="utf-8"))
    assert [e["symbol"] for e in old["entries"]] == ["AAA", "BBB"]
    assert store._day_path("2026-09-30").exists()
    row = load_session()
    assert row["symbol_allowlist"] == ["AAA"] and row["venue_levels"]["sim"]["symbol_allowlist"] == ["CCC"]
    [line] = [r for r in list_entries(limit=50) if r["action"] == "hot_list"]
    assert line["inputs"] == {"event": "rollover", "from": "2026-09-29", "to": "2026-09-30",
                              "yesterday": ["AAA", "BBB"], "error": None}
    service.today(WED_1000)                                                    # the same day: nothing rolls
    assert len([r for r in list_entries(limit=50) if r["action"] == "hot_list"]) == 1


def test_a_file_from_before_drops_the_retired_reset_error():
    """A file written while the rollover still reset the bot's buys may carry ``reset_error``: it reads without it."""
    store.save(doc_for("2026-09-30", "AISP", reset_error="the bot's stock lists could not be cleared"))
    store.forget_cache_for_tests()
    doc, error = store.read_raw()
    assert error is None and "reset_error" not in doc and [e["symbol"] for e in doc["entries"]] == ["AISP"]


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
    assert {i["event"] for i in lines} <= {"auto", "rollover"}                 # no side is ever set for them
    assert load_session().get("symbol_allowlist") in (None, [])


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


def test_the_feed_never_passes_its_own_cap(monkeypatch):
    doc = store.empty("2026-09-30")
    doc["entries"] = [entry(f"S{i:02d}", how="auto") for i in range(HOT_LIST_AUTO_CAP - 2)]
    store.save(doc)
    monkeypatch.setattr(auto, "live_gainers", lambda: (list(BOARD), None))
    assert asyncio.run(auto.tick(WED_1000)) == ["AAA", "BBB"]
    assert len(hot_list.listed_symbols(WED_1000)) == HOT_LIST_AUTO_CAP
    assert asyncio.run(auto.tick(WED_1000 + 30)) == []


def test_stars_never_take_the_feeds_room(monkeypatch):
    """Twenty stars of the operator's own leave the leaders rule its whole cap (ADR 044, 2026-10-12)."""
    store.save(doc_for("2026-09-30", *[f"S{i:02d}" for i in range(HOT_LIST_CAP)]))
    monkeypatch.setattr(auto, "live_gainers", lambda: (list(BOARD), None))
    assert asyncio.run(auto.tick(WED_1000)) == ["AAA", "BBB", "CCC", "DDD", "EEE"]


def test_auto_stars_never_refuse_a_star_and_only_stars_fill_the_cap():
    """The operator's report (2026-10-12): twenty auto stars made today's list 'full' for a star."""
    doc = store.empty("2026-09-30")
    doc["entries"] = [entry(f"A{i:02d}", how="auto") for i in range(HOT_LIST_AUTO_CAP)]
    store.save(doc)
    for i in range(HOT_LIST_CAP):
        assert service.star(f"S{i:02d}", by="operator", now=WED_1000)
    with pytest.raises(HotListError) as refused:
        service.star("ONEMORE", by="operator", now=WED_1000)
    assert refused.value.reason == HOT_LIST_FULL and f"starred {HOT_LIST_CAP} stocks" in refused.value.message


def test_starring_an_auto_star_makes_it_yours_in_its_place():
    doc = store.empty("2026-09-30")
    doc["entries"] = [entry("AAA", how="auto", board="gainers", rank=1, change_pct=0.6), entry("BBB")]
    store.save(doc)
    assert service.star("aaa", by="operator", now=WED_1000)
    assert not service.star("AAA", by="operator", now=WED_1000 + 1)              # a star already: no change
    saved, _ = store.read_raw()
    first = saved["entries"][0]
    assert first["symbol"] == "AAA" and first["how"] == "star" and first["at"] == WED_1000
    assert first["board"] == "gainers" and first["rank"] == 1                    # how it first came is kept
    star_lines = [r["inputs"] for r in list_entries(limit=20) if r["action"] == "hot_list"
                  and r["inputs"].get("event") == "star"]
    assert star_lines[-1] == {"event": "star", "symbol": "AAA", "by": "operator", "was": "auto"}


def test_a_promotion_counts_against_the_stars_cap():
    doc = store.empty("2026-09-30")
    doc["entries"] = [entry(f"S{i:02d}") for i in range(HOT_LIST_CAP)] + [entry("AUTO", how="auto")]
    store.save(doc)
    with pytest.raises(HotListError):
        service.star("AUTO", by="operator", now=WED_1000)
    assert store.read_raw()[0]["entries"][-1]["how"] == "auto"


def test_stars_are_listed_ahead_of_auto_stars_for_the_reserved_slots():
    doc = store.empty("2026-09-30")
    doc["entries"] = [entry("A1", how="auto"), entry("S1"), entry("A2", how="auto"), entry("S2")]
    store.save(doc)
    assert hot_list.listed_symbols(WED_1000) == ["S1", "S2", "A1", "A2"]


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


# -- HOD Momo's active set admits a caller's bot stocks, then the list ------------------------------------
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


def test_the_bots_stocks_are_admitted_ahead_of_the_list_and_counted_once():
    """The bot can only buy what a lane reads: a stock whose Buy is the bot's takes its reserved slot first, and a
    name on both counts as the bot's."""
    active.clear_session_state()
    snap = active.build_active_set(priority_symbols=["F1"], hot_symbols=["HOT1", "BOTH"],
                                   bot_symbols=["bot1", "BOTH"], capacity=40)
    assert snap.active[:4] == ["BOT1", "BOTH", "HOT1", "F1"]
    assert [snap.reasons[s] for s in snap.active[:4]] == ["bot_buy", "bot_buy", "hot_list", "former_momo"]
    assert snap.active.count("BOTH") == 1


def test_a_bot_stock_past_the_reserved_slots_says_why_and_the_list_gets_none():
    from hot_list import following

    active.clear_session_state()
    bots = [f"B{i:02d}" for i in range(21)]
    snap = active.build_active_set(gainer_rows=MOVERS, hot_symbols=["H00"], bot_symbols=bots, capacity=40)
    assert snap.active[:20] == bots[:20] and {snap.reasons[s] for s in bots[:20]} == {"bot_buy"}
    assert snap.reasons["B20"] == "bot_buy_over_reserved" and snap.reasons["H00"] == "hot_list_over_reserved"
    assert {"B20", "H00"} <= set(snap.uncovered)
    assert len([s for s in snap.active if s.startswith("M")]) == 20            # the movers keep their 20
    assert following.reason_not_followed("B20") == following.RESERVED_FULL


def test_a_bot_stock_ibkr_cannot_stream_says_so_and_leaves_its_slot():
    from hot_list import following

    active.clear_session_state()
    active.note_l1_subscribe_failed(["BAD"], cooldown_sec=600.0)
    snap = active.build_active_set(bot_symbols=["BAD", "GOOD"], hot_symbols=["HOT"], capacity=40)
    assert snap.active == ["GOOD", "HOT"] and snap.reasons["BAD"] == "bot_buy_l1_blocked"
    assert following.reason_not_followed("BAD") == following.L1_BLOCKED

def test_the_bridge_admits_todays_list_and_no_bot_stock():
    """ADR 072: the bot's stock list no longer takes a reserved slot -- the bridge admits the hot list only."""
    import ibkr_bridge

    on_practice("paper")
    active.clear_session_state()
    _session_with_lists(["ZBOT"], [])
    store.save(doc_for(store.trading_day(), "ZHOT"))
    admitted = ibkr_bridge.refresh_hod_active_set()
    assert admitted[:1] == ["ZHOT"] and "ZBOT" not in admitted
    assert active.get_priority_reason("ZHOT") == "hot_list" and active.get_priority_reason("ZBOT") is None


def test_the_setup_views_note_names_only_a_listed_stock_no_lane_reads():
    from hot_list import following

    on_practice("paper")
    active.clear_session_state()
    _session_with_lists(["BOTX"], [])
    store.save(doc_for(store.trading_day(), "HOTX"))
    bots = [f"B{i:02d}" for i in range(20)] + ["BOTX"]
    active.build_active_set(gainer_rows=MOVERS, bot_symbols=bots, hot_symbols=["HOTX"], capacity=40)
    assert following.listed_note("BOTX") is None                     # the bot's list is no longer named
    assert following.listed_note("HOTX") == ("HOTX is on today's hot list, but no lane reads it: HOD Momo's 20 "
                                             "reserved slots are full")
    assert following.listed_note("NONE") is None
