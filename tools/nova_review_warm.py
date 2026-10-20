"""Chromium for review-page screenshots. Started on the first PNG call, then kept.

A machine without Playwright answers ``REVIEW_SHOT_UNAVAILABLE`` instead of a
made-up image. Each request carries an id so a reply that arrives after the
timeout is not given to the next caller. stderr goes to DEVNULL so a full pipe
cannot stall the browser.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
SHOT = Path(__file__).with_name("nova_review_shot.mjs")
NODE_CWD = REPO / "frontend"
RENDERER_STDERR = subprocess.DEVNULL
MAX_SHOTS = 24
MAX_SHOT_BYTES = 8 * 1024 * 1024


def matching_reply(get_line: Callable[[float], str], req_id: str, timeout: float) -> dict[str, Any] | None:
    """Read lines until one has ``req_id``, or the timeout. Other ids are skipped."""
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            line = get_line(remaining)
        except queue.Empty:
            return None
        try:
            body = json.loads(line)
        except json.JSONDecodeError:
            continue
        if body.get("id") == req_id:
            return body


def _dir_prefix(root: str) -> str:
    return root if root.endswith(os.sep) else root + os.sep


def rotate_shots(directory: Path, *, keep: int = MAX_SHOTS, max_bytes: int = MAX_SHOT_BYTES,
                 protect: set[Path] | None = None) -> None:
    """Drop the oldest review PNGs once the folder is past the count or the byte cap.

    A path that disappears between the listing and the stat is skipped. ``protect``
    names files another request is about to return. Only a folder inside the system
    temp directory is scanned, and a file outside that folder is never removed.
    """
    temp_prefix = _dir_prefix(os.path.realpath(tempfile.gettempdir()))
    base = os.path.realpath(directory)
    if not base.startswith(temp_prefix):
        return
    prefix = _dir_prefix(base)
    held: set[str] = set()
    for path in protect or set():
        try:
            held.add(os.path.realpath(path))
        except OSError:
            continue
    ranked: list[tuple[float, int, str]] = []
    if base.startswith(temp_prefix):
        try:
            names = os.listdir(base)
        except OSError:
            names = []
        for name in names:
            if not (name.startswith("review-") and name.endswith(".png")):
                continue
            full = os.path.realpath(os.path.join(base, name))
            if full.startswith(prefix) and full not in held:
                path = Path(full)
                try:
                    info = path.stat()
                except OSError:
                    continue
                ranked.append((info.st_mtime, info.st_size, full))
    ranked.sort()
    total = sum(size for _mtime, size, _path in ranked)
    while ranked and (len(ranked) > keep or total > max_bytes):
        _mtime, size, old = ranked.pop(0)
        total -= size
        if old in held:
            continue
        if old.startswith(prefix):
            try:
                os.unlink(old)
            except OSError:
                continue


class ReviewShots:
    def __init__(self, shoot: Callable[[str, Path], dict[str, Any]] | None = None):
        self._shoot = shoot
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._lines: queue.Queue[str] = queue.Queue()
        self._error: dict[str, Any] | None = None
        self._started = False
        self._inflight: set[str] = set()

    def start(self) -> dict[str, Any]:
        if self._shoot is not None:
            self._started = True
            return {"ok": True, "ready": True, "mode": "injected"}
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return {"ok": True, "ready": True}
            self._error = None
            try:
                self._proc = subprocess.Popen(
                    ["node", str(SHOT)],
                    cwd=str(NODE_CWD),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=RENDERER_STDERR,
                    text=True,
                    bufsize=1,
                )
            except OSError as exc:
                self._error = {"ok": False, "error": {"code": "REVIEW_SHOT_UNAVAILABLE", "detail": str(exc)}}
                return self._error
            threading.Thread(target=self._read_stdout, name="nova-review-shot", daemon=True).start()
            self._started = True
        try:
            line = self._lines.get(timeout=45)
        except queue.Empty:
            self._error = {"ok": False, "error": {"code": "REVIEW_SHOT_UNAVAILABLE", "detail": "renderer did not answer"}}
            return self._error
        try:
            ready = json.loads(line)
        except json.JSONDecodeError:
            ready = {"ok": False}
        if not ready.get("ok"):
            code = ready.get("error") or "REVIEW_SHOT_UNAVAILABLE"
            self._error = {"ok": False, "error": {"code": code, "detail": ready.get("detail")}}
            return self._error
        return {"ok": True, "ready": True}

    def _read_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            self._lines.put(line.strip())

    def _get_line(self, timeout: float) -> str:
        return self._lines.get(timeout=timeout)

    def shoot(self, url: str, dest: Path) -> dict[str, Any]:
        if self._shoot is None and not self._started:
            started = self.start()
            if not started.get("ok"):
                return started
        with self._lock:
            return self._shoot_held(url, dest)

    def _shoot_held(self, url: str, dest: Path) -> dict[str, Any]:
        temp_prefix = _dir_prefix(os.path.realpath(tempfile.gettempdir()))
        base = os.path.realpath(dest.parent)
        full = os.path.realpath(os.path.join(base, os.path.basename(os.fspath(dest))))
        prefix = _dir_prefix(base)
        if base.startswith(temp_prefix) and full.startswith(prefix):
            os.makedirs(base, exist_ok=True)
            self._inflight.add(full)
            try:
                rotate_shots(Path(base), protect={Path(item) for item in self._inflight})
                if self._shoot is not None:
                    return self._shoot(url, Path(full))
                if self._error is not None:
                    return self._error
                proc = self._proc
                if proc is None or proc.poll() is not None or proc.stdin is None:
                    return {"ok": False, "error": {"code": "REVIEW_SHOT_UNAVAILABLE", "detail": "renderer is not running"}}
                req_id = uuid.uuid4().hex
                proc.stdin.write(json.dumps({"id": req_id, "url": url, "dest": full}) + "\n")
                proc.stdin.flush()
                body = matching_reply(self._get_line, req_id, 60)
                if body is None:
                    return {"ok": False, "error": {"code": "REVIEW_SHOT_FAILED", "detail": "screenshot timed out"}}
                if not body.get("ok"):
                    return {"ok": False, "error": {"code": body.get("error") or "REVIEW_SHOT_FAILED", "detail": body.get("detail")}}
                if full.startswith(prefix):
                    with open(full, "rb") as handle:
                        raw = handle.read()
                    return {"ok": True, "path": full, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "png": raw}
            finally:
                self._inflight.discard(full)
        return {"ok": False, "error": {"code": "REVIEW_SHOT_FAILED", "detail": "shot folder"}}

    def close(self) -> None:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.terminate()


def attach_images(answer: dict[str, Any], shots: ReviewShots, directory: Path) -> dict[str, Any]:
    """Fill ``images`` for png and both. A one-symbol call does not also shoot the gallery page."""
    if not answer.get("ok") or answer.get("output") == "interactive":
        return answer
    images = []
    pages = list(answer["urls"]["symbols"])
    gallery = answer["urls"].get("gallery")
    if gallery and len(pages) > 1:
        pages = pages + [{"symbol": "gallery", "url": gallery}]
    for page in pages:
        dest = directory / f"review-{page['symbol']}-{uuid.uuid4().hex[:8]}.png"
        shot = shots.shoot(page["url"], dest)
        if not shot.get("ok"):
            return shot
        images.append({
            "symbol": page["symbol"],
            "url": page["url"],
            "path": shot["path"],
            "sha256": shot["sha256"],
            "bytes": shot["bytes"],
            "png": shot.get("png"),
        })
    answer = dict(answer)
    answer["images"] = images
    answer["loaded"] = True
    return answer
