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


def _recorded_1074(when_utc: str, sid: str, process: str, reason: str, code: str, kind: str, user: str) -> str:
    """A System 1074 as ``wevtutil qe /f:xml`` printed it on the desk, the
    operator's user name and SID replaced."""
    return (
        f"<Event xmlns='{NS}'><System><Provider Name='User32' Guid='{{b0aa8734-56f7-41cc-b2f4-de228e98b946}}' "
        "EventSourceName='User32'/><EventID Qualifiers='32768'>1074</EventID><Version>0</Version><Level>4</Level>"
        "<Task>0</Task><Opcode>0</Opcode><Keywords>0x8080000000000000</Keywords>"
        f"<TimeCreated SystemTime='{_utc(when_utc)}'/><EventRecordID>157917</EventRecordID><Correlation/>"
        "<Execution ProcessID='1620' ThreadID='5716'/><Channel>System</Channel><Computer>DESKTOP-K82GUGN</Computer>"
        f"<Security UserID='{sid}'/></System><EventData>"
        f"<Data Name='param1'>{process} (DESKTOP-K82GUGN)</Data><Data Name='param2'>DESKTOP-K82GUGN</Data>"
        f"<Data Name='param3'>{reason}</Data><Data Name='param4'>{code}</Data><Data Name='param5'>{kind}</Data>"
        f"<Data Name='param6'></Data><Data Name='param7'>{user}</Data></EventData></Event>"
    )


SYSTEM = ("S-1-5-18", "NT AUTHORITY\\SYSTEM")
OPERATOR = ("S-1-5-21-1-2-3-1001", "DESKTOP-K82GUGN\\operator")
WINLOGON = "C:\\WINDOWS\\system32\\winlogon.exe"
START_MENU = (
    "C:\\Windows\\SystemApps\\Microsoft.Windows.StartMenuExperienceHost_cw5n1h2txyewy\\StartMenuExperienceHost.exe"
)
NO_TITLE = "No title for this reason could be found"

# 2026-10-05 06:45 ET: the power button, the PC back on two minutes later.
POWER_BUTTON_MORNING = "".join([
    _recorded_1074("2026-10-05T10:45:27.4809345", SYSTEM[0], WINLOGON, NO_TITLE, "0x500ff", "power off",
                   SYSTEM[1]),
    _event(12, "Microsoft-Windows-Kernel-General", "2026-10-05T10:47:26.0"),
    _event(7001, "Microsoft-Windows-Winlogon", "2026-10-05T10:48:37.0"),
])

# 2026-10-04 19:58 ET: Start > Power > Shut down, back on at 20:01.
START_MENU_EVENING = "".join([
    _recorded_1074("2026-10-04T23:58:57.0161278", OPERATOR[0], START_MENU, "Other (Unplanned)", "0x0",
                   "power off", OPERATOR[1]),
    _event(12, "Microsoft-Windows-Kernel-General", "2026-10-05T00:01:48.0"),
    _event(7001, "Microsoft-Windows-Winlogon", "2026-10-05T00:02:04.0"),
])


def test_the_power_button_is_named_and_said_as_a_power_off():
    (r,) = wr.restarts_from_events(wr.parse_events_xml(POWER_BUTTON_MORNING))
    assert (r.cause, r.label) == ("power_button", "the PC's power button")
    assert r.process == "winlogon.exe" and r.reason_code == "0x500ff" and r.shutdown_type == "power_off"
    assert r.windows_reason == NO_TITLE
    phrase = rr.restart_phrase(r, now=r.boot_ts + 600)
    assert phrase.startswith("This PC was powered off with its power button at ")
    assert "Start menu" not in phrase and "restarted" not in phrase
    why = rr.explain(rr.IbcLogin(ts=r.boot_ts + 300, full_auth=True), [r], now=r.boot_ts + 600)
    assert why["reason"] == "pc_restarted" and why["restart"]["cause"] == "power_button"
    assert why["text"].endswith("Powering the PC off ends IB Gateway's saved login, so IBKR needs your phone again.")


def test_the_second_power_button_morning_reads_the_same():
    xml = "".join([
        _recorded_1074("2026-10-06T11:16:00.3628754", SYSTEM[0], WINLOGON, NO_TITLE, "0x500ff", "power off",
                       SYSTEM[1]),
        _event(12, "Microsoft-Windows-Kernel-General", "2026-10-06T11:18:56.0"),
    ])
    (r,) = wr.restarts_from_events(wr.parse_events_xml(xml))
    assert r.cause == "power_button" and r.initiated_ts == _ts("2026-10-06T11:16:00.362875")


