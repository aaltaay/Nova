"""#14 evidence: an unattended 03:55 PASS, and no weekday phone login -- each
one explained. Built from already-read facts, so no Windows or log access."""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import premarket_verify as pv  # noqa: E402
from ibkr.relogin_reason import IbcLogin  # noqa: E402
from ibkr.windows_restarts import Restart  # noqa: E402

MORNING_LOG = """\
2026-09-21 03:55:07 [PASS] gateway_port listening
2026-09-21 03:55:08 [ERROR] RESULT FAIL leg=integrity
2026-09-22 03:55:02 [PASS] gateway_port listening
2026-09-22 03:55:03 [PASS] RESULT PASS
2026-09-22 11:10:00 [PASS] gateway_port listening
2026-09-22 11:10:01 [PASS] RESULT PASS
"""

DAILY_LOG = """\
2026-09-22 13:21:36 [INFO] Starting IB Gateway via IBC (C:\\Users\\op\\.nova\\ibc\\start_gateway.ps1)
2026-09-23 09:23:04 [INFO] Starting IB Gateway via IBC (C:\\Users\\op\\.nova\\ibc\\start_gateway.ps1)
2026-09-26 12:00:00 [INFO] Starting IB Gateway via IBC (C:\\Users\\op\\.nova\\ibc\\start_gateway.ps1)
"""


def _ts(text: str) -> float:
    return time.mktime(datetime.strptime(text, "%Y-%m-%d %H:%M:%S").timetuple())


UPDATE_RESTART = Restart(
    boot_ts=_ts("2026-09-23 02:32:00"),
    cause="windows_update",
    label="Windows Update (MoUsoCoreWorker.exe)",
    initiated_ts=_ts("2026-09-23 02:29:26"),
    process="MoUsoCoreWorker.exe",
    first_signin_ts=_ts("2026-09-23 09:22:51"),
)


def test_runs_split_by_date_and_gap_and_only_the_0355_window_is_unattended():
    runs = pv.parse_morning_runs(MORNING_LOG)
    assert [(r["date"], r["started"], r["unattended"], r["result"]) for r in runs] == [
        ("2026-09-21", "03:55:07", True, "FAIL"),
        ("2026-09-22", "03:55:02", True, "PASS"),
        ("2026-09-22", "11:10:00", False, "PASS"),
    ]
    assert runs[0]["failed_leg"] == "integrity"


def _evidence(now: str, **kw):
    base = dict(
        runs=pv.parse_morning_runs(MORNING_LOG),
        ibc_logins=[IbcLogin(ts=_ts("2026-09-23 09:23:10"), full_auth=True)],
        launches=pv.parse_gateway_launches(DAILY_LOG),
        restarts=[UPDATE_RESTART],
        days=7,
        now=_ts(now),
    )
    base.update(kw)
    return pv.build_evidence(**base)


def test_a_weekday_phone_login_keeps_14_open_and_says_it_was_windows_update():
    ev = _evidence("2026-09-23 10:00:00")
    assert ev["criteria"]["unattended_pass"] == {"met": True, "date": "2026-09-22"}
    assert ev["criteria"]["no_unexpected_logins"]["met"] is False
    # The 09:23:04 launch and IBC's 09:23:10 login are one start, counted once.
    assert [(r["source"], r["weekday"]) for r in ev["full_logins"]] == [("daily_start", "Tue"), ("ibc_log", "Wed")]
    wed = ev["full_logins"][-1]
    assert wed["relogin"]["reason"] == "pc_restarted" and wed["expected"] is False
    assert ev["met"] is False


def test_the_missed_morning_says_nobody_was_signed_in():
    ev = _evidence("2026-09-23 10:00:00")
    missed = {m["date"]: m["reason"] for m in ev["missed_mornings"]}
    assert "2026-09-23" in missed
    assert "Windows Update" in missed["2026-09-23"] and "nobody signed in until 09:22" in missed["2026-09-23"]


def test_a_weekend_phone_login_is_expected():
    ev = _evidence(
        "2026-09-27 10:00:00",
        ibc_logins=[],
        launches=[_ts("2026-09-26 12:00:00")],
        restarts=[],
    )
    (row,) = ev["full_logins"]
    assert row["weekday"] == "Sat" and row["expected"] is True
    assert ev["criteria"]["no_unexpected_logins"]["met"] is True


def test_an_unreadable_event_log_is_said_not_read_as_no_restarts():
    ev = _evidence("2026-09-23 10:00:00", restarts=None)
    assert ev["restarts_readable"] is False
    assert "could not be read" in pv.render_text(ev)
