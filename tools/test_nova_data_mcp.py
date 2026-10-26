"""The data front door over MCP (``tools/nova_data_mcp.py``, ADR 059): bounded inline answers, new output files only,
errors as answers, stdout kept for the protocol, every tool registered with honest annotations."""
from __future__ import annotations

import asyncio
import io
import sys
import threading
import time
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import nova_data_mcp as m  # noqa: E402

TOOLS = {"data_catalog", "data_status", "stock_day", "movers_search", "movers_scan", "board", "splits", "financials",
         "sec_shares", "sec_filings", "float_latest", "ipos", "ticker_details", "short_interest",
         "find_stock_days", "daily_bars", "market_context", "stock_day_stats", "order_flow", "halts", "catalysts",
         "symbols", "rvol_scan", "rvol_triggers", "rvol_outcomes", "cash_runway", "recorded_depth", "recorded_tape",
         "signal_catalog", "signal_series", "signal_scan", "signal_test"}
WRITES = {"stock_day", "movers_scan", "find_stock_days", "daily_bars", "order_flow", "rvol_scan", "rvol_triggers",
          "rvol_outcomes", "recorded_tape", "signal_series", "signal_scan", "signal_test"}


def test_a_big_table_answers_its_first_rows_and_says_how_many_matched():
    frame = pd.DataFrame({"x": range(500)})
    frame.attrs["rule"] = "r"
    answer = m.table_answer(frame, inline=10)
    assert answer["rows"] == 500 and answer["truncated"] is True and len(answer["data"]) == 10
    assert answer["meta"] == {"rule": "r"} and answer["out"] is None


def test_an_et_time_answers_in_et_not_utc():
    """#1086: DSS 2026-09-03's volume spike is the 09:40 ET bar; the answer said 13:40Z under ``time_et``."""
    from zoneinfo import ZoneInfo
    when = pd.to_datetime(["2026-09-03 13:40", None], utc=True).tz_convert(ZoneInfo("America/New_York"))
    answer = m.table_answer(pd.DataFrame({"time_et": when, "volume": [2910910.6, 1.0]}))
    assert answer["data"][0]["time_et"] == "2026-09-03T09:40:00-04:00"
    assert answer["data"][1]["time_et"] is None
    winter = pd.to_datetime(["2026-01-05 14:30"], utc=True).tz_convert(ZoneInfo("America/New_York"))
    assert m.table_answer(pd.DataFrame({"time_et": winter}))["data"][0]["time_et"] == "2026-01-05T09:30:00-05:00"


def test_an_output_file_is_new_plain_and_under_the_root(tmp_path):
    service = m.DataService(tmp_path)
    for bad in ("../x.parquet", "x.txt", "a/b.csv", ""):
        if bad:
            with pytest.raises(ValueError):
                service.output_path(bad)
    path = service.output_path("runners.parquet")
    assert path == tmp_path / "runners.parquet"
    answer = m.table_answer(pd.DataFrame({"x": [1, 2]}), path)
    assert Path(answer["out"]).is_file()
    with pytest.raises(FileExistsError):
        service.output_path("runners.parquet")


def test_a_failed_read_is_an_answer_and_prints_never_reach_stdout(capsys):
    def noisy():
        print("progress chatter")
        raise LookupError("no such stock")

    answer = m.call(noisy)
    assert answer == {"ok": False, "error": "LookupError: no such stock"}
    out = capsys.readouterr()
    assert out.out == "" and "progress chatter" in out.err


def test_the_catalog_serves_nova_s_recordings_and_names_what_it_still_does_not():
    answer = m.DataService().catalog()
    names = {d["name"]: d for d in answer["datasets"]}
    assert names["recorded_depth"]["mcp"] == "recorded_depth" and names["recorded_tape"]["mcp"].startswith("recorded_tape")
    assert "recorded_depth" in " ".join(answer["not_here"]) and "book_watch" in " ".join(answer["not_here"])
    assert "does not serve them yet" not in " ".join(answer["not_here"])


def test_the_catalog_names_units_and_as_of_rules_for_every_dataset():
    answer = m.DataService().catalog()
    assert answer["ok"] and {d["name"] for d in answer["datasets"]} >= {"movers_index", "financials", "sec_shares"}
    assert all(d["as_of"] and d["units"] and d["mcp"] for d in answer["datasets"])


