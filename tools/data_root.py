"""Put this checkout's data on F: -- backend\\.cache and backend\\logs (operator ask, 2026-09-24).

"we also have PLENTY of space in F drive, any recording and data, lets keep
them off the C drive!" The Session Records, downloads, leaderboard, catalysts
and eyes already default to F:. The desk's own folders did not:
``backend\\.cache`` (archive.db, the cold archive, nightly backups, l2.db, the
practice and execution ledgers, perf) and ``backend\\logs``.

``move`` copies each to ``F:\\Nova\\cache`` / ``F:\\Nova\\logs``, checks every
file arrived (size and modified time), renames the C: folder aside, puts a
directory junction at the old path, then removes the C: original. Every writer
-- the backend, the premarket scripts, Vite, research and tools -- keeps its
path and writes to F:. A junction whose drive is gone fails loudly; nothing
starts an empty store beside the real one. Only the checkout this runs from
moves: a worktree keeps its own ``backend\\.cache``, so an agent's engine never
shares the desk's ``api-instance.lock`` (which stops a holder it cannot see
listening on its own port).

Side effects (explicit, AGENTS.md invariant 2): ``move`` copies, renames,
creates junctions and deletes the C: originals once their F: copies are
verified. It refuses while Nova's API (:8000) or UI (:5173) answers. Rerun it
after any interruption: the marker ``.nova-data-root.json`` in the F: folder
and a ``<folder>.moved-<stamp>`` original say where the last run stopped.
``status`` is read-only.

    py -3 tools/data_root.py status [--json] [--repo PATH]
    py -3 tools/data_root.py move [--dry-run] [--repo PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
import time
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from constants_data_root import (  # noqa: E402
    DATA_CACHE_TARGET_WIN,
    DATA_LOGS_TARGET_WIN,
    DATA_MOVE_API_PORT,
    DATA_MOVE_MTIME_SLACK_SEC,
    DATA_MOVE_UI_PORT,
    DATA_MOVED_SUFFIX,
    DATA_ROOT_SCHEMA_VERSION,
)

MARKER = ".nova-data-root.json"
FOLDERS = (("cache", "backend/.cache", DATA_CACHE_TARGET_WIN), ("logs", "backend/logs", DATA_LOGS_TARGET_WIN))
Log = Callable[[str], None]


class MoveRefused(RuntimeError):
    """A state this tool will not guess its way through; the message says what to look at."""


# ── Reading a folder ─────────────────────────────────────────────────────────

def is_junction(path: Path) -> bool:
    return os.path.isjunction(path) or path.is_symlink()


def tree_files(root: Path) -> dict[str, tuple[int, float]]:
    """``{relative path: (size, mtime)}`` for every file under *root*, the marker left out."""
    out: dict[str, tuple[int, float]] = {}
    for base, dirs, files in os.walk(root):
        for name in dirs:
            if is_junction(Path(base) / name):
                raise MoveRefused(f"{Path(base) / name} is a link; move this folder by hand")
        for name in files:
            full = Path(base) / name
            rel = full.relative_to(root).as_posix()
            if rel == MARKER:
                continue
            st = full.stat()
            out[rel] = (st.st_size, st.st_mtime)
    return out


def mismatches(src: dict[str, tuple[int, float]], dst: dict[str, tuple[int, float]]) -> list[str]:
    """Files of *src* that *dst* lacks or holds at another size or modified time."""
    bad = []
    for rel, (size, mtime) in src.items():
        got = dst.get(rel)
        if got is None or got[0] != size or abs(got[1] - mtime) > DATA_MOVE_MTIME_SLACK_SEC:
            bad.append(rel)
    return bad


def read_marker(target: Path) -> dict[str, Any] | None:
    path = target / MARKER
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != DATA_ROOT_SCHEMA_VERSION:
        raise MoveRefused(f"{path} has an unknown schema_version; this tool will not guess what it means")
    return data


def write_marker(target: Path, **fields: Any) -> dict[str, Any]:
    data = {**(read_marker(target) or {}), **fields, "schema_version": DATA_ROOT_SCHEMA_VERSION}
    tmp = target / (MARKER + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, target / MARKER)
    return data


def _gb(n: int) -> str:
    return f"{n / 1024**3:.1f} GB" if n >= 1024**3 else f"{n / 1024**2:.0f} MB"


# ── Is Nova running? ─────────────────────────────────────────────────────────

def _listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def desk_running(cache: Path) -> list[str]:
    """What still holds these folders: the API, its lock's live process, the UI."""
    from api_instance_lock import pid_alive

    held = []
    if _listening(DATA_MOVE_API_PORT):
        held.append(f"the API answers on :{DATA_MOVE_API_PORT}")
    if _listening(DATA_MOVE_UI_PORT):
        held.append(f"the UI answers on :{DATA_MOVE_UI_PORT}")
    try:
        pid = int(json.loads((cache / "api-instance.lock").read_text(encoding="utf-8")).get("pid") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        pid = 0                                   # no lock, or a torn one: the ports above still decide
    if pid and pid_alive(pid):
        held.append(f"process {pid} holds {cache / 'api-instance.lock'}")
    return held


# ── Moving one folder ────────────────────────────────────────────────────────

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def sync(src: Path, target: Path, log: Log) -> dict[str, tuple[int, float]]:
    """Make *target* an exact copy of *src* (the marker kept). Resumes: an identical file is skipped."""
    src_files = tree_files(src)
    have = tree_files(target)
    todo = mismatches(src_files, have)
    total = sum(src_files[rel][0] for rel in todo)
    log(f"  copying {len(todo)} of {len(src_files)} files ({_gb(total)}) to {target}")
    started, done = time.monotonic(), 0
    for base, dirs, _files in os.walk(src):
        for name in dirs:
            (target / Path(base, name).relative_to(src)).mkdir(parents=True, exist_ok=True)
    for i, rel in enumerate(todo, 1):
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src_files[rel][0] >= 1024**3:
            log(f"    {rel} ({_gb(src_files[rel][0])})")
        shutil.copy2(src / rel, dst)
        done += src_files[rel][0]
        if i % 500 == 0 or i == len(todo):
            rate = done / max(time.monotonic() - started, 0.001)
            log(f"    {i}/{len(todo)} files, {_gb(done)} of {_gb(total)} ({_gb(int(rate))}/s)")
    for rel in sorted(set(have) - set(src_files)):
        (target / rel).unlink()                   # gone from C: since an earlier run; the copy follows
    return src_files


def _cleanup(original: Path, target: Path, log: Log) -> None:
    """Delete the C: original of a move whose F: copy was verified before the junction went in."""
    state = (read_marker(target) or {}).get("state")
    if state not in ("verified", "moved"):
        raise MoveRefused(f"{original} is left from a move that never verified {target}; look at both")
    log(f"  removing the C: original {original}")
    shutil.rmtree(original)


def move_folder(src: Path, target: Path, *, dry_run: bool, log: Log) -> str:
    """Move *src* to *target* behind a junction at *src*. Returns what happened."""
    originals = sorted(src.parent.glob(src.name + DATA_MOVED_SUFFIX + "*"))
    if is_junction(src):
        if os.path.normcase(os.path.realpath(src)) != os.path.normcase(os.path.realpath(target)):
            raise MoveRefused(f"{src} is already a link to {os.path.realpath(src)}, not {target}")
        if dry_run:
            return "already on F:" + (f"; would remove {len(originals)} C: original(s)" if originals else "")
        for original in originals:
            _cleanup(original, target, log)
        return "already on F:" + (f"; removed {len(originals)} C: original(s)" if originals else "")
    marker = read_marker(target) if target.exists() else None
    if src.exists() and originals:
        raise MoveRefused(f"both {src} and {originals[-1]} exist; something wrote {src} mid-move -- look at both")
    if src.exists() and (marker or {}).get("state") == "moved":
        raise MoveRefused(f"{target} became the data folder at {marker.get('moved_at')}, yet {src} is a real "
                          "folder again; something recreated it -- look at both before anything is copied")
    if src.exists():
        foreign = target.exists() and any(target.iterdir()) and os.path.normcase(
            str((marker or {}).get("moved_from") or "")) != os.path.normcase(str(src))
        if foreign:
            raise MoveRefused(f"{target} already holds files that are not a copy of {src}; this tool will not merge them")
        if dry_run:
            files = tree_files(src)
            return f"would move {len(files)} files ({_gb(sum(s for s, _ in files.values()))}) to {target}"
        target.mkdir(parents=True, exist_ok=True)
        write_marker(target, moved_from=str(src), state="copying", started_at=_now())
        src_files = sync(src, target, log)
        bad = mismatches(src_files, tree_files(target))
        if bad:
            raise MoveRefused(f"{len(bad)} files did not verify on {target} (first: {bad[0]}); C: is untouched")
        write_marker(target, state="verified", verified_at=_now(), files=len(src_files),
                     bytes=sum(s for s, _ in src_files.values()))
        original = src.with_name(src.name + DATA_MOVED_SUFFIX + time.strftime("%Y%m%d-%H%M%S"))
        try:
            src.rename(original)
        except OSError as exc:
            raise MoveRefused(f"cannot rename {src} ({exc}); a process still has a file open. "
                              "C: is untouched and still the data; rerun once it is closed") from exc
    elif originals:
        if dry_run:
            return f"would finish an interrupted move: junction {src} -> {target}"
        original = originals[-1]
        if (marker or {}).get("state") not in ("verified", "moved"):
            raise MoveRefused(f"{original} is left from a move that never verified {target}; look at both")
    else:
        if dry_run:
            return f"would create {target} and a junction to it at {src}"
        original = None
        if target.exists() and any(target.iterdir()) and marker is None:
            raise MoveRefused(f"{target} already holds files that this tool did not put there; look at it first")
        if marker and os.path.normcase(str(marker.get("moved_from") or "")) != os.path.normcase(str(src)):
            raise MoveRefused(f"{target} is the data of {marker.get('moved_from')}; two checkouts never share one "
                              "(they would share its api-instance.lock)")
        target.mkdir(parents=True, exist_ok=True)
        write_marker(target, moved_from=str(src), state="verified", verified_at=_now(), files=0, bytes=0)
    make_junction(src, target)
    if os.path.normcase(os.path.realpath(src)) != os.path.normcase(os.path.realpath(target)):
        raise MoveRefused(f"the junction at {src} does not resolve to {target}")
    write_marker(target, state="moved", moved_at=_now())
    log(f"  {src} -> {target} (junction)")
    if original is not None:
        _cleanup(original, target, log)
    return "moved to F:"


def make_junction(link: Path, target: Path) -> None:
    import _winapi

    _winapi.CreateJunction(str(target), str(link))


# ── Status and the command line ──────────────────────────────────────────────

def folder_status(repo: Path, fid: str, rel: str, target: str) -> dict[str, Any]:
    path = repo / rel
    real = Path(os.path.realpath(path))
    out: dict[str, Any] = {
        "id": fid, "path": str(path), "target": target, "real": str(real),
        "kind": "junction" if is_junction(path) else "folder" if path.is_dir() else "missing",
        "originals": [str(p) for p in sorted(path.parent.glob(path.name + DATA_MOVED_SUFFIX + "*"))],
        "files": None, "bytes": None, "error": None,
    }
    try:
        if real.is_dir():
            files = tree_files(real)
            out["files"], out["bytes"] = len(files), sum(s for s, _ in files.values())
    except (OSError, MoveRefused) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def status(repo: Path = REPO) -> dict[str, Any]:
    drive = Path(DATA_CACHE_TARGET_WIN).anchor
    try:
        free = shutil.disk_usage(drive).free if drive and Path(drive).exists() else None
    except OSError:
        free = None                               # stated as null: unknown, not "no room"
    return {
        "schema_version": DATA_ROOT_SCHEMA_VERSION,
        "repo": str(repo),
        "data_drive": {"root": drive, "mounted": bool(drive) and Path(drive).exists(), "free_bytes": free},
        "desk_running": desk_running(repo / "backend" / ".cache"),
        "folders": [folder_status(repo, *f) for f in FOLDERS],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Keep this checkout's data on F:.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status", help="where the data is now (read-only)")
    st.add_argument("--json", action="store_true")
    mv = sub.add_parser("move", help="move backend/.cache and backend/logs to F: behind junctions")
    mv.add_argument("--dry-run", action="store_true")
    for p in (st, mv):
        p.add_argument("--repo", type=Path, default=REPO, help="the checkout whose folders move (default: this one)")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()

    if args.cmd == "status":
        report = status(repo)
        if args.json:
            print(json.dumps(report, indent=2))
            return 0
        for f in report["folders"]:
            kind = {"junction": f"a junction to {f['real']}", "folder": "a folder on this drive",
                    "missing": "not there"}[f["kind"]]
            size = f"; {_gb(f['bytes'])} in {f['files']} files" if f["bytes"] is not None else ""
            print(f"{f['id']}: {f['path']} is {kind}{size}{'; ' + f['error'] if f['error'] else ''}")
            for original in f["originals"]:
                print(f"  C: original still here: {original}")
        drive = report["data_drive"]
        free = f", {_gb(drive['free_bytes'])} free" if drive["free_bytes"] is not None else ""
        print(f"data drive {drive['root'] or '(none)'}: {'mounted' if drive['mounted'] else 'not mounted'}{free}")
        print(f"desk running: {'; '.join(report['desk_running']) or 'no'}")
        return 0

    held = desk_running(repo / "backend" / ".cache")
    if held and not args.dry_run:
        print("data_root: stop Nova first (Stop Nova.bat): " + "; ".join(held), file=sys.stderr)
        return 3
    if sys.platform != "win32":
        print("data_root: junctions are a Windows feature; nothing to move here", file=sys.stderr)
        return 2
    if not Path(Path(DATA_CACHE_TARGET_WIN).anchor).exists():
        print(f"data_root: {Path(DATA_CACHE_TARGET_WIN).anchor} is not mounted", file=sys.stderr)
        return 2
    for fid, rel, target in FOLDERS:
        print(f"{fid}: {repo / rel}")
        try:
            print("  " + move_folder(repo / rel, Path(target), dry_run=args.dry_run, log=print))
        except MoveRefused as exc:
            print(f"data_root: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
