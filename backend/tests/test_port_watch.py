"""The port watch and the ``pc_ports`` row (operator report 2026-10-14: the desk PC ran out of network ports --
15,300 connections still held under process ids that no longer existed -- and the backend restarted 19 times)."""
from __future__ import annotations

import logging

import pytest

from diagnostics import collect_ports
from perf import port_watch
from winapi import tcp
from winapi.processes import Proc

DYN = (49152, 16384, "netsh")
NOW = 1_791_990_000.0
EST, TIME_WAIT = 5, 11


def conn(port: int, pid: int, state: int = EST) -> tcp.Conn:
    return tcp.Conn(state, port, pid)


@pytest.fixture(autouse=True)
def _reset():
    port_watch.reset_for_tests()
    yield
    port_watch.reset_for_tests()


def test_a_reading_counts_the_dynamic_ports_and_the_connections_closed_programs_hold():
    procs = [Proc(10, 1, "msedge.exe"), Proc(11, 1, "msedge.exe"), Proc(20, 1, "python.exe")]
    conns = [
        conn(8000, 20, tcp.MIB_TCP_STATE_LISTEN),       # a listener holds no outgoing port
        conn(50000, 10), conn(50001, 11), conn(50002, 20),
        conn(50003, 777), conn(50004, 777), conn(50005, 778),   # their programs have closed
        conn(50006, 0, TIME_WAIT),                      # owned by nobody: in use, never "closed"
        conn(3000, 20),                                  # outside the dynamic range
    ]
    read = port_watch.reading(now=NOW, conns=conns, procs=procs, dyn=DYN)
    assert read["kind"] == "ports" and read["schema_version"] == 1
    assert read["in_use"] == 7 and read["pct"] == 0
    assert read["closed"] == {"connections": 3, "pids": 2}
    assert read["top"] == [{"name": "msedge.exe", "count": 2}, {"name": "python.exe", "count": 2}]
    assert read["range"] == {"start": 49152, "count": 16384, "source": "netsh"}


def leak(in_use: int, closed: int) -> dict:
    return {"kind": "ports", "schema_version": 1, "ts": NOW, "range": {"start": 49152, "count": 16384,
            "source": "netsh"}, "in_use": in_use, "pct": round(100 * in_use / 16384),
            "closed": {"connections": closed, "pids": 755 if closed else 0}, "top": [{"name": "Grok Bot.exe", "count": 588}]}


def rows(read: dict | None, available: bool = True, now: float = NOW + 30):
    [r] = collect_ports.ports_rows(status={"available": available, "running": True, "every_sec": 60, "last": read},
                                   now=now)
    return r


def test_the_row_fails_when_the_ports_are_nearly_gone_and_says_a_restart_frees_them():
    r = rows(leak(16_000, 15_321))                           # 2026-10-14, minutes before 11:45 ET
    assert r["id"] == "pc_ports" and r["group"] == "process" and r["state"] == "fail"
    assert r["detail"] == "Network ports 16,000 of 16,384 in use (98%); 15,321 held by programs that have closed -- nearly out"
    assert "IB Gateway" in r["cause"] and "Restart the PC" in r["fix"] and "Grok Bot.exe 588" in r["fix"]
    assert "Grok Bot" not in r["detail"] + r["cause"]       # other programs only in the fix (an issue prints the rest)


def test_a_leak_warns_long_before_the_ports_run_out():
    r = rows(leak(2_100, 1_600))                             # the day after the boot
    assert r["state"] == "warn" and "programs that have closed" in r["cause"] and "Restart the PC" in r["fix"]
    assert rows(leak(12_000, 0))["state"] == "warn"           # living programs at 73%
    assert rows(leak(700, 7))["state"] == "ok"                # after the 12:35 reboot


def test_the_row_says_why_it_cannot_tell():
    assert rows(None)["state"] == "unknown"
    assert rows(leak(700, 7), now=NOW + 301)["state"] == "unknown"
    assert rows(None, available=False)["state"] == "off"


def test_the_log_warns_once_per_episode_with_counts_only(caplog):
    caplog.set_level(logging.WARNING, logger=port_watch.logger.name)
    port_watch._warn(leak(2_100, 1_600))
    port_watch._warn(leak(2_200, 1_700))
    assert len(caplog.records) == 1 and "1,600 connections held by 755 programs" in caplog.records[0].getMessage()
    assert "Grok" not in caplog.records[0].getMessage()
    port_watch._warn(leak(700, 7))                           # under both lines: the episode ends
    port_watch._warn(leak(2_100, 1_600))
    assert len(caplog.records) == 2


@pytest.mark.parametrize(("text", "expected"), [
    ("\nProtocol tcp Dynamic Port Range\n---------------------------------\nStart Port      : 49152\n"
     "Number of Ports : 16384\n", (49152, 16384)),
    ("Protokoll tcp Dynamischer Portbereich\nStartport       : 10000\nAnzahl Ports    : 55535\n", (10000, 55535)),
    ("The requested operation requires elevation.", None),
])
def test_the_dynamic_range_is_read_from_netsh_in_any_language(text, expected):
    assert tcp.parse_dynamic_range(text) == expected


def test_a_table_port_is_network_byte_order():
    assert tcp.port_of(0x401F) == 8000           # 8000 is 0x1F40, stored low byte first
    assert tcp.port_of(0xFFFF0050) == 0x5000      # only the low 16 bits are the port
