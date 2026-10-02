"""A Gateway logged in but refusing its API port restarts itself through IBC; one Gateway only.

2026-10-02: after a 30-minute Wi-Fi drop the Gateway was logged in with both farms ON and port
4001 LISTENING, yet refused every connect; and Nova's launcher, which looked for a process named
``ibgateway`` while Gateway 10.45 runs as ``ibgateway1.exe``, started a second Gateway that took
over the IBKR login.
"""
from __future__ import annotations

import asyncio

import pytest

from constants_ibkr import IBKR_GATEWAY_API_HEAL_COOLDOWN_SEC, IBKR_GATEWAY_API_STUCK_SEC
from ibkr import gateway_api_heal as heal
from ibkr import gateway_process

UP = heal.Facts(listening=True, gateway_running=True, internet=True)


@pytest.fixture(autouse=True)
def _reset():
    heal.reset_for_tests()
    gateway_process.reset_for_tests()
    yield
    heal.reset_for_tests()
    gateway_process.reset_for_tests()


def test_gateway_1045_runs_as_ibgateway1_and_counts_as_a_gateway():
    csv = ('"System Idle Process","0","Services","0","8 K"\r\n'
           '"ibgateway1.exe","55632","Console","1","712,532 K"\r\n'
           '"tws.exe","10","Console","1","1 K"\r\n'
           '"ibgatewayhelper.exe","11","Console","1","1 K"\r\n')
    assert gateway_process.gateway_images(csv) == ["ibgateway1.exe", "tws.exe"]
    assert gateway_process.gateway_images('"python.exe","1","Console","1","1 K"\r\n') == []


def test_the_process_check_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(gateway_process.os, "name", "nt")
    monkeypatch.setattr(gateway_process, "_tasklist", lambda: calls.append(1) or '"ibgateway1.exe","1"\r\n')
    assert gateway_process.running(now=100.0) and gateway_process.running(now=102.0)
    assert len(calls) == 1
    assert gateway_process.running(now=200.0) and len(calls) == 2


def test_decide_restarts_only_a_logged_in_gateway_refusing_long_enough():
    t0 = 1_000.0
    late = t0 + IBKR_GATEWAY_API_STUCK_SEC
    assert heal.decide(t0 + 30, first_refused=t0, facts=UP, last_restart_at=None) == heal.WAIT
    assert heal.decide(late, first_refused=t0, facts=UP, last_restart_at=None) == heal.RESTART
    assert heal.decide(late, first_refused=t0, facts=heal.Facts(False, True, True), last_restart_at=None) == heal.NOT_LISTENING
    assert heal.decide(late, first_refused=t0, facts=heal.Facts(True, False, True), last_restart_at=None) == heal.NO_GATEWAY
    assert heal.decide(late, first_refused=t0, facts=heal.Facts(True, True, False), last_restart_at=None) == heal.NO_INTERNET
    assert heal.decide(late, first_refused=t0, facts=UP, last_restart_at=late - 60) == heal.COOLDOWN
    assert heal.decide(late, first_refused=t0, facts=UP,
                       last_restart_at=late - IBKR_GATEWAY_API_HEAL_COOLDOWN_SEC) == heal.RESTART


def test_netstat_listening_ports():
    text = ("  Proto  Local Address          Foreign Address        State           PID\n"
            "  TCP    0.0.0.0:4001           0.0.0.0:0              LISTENING       55632\n"
            "  TCP    127.0.0.1:52575        127.0.0.1:4001         ESTABLISHED     58168\n"
            "  TCP    [::]:4003              [::]:0                 LISTENING       55632\n")
    assert heal.listening_ports(text) == {4001, 4003}


def test_a_stuck_port_sends_ibc_restart_once(monkeypatch, tmp_path):
    sent: list[str] = []
    monkeypatch.setattr(heal, "gather", lambda port: UP)
    monkeypatch.setattr(heal, "send_ibc_command", lambda cmd: sent.append(cmd) or None)
    monkeypatch.setattr(heal, "_ibc_ini", lambda: tmp_path / "config.ini")
    t = 1_000.0
    for step in range(0, int(IBKR_GATEWAY_API_STUCK_SEC) + 12, 12):   # the dialer retries every ~12 s
        asyncio.run(heal.after_refused(4001, now=t + step))
    assert sent == ["RESTART"]
    assert heal.view()["state"] == heal.RESTART and heal.view()["last_restart"]["ok"]
    asyncio.run(heal.after_refused(4001, now=t + IBKR_GATEWAY_API_STUCK_SEC + 24))
    assert sent == ["RESTART"] and heal.view()["state"] == heal.COOLDOWN
    heal.note_connected()
    assert heal.view()["state"] == "ok" and heal.view()["refused_since"] is None


def test_a_gap_in_the_refusals_starts_the_clock_again(monkeypatch):
    monkeypatch.setattr(heal, "gather", lambda port: UP)
    monkeypatch.setattr(heal, "send_ibc_command", lambda cmd: pytest.fail("no restart"))
    asyncio.run(heal.after_refused(4001, now=1_000.0))
    assert asyncio.run(heal.after_refused(4001, now=1_000.0 + IBKR_GATEWAY_API_STUCK_SEC + 300)) == heal.WAIT


def test_only_refusals_count():
    asyncio.run(heal.after_failed("timeout", 4001))
    assert heal.view()["refused_since"] is None


def test_restart_failure_is_stated(monkeypatch, tmp_path):
    monkeypatch.setattr(heal, "gather", lambda port: UP)
    monkeypatch.setattr(heal, "send_ibc_command", lambda cmd: "IBC's command server did not answer")
    monkeypatch.setattr(heal, "_ibc_ini", lambda: tmp_path / "config.ini")
    for step in range(0, int(IBKR_GATEWAY_API_STUCK_SEC) + 12, 12):
        asyncio.run(heal.after_refused(4001, now=float(step)))
    view = heal.view()
    assert view["state"] == "restart_failed" and "did not answer" in view["text"]


def test_ensure_command_server_turns_it_on_for_this_pc_only(tmp_path):
    ini = tmp_path / "config.ini"
    ini.write_text("TradingMode=live\nCommandServerPort=0\nControlFrom=\nBindAddress=\n", encoding="utf-8")
    assert heal.ensure_command_server(ini) is True
    text = ini.read_text(encoding="utf-8")
    assert "CommandServerPort=7462" in text and "ControlFrom=127.0.0.1" in text and "BindAddress=127.0.0.1" in text
    assert heal.ensure_command_server(ini) is False
    assert heal.ensure_command_server(tmp_path / "missing.ini") is False


def test_the_launcher_sees_a_running_gateway_and_starts_no_second(monkeypatch):
    from ibkr import launch_gateway

    monkeypatch.setattr(gateway_process, "running", lambda now=None: True)
    assert launch_gateway._gateway_process_running() is True


def test_the_ladder_names_who_holds_every_line():
    from line_lending.view import cap_words

    lines = [{"symbol": "SDEV", "held_by": "record"}, {"symbol": "SSM", "held_by": "record"},
             {"symbol": "AMOD", "held_by": "tab"}]
    words = cap_words("AZTA", lines)
    assert "AMOD in another Level 2" in words and "SDEV and SSM recording" in words
    assert "AZTA's book comes up by itself" in words
