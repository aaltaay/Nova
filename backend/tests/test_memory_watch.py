"""The memory watch and its ``pc_memory`` row (operator report 2026-10-11, "nova keeps driving the ram higher").

The PC sat at 72 of 80 GB committed while Nova held 3.4 GB; nothing said whose the rest was. These pin
who counts as Nova (by pid, never by a name), that the other programs are named only where an issue
report never copies them, and that the warnings fire once per episode.
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass

import pytest

from constants_perf import (
    PERF_MEMORY_API_LEAK_MB,
    PERF_MEMORY_CLIENT_FRESH_SEC,
    PERF_MEMORY_DESK_LEAK_MB,
    PERF_MEMORY_STALE_SEC,
    PERF_MEMORY_TOP,
)
from diagnostics.collect_memory import memory_rows
from perf import memory_watch as mw

T0 = 1_791_700_000.0
MB = 2**20
API = 100


@dataclass(frozen=True)
class P:
    pid: int
    ppid: int
    name: str


@pytest.fixture(autouse=True)
def _reset():
    mw.reset_for_tests()
    yield
    mw.reset_for_tests()


def _pc(load=60, used=40_000, limit=80_000):
    return {"load_pct": load, "ram_total_mb": 32_000, "ram_free_mb": 8_000, "commit_limit_mb": limit,
            "commit_used_mb": used}


# The packaged desk: Nova.exe (10) starts the API (100), which starts a Sim import (101) and IBC's loop (300),
# which starts Gateway (301). Another program (200) runs two workers; 150 is a stale "child" of the API's pid
# from before the API existed (Windows reuses pids). 4 is a protected process Windows will not open.
PROCS = [
    P(10, 1, "Nova.exe"), P(11, 10, "Nova.exe"), P(12, 10, "Nova.exe"),
    P(API, 10, "nova-api.exe"), P(101, API, "nova-api.exe"), P(150, API, "python3.13.exe"),
    P(300, API, "cmd.exe"), P(301, 300, "java.exe"),
    P(200, 1, "python3.13.exe"), P(201, 200, "python3.13.exe"), P(202, 200, "python3.13.exe"),
    P(400, 1, "msedge.exe"), P(4, 0, "System"), P(0, 0, "[System Process]"),
]
SIZES = {10: 400, 11: 300, 12: 600, API: 1900, 101: 900, 150: 50, 300: 5, 301: 420,
         200: 60, 201: 7300, 202: 1300, 400: 800}
BORN = {pid: 1000.0 + pid for pid in SIZES}
BORN[150] = 500.0          # older than the API: its parent pid is a reused number


def _reading(pc=None, sizes=SIZES, desk=frozenset({10, 11, 12}), now=T0):
    return mw.reading(now=now, api_pid=API, procs=PROCS, private_of=lambda pid: sizes[pid] * MB if pid in sizes else None,
                      created=BORN.get, desk=set(desk), gateway={300, 301}, pc=pc or _pc())


def test_nova_is_counted_by_pid_and_part_and_the_rest_by_program():
    read = _reading()
    roles = {n["pid"]: n["role"] for n in read["nova"]["processes"]}
    assert roles == {10: "desk", 11: "desk", 12: "desk", API: "api", 101: "children", 300: "gateway", 301: "gateway"}
    assert read["nova"]["parts"] == {"api": 1900, "children": 900, "desk": 1300, "gateway": 425}
    assert read["nova"]["total_mb"] == 4525
    python = next(g for g in read["others"] if g["name"] == "python3.13.exe")
    assert (python["count"], python["private_mb"], python["largest_pid"], python["largest_mb"]) == (4, 8710, 201, 7300)
    assert [g["name"] for g in read["others"]] == ["python3.13.exe", "msedge.exe"]
    assert read["others_total_mb"] == 8710 + 800
    assert read["unreadable"] == 1                      # pid 4; pid 0 is not a process
    assert read["kind"] == "memory" and read["schema_version"] == 1 and read["ts"] == T0


def test_an_unknown_start_time_never_counts_as_nova():
    born = dict(BORN)
    del born[101]
    read = mw.reading(now=T0, api_pid=API, procs=PROCS, private_of=lambda pid: SIZES.get(pid, 0) * MB,
                      created=born.get, desk={10}, gateway=set(), pc=_pc())
    assert 101 not in {n["pid"] for n in read["nova"]["processes"]}


def test_only_the_biggest_other_programs_are_kept():
    procs = [P(API, 1, "python.exe")] + [P(1000 + i, 1, f"app{i}.exe") for i in range(PERF_MEMORY_TOP + 3)]
    read = mw.reading(now=T0, api_pid=API, procs=procs, private_of=lambda pid: pid * MB, created=lambda pid: 1.0,
                      desk=set(), gateway=set(), pc=_pc())
    assert len(read["others"]) == PERF_MEMORY_TOP
    assert read["others"][0]["name"] == f"app{PERF_MEMORY_TOP + 2}.exe"


def test_desk_pids_come_only_from_fresh_window_reports():
    clients = {"electron-main": {"received_ts": T0 - 5, "processes": [{"pid": 10}, {"pid": 11}, {"pid": None}]},
               "old": {"received_ts": T0 - PERF_MEMORY_CLIENT_FRESH_SEC - 1, "processes": [{"pid": 99}]}}
    assert mw.desk_pids(clients, T0) == {10, 11}


def test_gateway_pids_come_from_the_priority_keeper_not_from_a_name():
    view = {"processes": [{"role": "api", "pid": API}, {"role": "gateway", "pid": 301}, {"role": "ibc_loop", "pid": 300}]}
    assert mw.gateway_pids(view) == {300, 301}


def test_pressure_warns_once_per_episode_without_naming_other_programs(caplog):
    caplog.set_level(logging.WARNING, logger="perf.memory_watch")
    for pc in (_pc(load=92), _pc(load=95), _pc(load=88)):      # one episode: 88 is still above the re-arm line
        mw._warn(_reading(pc=pc))
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "Nova 4.4 GB (API 1.9, Sim import 0.9, desk 1.3, Gateway 0.4)" in message
    assert "other programs 9.3 GB" in message
    assert "python3.13.exe" not in message and "msedge" not in message     # an issue dump prints this log
    mw._warn(_reading(pc=_pc(load=70)))                          # under 85: the episode ends
    mw._warn(_reading(pc=_pc(load=40_000, used=73_000)))         # 91% committed: a new episode
    assert len(caplog.records) == 2


def test_a_nova_part_past_its_leak_line_warns_once(caplog):
    caplog.set_level(logging.WARNING, logger="perf.memory_watch")
    leaking = {**SIZES, API: PERF_MEMORY_API_LEAK_MB + 100}
    mw._warn(_reading(sizes=leaking))
    mw._warn(_reading(sizes=leaking))
    assert [r.getMessage() for r in caplog.records] == [
        f"Nova's API holds {(PERF_MEMORY_API_LEAK_MB + 100) / 1024:.1f} GB, past its "
        f"{PERF_MEMORY_API_LEAK_MB / 1024:.1f} GB leak line: memory it keeps and does not free"]


def _row(status):
    (only,) = memory_rows(status=status, now=T0 + 30)
    assert only["id"] == "pc_memory" and only["group"] == "process"     # its evidence stays out of issue dumps
    for g in (only["evidence"] or {}).get("others", []):                # never in the text an issue report copies
        assert g["name"] not in only["detail"] and g["name"] not in only["cause"], g["name"]
    return only


def _status(read):
    return {"available": True, "running": True, "every_sec": 60, "last": read}


def test_a_normal_pc_is_ok_with_novas_share():
    row = _row(_status(_reading()))
    assert row["state"] == "ok"
    assert row["detail"] == ("PC memory 60% in use, 39.1 GB of 78.1 GB committed. Nova 4.4 GB (API 1.9, Sim import "
                             "0.9, desk 1.3, Gateway 0.4), 11% of it; other programs 9.3 GB")
    assert "python3.13.exe x4 8.5 GB (largest pid 201, 7.1 GB)" in row["fix"]


def test_a_full_pc_held_by_other_programs_names_them_in_the_fix():
    row = _row(_status(_reading(pc=_pc(load=91, used=70_000))))
    assert row["state"] == "warn"
    assert row["cause"].startswith("Other programs hold most of it.")
    assert "python3.13.exe x4" in row["fix"] and "Task Manager" in row["fix"]


def test_a_full_pc_held_by_nova_says_so():
    row = _row(_status(_reading(pc=_pc(load=92, used=6_000, limit=6_500))))
    assert row["state"] == "warn" and row["cause"] == "Nova holds most of it."


def test_a_commit_charge_at_its_limit_fails():
    row = _row(_status(_reading(pc=_pc(load=95, used=78_500))))
    assert row["state"] == "fail" and "nearly out" in row["detail"]
    assert "IB Gateway" in row["cause"]


@pytest.mark.parametrize(("pid", "line", "words"), [(API, PERF_MEMORY_API_LEAK_MB, "API"),
                                                    (12, PERF_MEMORY_DESK_LEAK_MB, "desk")])
def test_a_nova_part_past_its_leak_line_fails_even_on_a_quiet_pc(pid, line, words):
    sizes = {**SIZES, pid: line}
    row = _row(_status(_reading(sizes=sizes)))
    assert row["state"] == "fail"
    assert row["detail"].startswith(f"Nova's {words} holds")
    assert "a leak in Nova" in row["cause"]


def test_no_reading_stale_reading_and_off_windows():
    assert _row({"available": True, "running": True, "last": None})["state"] == "unknown"
    stale = _reading(now=T0 + 30 - PERF_MEMORY_STALE_SEC - 1)
    assert _row(_status(stale))["state"] == "unknown"
    assert _row({"available": False, "running": False, "last": None})["state"] == "off"


def test_tick_is_nothing_off_windows(monkeypatch):
    import winapi
    import winapi.memory
    import winapi.processes  # noqa: F401  (imported before the patch, so they keep the real check)

    monkeypatch.setattr(winapi, "available", lambda: False)
    assert mw.tick(now=T0) is None
    assert mw.status()["last"] is None


@pytest.mark.skipif(sys.platform != "win32", reason="reads Windows' memory counters")
def test_tick_reads_this_pc_and_writes_the_day_file(monkeypatch):
    from perf import recorder

    written = []
    monkeypatch.setattr(recorder, "persist", written.append)
    read = mw.tick()
    assert written == [read] and mw.status()["last"] is read
    assert read["pc"]["commit_limit_mb"] >= read["pc"]["commit_used_mb"] > 0
    api = [n for n in read["nova"]["processes"] if n["role"] == "api"]
    assert [n["pid"] for n in api] == [os.getpid()] and api[0]["private_mb"] > 0
    assert read["others_total_mb"] > 0
