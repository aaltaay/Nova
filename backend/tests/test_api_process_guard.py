"""Parent-loss and dark-port self-exit predicates (D-005)."""
from __future__ import annotations

import api_process_guard as guard


def test_parent_lost_when_launcher_dies():
    assert guard.parent_lost(100, 100, parent_alive=False) is True
    assert guard.parent_lost(100, 1, parent_alive=True) is True
    assert guard.parent_lost(100, 100, parent_alive=True) is False
    assert guard.parent_lost(1, 1, parent_alive=False) is False


def test_dark_port_exits_only_after_grace():
    assert guard.should_exit_for_dark_port(1.0, listening=False, grace_sec=10) is False
    assert guard.should_exit_for_dark_port(10.0, listening=False, grace_sec=10) is True
    assert guard.should_exit_for_dark_port(99.0, listening=True, grace_sec=10) is False


def test_a_probe_that_cannot_run_never_stops_the_api():
    assert guard.should_exit_for_dark_port(9999.0, listening=None, grace_sec=10) is False


class _Stop(BaseException):
    """Ends a watch loop in a test (the loop catches Exception)."""


def _run_watch(monkeypatch, answers):
    exits: list[int] = []
    flushed: list[bool] = []
    calls = iter(answers)

    def probe(_host, _port):
        try:
            answer = next(calls)
        except StopIteration:
            raise _Stop from None
        if isinstance(answer, Exception):
            raise answer
        return answer

    def fake_exit(code):
        exits.append(code)
        raise _Stop

    monkeypatch.setattr(guard.os, "_exit", fake_exit)
    monkeypatch.setattr(guard, "_flush_before_exit", lambda: flushed.append(True))
    try:
        guard._watch_listen("127.0.0.1", 8000, started_at=-1e9, port_listening=probe, interval_sec=0,
                            grace_sec=10)
    except _Stop:
        pass
    return exits, flushed


def test_the_listen_watch_stays_up_while_the_pc_refuses_test_connections(monkeypatch, caplog):
    # 2026-10-14: out of ports, every probe failed and the guard stopped a serving API 19 times.
    caplog.set_level("WARNING", logger=guard.logger.name)
    exits, _ = _run_watch(monkeypatch, [None, None, OSError(10048, "in use"), None, True])
    assert exits == []
    assert sum("cannot tell whether" in r.getMessage() for r in caplog.records) == 1   # once per streak


def test_a_dark_port_still_exits_and_writes_out_what_it_holds_first(monkeypatch):
    exits, flushed = _run_watch(monkeypatch, [None, False])
    assert exits == [1] and flushed == [True]


def test_flush_before_exit_drains_the_journal_then_the_log_queue(monkeypatch):
    import sys
    import types

    order: list[str] = []
    journal = types.SimpleNamespace(flush=lambda timeout: order.append(f"journal {timeout}") or True)
    setup = types.SimpleNamespace(shutdown_logging=lambda: order.append("logs"))
    monkeypatch.setitem(sys.modules, "eyes.journal", journal)
    monkeypatch.setitem(sys.modules, "logging_setup", setup)
    guard._flush_before_exit()
    assert order == [f"journal {guard.JOURNAL_FLUSH_SEC}", "logs"]


def test_a_journal_that_cannot_drain_says_how_many_lines_the_exit_loses(monkeypatch, caplog):
    import sys
    import types

    caplog.set_level("ERROR", logger=guard.logger.name)
    journal = types.SimpleNamespace(flush=lambda timeout: False, status=lambda: {"queued": 37})
    monkeypatch.setitem(sys.modules, "eyes.journal", journal)
    monkeypatch.setitem(sys.modules, "logging_setup", types.SimpleNamespace(shutdown_logging=lambda: None))
    guard._flush_before_exit()
    [rec] = caplog.records
    assert "37 line(s) queued" in rec.getMessage() and "lost" in rec.getMessage()