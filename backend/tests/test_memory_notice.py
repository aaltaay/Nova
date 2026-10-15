"""The desk's low-memory notice (operator ask 2026-10-15).

A one-off script grew past 175 GB on the 96 GB desk PC; the memory watch read the PC nearly out at 08:47 ET and
the TraderTV LIVE page went blank at 09:02, with nothing on the desk saying why. These pin when the strip shows
(the ``pc_memory`` row's 90% line, Nova's trading session, a fresh reading, an open episode), the episode's hold
and its early close, the words that name the process holding the most, that the program is named only where an
issue report never copies it, and that nothing on this path can act on a process. Process names are made up.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from constants_perf import PERF_MEMORY_NOTICE_HOLD_SEC, PERF_MEMORY_STALE_SEC
from diagnostics.collect_memory import memory_rows
from perf import memory_notice as mn
from perf import memory_watch as mw

ET = ZoneInfo("America/New_York")
T = datetime(2026, 10, 15, 8, 47, tzinfo=ET).timestamp()    # a Thursday, inside Nova's 04:00-20:00 ET session
MB = 2**20
API = 100
CRUNCHER = 500                                                # the made-up script that eats the PC


@dataclass(frozen=True)
class P:
    pid: int
    ppid: int
    name: str


PROCS = [P(API, 1, "nova-api.exe"), P(CRUNCHER, 1, "numbercruncher.exe"),
         P(600, 1, "tabhoarder.exe"), P(601, 600, "tabhoarder.exe"), P(602, 600, "tabhoarder.exe")]
BORN = {API: T - 3 * 3600, CRUNCHER: T - 180, 600: T - 7200, 601: T - 7000, 602: T - 6000}
SIZES = {API: 1900, CRUNCHER: 121_446, 600: 900, 601: 800, 602: 700}     # MB; 121,446 MB reads 118.6 GB


@pytest.fixture(autouse=True)
def _reset():
    mw.reset_for_tests()
    yield
    mw.reset_for_tests()


def _pc(free_gb=0.1, used_gb=182, limit_gb=188, total_gb=96):
    total, free = total_gb * 1024, round(free_gb * 1024)
    return {"load_pct": round(100 * (total - free) / total), "ram_total_mb": total, "ram_free_mb": free,
            "commit_limit_mb": limit_gb * 1024, "commit_used_mb": used_gb * 1024}


def _read(now=T, pc=None, sizes=SIZES, born=BORN):
    return mw.reading(now=now, api_pid=API, procs=PROCS, private_of=lambda pid: sizes[pid] * MB if pid in sizes else None,
                      created=born.get, desk=set(), gateway=set(), pc=pc or _pc())


def _status(read, episode="open"):
    if episode == "open":
        episode = mw.next_episode(None, read)
    return {"available": True, "running": True, "every_sec": 60, "last": read, "episode": episode}


def _notice(read, now=T, episode="open", in_session=True):
    return mn.notice(status=_status(read, episode), now=now, in_session=in_session)


# -- the reading names the one process holding the most ------------------------------------------------------

def test_the_reading_names_the_biggest_process_and_when_it_started():
    assert _read()["biggest"] == {"name": "numbercruncher.exe", "pid": CRUNCHER, "private_mb": 121_446,
                                  "started_at": round(T - 180, 3), "role": None}


def test_novas_own_process_can_be_the_biggest_and_says_whose_it_is():
    read = _read(sizes={**SIZES, CRUNCHER: 100})
    assert read["biggest"]["pid"] == API and read["biggest"]["role"] == "api"


def test_no_biggest_when_nothing_can_be_read_and_an_unknown_start_is_none():
    assert _read(sizes={})["biggest"] is None
    born = {pid: t for pid, t in BORN.items() if pid != CRUNCHER}
    assert _read(born=born)["biggest"]["started_at"] is None


# -- the episode ------------------------------------------------------------------------------------------------

def test_the_episode_opens_at_the_line_and_keeps_its_start_while_low():
    assert mw.next_episode(None, _read(pc=_pc(free_gb=40, used_gb=80))) is None          # a healthy PC
    first = mw.next_episode(None, _read())
    assert first == {"since": T, "last_low_at": T, "pid": CRUNCHER}
    later = mw.next_episode(first, _read(now=T + 60, sizes={**SIZES, 600: 130_000}))      # another leads, still low
    assert later == {"since": T, "last_low_at": T + 60, "pid": 600}


def test_the_episode_holds_through_a_short_relief_while_the_same_process_leads():
    episode = mw.next_episode(None, _read())
    relief = _read(now=T + 120, pc=_pc(free_gb=34.6, used_gb=188, limit_gb=232))        # 2026-10-15 08:56
    assert mw.next_episode(episode, relief) == episode
    over = _read(now=T + PERF_MEMORY_NOTICE_HOLD_SEC, pc=_pc(free_gb=34.6, used_gb=188, limit_gb=232))
    assert mw.next_episode(episode, over) is None                                          # the hold ran out


def test_the_episode_closes_at_once_when_the_biggest_process_lets_go():
    episode = mw.next_episode(None, _read())
    gone = {pid: mb for pid, mb in SIZES.items() if pid != CRUNCHER}                     # the operator closed it
    assert mw.next_episode(episode, _read(now=T + 60, pc=_pc(free_gb=63.8, used_gb=59, limit_gb=146),
                                           sizes=gone)) is None


def test_a_reading_without_the_pcs_numbers_leaves_the_episode_as_it_was():
    episode = mw.next_episode(None, _read())
    blind = {**_read(now=T + 60), "pc": None}
    assert mw.next_episode(episode, blind) == episode
    assert mw.next_episode(None, blind) is None


# -- the notice's words ---------------------------------------------------------------------------------------

def test_nearly_out_names_the_biggest_process_how_much_and_how_long():
    note = _notice(_read())
    assert note["level"] == "nearly_out"
    assert note["text"] == "PC memory nearly out: 0.1 GB of 96 GB free, 182 of 188 GB committed."
    assert note["hint"] == ("Biggest: numbercruncher.exe, PID 500, holds 118.6 GB, running 3 min. "
                            "Nova only warns: it never stops a program. Task Manager > Details, by PID.")
    assert note["biggest"]["run_sec"] == 180 and note["group"] is None
    assert note["since"] == T and note["ts"] == T and note["pc"]["ram_free_mb"] == 102


def test_low_says_what_is_short():
    ram = _notice(_read(pc=_pc(free_gb=8.9, used_gb=120)))
    assert ram["level"] == "low" and ram["text"] == "PC memory low: 8.9 GB of 96 GB free."
    commit = _notice(_read(pc=_pc(free_gb=40, used_gb=135, limit_gb=146)))
    assert commit["level"] == "low" and commit["text"] == "PC memory low: 135 of 146 GB committed."


def test_easing_says_when_it_was_low_and_what_is_free_now():
    episode = mw.next_episode(None, _read())
    relief = _read(now=T + 120, pc=_pc(free_gb=34.6, used_gb=188, limit_gb=232))
    note = _notice(relief, now=T + 130, episode=mw.next_episode(episode, relief))
    assert note["level"] == "easing"
    assert note["text"] == "PC memory was low 2 min ago: 34.6 GB of 96 GB free now."
    assert note["hint"].startswith("Biggest: numbercruncher.exe, PID 500, holds 118.6 GB, running 5 min.")
    soon = _notice(relief, now=T + 30, episode=episode)
    assert soon["text"].startswith("PC memory was low under a minute ago:")


def test_the_key_is_the_episode_and_its_biggest_process_whatever_the_level():
    episode = mw.next_episode(None, _read(pc=_pc(free_gb=8.9, used_gb=120)))
    low = _notice(_read(pc=_pc(free_gb=8.9, used_gb=120)), episode=episode)
    assert low["level"] == "low" and low["key"] == f"{T:.0f}|500"
    out = _notice(_read(now=T + 60), now=T + 60, episode=mw.next_episode(episode, _read(now=T + 60)))
    assert out["level"] == "nearly_out" and out["key"] == low["key"]           # the desk compares the levels
    relief = _read(now=T + 120, pc=_pc(free_gb=34.6, used_gb=188, limit_gb=232))
    easing = _notice(relief, now=T + 120, episode=mw.next_episode(episode, relief))
    assert easing["level"] == "easing" and easing["key"] == low["key"]
    other = _read(now=T + 60, pc=_pc(free_gb=8.9, used_gb=120), sizes={**SIZES, 600: 130_000})
    assert _notice(other, now=T + 60, episode=mw.next_episode(episode, other))["key"] == f"{T:.0f}|600"
    later = _read(now=T + 900)
    assert _notice(later, now=T + 900, episode=mw.next_episode(None, later))["key"] == f"{T + 900:.0f}|500"


def test_a_program_of_many_processes_is_named_beside_the_biggest_one():
    many = {API: 1900, CRUNCHER: 2000, 600: 1500, 601: 1500, 602: 1500}
    note = _notice(_read(sizes=many))
    assert note["group"] == {"name": "tabhoarder.exe", "count": 3, "private_mb": 4500}
    assert note["hint"].startswith("Biggest: numbercruncher.exe, PID 500, holds 2.0 GB, running 3 min. "
                                   "3 tabhoarder.exe processes hold 4.4 GB together. Nova only warns")
    led = {API: 1900, CRUNCHER: 100, 600: 2000, 601: 1500, 602: 1000}
    assert "It is one of 3 tabhoarder.exe processes, 4.4 GB together." in _notice(_read(sizes=led))["hint"]
    nova = {API: 2100, CRUNCHER: 100, 600: 1500, 601: 1500, 602: 1500}
    assert _notice(_read(sizes=nova))["hint"].startswith(
        "Biggest: Nova's API (nova-api.exe), PID 100, holds 2.1 GB, running 3 h. "
        "3 tabhoarder.exe processes hold 4.4 GB together.")
    assert _notice(_read())["group"] is None                                     # one process is the story


def test_unknown_start_and_nothing_readable_are_said_plainly():
    born = {pid: t for pid, t in BORN.items() if pid != CRUNCHER}
    assert "PID 500, holds 118.6 GB, start time unknown." in _notice(_read(born=born))["hint"]
    assert mn.biggest_words(None, None) == "Biggest: no process could be read."


@pytest.mark.parametrize(("sec", "words"), [(-5, "under a minute"), (59, "under a minute"), (60, "1 min"),
                                            (3599, "59 min"), (3600, "1 h"), (3660, "1 h 1 min"),
                                            (86_400, "1 d"), (90_000, "1 d 1 h")])
def test_run_words(sec, words):
    assert mn.run_words(sec) == words


# -- when there is no notice ----------------------------------------------------------------------------------

def test_no_notice_outside_the_session_without_an_episode_or_a_fresh_reading():
    read = _read()
    assert _notice(read, in_session=False) is None
    assert _notice(read, episode=None) is None
    assert _notice(read, now=T + PERF_MEMORY_STALE_SEC + 1) is None
    assert mn.notice(status={**_status(read), "available": False}, now=T, in_session=True) is None
    assert _notice({**read, "pc": None}) is None
    assert mn.notice(status={"available": True, "running": True, "last": None, "episode": None}, now=T,
                     in_session=True) is None


@pytest.mark.parametrize(("when", "on"), [
    (datetime(2026, 10, 15, 8, 47), True),        # Thursday premarket
    (datetime(2026, 10, 15, 4, 0), True),         # the session's first minute
    (datetime(2026, 10, 15, 3, 59), False),
    (datetime(2026, 10, 15, 20, 0), False),       # the session ends at 20:00
    (datetime(2026, 10, 17, 10, 0), False),       # Saturday
    (datetime(2026, 12, 25, 10, 0), False),       # an NYSE holiday
])
def test_the_route_judges_nova_s_trading_session(monkeypatch, when, on):
    now = when.replace(tzinfo=ET).timestamp()
    read = _read(now=now)
    monkeypatch.setattr(mw, "status", lambda: _status(read))
    answer = mn.view(now=now)
    assert answer["schema_version"] == 1 and answer["in_session"] is on
    assert (answer["notice"] is not None) is on


def test_get_memory_notice_answers_the_view(monkeypatch):
    from perf.routes import router

    seen = {}
    monkeypatch.setattr(mn, "view", lambda now=None: seen.setdefault("view", {"schema_version": 1, "notice": None}))
    app = FastAPI()
    app.include_router(router)
    res = TestClient(app).get("/api/perf/memory-notice")
    assert res.status_code == 200 and res.json() == {"schema_version": 1, "notice": None} and "view" in seen


# -- the program is named only on the desk, and nothing acts on it --------------------------------------------

def test_the_pc_memory_row_names_the_biggest_process_only_in_its_fix():
    (row,) = memory_rows(status=_status(_read()), now=T)
    assert row["state"] == "fail"
    assert "Biggest: numbercruncher.exe, PID 500, holds 118.6 GB, running 3 min." in row["fix"]
    assert "numbercruncher" not in row["detail"] and "numbercruncher" not in row["cause"]


def test_the_api_log_never_names_the_program(caplog):
    caplog.set_level(logging.WARNING, logger="perf.memory_watch")
    mw._warn(_read())
    assert caplog.records and all("numbercruncher" not in r.getMessage() for r in caplog.records)


def test_nothing_on_the_memory_path_can_stop_pause_or_slow_a_process():
    backend = Path(__file__).resolve().parents[1]
    acting = ("TerminateProcess", "NtSuspendProcess", "SuspendThread", "DebugActiveProcess", "SetPriorityClass",
              "SetProcessWorkingSetSize", "EmptyWorkingSet", "SetInformationProcess", "taskkill", "os.kill",
              ".terminate(", ".kill(", "PROCESS_TERMINATE", "PROCESS_SUSPEND_RESUME", "PROCESS_SET_INFORMATION")
    for rel in ("perf/memory_watch.py", "perf/memory_notice.py", "winapi/memory.py", "winapi/processes.py",
                "diagnostics/collect_memory.py"):
        text = (backend / rel).read_text(encoding="utf-8")
        assert not [word for word in acting if word in text], rel
