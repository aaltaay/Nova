from __future__ import annotations

from datetime import datetime

from ibkr import second_factor as sf

FRESH_PROMPT = """
2026-08-25 20:37:04:054 IBC: Click button: Log In
2026-08-25 20:37:04:554 IBC: Second Factor Authentication initiated
"""

STALE_PROMPT = """
2026-08-25 03:40:10:234 IBC: Click button: Log In
2026-08-25 03:40:11:154 IBC: Second Factor Authentication initiated
"""

COMPLETED_THEN_NEW_STALE = """
2026-08-20 03:40:08:334 IBC: Second Factor Authentication initiated
2026-08-20 03:49:47:998 IBC: Second Factor Authentication initiated
"""

LOGGED_IN = """
2026-08-19 19:09:32:241 IBC: Second Factor Authentication initiated
2026-08-19 19:09:49:803 IBC: Login has completed
"""

NO_PROMPT_YET = """
2026-08-25 20:30:36:145 IBC: Starting session: will exit if login dialog is not displayed within 60 seconds
"""


def test_no_second_factor_line_is_empty():
    state = sf.parse_second_factor_state(NO_PROMPT_YET)
    assert state.pending is False
    assert state.age_sec is None
    assert state.stale is False


def test_completed_login_clears_pending():
    state = sf.parse_second_factor_state(LOGGED_IN)
    assert state.pending is False
    assert state.stale is False


def test_fresh_prompt_is_pending_not_stale():
    now = datetime(2026, 8, 25, 20, 38, 0)  # 56s after 20:37:04
    state = sf.parse_second_factor_state(FRESH_PROMPT, now=now)
    assert state.pending is True
    assert state.stale is False
    assert 55.0 <= state.age_sec <= 57.0


def test_stale_prompt_past_ibc_timeout():
    now = datetime(2026, 8, 25, 3, 45, 0)  # ~289s after 03:40:11
    state = sf.parse_second_factor_state(STALE_PROMPT, now=now)
    assert state.pending is True
    assert state.stale is True
    assert state.age_sec > 180.0


def test_relogin_resets_age_to_newest_attempt():
    """A re-login (IBC's own timeout retry) overwrites the tracked prompt
    with the newer attempt's timestamp -- age is measured from attempt 2,
    not attempt 1."""
    now = datetime(2026, 8, 20, 3, 50, 0)  # 12s after the second attempt
    state = sf.parse_second_factor_state(COMPLETED_THEN_NEW_STALE, now=now)
    assert state.pending is True
    assert state.stale is False
    assert 10.0 <= state.age_sec <= 14.0


def test_current_state_empty_when_gateway_not_running(tmp_path):
    log = tmp_path / "IBC-x.txt"
    log.write_text(STALE_PROMPT, encoding="utf-8")
    state = sf.current_state(log_dir=tmp_path, gateway_process_running=False)
    assert state.pending is False


def test_current_state_reads_newest_log_when_running(tmp_path):
    log = tmp_path / "IBC-x.txt"
    log.write_text(FRESH_PROMPT, encoding="utf-8")
    now = datetime(2026, 8, 25, 20, 38, 0)
    state = sf.current_state(
        log_dir=tmp_path, now=now, gateway_process_running=True
    )
    assert state.pending is True
    assert state.stale is False


def test_current_state_no_log_dir_is_empty(tmp_path):
    missing = tmp_path / "does-not-exist"
    state = sf.current_state(log_dir=missing, gateway_process_running=True)
    assert state.pending is False


def _no_process_check():
    raise AssertionError("the Gateway process check must not run")


def test_no_open_prompt_never_starts_the_process_check(tmp_path, monkeypatch):
    """ADR 026: the check starts PowerShell and blocked the HTTP loop ~265 ms on
    every /api/ibkr/status poll; only an open prompt in the log needs it."""
    monkeypatch.setattr(sf, "_gateway_process_running", _no_process_check)
    (tmp_path / "IBC-x.txt").write_text("", encoding="utf-8")
    assert sf.current_state(log_dir=tmp_path).pending is False
    assert sf.current_state(log_dir=tmp_path / "missing").pending is False


def test_open_prompt_still_asks_whether_gateway_runs(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(sf, "_gateway_process_running", lambda: calls.append(1) or False)
    (tmp_path / "IBC-x.txt").write_text(FRESH_PROMPT, encoding="utf-8")
    assert sf.current_state(log_dir=tmp_path).pending is False
    assert calls == [1]
