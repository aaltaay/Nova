"""tools/data_root.py: the checkout's data moves to F: behind junctions, and a
half-finished move is finished or refused, never guessed (operator ask 2026-09-24).

The copy, the checks and the refusals run on every OS; the junction steps run
on Windows only. Targets are temp folders: no test touches F:.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data_root as dr  # noqa: E402

WINDOWS = pytest.mark.skipif(sys.platform != "win32", reason="directory junctions are Windows-only")
FILES = {
    "archive.db": "a" * 300,
    "backups/2026-09-24/archive.db": "b" * 200,
    "perf/stalls/1790258875786-http.json": "{}",
    "practice-paper.json": '{"schema_version": 1}',
}


def _tree(root: Path, files: dict[str, str] = FILES) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _marker(target: Path) -> dict:
    return json.loads((target / dr.MARKER).read_text(encoding="utf-8"))


def test_sync_copies_every_file_and_a_rerun_copies_nothing(tmp_path):
    src, dst = _tree(tmp_path / "cache"), tmp_path / "f_cache"
    (src / "sim_capture").mkdir()
    dst.mkdir()
    lines: list[str] = []
    dr.sync(src, dst, lines.append)
    assert dr.mismatches(dr.tree_files(src), dr.tree_files(dst)) == []
    assert (dst / "sim_capture").is_dir()                       # empty folders come along
    lines.clear()
    dr.sync(src, dst, lines.append)
    assert lines[0].startswith("  copying 0 of 4 files")


def test_a_file_gone_from_c_since_an_earlier_run_goes_from_the_copy(tmp_path):
    src, dst = _tree(tmp_path / "cache"), tmp_path / "f_cache"
    dst.mkdir()
    dr.sync(src, dst, lambda _line: None)
    (src / "perf/stalls/1790258875786-http.json").unlink()
    dr.sync(src, dst, lambda _line: None)
    assert not (dst / "perf/stalls/1790258875786-http.json").exists()


def test_a_changed_size_or_time_does_not_verify(tmp_path):
    src = {"a.db": (10, 1000.0), "b.db": (5, 1000.0)}
    assert dr.mismatches(src, {"a.db": (10, 1001.0), "b.db": (5, 1000.0)}) == []      # inside the slack
    assert dr.mismatches(src, {"a.db": (11, 1000.0), "b.db": (5, 1000.0)}) == ["a.db"]
    assert dr.mismatches(src, {"a.db": (10, 1100.0)}) == ["a.db", "b.db"]


def test_dry_run_changes_nothing(tmp_path):
    src, target = _tree(tmp_path / "cache"), tmp_path / "f_cache"
    said = dr.move_folder(src, target, dry_run=True, log=lambda _line: None)
    assert said.startswith("would move 4 files")
    assert not target.exists() and dr.tree_files(src).keys() == FILES.keys()


def test_a_target_holding_other_files_is_never_merged(tmp_path):
    src, target = _tree(tmp_path / "cache"), _tree(tmp_path / "f_cache", {"someone-else.txt": "x"})
    with pytest.raises(dr.MoveRefused, match="not a copy of"):
        dr.move_folder(src, target, dry_run=False, log=lambda _line: None)
    assert dr.tree_files(target).keys() == {"someone-else.txt"}


def test_c_is_never_copied_over_a_moved_folder(tmp_path):
    # F: became the data folder; then something recreated backend\.cache on C:.
    src, target = _tree(tmp_path / "cache", {"practice-paper.json": "{}"}), _tree(tmp_path / "f_cache")
    dr.write_marker(target, moved_from=str(src), state="moved", moved_at="2026-09-24T20:30:00")
    with pytest.raises(dr.MoveRefused, match="real folder again"):
        dr.move_folder(src, target, dry_run=False, log=lambda _line: None)
    assert dr.tree_files(target).keys() == FILES.keys()


def test_two_checkouts_never_share_one_data_folder(tmp_path):
    target = _tree(tmp_path / "f_cache")
    dr.write_marker(target, moved_from=str(tmp_path / "desk" / "cache"), state="moved")
    with pytest.raises(dr.MoveRefused, match="two checkouts never share"):
        dr.move_folder(tmp_path / "worktree" / "cache", target, dry_run=False, log=lambda _line: None)


def test_an_unknown_marker_version_is_refused(tmp_path):
    target = tmp_path / "f_cache"
    target.mkdir()
    (target / dr.MARKER).write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
    with pytest.raises(dr.MoveRefused, match="unknown schema_version"):
        dr.read_marker(target)


def test_move_refuses_while_nova_runs(monkeypatch, capsys):
    monkeypatch.setattr(dr, "desk_running", lambda _cache: ["the API answers on :8000"])
    assert dr.main(["move"]) == 3
    assert "stop Nova first" in capsys.readouterr().err


def test_status_names_each_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(dr, "desk_running", lambda _cache: [])
    _tree(tmp_path / "backend" / ".cache")
    report = dr.status(tmp_path)
    assert report["schema_version"] == 1 and report["desk_running"] == []
    cache, logs = report["folders"]
    assert (cache["id"], cache["kind"], cache["files"], cache["bytes"]) == ("cache", "folder", 4, sum(len(t) for t in FILES.values()))
    assert (logs["id"], logs["kind"], logs["files"]) == ("logs", "missing", None)


@WINDOWS
def test_move_leaves_a_junction_where_the_folder_was(tmp_path):
    src, target = _tree(tmp_path / "cache"), tmp_path / "f_cache"
    assert dr.move_folder(src, target, dry_run=False, log=lambda _line: None) == "moved to F:"
    assert os.path.isjunction(src)
    assert os.path.normcase(os.path.realpath(src)) == os.path.normcase(str(target))
    assert (src / "archive.db").read_text(encoding="utf-8") == FILES["archive.db"]     # read through the old path
    (src / "new.jsonl").write_text("{}", encoding="utf-8")
    assert (target / "new.jsonl").is_file()                                          # and written to F:
    assert not list(tmp_path.glob("cache" + dr.DATA_MOVED_SUFFIX + "*"))            # the C: original is gone
    assert _marker(target)["state"] == "moved" and _marker(target)["files"] == 4
    assert dr.move_folder(src, target, dry_run=False, log=lambda _line: None) == "already on F:"


@WINDOWS
def test_an_open_file_leaves_c_as_it_was_and_a_rerun_finishes(tmp_path):
    src, target = _tree(tmp_path / "cache"), tmp_path / "f_cache"
    with open(src / "archive.db", "rb"):
        with pytest.raises(dr.MoveRefused, match="still has a file open"):
            dr.move_folder(src, target, dry_run=False, log=lambda _line: None)
        assert src.is_dir() and not os.path.isjunction(src)
    assert dr.move_folder(src, target, dry_run=False, log=lambda _line: None) == "moved to F:"
    assert os.path.isjunction(src)


@WINDOWS
def test_a_move_cut_off_before_the_junction_is_finished_by_the_next_run(tmp_path):
    src, target = _tree(tmp_path / "cache"), tmp_path / "f_cache"
    target.mkdir()
    dr.write_marker(target, moved_from=str(src), state="copying")
    dr.sync(src, target, lambda _line: None)
    dr.write_marker(target, state="verified")
    src.rename(src.with_name("cache" + dr.DATA_MOVED_SUFFIX + "20260924-203000"))     # then the power went
    assert dr.move_folder(src, target, dry_run=False, log=lambda _line: None) == "moved to F:"
    assert os.path.isjunction(src) and (src / "practice-paper.json").is_file()
    assert not list(tmp_path.glob("cache" + dr.DATA_MOVED_SUFFIX + "*"))


@WINDOWS
def test_an_original_left_from_an_unverified_copy_is_kept(tmp_path):
    src, target = _tree(tmp_path / "cache"), tmp_path / "f_cache"
    target.mkdir()
    dr.write_marker(target, moved_from=str(src), state="copying")
    original = src.with_name("cache" + dr.DATA_MOVED_SUFFIX + "20260924-203000")
    src.rename(original)
    with pytest.raises(dr.MoveRefused, match="never verified"):
        dr.move_folder(src, target, dry_run=False, log=lambda _line: None)
    assert original.is_dir() and not src.exists()
