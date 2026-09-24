"""The ``data_folders`` row: which drive really holds each of Nova's data folders.

Operator ask 2026-09-24: "any recording and data, lets keep them off the C
drive". Judged on each folder's real path (junctions resolved): on C: while F:
is mounted warns with the fix, a folder whose drive is gone fails, a folder
that cannot be resolved is unknown with the reason.
"""
from __future__ import annotations

from diagnostics import collect_data_root, gather as gather_mod

DESK = r"C:\Users\op\github\Nova\backend"


def _folder(fid: str, real: str, *, path: str | None = None, env: str | None = None, error: str | None = None):
    return {"id": fid, "label": fid.title(), "path": path or real, "real": None if error else real,
            "env": env, "error": error}


def _row(folders, *, mounted: bool = True):
    [row] = collect_data_root.data_folder_rows(
        folders=folders, data_drive="F:", data_drive_mounted=mounted, system_drive="C:")
    assert row["id"] == "data_folders" and row["group"] == "process"
    return row


MOVED = [
    _folder("cache", r"F:\Nova\cache", path=DESK + r"\.cache"),
    _folder("logs", r"F:\Nova\logs", path=DESK + r"\logs"),
    _folder("captures", r"F:\Nova\sim_capture", env="NOVA_SIM_CAPTURE_DIR"),
    _folder("leaderboard", r"F:\Nova\leaderboard"),
]


def test_every_folder_on_f_is_ok():
    row = _row(MOVED)
    assert row["state"] == "ok" and row["detail"] == "All 4 data folders on F:"
    assert row["evidence"]["folders"][0]["path"] == DESK + r"\.cache"      # the junction and where it leads


def test_the_checkout_folders_still_on_c_warn_with_the_move():
    folders = [_folder("cache", DESK + r"\.cache"), _folder("logs", DESK + r"\logs"), *MOVED[2:]]
    row = _row(folders)
    assert row["state"] == "warn"
    assert row["detail"] == (f"On C: while F: is mounted: Cache ({DESK}\\.cache), Logs ({DESK}\\logs)")
    assert row["fix"] == "Stop Nova (Stop Nova.bat), run `py -3 tools/data_root.py move`, then start Nova."
    assert "stay off C:" in row["cause"]


def test_a_folder_an_env_var_puts_on_c_names_the_variable():
    folders = [*MOVED[:2], _folder("captures", r"C:\Users\op\AppData\Local\Nova\sim_capture", env="NOVA_SIM_CAPTURE_DIR")]
    row = _row(folders)
    assert row["state"] == "warn"
    assert row["fix"] == "Set NOVA_SIM_CAPTURE_DIR to a folder on F: in .env, then Reload backend."


def test_a_junction_whose_drive_is_gone_fails():
    row = _row(MOVED, mounted=False)
    assert row["state"] == "fail" and row["detail"].startswith("F: is not reachable: Cache (F:\\Nova\\cache)")


def test_a_folder_that_cannot_be_resolved_is_unknown_never_ok():
    row = _row([*MOVED, _folder("eyes", "", error="PermissionError: denied")])
    assert row["state"] == "unknown" and "Eyes (PermissionError: denied)" in row["detail"]


def test_without_an_f_drive_c_is_the_only_place():
    row = _row([_folder("cache", DESK + r"\.cache"), _folder("logs", "/srv/nova/backend/logs")], mounted=False)
    assert row["state"] == "ok" and row["detail"] == "All 2 data folders on C: (no F: drive on this PC)"


def test_the_shell_resolves_every_folder_without_creating_one(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path / "not-created-cache"))
    monkeypatch.setenv("NOVA_LOG_DIR", str(tmp_path / "not-created-logs"))
    inputs = gather_mod._data_folder_inputs()
    by_id = {f["id"]: f for f in inputs["folders"]}
    assert list(by_id) == ["cache", "logs", "captures", "downloads", "leaderboard", "catalysts", "eyes"]
    assert all(f["error"] is None and f["real"] for f in by_id.values())
    assert by_id["cache"]["env"] == "NOVA_CACHE_DIR"
    assert not (tmp_path / "not-created-cache").exists() and not (tmp_path / "not-created-logs").exists()
    row = {r["id"]: r for r in gather_mod.gather()["rows"]}["data_folders"]
    assert row["state"] in ("ok", "warn") and len(row["evidence"]["folders"]) == 7