def test_a_day_without_a_board_answers_covered_false_at_the_top(monkeypatch):
    from market_reads import reads
    frame = pd.DataFrame()
    frame.attrs.update(covered=False, board="gainers", gap={"reason": "not_recorded"}, note="no gainers board")
    monkeypatch.setattr(reads, "board", lambda *a: frame)
    answer = m.DataService().board("2023-06-01", "09:45")
    assert answer["ok"] and answer["rows"] == 0 and answer["covered"] is False
    assert answer["gap"] == {"reason": "not_recorded"} and answer["note"] == "no gainers board"


def test_a_stock_day_page_answers_its_cursor_and_writes_the_whole_page(monkeypatch, tmp_path):
    from market_reads import stock_days
    asked = {}

    def page(**kwargs):
        asked.update(kwargs)
        frame = pd.DataFrame({"date": ["2025-03-03"] * 300, "symbol": [f"S{i:03d}" for i in range(300)]})
        frame.attrs.update(next_cursor="2025-03-03|S299", float_rule="r")
        return frame

    monkeypatch.setattr(stock_days, "find_stock_days", page)
    answer = m.DataService(tmp_path).find_stock_days({"date_from": "2025-03-03"}, page_size=300,
                                                     output_name="page.parquet")
    assert answer["next_cursor"] == "2025-03-03|S299" and answer["rows"] == 300 and len(answer["data"]) == 200
    assert asked["to_file"] is True and pd.read_parquet(answer["out"]).shape[0] == 300


def test_catalysts_answer_items_and_the_days_verdicts(monkeypatch):
    from market_reads import catalysts
    items = pd.DataFrame({"title": ["8-K"], "published_et": ["2026-09-09 07:30"]})
    verdicts = pd.DataFrame({"session_date": ["2026-09-09"], "verdict": ["catalyst"]})
    verdicts.attrs["coverage"] = "2021-10-11 .. 2026-09-21"
    monkeypatch.setattr(catalysts, "items", lambda *a, **k: items)
    monkeypatch.setattr(catalysts, "verdicts", lambda **k: verdicts)
    answer = m.DataService().catalysts("IRD", "2026-09-08", "2026-09-09")
    assert answer["data"][0]["title"] == "8-K" and answer["verdicts"] == [{"session_date": "2026-09-09",
                                                                         "verdict": "catalyst"}]
    assert answer["verdicts_meta"]["coverage"].startswith("2021")


def test_cash_runway_answers_the_library_read_and_the_defaults_agree(monkeypatch):
    import market_data_runway
    import nova_data_runway
    from market_reads import runway
    asked = {}

    def read(symbol, day, cik=None, lookback_days=runway.DEFAULT_LOOKBACK_DAYS):
        asked.update(symbol=symbol, day=day, cik=cik, lookback_days=lookback_days)
        return {"symbol": symbol, "cash": None, "runway": {"months": None, "status": "no_balance_sheet"}}

    monkeypatch.setattr(runway, "runway", read)
    answer = m.DataService().cash_runway("GURE", "2024-03-01")
    assert answer == {"ok": True, "symbol": "GURE", "cash": None,
                      "runway": {"months": None, "status": "no_balance_sheet"}}
    assert asked == {"symbol": "GURE", "day": "2024-03-01", "cik": None, "lookback_days": 1095}
    assert runway.DEFAULT_LOOKBACK_DAYS == nova_data_runway.DEFAULT_LOOKBACK_DAYS         == market_data_runway.DEFAULT_LOOKBACK_DAYS


def test_cash_runway_is_a_heavy_read_and_a_bad_day_is_an_answer():
    assert "cash_runway" not in m.LIGHT_TOOLS            # it can build the reference index: one heavy read at a time
    answer = m.call(m.DataService().cash_runway, "GURE", "not-a-day")
    assert answer["ok"] is False and answer["error"].startswith("ValueError")


def test_the_catalog_lists_cash_runway_with_its_tool_and_command():
    entry = next(d for d in m.DataService().catalog()["datasets"] if d["name"] == "cash_runway")
    assert entry["mcp"] == "cash_runway" and entry["cli"] == "market_data.py runway SYMBOL DAY"
    assert "stale" in entry["as_of"] and "null" in entry["units"]


