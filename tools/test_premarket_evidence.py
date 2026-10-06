"""#742: missing quiet-week evidence must never become a successful verdict.

All files are temporary; Windows queries are replaced with already-read facts.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import premarket_verify as pv  # noqa: E402


def _ts(text):
    return time.mktime(datetime.strptime(text, "%Y-%m-%d %H:%M:%S").timetuple())


NOW = _ts("2026-09-23 10:00:00")
PASS = "2026-09-22 03:55:01 [PASS] RESULT PASS\n"


@pytest.fixture
def logs(tmp_path, monkeypatch):
    nova, ibc = tmp_path / "logs", tmp_path / "ibc"
    nova.mkdir()
    ibc.mkdir()
    (nova / "morning-check.log").write_text(PASS, encoding="utf-8")
    # Dated retained observations before the requested start and throughout
    # every completed date; only ONE morning check is required for its criterion.
    (nova / "daily-start.log").write_text(
        "".join(f"2026-09-{day:02} 03:40:00 [INFO] Gateway API port already listening -- skip launch\n"
                for day in range(15, 23)), encoding="utf-8")
    (ibc / "IBC-quiet.txt").write_text(
        "".join(f"autorestart file found\n2026-09-{day:02} 23:45:00:100 IBC: saved login\n"
                for day in range(15, 23)), encoding="utf-8")
    monkeypatch.setattr(pv.time, "time", lambda: NOW)
    monkeypatch.setattr(pv, "windows_supported", lambda: True, raising=False)
    monkeypatch.setattr(pv.windows_restarts, "recent_restarts", lambda _days: [])
    return nova, ibc


def _cli(logs, capsys, *extra):
    nova, ibc = logs
    code = pv.main(["--log-dir", str(nova), "--ibc-log-dir", str(ibc), "--json", *extra])
    return code, json.loads(capsys.readouterr().out)


def _deny_read(monkeypatch, denied):
    original = Path.read_text

    def read(path, *args, **kwargs):
        if path == denied:
            raise PermissionError("test: permission denied")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)


def test_bare_empty_facts_do_not_prove_a_quiet_week():
    ev = pv.build_evidence(runs=pv.parse_morning_runs(PASS), ibc_logins=[], launches=[],
                           restarts=[], days=7, now=NOW)
    assert ev["criteria"]["unattended_pass"]["met"] is True
    assert ev["met"] is False
    assert ev["criteria"]["no_unexpected_logins"]["known"] is False


def test_observed_quiet_week_accepts_one_pass_despite_missed_mornings(logs, capsys):
    code, ev = _cli(logs, capsys)
    assert code == 0 and ev["met"] is True
    assert len(ev["missed_mornings"]) == 4
    assert ev["criteria"]["no_unexpected_logins"] == {"met": True, "count": 0, "known": True}
    assert ev["evidence_sources"]["windows_restarts"]["status"] == "readable"
    assert ev["restarts"] == []
    assert ev["login_evidence"]["complete"] is True


@pytest.mark.parametrize("source", ["daily_start", "ibc"])
def test_readable_empty_login_file_has_no_window_history(logs, capsys, source):
    path = logs[0] / "daily-start.log" if source == "daily_start" else logs[1] / "IBC-quiet.txt"
    path.write_text("", encoding="utf-8")
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["met"] is False
    assert ev["evidence_sources"][source]["status"] == "readable"
    assert ev["evidence_sources"][source]["first_ts"] is None
    assert "dated observations" in pv.render_text(ev)


def test_missing_ibc_directory_is_unknown_not_quiet(logs, capsys):
    (logs[1] / "IBC-quiet.txt").unlink()
    logs[1].rmdir()
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["met"] is False
    assert ev["evidence_sources"]["ibc"]["status"] == "missing"
    assert "quiet week not verified" in pv.render_text(ev)


def test_missing_daily_file_preserves_missing_status(logs, capsys):
    (logs[0] / "daily-start.log").unlink()
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["evidence_sources"]["daily_start"]["status"] == "missing"


def test_unreadable_daily_file_preserves_error(logs, capsys, monkeypatch):
    _deny_read(monkeypatch, logs[0] / "daily-start.log")
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["evidence_sources"]["daily_start"]["status"] == "unreadable"
    assert "permission denied" in pv.render_text(ev)


def test_invalid_bytes_are_unreadable_evidence_not_replacement_text(logs, capsys):
    (logs[0] / "daily-start.log").write_bytes(b"\xff")
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["evidence_sources"]["daily_start"]["status"] == "unreadable"


def test_an_undated_daily_gateway_launch_cannot_hide_behind_other_valid_dates(logs, capsys):
    with (logs[0] / "daily-start.log").open("a", encoding="utf-8") as file:
        file.write("2026-09-99 12:00:00 [INFO] Starting IB Gateway via IBC (test launcher)\n")
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["evidence_sources"]["daily_start"]["status"] == "partial"


def test_text_report_names_the_requested_window_and_read_time(logs, capsys):
    _, ev = _cli(logs, capsys)
    text = pv.render_text(ev)
    assert "Requested proof window: 2026-09-16 10:00:00 to 2026-09-23 10:00:00" in text
    assert "read at 2026-09-23 10:00:00" in text


def test_unreadable_ibc_directory_is_not_a_readable_empty_collection(logs, capsys, monkeypatch):
    original = Path.iterdir

    def listing(path):
        if path == logs[1]:
            raise PermissionError("test: directory permission denied")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", listing)
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["evidence_sources"]["ibc"]["status"] == "unreadable"


def test_one_failed_ibc_file_keeps_partial_source_open(logs, capsys, monkeypatch):
    broken = logs[1] / "IBC-unreadable.txt"
    broken.write_text("a file whose read fails", encoding="utf-8")
    _deny_read(monkeypatch, broken)
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["evidence_sources"]["ibc"]["status"] == "partial"
    assert "IBC-unreadable.txt" in pv.render_text(ev)


def test_ibc_file_disappearing_during_read_preserves_missing_status(logs, capsys, monkeypatch):
    path = logs[1] / "IBC-quiet.txt"
    original = Path.read_text

    def vanished(file, *args, **kwargs):
        if file == path:
            raise FileNotFoundError("test: file disappeared after directory listing")
        return original(file, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", vanished)
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["evidence_sources"]["ibc"]["status"] == "missing"


def test_old_boundary_timestamp_alone_does_not_establish_coverage(logs, capsys):
    (logs[0] / "daily-start.log").write_text(
        "2026-09-15 03:40:00 [INFO] old observation\n"
        "2026-09-22 03:40:00 [INFO] recent observation\n", encoding="utf-8")
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["login_evidence"]["complete"] is False
    assert "2026-09-17" in pv.render_text(ev)


def test_short_retained_history_cannot_certify_requested_week(logs, capsys):
    (logs[1] / "IBC-quiet.txt").write_text(
        "autorestart file found\n2026-09-22 23:45:00:100 IBC: saved login\n", encoding="utf-8")
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["criteria"]["no_unexpected_logins"]["known"] is False
    assert "window start" in pv.render_text(ev)


def test_undated_gateway_authentication_cannot_be_assumed_outside_window(logs, capsys):
    with (logs[1] / "IBC-quiet.txt").open("a", encoding="utf-8") as file:
        file.write("autorestart file not found\n")
    code, ev = _cli(logs, capsys)
    assert code == 1 and "undated Gateway start" in pv.render_text(ev)


@pytest.mark.parametrize("banner", [
    "Starting IBC version 3.24.1 on Tue 09/22/2026 at 12:",
    "Starting IBC version 3.24.1",
    "Starting IBC version 3.24.1 on Tue 09/99/2026 at 12:00:00.25",
])
def test_malformed_ibc_start_cannot_reuse_an_older_out_of_window_banner(logs, capsys, banner):
    (logs[1] / "IBC-quiet.txt").write_text(
        "Starting IBC version 3.24.1 on Sun 09/13/2026 at 12:00:00.25\n"
        "autorestart file found\n2026-09-13 12:00:00:100 IBC: saved login\n"
        + "".join(f"2026-09-{day:02} 23:45:00:100 IBC: saved login\n"
                  for day in range(15, 23))
        + banner + "\nautorestart file not found: full authentication will be required\n",
        encoding="utf-8")
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["met"] is False
    assert ev["evidence_sources"]["ibc"]["status"] == "partial"
    assert ev["criteria"]["no_unexpected_logins"]["known"] is False
    text = pv.render_text(ev)
    assert "malformed IBC startup banner" in text and "quiet week not verified" in text


@pytest.mark.parametrize("banner", [
    "Starting IBC version 3.24.1 on Tue 09/22/2026 at 12:00:00.25",
    "Starting IBC version 3.24.1 on Tue 9/22/2026 at  9:23:06.25",
])
def test_valid_ibc_start_banner_keeps_observed_quiet_week_known(logs, capsys, banner):
    with (logs[1] / "IBC-quiet.txt").open("a", encoding="utf-8") as file:
        file.write(banner + "\nautorestart file found\n")
    code, ev = _cli(logs, capsys)
    assert code == 0 and ev["met"] is True
    assert ev["evidence_sources"]["ibc"]["status"] == "readable"


@pytest.mark.parametrize("later_records", [
    "autorestart file not found\n",
    "autorestart file not found\nautorestart file not found\n",
    "autorestart file found\n",
    "Starting IBC version 3.24.1 on Sun 09/13/2026 at 12:00:00.25\n"
    "autorestart file not found\nautorestart file not found\n",
    "Starting IBC version 3.24.1 on Tue 09/22/2026 at 12:00:00.25\n"
    "autorestart file not found\n"
    "Starting IBC version 3.24.1 on Sun 09/13/2026 at 12:00:00.25\n",
])
def test_later_undated_auth_cannot_borrow_consumed_or_other_startup_banner(logs, capsys, later_records):
    (logs[1] / "IBC-quiet.txt").write_text(
        "Starting IBC version 3.24.1 on Sun 09/13/2026 at 12:00:00.25\n"
        "autorestart file found\n2026-09-13 12:00:00:100 IBC: saved login\n"
        + "".join(f"2026-09-{day:02} 23:45:00:100 IBC: saved login\n"
                  for day in range(15, 23))
        + later_records, encoding="utf-8")
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["met"] is False
    assert ev["evidence_sources"]["ibc"]["status"] == "partial"
    assert ev["criteria"]["no_unexpected_logins"]["known"] is False
    assert "authentication record" in pv.render_text(ev)


def test_a_fresh_weekend_banner_can_date_its_first_full_auth_record(logs, capsys):
    with (logs[1] / "IBC-quiet.txt").open("a", encoding="utf-8") as file:
        file.write("Starting IBC version 3.24.1 on Sat 09/19/2026 at 12:00:00.25\n"
                   "autorestart file not found\n")
    code, ev = _cli(logs, capsys)
    assert code == 0 and ev["met"] is True
    assert ev["evidence_sources"]["ibc"]["status"] == "readable"
    assert len(ev["full_logins"]) == 1 and ev["full_logins"][0]["expected"] is True


@pytest.mark.parametrize("full_auth", [False, True])
def test_later_auth_with_its_own_dated_line_remains_known(logs, capsys, full_auth):
    with (logs[1] / "IBC-quiet.txt").open("a", encoding="utf-8") as file:
        file.write("Starting IBC version 3.24.1 on Sun 09/13/2026 at 12:00:00.25\n"
                   "autorestart file found\n2026-09-13 12:00:00:100 IBC: saved login\n"
                   + ("autorestart file not found\n" if full_auth else "autorestart file found\n")
                   + "2026-09-22 12:00:00:100 IBC: authentication complete\n")
    code, ev = _cli(logs, capsys)
    assert code == int(full_auth)
    assert ev["evidence_sources"]["ibc"]["status"] == "readable"
    assert ev["criteria"]["no_unexpected_logins"]["known"] is True
    assert ev["criteria"]["no_unexpected_logins"]["count"] == int(full_auth)


def test_cross_start_rejected_auth_does_not_claim_a_weekday_failure(logs, capsys):
    with (logs[1] / "IBC-quiet.txt").open("a", encoding="utf-8") as file:
        file.write("Starting IBC version 3.24.1 on Sat 09/19/2026 at 12:00:00.25\n"
                   "autorestart file not found\n"
                   "Starting IBC version 3.24.1 on Tue 09/22/2026 at 12:00:00.25\n")
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["evidence_sources"]["ibc"]["status"] == "partial"
    assert ev["full_logins"] == []
    assert ev["criteria"]["no_unexpected_logins"] == {"met": False, "count": 0, "known": False}
    assert "quiet week not verified" in pv.render_text(ev)


@pytest.mark.parametrize("dated_first", [False, True])
def test_genuine_dated_login_still_counts_alongside_rejected_auth(logs, capsys, dated_first):
    dated = "autorestart file not found\n2026-09-22 12:00:00:100 IBC: fresh login\n"
    rejected = ("Starting IBC version 3.24.1 on Sat 09/19/2026 at 12:00:00.25\n"
                "autorestart file not found\n"
                "Starting IBC version 3.24.1 on Tue 09/22/2026 at 12:00:00.25\n")
    with (logs[1] / "IBC-quiet.txt").open("a", encoding="utf-8") as file:
        file.write(dated + rejected if dated_first else rejected + dated)
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["evidence_sources"]["ibc"]["status"] == "partial"
    assert ev["criteria"]["no_unexpected_logins"] == {"met": False, "count": 1, "known": True}
    assert len(ev["full_logins"]) == 1 and ev["full_logins"][0]["ts"] == _ts("2026-09-22 12:00:00")


def test_unused_old_banner_expires_when_dated_history_moves_to_another_date(logs, capsys):
    path = logs[1] / "IBC-quiet.txt"
    path.write_text("Starting IBC version 3.24.1 on Sun 09/13/2026 at 12:00:00.25\n"
                    + "".join(f"2026-09-{day:02} 23:45:00:100 IBC: saved login\n"
                              for day in range(15, 23))
                    + "autorestart file not found\n", encoding="utf-8")
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["evidence_sources"]["ibc"]["status"] == "partial"
    assert ev["full_logins"] == [] and ev["criteria"]["no_unexpected_logins"]["known"] is False


def test_first_auth_can_use_its_banner_after_other_same_date_ibc_lines(logs, capsys):
    with (logs[1] / "IBC-quiet.txt").open("a", encoding="utf-8") as file:
        file.write("Starting IBC version 3.24.1 on Sat 09/19/2026 at 12:00:00.25\n"
                   "2026-09-19 12:00:01:100 IBC: startup configuration\n"
                   "autorestart file not found\n")
    code, ev = _cli(logs, capsys)
    assert code == 0 and ev["evidence_sources"]["ibc"]["status"] == "readable"
    assert len(ev["full_logins"]) == 1 and ev["full_logins"][0]["expected"] is True


@pytest.mark.parametrize("later_records", [
    "Starting IBC version 3.24.1 on Tue 09/22/2026 at 12:00:00.25\n",
    "Starting IBC version 3.24.1 on Tue 09/22/2026 at 12:00:00.25\n"
    "Starting IBC version 3.24.1 on Tue 09/22/2026 at 13:00:00.25\n"
    "autorestart file found\n2026-09-22 13:00:01:100 IBC: saved login\n",
    "Starting IBC version 3.24.1 on Sun 09/13/2026 at 12:00:00.25\n"
    "2026-09-22 13:00:01:100 IBC: retained history\n",
])
def test_startup_without_authentication_outcome_cannot_prove_quiet_week(logs, capsys, later_records):
    with (logs[1] / "IBC-quiet.txt").open("a", encoding="utf-8") as file:
        file.write(later_records)
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["met"] is False
    assert ev["evidence_sources"]["ibc"]["status"] == "partial"
    assert ev["criteria"]["no_unexpected_logins"] == {"met": False, "count": 0, "known": False}
    assert ev["full_logins"] == []
    assert "startup has no authentication outcome" in pv.render_text(ev)


@pytest.mark.parametrize("dated_line", [
    "2026-09-19 12:00:01:100 IBC: full authentication complete\n",
    "2026-09-22 11:59:59:100 IBC: full authentication complete\n",
])
def test_authentication_timestamp_before_its_startup_is_unknown(logs, capsys, dated_line):
    with (logs[1] / "IBC-quiet.txt").open("a", encoding="utf-8") as file:
        file.write("Starting IBC version 3.24.1 on Tue 09/22/2026 at 12:00:00.25\n"
                   "autorestart file not found\n" + dated_line)
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["met"] is False
    assert ev["evidence_sources"]["ibc"]["status"] == "partial"
    assert ev["criteria"]["no_unexpected_logins"] == {"met": False, "count": 0, "known": False}
    assert ev["full_logins"] == []
    assert "predates its IBC startup banner" in pv.render_text(ev)


@pytest.mark.parametrize("second", ["00", "01"])
def test_valid_same_start_authentication_preserves_quiet_week(logs, capsys, second):
    with (logs[1] / "IBC-quiet.txt").open("a", encoding="utf-8") as file:
        file.write("Starting IBC version 3.24.1 on Sat 09/19/2026 at 12:00:00.25\n"
                   "autorestart file not found\n"
                   f"2026-09-19 12:00:{second}:100 IBC: full authentication complete\n")
    code, ev = _cli(logs, capsys)
    assert code == 0 and ev["met"] is True
    assert ev["evidence_sources"]["ibc"]["status"] == "readable"
    assert ev["criteria"]["no_unexpected_logins"] == {"met": True, "count": 0, "known": True}
    assert len(ev["full_logins"]) == 1 and ev["full_logins"][0]["expected"] is True


def test_real_unexpected_login_still_proves_failure(logs, capsys):
    with (logs[1] / "IBC-quiet.txt").open("a", encoding="utf-8") as file:
        file.write("autorestart file not found\n2026-09-22 12:00:00:100 IBC: fresh login\n")
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["criteria"]["no_unexpected_logins"] == {"met": False, "count": 1, "known": True}
    assert "UNEXPECTED" in pv.render_text(ev)


def test_unreadable_windows_query_keeps_valid_login_logs_unknown(logs, capsys, monkeypatch):
    monkeypatch.setattr(pv.windows_restarts, "recent_restarts", lambda _days: None)
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["evidence_sources"]["windows_restarts"]["status"] == "unreadable"
    text = pv.render_text(ev)
    assert "could not be read" in text and "quiet week not verified" in text


def test_non_windows_is_unsupported_and_never_queries_windows(logs, capsys, monkeypatch):
    monkeypatch.setattr(pv, "windows_supported", lambda: False)

    def forbidden_query(_days):
        pytest.fail("an unsupported platform must not query Windows")

    monkeypatch.setattr(pv.windows_restarts, "recent_restarts", forbidden_query)
    code, ev = _cli(logs, capsys)
    assert code == 1 and ev["evidence_sources"]["windows_restarts"]["status"] == "unsupported"
    assert ev["evidence_sources"]["windows_restarts"]["queried_since"] is None
    assert "unsupported on this platform" in pv.render_text(ev)


def test_a_short_requested_window_does_not_replace_the_week_criterion(logs, capsys):
    (logs[0] / "morning-check.log").write_text(PASS.replace("09-22", "09-23"), encoding="utf-8")
    code, ev = _cli(logs, capsys, "--days", "1")
    assert code == 1 and "at least 7 days" in pv.render_text(ev)
