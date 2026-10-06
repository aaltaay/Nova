"""Pure record-level proof: rejected timestamps never become observed logins."""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from premarket_ibc import parse_ibc_evidence  # noqa: E402


def _ts(text):
    return time.mktime(datetime.strptime(text, "%Y-%m-%d %H:%M:%S").timetuple())


def test_cross_start_unknown_record_and_genuine_dated_record_are_distinct():
    evidence = parse_ibc_evidence(
        "Starting IBC version 3.24.1 on Sat 09/19/2026 at 12:00:00.25\n"
        "autorestart file not found\n"
        "Starting IBC version 3.24.1 on Tue 09/22/2026 at 12:00:00.25\n"
        "autorestart file not found\n2026-09-22 12:00:01:100 IBC: fresh login\n")
    assert [(record.ts, record.full_auth) for record in evidence.logins] == [
        (None, True), (_ts("2026-09-22 12:00:01"), True)]
    assert "crosses another IBC startup" in " ".join(evidence.problems)
    assert _ts("2026-09-19 12:00:00") not in evidence.stamps


def test_saved_first_record_does_not_date_a_later_undated_full_auth():
    evidence = parse_ibc_evidence(
        "Starting IBC version 3.24.1 on Sat 09/19/2026 at 12:00:00.25\n"
        "autorestart file found\nautorestart file not found\n")
    assert [(record.ts, record.full_auth) for record in evidence.logins] == [
        (_ts("2026-09-19 12:00:00"), False), (None, True)]
    assert "no fresh banner" in " ".join(evidence.problems)


def test_a_separate_file_cannot_reuse_another_files_startup():
    first = parse_ibc_evidence(
        "Starting IBC version 3.24.1 on Sat 09/19/2026 at 12:00:00.25\n"
        "autorestart file found\n")
    second = parse_ibc_evidence("autorestart file not found\n")
    assert first.logins[0].ts == _ts("2026-09-19 12:00:00")
    assert second.logins[0].ts is None and second.stamps == ()
    assert second.problems
