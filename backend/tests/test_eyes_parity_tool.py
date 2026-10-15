"""``tools/eyes_parity.py`` (#966): the live eyes' triggers matched to a replay's, and the sums.

Lives with the backend tests because the tool runs the backend's own replay; only its pure parts are
tested here (the run itself needs the desk's journal and recordings).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "eyes_parity.py"
_spec = importlib.util.spec_from_file_location("eyes_parity", _TOOL)
eyes_parity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eyes_parity)

T0 = eyes_parity.PACE_CURVE_SINCE + 3600          # a day whose live code reads like today's


def _line(**kw) -> str:
    return json.dumps({"source": "live", **kw}, separators=(",", ":"))


def test_live_triggers_keep_recorded_symbols_their_grade_and_one_of_a_doubled_line():
    lines = [
        _line(event="armed", symbol="VEEA", setup_type="first_pullback", ts=T0 - 60, grade="B"),
        _line(event="triggered", symbol="VEEA", setup_type="first_pullback", ts=T0,
              setup={"trigger": 5.68}, tape={"verdict": "go"}),
        _line(event="triggered", symbol="VEEA", setup_type="first_pullback", ts=T0 + 0.2,
              setup={"trigger": 5.68}, tape={"verdict": "go"}),
        _line(event="triggered", symbol="NOREC", setup_type="first_pullback", ts=T0, setup={}, tape={}),
        json.dumps({"source": "sim", "event": "triggered", "symbol": "VEEA", "setup_type": "bull_flag", "ts": T0}),
    ]
    got = eyes_parity.live_triggers(lines, {"VEEA"})
    assert list(got) == ["VEEA"]
    assert got["VEEA"] == [{"ts": T0, "setup_type": "first_pullback", "trigger": 5.68, "tape": "go", "grade": "B"}]


def test_compare_takes_the_nearest_replay_trigger_of_the_same_setup():
    live = [{"ts": T0, "setup_type": "first_pullback", "trigger": 5.68, "tape": "go", "grade": "B"}]
    replays = [
        {"ts": T0 + 30, "setup_type": "first_pullback", "trigger": 5.70, "tape": "wait", "grade": "B"},
        {"ts": T0 + 1.5, "setup_type": "first_pullback", "trigger": 5.68, "tape": "go", "grade": "B"},
        {"ts": T0, "setup_type": "bull_flag", "trigger": 5.68, "tape": "go", "grade": "B"},
    ]
    (row,) = eyes_parity.compare("2026-10-14", "VEEA", live, replays, inside=lambda _ts: True)
    assert (row["dt"], row["replay_trigger"], row["replay_tape"]) == (1.5, 5.68, "go")


def test_a_live_trigger_the_replay_never_made_reads_unmatched():
    live = [{"ts": T0, "setup_type": "first_pullback", "trigger": 5.68, "tape": "go", "grade": "B"}]
    far = [{"ts": T0 + eyes_parity.MATCH_SEC + 1, "setup_type": "first_pullback", "trigger": 5.68,
            "tape": "go", "grade": "B"}]
    (row,) = eyes_parity.compare("2026-10-14", "VEEA", live, far, inside=lambda _ts: True)
    assert row["replay_at"] is None and row["dt"] is None


def test_summarize_judges_tape_only_where_the_trigger_lines_up_and_live_read_on_arrival():
    def row(ts, live_tape, replay_tape, *, level=5.68, dt=0.5, live_grade="B", replay_grade="B", inside=True):
        return {"inside": inside, "live_ts": ts, "replay_at": "x", "dt": dt, "live_trigger": 5.68,
                "replay_trigger": level, "live_tape": live_tape, "replay_tape": replay_tape,
                "live_grade": live_grade, "replay_grade": replay_grade}

    old = eyes_parity.READ_ON_ARRIVAL_SINCE - 86400
    rows = [
        row(T0, "go", "go"),                              # aligned, today's read: agrees
        row(T0, "go", "wait", level=5.69),                # another level: not judged on tape
        row(old, "wait", "go"),                           # aligned, but live read at the stamp then
        row(T0, "go", "go", inside=False),                # outside the recording: not counted
        row(old, "go", "go", live_grade="C", replay_grade="B"),
    ]
    s = eyes_parity.summarize(rows)
    assert (s["live_triggers_inside"], s["rebuilt"], s["aligned"]) == (4, 4, 3)
    assert (s["aligned_read_on_arrival"], s["aligned_read_on_arrival_same_tape"]) == (1, 1)
    assert (s["rebuilt_on_pace_curve"], s["rebuilt_on_pace_curve_same_grade"]) == (2, 2)
