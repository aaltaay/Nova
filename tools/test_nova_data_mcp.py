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
         "symbols", "rvol_scan", "rvol_triggers", "rvol_outcomes"}
WRITES = {"stock_day", "movers_scan", "find_stock_days", "daily_bars", "order_flow", "rvol_scan", "rvol_triggers",
          "rvol_outcomes"}


def test_a_big_table_answers_its_first_rows_and_says_how_many_matched():
    frame = pd.DataFrame({"x": range(500)})
    frame.attrs["rule"] = "r"
    answer = m.table_answer(frame, inline=10)
    assert answer["rows"] == 500 and answer["truncated"] is True and len(answer["data"]) == 10
    assert answer["meta"] == {"rule": "r"} and answer["out"] is None


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
