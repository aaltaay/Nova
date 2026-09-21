"""The Record smoke tool's verdict: prints this run added, never cumulative counts (#315)."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "record_smoke", Path(__file__).resolve().parents[2] / "tools" / "record_smoke.py")
record_smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(record_smoke)


def run(start_counts, stop_counts, **start):
    return record_smoke.verdict(
        {"capture": True, **start, "recorder": {"counts": start_counts}},
        [{"healthy": True}],
        {"recorder": {"counts": stop_counts}},
    )


def test_counts_only_what_this_run_added():
    ok, notes = run({"prints": 500, "quotes": 10, "l2": 10}, {"prints": 540, "quotes": 16, "l2": 16})
    assert ok and notes[0].startswith("prints=40 quotes=6 l2=6")


def test_a_resumed_folder_with_no_new_prints_is_nothing_recorded():
    ok, _ = run({"prints": 500}, {"prints": 500})
    assert not ok


def test_prints_without_depth_says_so():
    ok, notes = run({"prints": 0}, {"prints": 12})
    assert ok and any("Prints only" in note for note in notes)


def test_a_refused_start_reports_the_reason():
    ok, notes = record_smoke.verdict({"capture": False, "error": "IBKR tape transport down"}, [], {})
    assert not ok and notes == ["Record refused: IBKR tape transport down"]
