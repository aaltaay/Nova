"""Backtest the eyes on Session Records (ADR 029).

A run takes one setup's templates (the first pullback's unless ``setup`` names
another with a scanner, ADR 031) and Session Records, replays each
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

ADR 034: a run may add **variants** -- templates made for this run only, a base
template's values with some parameters changed, never stored -- so a sweep can
try many numbers on the same recordings. A variant's manifest entry adds
``variant: true``, ``base`` and ``overrides``; every template's summary adds
``exits`` (scoring exits by reason), ``flush`` (what a flush did) and
``vs_base``: the same setups (same symbol, day and leg) paired with the run's
first template -- ``{base, paired, avg_r_delta, better, worse, same}``.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from constants_bot import BOT_SETUP_FIRST_PULLBACK, BOT_SETUPS_WITH_SCANNER
from constants_eyes import (
    EYES_BACKTEST_MAX_SESSIONS,
    EYES_BACKTEST_MAX_VARIANTS,
    EYES_BACKTEST_RUNS_LISTED,
    EYES_BACKTESTS_DIRNAME,
    EYES_REPLAY_SOURCE_BACKTEST,
    EYES_SCHEMA_VERSION,
    EYES_VARIANT_ID_PREFIX,
)

logger = logging.getLogger(__name__)
RUN_ID_RE = re.compile(r"\d{8}-\d{6}-[0-9a-f]{6}")
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


def _templates(template_ids: list[str] | None, setup: str = BOT_SETUP_FIRST_PULLBACK) -> list[Any]:
    from setup_templates.catalogue import TemplateError
    from setup_templates.store import get_store

    if setup not in BOT_SETUPS_WITH_SCANNER:
        raise TemplateError(f"{setup.replace('_', ' ')} has no scanner to replay", "setup", code="SETUP_UNKNOWN")
    store = get_store()
    every = [t for t in store.templates(setup) if not t.error]
    if not template_ids:
        return every
    known = {t.id: t for t in every}
    missing = [tid for tid in template_ids if tid not in known]
    if missing:
        raise TemplateError(f"no usable {setup.replace('_', ' ')} template {', '.join(missing)}", missing[0],
                            code="TEMPLATE_UNKNOWN")
    return [known[tid] for tid in template_ids]


def variant_templates(setup: str, variants: list[dict] | None) -> list[Any]:
    """Templates for this run only: each a base template's values with ``values`` over them, never stored."""
    from setup_templates import catalogue
    from setup_templates.catalogue import TemplateError
    from setup_templates.store import Template, get_store

    if not variants:
        return []
    if len(variants) > EYES_BACKTEST_MAX_VARIANTS:
        raise TemplateError(f"a run takes at most {EYES_BACKTEST_MAX_VARIANTS} variants", "variants",
                            code="TEMPLATE_INVALID")
    known = {t.id: t for t in get_store().templates(setup) if not t.error}
    out = []
    for i, v in enumerate(variants, 1):
        base_id = str(v.get("base") or "default")
        base = known.get(base_id)
        if base is None:
            raise TemplateError(f"no usable {setup.replace('_', ' ')} template {base_id}", base_id,
                                code="TEMPLATE_UNKNOWN")
        overrides = dict(v.get("values") or {})
        values = catalogue.validate(setup, overrides, base=base.values)
        name = str(v.get("name") or "").strip() or (
            ", ".join(f"{k}={overrides[k]}" for k in sorted(overrides)) or f"{base.name} (base)")
        t = Template(setup=setup, id=f"{EYES_VARIANT_ID_PREFIX}{i:02d}", name=name[:120], rev=1, values=values,
                     note=f"backtest variant of {base_id}")
        t.base_id, t.overrides = base_id, overrides   # type: ignore[attr-defined]
        out.append(t)
    return out


def _pair_key(row: dict) -> tuple:
    return (row.get("date"), row.get("symbol"), row.get("leg_t"), row.get("setup_type"))


def _vs_base(mine: list[dict], base: list[dict], base_id: str) -> dict[str, Any]:
    """The same setups (symbol, day, leg) scored by this template and by the run's first one."""
    theirs = {_pair_key(r): r for r in base if r.get("bar_r") is not None}
    deltas = [float(r["bar_r"]) - float(theirs[_pair_key(r)]["bar_r"]) for r in mine
              if r.get("bar_r") is not None and _pair_key(r) in theirs]
    return {"base": base_id, "paired": len(deltas),
            "avg_r_delta": round(sum(deltas) / len(deltas), 3) if deltas else None,
            "better": sum(1 for d in deltas if d > 1e-9), "worse": sum(1 for d in deltas if d < -1e-9),
            "same": sum(1 for d in deltas if abs(d) <= 1e-9)}


