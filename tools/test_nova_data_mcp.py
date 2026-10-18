"""The data front door over MCP (``tools/nova_data_mcp.py``, ADR 059): bounded inline answers, new output files only,
errors as answers, stdout kept for the protocol, every tool registered with honest annotations."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import nova_data_mcp as m  # noqa: E402

TOOLS = {"data_catalog", "data_status", "stock_day", "movers_search", "movers_scan", "board", "splits", "financials",
         "sec_shares", "sec_filings", "float_latest", "ipos", "ticker_details", "short_interest"}
WRITES = {"stock_day", "movers_scan"}


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


def test_every_tool_is_registered_and_only_file_writers_are_not_read_only():
    pytest.importorskip("mcp")
    server = m.create_server(m.DataService())
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert set(tools) == TOOLS
    for name, tool in tools.items():
        assert tool.annotations.readOnlyHint is (name not in WRITES), name
        assert tool.annotations.destructiveHint is False and tool.description
