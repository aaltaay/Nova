"""The day's IBKR feed incidents, from Nova's own records (ADR 045 amendment 2026-10-14)."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from practice.clock import ET

TOOL = Path(__file__).resolve().parents[2] / "tools" / "ibkr_feed_report.py"
T0 = datetime(2026, 10, 14, 9, 25, 11, tzinfo=ET).timestamp()


def _tool():
    spec = importlib.util.spec_from_file_location("ibkr_feed_report", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cache(tmp_path: Path) -> Path:
    perf = tmp_path / "perf"
    perf.mkdir()
    rows = [
        {"kind": "ib_notice", "ts": T0 - 63, "code": 1100, "notice": "connectivity_lost", "farm": None,
         "message": "Connectivity between IBKR and Trader Workstation has been lost."},
        {"kind": "ib_notice", "ts": T0 - 62, "code": 2105, "notice": "broken", "farm": "ushmds"},
        {"kind": "tape_silence", "ts": T0 + 10, "symbol": "GENK",
         "reading": {"state": "dead", "since": T0, "pipeline": ["BEZ"], "history_unanswered_since": T0}},
        # A quiet premarket name read "silent" is not evidence of anything.
        {"kind": "tape_silence", "ts": T0 - 3600, "symbol": "XLU", "reading": {"state": "silent", "since": T0 - 3700}},
        {"kind": "tape_recovery", "phase": "sent", "asked_ts": T0 + 10, "lines": ["BEZ", "GENK"], "sent": True},
        {"kind": "tape_recovery", "phase": "verified", "asked_ts": T0 + 10, "lines": ["BEZ", "GENK"], "sent": True,
         "back": ["GENK"], "still_dead": ["BEZ"]},
        {"kind": "sample", "ts": T0},
    ]
    (perf / "2026-10-14.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n", encoding="utf-8")
    conn = sqlite3.connect(tmp_path / "archive.db")
    conn.execute("CREATE TABLE tape_ibkr (symbol TEXT, ts REAL, price REAL)")
    conn.execute("CREATE TABLE l1_ticks (symbol TEXT, ts REAL, price REAL)")
    conn.executemany("INSERT INTO tape_ibkr VALUES (?, ?, ?)",
                     [("GENK", T0, 2.59), ("GENK", T0 + 194.8, 2.35), ("BEZ", T0 + 194.8, 3.1)])
    conn.executemany("INSERT INTO l1_ticks VALUES (?, ?, ?)",
                     [("GENK", T0 + 11, 2.7592), ("GENK", T0 + 100, 2.31), ("GENK", T0 + 150, 2.83)])
    conn.commit()
    conn.close()
    return tmp_path


def test_a_dead_stall_is_measured_against_what_level_1_delivered(tmp_path):
    tool = _tool()
    report = tool.build("2026-10-14", _cache(tmp_path))
    assert [r["code"] for r in report["connectivity"]] == [1100]
    [stall] = report["stalls"]
    genk, bez = stall["lines"]
    assert genk["symbol"] == "GENK" and round(genk["seconds"]) == 195 and genk["l1_updates"] == 3
    assert (genk["l1_low"], genk["l1_high"]) == (2.31, 2.83)
    assert bez["symbol"] == "BEZ" and bez["peer"] is True and bez["l1_updates"] == 0


def test_the_report_reads_as_evidence_for_ibkr(tmp_path):
    tool = _tool()
    text = tool.render(tool.build("2026-10-14", _cache(tmp_path)))
    assert "IB Gateway lost its connection to IBKR 1 time(s)" in text
    assert "### Stall 1: from 09:25:11 -- BEZ, GENK" in text
    assert "| GENK | 09:25:11 | 09:28:25 | 195 s | 3 | 2.31-2.83 |" in text
    assert "| BEZ (same stall) |" in text
    assert "historical data (HMDS) stopped answering from 09:25:11" in text
    assert "lines BEZ, GENK -- sent; prints back on GENK 30 s later" in text
    assert "XLU" not in text                                    # a silent quiet name is not a stall
    assert "## Question for IBKR" in text


def test_older_days_take_ibkrs_connectivity_from_the_text_log(tmp_path):
    tool = _tool()
    log = tmp_path / "api-console.log"
    log.write_text(
        "2026-10-14 09:24:08,197 WARNING ib_async.wrapper Error 1100, reqId -1: Connectivity between IBKR and "
        "Trader Workstation has been lost.\n"
        "2026-10-14 09:24:14,982 WARNING ib_async.wrapper Error 1102, reqId -1: Connectivity ... restored - data "
        "maintained.\n"
        "2026-10-13 09:00:00,000 WARNING ib_async.wrapper Error 1100, reqId -1: another day\n",
        encoding="utf-8",
    )
    rows = tool.connectivity_from_log(log, "2026-10-14")
    assert [(r["code"], datetime.fromtimestamp(r["ts"], ET).strftime("%H:%M:%S")) for r in rows] == [
        (1100, "09:24:08"), (1102, "09:24:14")]
    empty = tmp_path / "empty"
    (empty / "perf").mkdir(parents=True)
    assert [r["code"] for r in tool.build("2026-10-14", empty, log)["connectivity"]] == [1100, 1102]
