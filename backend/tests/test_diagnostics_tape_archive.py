"""The tape archive row says when Paper resting orders cannot see their prints.

2026-09-24: the L2 tape writer latched at 07:29 ET and every resting Paper
order waited unfilled with nothing on the desk saying why; the only trace was
``/api/l2/status``. The row fails while a resting symbol's prints are not
reaching the archive, warns on a recent loss, and is otherwise quiet.
"""
from __future__ import annotations

from diagnostics import collect_tape_archive, gather as gather_mod

WRITING = {"error": None, "pending": 0, "written": 120, "dropped": 0, "losing": False, "losses": []}
RECEIVING = {"state": "receiving", "healthy": True, "sink_state": None, "last_write_ts": 1.0}
BLIND = {"state": "receiving", "healthy": False, "sink_state": "stale", "last_write_ts": None}
QUIET = {"state": "stale", "healthy": False, "sink_state": "stale", "last_write_ts": None}


def one(**kwargs):
    rows = collect_tape_archive.tape_archive_rows(**kwargs)
    assert len(rows) == 1 and rows[0]["id"] == "tape_archive" and rows[0]["group"] == "practice"
    return rows[0]


def test_a_resting_symbol_printing_with_nothing_archived_fails_and_names_it():
    latched = dict(WRITING, error="L2 tape backlog full since 07:29:41 ET: 1 print(s) lost; still losing prints")
    got = one(health={"writer": latched, "symbols": {"APUS": BLIND}}, resting=["APUS"])
    assert got["state"] == "fail"
    assert "APUS" in got["detail"] and "nothing archived" in got["detail"]
    assert "backlog full" in got["cause"]
    assert "Fill now" in got["fix"]


def test_a_writer_losing_prints_now_fails_while_an_order_rests():
    losing = dict(WRITING, losing=True, dropped=40,
                  error="L2 tape backlog full since 08:54:10 ET: 40 print(s) lost (APUS); still losing prints")
    got = one(health={"writer": losing, "symbols": {"APUS": RECEIVING}}, resting=["APUS"])
    assert got["state"] == "fail" and "can miss fills" in got["detail"]


def test_a_resting_symbol_with_no_archived_line_fails():
    got = one(health={"writer": WRITING, "symbols": {}}, resting=["apus"])
    assert got["state"] == "fail" and "APUS not archived" in got["detail"]


def test_a_recent_loss_that_ended_warns_and_says_prints_still_fill():
    ended = dict(WRITING, dropped=12,
                 error="L2 tape backlog full 07:29:41-07:29:44 ET: 12 print(s) lost (VRME); writing again")
    got = one(health={"writer": ended, "symbols": {"APUS": RECEIVING}}, resting=["APUS"])
    assert got["state"] == "warn" and "writing again" in got["detail"]
    assert "next print that crosses" in got["cause"]


def test_a_blind_symbol_without_a_resting_order_only_warns():
    got = one(health={"writer": WRITING, "symbols": {"PFSA": BLIND}}, resting=[])
    assert got["state"] == "warn" and "PFSA" in got["detail"]


def test_a_quiet_line_is_not_blind():
    got = one(health={"writer": WRITING, "symbols": {"APUS": QUIET}}, resting=["APUS"])
    assert got["state"] == "ok"


def test_nothing_archived_and_nothing_resting_is_off():
    assert one(health={"writer": WRITING, "symbols": {}}, resting=[])["state"] == "off"


def test_a_healthy_archive_is_ok_with_its_counts():
    got = one(health={"writer": WRITING, "symbols": {"APUS": RECEIVING}}, resting=["APUS"])
    assert got["state"] == "ok" and "APUS" in got["detail"] and "120 written" in got["detail"]


def test_the_checklist_carries_the_row():
    ids = {row["id"] for row in gather_mod.gather()["rows"]}
    assert "tape_archive" in ids