def _counts(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        if r.get(key):
            out[str(r[key])] = out.get(str(r[key]), 0) + 1
    return dict(sorted(out.items()))


def summarize_run(rows: list[dict], templates: list[Any], sessions_ok: int) -> dict[str, Any]:
    from setup_scanner.readout import evaluate
    from setup_scanner.summary import summarize

    from constants_setups import SETUPS_READOUT_KIND, SETUPS_READOUT_KINDS

    out: dict[str, Any] = {}
    first = templates[0].id if templates else None
    base_rows = [r for r in rows if r.get("template_id") == first]
    for t in templates:
        mine = [r for r in rows if r.get("template_id") == t.id]
        kind = SETUPS_READOUT_KINDS.get(getattr(t, "setup", BOT_SETUP_FIRST_PULLBACK), SETUPS_READOUT_KIND)
        out[t.id] = {"name": t.name, "rev": t.rev, "sessions": sessions_ok, "summary": summarize(mine),
                     "readout": evaluate(mine, {"id": t.id, "rev": t.rev, "name": t.name}, kind),
                     "exits": _counts(mine, "bar_exit_reason"), "flush": _counts(mine, "flush_action"),
                     "vs_base": _vs_base(mine, base_rows, first) if t.id != first else None}
    return out


def _run_templates(template_ids: list[str] | None, setup: str, variants: list[dict] | None) -> list[Any]:
    """The stored templates asked for (every one when none are named and no variant is), then the variants."""
    made = variant_templates(setup, variants)
    if made and not template_ids:
        return made
    return _templates(template_ids, setup) + made


def run(*, template_ids: list[str] | None = None, sessions: list[tuple[str, str]] | None = None,
        run_id: str | None = None, load: Callable[[str, str], Any] | None = None,
        progress: Callable[[int, int], None] | None = None, setup: str = BOT_SETUP_FIRST_PULLBACK,
        variants: list[dict] | None = None) -> dict[str, Any]:
    """Run synchronously; returns the finished manifest. Writes as it goes, so a crash leaves a partial run."""
    from eyes.recording import load as load_recording
    from eyes.recording import usable_sessions
    from eyes.replay import EyesReplay
    from eyes.journal import line

    templates = _run_templates(template_ids, setup, variants)
    todo = list(sessions) if sessions else usable_sessions()
    todo = todo[:EYES_BACKTEST_MAX_SESSIONS]
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    folder = backtests_dir() / run_id
    folder.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "schema_version": EYES_SCHEMA_VERSION, "run_id": run_id, "created_at": time.time(), "finished_at": None,
        "status": "running", "error": None, "setup": setup,
        "templates": [{"id": t.id, "rev": t.rev, "name": t.name, "params_hash": t.fingerprint, "values": t.values}
                      | ({"variant": True, "base": t.base_id, "overrides": t.overrides}
                         if hasattr(t, "base_id") else {}) for t in templates],
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


def start(*, template_ids: list[str] | None = None, sessions: list[tuple[str, str]] | None = None,
          setup: str = BOT_SETUP_FIRST_PULLBACK, variants: list[dict] | None = None) -> dict[str, Any]:
    """Start a run on a worker thread; returns its id at once (the route answers 202)."""
    _run_templates(template_ids, setup, variants)   # refuse an unknown setup, template or value before a thread
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    thread = threading.Thread(target=run, kwargs={"template_ids": template_ids, "sessions": sessions,
                                                  "run_id": run_id, "setup": setup, "variants": variants},
                              name=f"eyes-backtest-{run_id}", daemon=True)
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


def run_dir(run_id: str) -> Path | None:
    """A run's folder: only for a well-formed run id, and only inside the backtests folder."""
    if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        return None
    root = os.path.realpath(backtests_dir())
    folder = os.path.realpath(os.path.join(root, run_id))
    if not folder.startswith(root + os.sep):
        return None
    return Path(folder)


def read_manifest(run_id: str) -> dict[str, Any] | None:
    folder = run_dir(run_id)
    if folder is None:
        return None
    path = folder / "manifest.json"
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
    folder = run_dir(run_id)
    if folder is None:
        return None
    path = folder / "summary.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("eyes backtest: unreadable summary %s", path)
        return None
