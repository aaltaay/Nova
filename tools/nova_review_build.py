#!/usr/bin/env python3
"""The review page's own build: built from the checkout's frontend source, rebuilt when that source changes.

The review engine serves a Vite build of ``frontend/`` at ``/review``. A build made before a pull serves an old
page. On 2026-10-24 the checkout's ``frontend/dist`` predated the review page itself, so the page at ``/review`` was
the desk, every ``nova_chart`` screenshot waited 25 s for ``data-review-ready`` and failed with
``REVIEW_SHOT_FAILED``. This module owns a separate folder, ``frontend/dist-review``, records which frontend source
each build came from, and builds again when the source differs. ``frontend/dist`` (the desktop pack's build) is
never written.

Layout: ``frontend/dist-review/current.json`` names the build in use; each build is its own folder
``frontend/dist-review/<id>/``. The previous build is kept, so a page that loaded before a rebuild still finds its
assets. Older builds are deleted.

    py -3 tools/nova_review_build.py            # build when stale, print the status
    py -3 tools/nova_review_build.py --check    # report only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
READY_MARK = b"data-review-ready"
BUILD_TIMEOUT_SEC = 300
CHECK_EVERY_SEC = 30.0
RETRY_FAILED_SEC = 300.0
KEEP_BUILDS = 2

_LOCK = threading.Lock()
_LAST: dict[str, Any] = {"state": "unchecked"}
_LAST_AT = 0.0
_FAILED: tuple[str, float] = ("", 0.0)      # (fingerprint, when) of the last build that failed

Builder = Callable[[Path, Path], tuple[bool, str]]


def frontend_dir() -> Path:
    return REPO / "frontend"


def build_root() -> Path:
    return frontend_dir() / "dist-review"


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.decode("utf-8", "replace") if out.returncode == 0 else None


def _mtime_fingerprint() -> str:
    newest = 0.0
    front = frontend_dir()
    for name in ("src", "public", "index.html", "vite.config.ts", "package.json", "package-lock.json"):
        path = front / name
        files = path.rglob("*") if path.is_dir() else [path]
        for item in files:
            try:
                newest = max(newest, item.stat().st_mtime)
            except OSError:
                continue
    return f"mtime:{newest:.0f}"


def source_fingerprint() -> str:
    """The committed frontend tree, plus the content of any uncommitted change under frontend/."""
    tree = (_git("rev-parse", "HEAD:frontend") or "").strip()
    if not tree:
        return _mtime_fingerprint()
    status = _git("status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "frontend")
    if status is None:
        return _mtime_fingerprint()
    own = build_root().relative_to(REPO).as_posix()          # the builds themselves are never source
    entries = []
    for item in status.split("\0"):
        rel = item[3:] if len(item) > 3 and item[2] == " " else item
        if rel and not rel.startswith(own):
            entries.append(rel)
    if not entries:
        return f"git:{tree}"
    digest = hashlib.sha256()
    for rel in sorted(entries):
        digest.update(rel.encode())
        path = REPO / rel
        if path.is_file():
            digest.update(path.read_bytes())
        else:
            digest.update(b"<gone>")
    return f"git:{tree}+{digest.hexdigest()[:16]}"


def build_id(fingerprint: str) -> str:
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:12]


def has_review_page(folder: Path) -> bool:
    """True when the folder is a built page whose bundle contains the review app."""
    if not (folder / "index.html").is_file():
        return False
    for script in (folder / "assets").glob("*.js"):
        try:
            if READY_MARK in script.read_bytes():
                return True
        except OSError:
            continue
    return False


def read_current() -> dict[str, Any] | None:
    path = build_root() / "current.json"
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(body, dict) or body.get("schema_version") != SCHEMA_VERSION:
        print(f"nova-review-build: ignoring {path.name} with schema_version "
              f"{body.get('schema_version') if isinstance(body, dict) else None}", file=sys.stderr)
        return None
    return body


def _write_current(body: dict[str, Any]) -> None:
    root = build_root()
    tmp = root / f"current.json.tmp-{os.getpid()}"
    tmp.write_text(json.dumps(body, indent=1), encoding="utf-8")
    os.replace(tmp, root / "current.json")


def vite_build(front: Path, out_dir: Path) -> tuple[bool, str]:
    """Run the checkout's own Vite into out_dir. Returns (ok, the last lines of its output)."""
    node = shutil.which("node")          # PATH only, as nova_chart_warm.py: no program path comes from the environment
    vite = front / "node_modules" / "vite" / "bin" / "vite.js"
    if not node:
        return False, "node is not on PATH"
    if not vite.is_file():
        return False, "frontend/node_modules is missing (run npm ci in frontend)"
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        done = subprocess.run(
            [node, str(vite), "build", "--outDir", str(out_dir), "--emptyOutDir", "--logLevel", "warn"],
            cwd=str(front), capture_output=True, timeout=BUILD_TIMEOUT_SEC, check=False, **kwargs,
        )
    except subprocess.TimeoutExpired:
        return False, f"vite build took more than {BUILD_TIMEOUT_SEC} s"
    except OSError as exc:
        return False, f"vite build did not start: {exc}"
    tail = (done.stdout + done.stderr).decode("utf-8", "replace")[-2000:]
    return done.returncode == 0, tail