def _hold(name: str, started: threading.Event, release: threading.Event):
    def body():
        started.set()
        release.wait(5)
        return {"ok": True}
    body.__name__ = name
    return body


def test_a_light_read_does_not_queue_behind_a_heavy_one_in_the_same_process():
    started, release = threading.Event(), threading.Event()
    heavy = threading.Thread(target=m.call, args=(_hold("stock_day", started, release),))
    heavy.start()
    assert started.wait(2)

    def symbols():
        return {"ok": True, "light": True}

    t0 = time.monotonic()
    answer = m.call(symbols)
    waited = time.monotonic() - t0
    release.set()
    heavy.join(5)
    assert answer == {"ok": True, "light": True} and waited < 0.5


def test_heavy_reads_still_run_one_at_a_time_per_process():
    started, release = threading.Event(), threading.Event()
    first = threading.Thread(target=m.call, args=(_hold("stock_day", started, release),))
    first.start()
    assert started.wait(2)
    second_started = threading.Event()
    second = threading.Thread(target=m.call, args=(_hold("order_flow", second_started, threading.Event()),))
    second.start()
    assert not second_started.wait(0.3)          # queued behind the first heavy read
    release.set()
    first.join(5)
    assert second_started.wait(2)
    second.join(6)


def test_prints_from_overlapping_calls_never_reach_stdout(capsys):
    started, release = threading.Event(), threading.Event()

    def stock_day():
        print("heavy chatter")
        started.set()
        release.wait(5)
        print("heavy done")
        return {"ok": True}

    def catalog():
        print("light chatter")
        return {"ok": True}

    heavy = threading.Thread(target=m.call, args=(stock_day,))
    heavy.start()
    assert started.wait(2)
    m.call(catalog)
    release.set()
    heavy.join(5)
    out = capsys.readouterr()
    assert out.out == "" and all(s in out.err for s in ("heavy chatter", "light chatter", "heavy done"))


def test_the_protocol_keeps_the_real_stdout_buffer():
    real = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    stand_in = m.PrintsToStderr(real)
    assert stand_in.buffer is real.buffer


def test_every_tool_is_registered_and_only_file_writers_are_not_read_only():
    server = m.create_server(m.DataService())
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert set(tools) == TOOLS
    for name, tool in tools.items():
        assert tool.annotations.readOnlyHint is (name not in WRITES), name
        assert tool.annotations.destructiveHint is False and tool.description


def test_recorded_depth_answers_the_librarys_book_and_its_coverage(monkeypatch):
    from market_reads import recordings
    asked = {}

    def depth(symbol, day, at, source, max_age_sec):
        asked.update(symbol=symbol, day=day, at=at, source=source, max_age_sec=max_age_sec)
        return {"symbol": symbol, "covered": True, "source": "capture", "book": {"best_bid": 1.02, "age_sec": 30.0},
                "coverage": {"capture": {"gaps": [{"reason": "restart"}]}}}

    monkeypatch.setattr(recordings, "depth", depth)
    answer = m.DataService().recorded_depth("GRML", "2026-10-14", "09:31:30", "capture", 120.0)
    assert answer["ok"] and answer["book"]["best_bid"] == 1.02 and answer["coverage"]["capture"]["gaps"]
    assert asked == {"symbol": "GRML", "day": "2026-10-14", "at": "09:31:30", "source": "capture", "max_age_sec": 120.0}


def test_a_bad_recorded_read_is_an_answer_not_a_crash():
    answer = m.call(m.DataService().recorded_depth, "GRML", "2026-10-14", "99:00")
    assert answer["ok"] is False and answer["error"].startswith("ValueError: '99:00' is not an ET clock time")


