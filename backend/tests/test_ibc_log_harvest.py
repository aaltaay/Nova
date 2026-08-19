from __future__ import annotations

from ibkr.ibc_log_harvest import parse_ibc_log_events, record_recent_ibc_into_trail


SAMPLE = """
2026-08-19 15:43:43:372 IBC: Setting Trading mode = live
2026-08-19 15:43:44:000 IBC: Setting user name
2026-08-19 15:43:44:001 IBC: Setting password
2026-08-19 15:43:44:002 IBC: Click button: Log In
2026-08-19 15:43:45:000 IBC: detected frame entitled: Authenticating...; event=Opened
2026-08-19 15:43:47:983 IBC: Login has completed
2026-08-19 15:43:47:999 IBC: detected dialog entitled: DUQ266899 Trader Workstation Configuration (Simulated Trading); event=Opened
"""


def test_parse_ibc_log_records_auto_login_and_simulated_not_password():
    ev = parse_ibc_log_events(SAMPLE)
    kinds = [e["event"] for e in ev]
    assert "ibc_trading_mode" in kinds
    assert "ibc_clicked_login" in kinds
    assert "ibc_authenticating" in kinds
    assert "ibc_login_completed" in kinds
    assert "ibc_simulated_trading" in kinds
    blob = " ".join(e.get("note") or "" for e in ev)
    assert "password" not in blob.lower()
    assert "DUQ266899" not in blob
    assert "Simulated Trading" in blob


def test_harvest_only_suffix_after_origin(tmp_path, monkeypatch):
    log = tmp_path / "IBC-x.txt"
    old = "IBC: Setting Trading mode = live\nIBC: Click button: Log In\n"
    log.write_text(old, encoding="utf-8")
    origin = log.stat().st_size
    log.write_text(old + "IBC: Setting Trading mode = paper\n", encoding="utf-8")
    events: list[dict] = []
    monkeypatch.setattr(
        "ibkr.ibc_log_harvest.append_event",
        lambda **kwargs: events.append(kwargs),
    )
    n = record_recent_ibc_into_trail(
        requested="paper", log_dir=tmp_path, origin_size=origin,
    )
    assert n == 1
    assert events[0]["event"] == "ibc_trading_mode"
    assert "paper" in (events[0].get("note") or "").lower()