def _prune(keep: list[str]) -> None:
    for item in build_root().iterdir():
        if item.is_dir() and item.name not in keep:
            shutil.rmtree(item, ignore_errors=True)


def _status(state: str, current: dict[str, Any] | None, detail: str = "", source: str = "dist-review") -> dict[str, Any]:
    out: dict[str, Any] = {"state": state, "source": source}
    if current:
        out.update({"build": current.get("build"), "built_at": current.get("built_at"),
                    "fingerprint": current.get("fingerprint")})
    if detail:
        out["detail"] = detail
    return out


def serving_dirs() -> list[Path]:
    """Folders to serve from, best first: the current build, the previous one, else a fallback with the review page."""
    override = os.environ.get("NOVA_REVIEW_DIST")
    if override:
        return [Path(override)]
    found: list[Path] = []
    current = read_current()
    if current:
        for key in ("build", "previous"):
            name = current.get(key)
            if isinstance(name, str) and name and (build_root() / name).is_dir():
                found.append(build_root() / name)
    if not found and has_review_page(frontend_dir() / "dist"):
        found.append(frontend_dir() / "dist")
    return found


def ensure_fresh(builder: Builder | None = None, max_age: float | None = None) -> dict[str, Any]:
    """Build the review page when the frontend source changed. Safe to call from many threads."""
    global _LAST, _LAST_AT, _FAILED
    if os.environ.get("NOVA_REVIEW_DIST"):
        return {"state": "override", "source": "NOVA_REVIEW_DIST"}
    age = CHECK_EVERY_SEC if max_age is None else max_age
    with _LOCK:
        if _LAST.get("state") == "fresh" and time.monotonic() - _LAST_AT < age:
            return dict(_LAST)
        fingerprint = source_fingerprint()
        current = read_current()
        wanted = build_id(fingerprint)
        if current and current.get("build") == wanted and has_review_page(build_root() / wanted):
            _LAST, _LAST_AT = _status("fresh", current), time.monotonic()
            return dict(_LAST)
        if _FAILED[0] == fingerprint and time.monotonic() - _FAILED[1] < RETRY_FAILED_SEC and max_age != 0:
            return dict(_LAST)                       # the same source failed a moment ago: do not rebuild per request
        build_root().mkdir(parents=True, exist_ok=True)
        tmp = build_root() / f"{wanted}.tmp-{os.getpid()}"
        shutil.rmtree(tmp, ignore_errors=True)
        ok, tail = (builder or vite_build)(frontend_dir(), tmp)
        (build_root() / "build.log").write_text(tail, encoding="utf-8")
        if ok and has_review_page(tmp):
            final = build_root() / wanted
            shutil.rmtree(final, ignore_errors=True)
            os.replace(tmp, final)
            body = {"schema_version": SCHEMA_VERSION, "build": wanted, "fingerprint": fingerprint,
                    "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "previous": (current or {}).get("build") if (current or {}).get("build") != wanted else None}
            _write_current(body)
            _prune([name for name in (body["build"], body["previous"]) if name][:KEEP_BUILDS])
            _LAST, _LAST_AT = _status("fresh", body), time.monotonic()
            return dict(_LAST)
        shutil.rmtree(tmp, ignore_errors=True)
        _FAILED = (fingerprint, time.monotonic())
        detail = "the build has no review page" if ok else (tail.strip().splitlines() or ["vite build failed"])[-1]
        usable = serving_dirs()
        state = "stale" if usable else "unavailable"
        source = "dist-review" if usable and usable[0].parent == build_root() else ("frontend/dist" if usable else "none")
        _LAST, _LAST_AT = _status(state, current, detail, source), time.monotonic()
        return dict(_LAST)


def last_status() -> dict[str, Any]:
    with _LOCK:
        return dict(_LAST)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the review page when the frontend source changed")
    parser.add_argument("--check", action="store_true", help="report only, never build")
    args = parser.parse_args(argv)
    if args.check:
        current = read_current()
        fresh = bool(current and current.get("build") == build_id(source_fingerprint())
                     and has_review_page(build_root() / str(current.get("build"))))
        result = _status("fresh" if fresh else "stale", current)
    else:
        result = ensure_fresh(max_age=0)
    print(json.dumps(result, indent=1))
    return 0 if result.get("state") in ("fresh", "override") else 1


if __name__ == "__main__":
    sys.exit(main())
