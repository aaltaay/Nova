"""#14: say why IB Gateway needed a phone login -- a PC restart (and who asked
for it), or a fresh start -- from the IBC log and the Windows event log.

Fixtures are the real 2026-09-23 desk: Windows Update restarted the PC at
02:29 ET, Windows sat at the sign-in screen until 09:22, and IBC's 09:23 start
found no autorestart file.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from diagnostics.collect_gateway import gateway_rows
from ibkr import relogin_reason as rr
from ibkr import windows_restarts as wr

NS = "http://schemas.microsoft.com/win/2004/08/events/event"


def _utc(text: str) -> str:
    return text + "Z"


def _event(event_id: int, provider: str, when_utc: str, data: dict[str, str] | None = None) -> str:
    items = "".join(f"<Data Name='{k}'>{v}</Data>" for k, v in (data or {}).items())
    return (
        f"<Event xmlns='{NS}'><System><Provider Name='{provider}'/><EventID>{event_id}</EventID>"
        f"<TimeCreated SystemTime='{_utc(when_utc)}'/></System><EventData>{items}</EventData></Event>"
    )


def _planned(when_utc: str, exe: str, reason: str) -> str:
    return _event(1074, "User32", when_utc, {
        "param1": f"C:\\WINDOWS\\x\\{exe} (DESKTOP-K82GUGN)",
        "param3": reason,
        "param5": "restart",
    })


def _ts(utc: str) -> float:
    return datetime.fromisoformat(utc).replace(tzinfo=timezone.utc).timestamp()


UPDATE_NIGHT = "".join([
    _planned("2026-09-23T06:29:26.5064098", "MoUsoCoreWorker.exe", "Operating System: Service pack (Planned)"),
    _event(12, "Microsoft-Windows-Kernel-General", "2026-09-23T06:30:48.0"),
    _planned("2026-09-23T06:31:45.5640494", "TrustedInstaller.exe", "Operating System: Upgrade (Planned)"),
    _event(12, "Microsoft-Windows-Kernel-General", "2026-09-23T06:32:00.0"),
    _event(12, "Microsoft-Windows-UserModePowerService", "2026-09-23T07:00:00.0"),
    _event(7001, "Microsoft-Windows-Winlogon", "2026-09-23T13:22:51.8"),
])


def test_windows_update_double_reboot_is_one_restart_named_by_who_started_it():
    restarts = wr.restarts_from_events(wr.parse_events_xml(UPDATE_NIGHT))
    assert len(restarts) == 1
    r = restarts[0]
    assert r.cause == "windows_update" and r.process == "MoUsoCoreWorker.exe"
    assert r.windows_reason == "Operating System: Service pack (Planned)"
    assert r.initiated_ts == _ts("2026-09-23T06:29:26.506409")
    assert r.boot_ts == _ts("2026-09-23T06:32:00")
    assert r.first_signin_ts == _ts("2026-09-23T13:22:51.8")


def test_unexpected_shutdown_and_unrecorded_restart_are_stated_not_guessed():
    xml = "".join([
        _event(12, "Microsoft-Windows-Kernel-General", "2026-09-21T14:35:00.0"),
        _event(12, "Microsoft-Windows-Kernel-General", "2026-09-21T17:44:40.0"),
        _event(6008, "EventLog", "2026-09-21T17:44:52.3"),
        _event(12, "Microsoft-Windows-Kernel-General", "2026-09-22T17:20:40.0"),
        _planned("2026-09-22T17:20:32.0", "StartMenuExperienceHost.exe", "Other (Unplanned)"),
    ])
    causes = [r.cause for r in wr.restarts_from_events(wr.parse_events_xml(xml))]
    assert causes == ["unknown", "unexpected", "start_menu"]


def test_unreadable_event_xml_is_unknown_not_no_events():
    assert wr.parse_events_xml("<Event><broken") is None
    assert wr.parse_events_xml("") == []


IBC_LOG = """
Starting IBC version 3.24.1 on Wed 09/23/2026 at  9:23:06.25
Finding autorestart file
autorestart file not found: full authentication will be required
2026-09-23 09:23:10:348 IBC: version: 3.24.1
2026-09-23 09:23:20:323 IBC: Second Factor Authentication initiated
"""

IBC_RESTART_LOG = """
Finding autorestart file
autorestart file found at C:\\Jts\\abc\\autorestart: authentication will not be required
2026-09-22 23:45:04:001 IBC: version: 3.24.1
"""


def test_ibc_log_says_whether_a_start_needed_the_phone():
    (login,) = rr.parse_ibc_logins(IBC_LOG)
    assert login.full_auth is True
    assert login.ts == time.mktime(datetime(2026, 9, 23, 9, 23, 10).timetuple())
    (restart,) = rr.parse_ibc_logins(IBC_RESTART_LOG)
    assert restart.full_auth is False


def test_a_restart_before_the_login_is_the_reason_and_the_signin_wait_is_said():
    restarts = wr.restarts_from_events(wr.parse_events_xml(UPDATE_NIGHT))
    (login,) = rr.parse_ibc_logins(IBC_LOG)
    why = rr.explain(login, restarts, now=login.ts + 60)
    assert why["reason"] == "pc_restarted"
    assert why["text"].startswith("Windows Update (MoUsoCoreWorker.exe) restarted this PC at")
    assert "sign-in screen until" in why["text"] and "needs your phone" in why["text"]
    assert why["restart"]["cause"] == "windows_update"


def test_the_saved_login_reused_is_not_a_phone_login():
    (login,) = rr.parse_ibc_logins(IBC_RESTART_LOG)
    assert rr.explain(login, [], now=login.ts)["reason"] == "token_reused"


def test_a_fresh_start_with_no_restart_names_the_causes_it_cannot_tell_apart():
    (login,) = rr.parse_ibc_logins(IBC_LOG)
    why = rr.explain(login, [], now=login.ts)
    assert why["reason"] == "gateway_started_fresh"
    assert "closed or had crashed" in why["text"] and why["restart"] is None


def test_a_restart_older_than_a_day_is_not_blamed():
    restarts = wr.restarts_from_events(wr.parse_events_xml(UPDATE_NIGHT))
    (login,) = rr.parse_ibc_logins(IBC_LOG)
    later = login.ts + 3 * 86400
    assert rr.explain(rr.IbcLogin(ts=later, full_auth=True), restarts, now=later)["reason"] == "gateway_started_fresh"


def test_an_unreadable_event_log_never_claims_a_restart():
    why = rr.explain(None, None, now=time.time())
    assert why["reason"] == "unknown" and "could not be read" in why["text"]


def test_diagnostics_row_leads_with_the_reason_while_a_prompt_is_open():
    rows = gateway_rows(
        enabled=True,
        session={"state": "connecting", "usable": False, "transport_up": False, "reason": "gateway_authenticating"},
        ports={"live_port": 4001, "paper_port": 4002, "live_reachable": False, "paper_reachable": False},
        ibc={
            "second_factor_pending": True,
            "second_factor_age_sec": 30.0,
            "second_factor_stale": False,
            "launcher_present": True,
            "relogin": {"reason": "pc_restarted", "text": "Windows Update restarted this PC at 02:29."},
        },
        last_error=None,
        attach={"attempts_in_window": 0},
        heal={},
    )
    row = next(r for r in rows if r["id"] == "gateway_ibc_login")
    assert row["state"] == "warn"
    assert row["cause"].startswith("Windows Update restarted this PC at 02:29.")
    assert row["evidence"]["relogin"]["reason"] == "pc_restarted"


def test_no_prompt_no_reason_in_the_row():
    rows = gateway_rows(
        enabled=True,
        session={"state": "ready", "usable": True, "transport_up": True, "reason": "ok"},
        ports={"live_port": 4001, "paper_port": 4002, "live_reachable": True, "paper_reachable": False},
        ibc={"second_factor_pending": False, "launcher_present": True, "relogin": {"text": "stale"}},
        last_error=None,
        attach={"attempts_in_window": 0},
        heal={},
    )
    row = next(r for r in rows if r["id"] == "gateway_ibc_login")
    assert row["state"] == "ok" and "stale" not in row["cause"]


def test_launcher_passes_the_weekday_ibc_can_no_longer_read_from_wmic(monkeypatch, tmp_path):
    from ibkr import launch_gateway

    seen = {}
    monkeypatch.setattr(launch_gateway.subprocess, "Popen", lambda args, **kw: seen.update(kw))
    launch_gateway._start_process(tmp_path / "start_gateway.ps1", via_powershell=True)
    assert seen["env"]["DAYOFWEEK"] == datetime.now().strftime("%A").upper()
