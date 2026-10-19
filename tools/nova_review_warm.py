"""One Chromium for review-page screenshots, kept for the MCP process lifetime.

The first chart call should not pay a browser cold start. ``start`` launches
``nova_review_shot.mjs`` and waits until it says it is ready. A machine without
Playwright answers ``REVIEW_SHOT_UNAVAILABLE`` instead of a made-up image.
"""
from __future__ import annotations

import hashlib
import json
import queue
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
SHOT = Path(__file__).with_name("nova_review_shot.mjs")
NODE_CWD = REPO / "frontend"


class ReviewShots:
    def __init__(self, shoot: Callable[[str, Path], dict[str, Any]] | None = None):
        self._shoot = shoot
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._lines: queue.Queue[str] = queue.Queue()
        self._error: dict[str, Any] | None = None
        self._started = False

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
                    stderr=subprocess.PIPE,
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

    def shoot(self, url: str, dest: Path) -> dict[str, Any]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if self._shoot is not None:
            return self._shoot(url, dest)
        if not self._started:
            started = self.start()
            if not started.get("ok"):
                return started
        if self._error is not None:
            return self._error
        proc = self._proc
        if proc is None or proc.poll() is not None or proc.stdin is None:
            return {"ok": False, "error": {"code": "REVIEW_SHOT_UNAVAILABLE", "detail": "renderer is not running"}}
        with self._lock:
            proc.stdin.write(json.dumps({"url": url, "dest": str(dest)}) + "\n")
            proc.stdin.flush()
            try:
                line = self._lines.get(timeout=60)
            except queue.Empty:
                return {"ok": False, "error": {"code": "REVIEW_SHOT_FAILED", "detail": "screenshot timed out"}}
        try:
            body = json.loads(line)
        except json.JSONDecodeError:
            return {"ok": False, "error": {"code": "REVIEW_SHOT_FAILED", "detail": line}}
        if not body.get("ok"):
            return {"ok": False, "error": {"code": body.get("error") or "REVIEW_SHOT_FAILED", "detail": body.get("detail")}}
        raw = dest.read_bytes()
        return {"ok": True, "path": str(dest), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

    def close(self) -> None:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.terminate()


def attach_images(answer: dict[str, Any], shots: ReviewShots, directory: Path) -> dict[str, Any]:
    """Fill ``images`` for png and both. Interactive answers are returned untouched."""
    if not answer.get("ok") or answer.get("output") == "interactive":
        return answer
    images = []
    pages = list(answer["urls"]["symbols"])
    gallery = answer["urls"].get("gallery")
    if gallery and len(pages) >= 1:
        pages = pages + [{"symbol": "gallery", "url": gallery}]
    for page in pages:
        dest = directory / f"review-{page['symbol']}-{uuid.uuid4().hex[:8]}.png"
        shot = shots.shoot(page["url"], dest)
        if not shot.get("ok"):
            return shot
        images.append({"symbol": page["symbol"], "url": page["url"], "path": shot["path"],
                       "sha256": shot["sha256"], "bytes": shot["bytes"]})
    answer = dict(answer)
    answer["images"] = images
    answer["loaded"] = True
    return answer