def test_recorded_tape_answers_a_table_with_its_coverage_and_writes_only_a_new_file(monkeypatch, tmp_path):
    from market_reads import recordings
    frame = pd.DataFrame({"time_et": ["09:31:00.250"], "price": [1.0], "source": ["archive"]})
    frame.attrs.update(source="archive", capped=False, coverage={"dropped_total": 12}, rules="r")
    monkeypatch.setattr(recordings, "tape", lambda *a: frame)
    answer = m.DataService(tmp_path).recorded_tape("GRML", "2026-10-14", "09:31", "09:32", "archive", 50,
                                                   output_name="tape.parquet")
    assert answer["ok"] and answer["rows"] == 1 and answer["data"][0]["time_et"] == "09:31:00.250"
    assert answer["meta"]["coverage"] == {"dropped_total": 12} and pd.read_parquet(answer["out"]).shape == (1, 3)
    with pytest.raises(FileExistsError):
        m.DataService(tmp_path).recorded_tape("GRML", "2026-10-14", output_name="tape.parquet")


def test_the_recorded_reads_are_heavy_ones_so_they_queue_behind_each_other_per_process():
    assert not {"recorded_depth", "recorded_tape"} & m.LIGHT_TOOLS


def test_find_stock_days_hands_the_ranking_kinds_and_limit_arguments_to_the_read(monkeypatch):
    """#1086: sort / limit / outstanding_max / kinds reach the library unchanged; an unset kinds stays unset there."""
    from market_reads import stock_days
    asked = {}

    def page(**kwargs):
        asked.update(kwargs)
        frame = pd.DataFrame({"date": ["2026-09-17"], "symbol": ["AEMD"]})
        frame.attrs.update(next_cursor="2026-09-17|AEMD")
        return frame

    monkeypatch.setattr(stock_days, "find_stock_days", page)
    service = m.DataService()
    answer = service.find_stock_days({"date_from": "2026-09-01"}, sort="high", limit=10, outstanding_max=2e7,
                                     kinds=["all"])
    assert (asked["sort"], asked["limit"], asked["outstanding_max"], asked["kinds"]) == ("high", 10, 2e7, ["all"])
    assert asked["float_max"] is None and asked["page_size"] is None and answer["next_cursor"] == "2026-09-17|AEMD"
    service.find_stock_days({"date_from": "2026-09-01"})
    assert asked["kinds"] is None and asked["sort"] is None, "the defaults are the library's (common stock, oldest)"
    service.find_stock_days({"date_from": "2026-09-01"}, catalyst_category=["fda_regulatory"],
                            catalyst_words=["approv"], rvol_daily_min=5)
    assert (asked["catalyst_category"], asked["catalyst_words"], asked["rvol_daily_min"]) == (
        ["fda_regulatory"], ["approv"], 5)


def test_a_bars_answer_carries_the_gaps_and_fill_gaps_reaches_the_read(monkeypatch):
    import contextlib

    from market_reads import reads, slots
    asked = {}
    gaps = [{"first_et": "09:46", "last_et": "09:49", "buckets": 4}]

    def bars(symbol, day, tf, start, end, fill_gaps):
        asked["fill_gaps"] = fill_gaps
        frame = pd.DataFrame({"time_et": pd.to_datetime(["2026-09-03 13:45"], utc=True).tz_convert("America/New_York"),
                              "close": [3.1]})
        frame.attrs.update(gaps=gaps, gap_runs=1, gap_buckets=4, gaps_truncated=False)
        return frame

    monkeypatch.setattr(reads, "bars", bars)
    monkeypatch.setattr(slots, "heavy", lambda what: contextlib.nullcontext())
    answer = m.DataService().stock_day("bars", "DSS", "2026-09-03", fill_gaps=True)
    assert asked["fill_gaps"] is True
    assert answer["meta"]["gaps"] == gaps and answer["meta"]["gap_buckets"] == 4
    m.DataService().stock_day("bars", "DSS", "2026-09-03")
    assert asked["fill_gaps"] is False


def test_the_tool_descriptions_state_the_defaults_a_call_cannot_see():
    tools = {t.name: t for t in asyncio.run(m.create_server(m.DataService()).list_tools())}
    find = tools["find_stock_days"]
    assert "COMMON STOCK" in find.description and "outstanding_max" in find.description
    assert {"sort", "limit", "outstanding_max", "kinds", "catalyst_category", "catalyst_words",
            "rvol_daily_min"} <= set(find.inputSchema["properties"])
    assert "rvol_daily" in find.description and "fda_regulatory" in find.description
    assert "fill_gaps" in tools["stock_day"].inputSchema["properties"] and "meta.gaps" in tools["stock_day"].description
    assert "movers_search" in find.description and "market board" in tools["board"].description
