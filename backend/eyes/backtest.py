"""Backtest the eyes on Session Records (ADR 029).

A run takes first-pullback templates and Session Records, replays each
recording through one lane per template (``eyes/replay.py``) from 04:00 to the
session's end, and keeps what the eyes would have done: every armed setup with
its tape at near and at the trigger and its scores, and every observation.

Owner: this module -- the only writer of ``<eyes dir>/backtests/<run_id>/``:
``manifest.json`` (``{schema_version, run_id, created_at, finished_at, status:
running | done | failed, error, templates: [{id, rev, name, params_hash,
values}], sessions: [{date, symbol, status: ok | skipped, reason, setups,
recording}]}``), ``setups.jsonl`` (one scoreboard-shaped row per armed setup,
plus ``date`` / ``symbol``), ``events.jsonl`` (journal-shaped lines, ``source:
"backtest"``) and ``summary.json`` (``{schema_version, run_id, templates: {ID:
{name, rev, sessions, summary, readout}}}`` -- ``summary`` is the scoreboard's
split, ``readout`` the §2g rules applied to the run as if it were live).
Invalidation: none -- a run is a record. Never ``setups.db``, never the live
read-out: Strategy is earned on live evidence only.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from constants_bot import BOT_SETUP_FIRST_PULLBACK
from constants_eyes import (
    EYES_BACKTEST_MAX_SESSIONS,
    EYES_BACKTEST_RUNS_LISTED,
    EYES_BACKTESTS_DIRNAME,
    EYES_REPLAY_SOURCE_BACKTEST,
    EYES_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)
_runs_lock = threading.Lock()
_running: dict[str, threading.Thread] = {}


def backtests_dir() -> Path:
    from eyes.journal import eyes_dir

    return eyes_dir() / EYES_BACKTESTS_DIRNAME


def _write_json(path: Path, payload: dict) -> None:
    from scanner_wire import wire_safe

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(wire_safe(payload), indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _templates(template_ids: list[str] | None) -> list[Any]:
    from setup_templates.catalogue import TemplateError
    from setup_templates.store import get_store

    store = get_store()
    every = [t for t in store.templates(BOT_SETUP_FIRST_PULLBACK) if not t.error]
    if not template_ids:
        return every
    known = {t.id: t for t in every}
    missing = [tid for tid in template_ids if tid not in known]
    if missing:
        raise TemplateError(f"no usable first-pullback template {', '.join(missing)}", missing[0],
                            code="TEMPLATE_UNKNOWN")
    return [known[tid] for tid in template_ids]


def summarize_run(rows: list[dict], templates: list[Any], sessions_ok: int) -> dict[str, Any]:
    from setup_scanner.readout import evaluate
    from setup_scanner.summary import summarize

    out: dict[str, Any] = {}
    for t in templates:
        mine = [r for r in rows if r.get("template_id") == t.id]
        out[t.id] = {"name": t.name, "rev": t.rev, "sessions": sessions_ok, "summary": summarize(mine),
                     "readout": evaluate(mine, {"id": t.id, "rev": t.rev, "name": t.name})}
    return out


def run(*, template_ids: list[str] | None = None, sessions: list[tuple[str, str]] | None = None,
        run_id: str | None = None, load: Callable[[str, str], Any] | None = None,
        progress: Callable[[int, int], None] | None = None) -> dict[str, Any]:
    """Run synchronously; returns the finished manifest. Writes as it goes, so a crash leaves a partial run."""
    from eyes.recording import load as load_recording
    from eyes.recording import usable_sessions
    from eyes.replay import EyesReplay
    from eyes.journal import line

    templates = _templates(template_ids)
    todo = list(sessions) if sessions else usable_sessions()
    todo = todo[:EYES_BACKTEST_MAX_SESSIONS]
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    folder = backtests_dir() / run_id
    folder.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "schema_version": EYES_SCHEMA_VERSION, "run_id": run_id, "created_at": time.time(), "finished_at": None,
        "status": "running", "error": None,
        "templates": [{"id": t.id, "rev": t.rev, "name": t.name, "params_hash": t.fingerprint, "values": t.values}
                      for t in templates],
        "sessions": [],
    }
    _write_json(folder / "manifest.json", manifest)
    rows: list[dict] = []
    ok = 0
    try:
        with (folder / "events.jsonl").open("w", encoding="utf-8") as events, \
                (folder / "setups.jsonl").open("w", encoding="utf-8") as setups:
            for i, (date, symbol) in enumerate(todo):
                entry: dict[str, Any] = {"date": date, "symbol": symbol, "status": "ok", "reason": None, "setups": 0}
                try:
                    rec = (load or load_recording)(date, symbol)
                except (ValueError, OSError) as exc:
                    entry.update(status="skipped", reason=str(exc))
                else:
                    replay = EyesReplay(rec, templates, source=EYES_REPLAY_SOURCE_BACKTEST, all_propose=True,
                                        journal=lambda ev: events.write(line({**ev, "run_id": run_id}) + "\n"))
                    replay.run_to_end()
                    got = [{**r, "date": date, "symbol": symbol, "run_id": run_id} for r in replay.rows.values()]
                    for r in got:
                        setups.write(json.dumps(r, default=str) + "\n")
                    rows += got
                    entry.update(setups=len(got), recording=rec.summary())
                    ok += 1
                manifest["sessions"].append(entry)
                _write_json(folder / "manifest.json", manifest)
                if progress:
                    progress(i + 1, len(todo))
        _write_json(folder / "summary.json", {"schema_version": EYES_SCHEMA_VERSION, "run_id": run_id,
                                              "templates": summarize_run(rows, templates, ok)})
        manifest["status"] = "done"
    except Exception as exc:
        logger.exception("eyes backtest %s failed", run_id)
        manifest.update(status="failed", error=str(exc))
    manifest["finished_at"] = time.time()
    _write_json(folder / "manifest.json", manifest)
    return manifest


def start(*, template_ids: list[str] | None = None, sessions: list[tuple[str, str]] | None = None) -> dict[str, Any]:
    """Start a run on a worker thread; returns its id at once (the route answers 202)."""
    _templates(template_ids)           # refuse an unknown template before a thread starts
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    thread = threading.Thread(target=run, kwargs={"template_ids": template_ids, "sessions": sessions,
                                                  "run_id": run_id}, name=f"eyes-backtest-{run_id}", daemon=True)
    with _runs_lock:
        _running[run_id] = thread
    thread.start()
    return {"run_id": run_id, "status": "running"}


def list_runs(limit: int = EYES_BACKTEST_RUNS_LISTED) -> list[dict[str, Any]]:
    root = backtests_dir()
    if not root.is_dir():
        return []
    out = []
    for folder in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True)[:limit]:
        man = read_manifest(folder.name)
        if man is None:
            continue
        out.append({k: man.get(k) for k in ("run_id", "created_at", "finished_at", "status", "error")}
                   | {"templates": [t.get("name") for t in man.get("templates") or []],
                      "sessions": len(man.get("sessions") or []),
                      "setups": sum(int(s.get("setups") or 0) for s in man.get("sessions") or [])})
    return out


def read_manifest(run_id: str) -> dict[str, Any] | None:
    path = backtests_dir() / run_id / "manifest.json"
    if not path.is_file():
        return None
    try:
        man = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("eyes backtest: unreadable manifest %s", path)
        return None
    if man.get("schema_version") != EYES_SCHEMA_VERSION:
        logger.warning("eyes backtest: %s has schema %r -- skipped", path, man.get("schema_version"))
        return None
    return man


def read_summary(run_id: str) -> dict[str, Any] | None:
    path = backtests_dir() / run_id / "summary.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("eyes backtest: unreadable summary %s", path)
        return None