def test_a_start_menu_power_off_says_powered_off_not_restarted():
    (r,) = wr.restarts_from_events(wr.parse_events_xml(START_MENU_EVENING))
    assert (r.cause, r.shutdown_type, r.reason_code) == ("start_menu", "power_off", "0x0")
    assert rr.restart_phrase(r, now=r.boot_ts + 600).startswith("This PC was powered off from the Start menu at ")


def test_winlogon_on_behalf_of_a_user_stays_the_start_menu():
    xml = _recorded_1074("2026-09-22T17:20:32.0", OPERATOR[0], WINLOGON, "Other (Unplanned)", "0x0", "restart",
                         OPERATOR[1]) + _event(12, "Microsoft-Windows-Kernel-General", "2026-09-22T17:20:40.0")
    (r,) = wr.restarts_from_events(wr.parse_events_xml(xml))
    assert (r.cause, r.shutdown_type) == ("start_menu", "restart")
    assert rr.restart_phrase(r, now=r.boot_ts + 60).startswith("This PC was restarted from the Start menu at ")


def test_winlogon_for_system_that_restarts_is_not_the_power_button():
    # Recorded 2026-09-12 15:21 ET: the power-button signature, but Shutdown
    # Type restart -- a power button only powers off, so Nova names winlogon.
    xml = _recorded_1074("2026-09-12T19:21:43.2956091", SYSTEM[0], WINLOGON, NO_TITLE, "0x500ff", "restart",
                         SYSTEM[1]) + _event(12, "Microsoft-Windows-Kernel-General", "2026-09-12T19:22:30.0")
    (r,) = wr.restarts_from_events(wr.parse_events_xml(xml))
    assert r.cause == "app" and r.shutdown_type == "restart"
    phrase = rr.restart_phrase(r, now=r.boot_ts + 60)
    assert phrase.startswith("Windows' sign-in process (winlogon.exe), with no user named restarted this PC at ")
    assert "power button" not in phrase and "Start menu" not in phrase


def test_system_is_read_from_the_account_name_when_the_sid_is_missing():
    xml = _planned("2026-10-05T10:45:27.48", "winlogon.exe", NO_TITLE).replace(
        "<Data Name='param5'>restart</Data>",
        "<Data Name='param4'>0x500ff</Data><Data Name='param5'>power off</Data>"
        "<Data Name='param7'>NT AUTHORITY\\SYSTEM</Data>",
    ) + _event(12, "Microsoft-Windows-Kernel-General", "2026-10-05T10:47:26.0")
    (r,) = wr.restarts_from_events(wr.parse_events_xml(xml))
    assert r.cause == "power_button"


def test_a_shutdown_type_nova_cannot_read_is_unknown_and_says_restarted():
    xml = _recorded_1074("2026-10-05T10:45:27.48", SYSTEM[0], WINLOGON, NO_TITLE, "0x500ff", "Ausschalten",
                         SYSTEM[1]) + _event(12, "Microsoft-Windows-Kernel-General", "2026-10-05T10:47:26.0")
    (r,) = wr.restarts_from_events(wr.parse_events_xml(xml))
    assert r.shutdown_type is None and r.cause == "app"
    assert " restarted this PC at " in rr.restart_phrase(r, now=r.boot_ts + 60)


def test_the_query_asks_each_event_of_its_own_provider_only(monkeypatch):
    seen = {}

    def fake_run(args, **kw):
        seen["query"] = next(a for a in args if a.startswith("/q:"))
        return type("Done", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(wr.sys, "platform", "win32")
    monkeypatch.setattr(wr.subprocess, "run", fake_run)
    assert wr._query_events(8) == ""
    assert "(EventID=12 and Provider[@Name='Microsoft-Windows-Kernel-General'])" in seen["query"]
    assert "(EventID=1074 and Provider[@Name='User32'])" in seen["query"]
    assert "(EventID=6008 and Provider[@Name='EventLog'])" in seen["query"]
    assert "(EventID=7001 and Provider[@Name='Microsoft-Windows-Winlogon'])" in seen["query"]


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
