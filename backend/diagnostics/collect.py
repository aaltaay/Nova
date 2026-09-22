"""Pure collectors: process, integrations, practice, frontend rows (ADR 021).

Every function takes plain inputs and returns rows. No module state, no
I/O -- ``gather.py`` reads the live modules and feeds these.
"""
from __future__ import annotations

import os
from typing import Any

from constants_diagnostics import (
    DIAG_ACTION_RELOAD_BACKEND,
    DIAG_ENV_MISSING_CAUSE,
    DIAG_ENV_MISSING_FIX,
    DIAG_ENV_MISSING_PREFIX,
    DIAG_ENV_SOURCE_FILE,
    DIAG_ENV_SOURCE_PROCESS,
    DIAG_ENV_SOURCE_UNSET,
    DIAG_GROUP_FRONTEND,
    DIAG_GROUP_INTEGRATIONS,
    DIAG_GROUP_PRACTICE,
    DIAG_GROUP_PROCESS,
    DIAG_INTEGRATION_KEYS,
    DIAG_STATE_FAIL,
    DIAG_STATE_OFF,
    DIAG_STATE_OK,
    DIAG_STATE_UNKNOWN,
    DIAG_STATE_WARN,
    DIAG_TRUE_VALUES,
)
from diagnostics.rows import row


# ── Process ───────────────────────────────────────────────────────────────────

def process_rows(facts: dict[str, Any]) -> list[dict[str, Any]]:
    """Rows judged from ``process_info.process_facts()``."""
    env = facts.get("env_file") or {}
    rows: list[dict[str, Any]] = []

    tag = facts.get("release_tag")
    commit = facts.get("commit")
    rows.append(row(
        id="process_identity",
        group=DIAG_GROUP_PROCESS,
        title="API process",
        state=DIAG_STATE_OK,
        detail=(
            f"pid {facts.get('pid')} · {tag or 'revision unknown'}"
            f"{f' ({commit})' if commit else ''} · Python {facts.get('python')}"
            f"{' · frozen desktop sidecar' if facts.get('frozen') else ' · dev'}"
            f"{' · uvicorn --reload' if facts.get('reload') else ''}"
        ),
        cause="What answered this request.",
        fix="Compare pid / instance id with the process owner row -- a different pid means a different process.",
        since=facts.get("started_at"),
        evidence={
            "pid": facts.get("pid"),
            "parent_pid": facts.get("parent_pid"),
            "instance_id": facts.get("instance_id"),
            "started_at": facts.get("started_at"),
            "uptime_sec": round(float(facts.get("uptime_sec") or 0.0), 1),
            "release_tag": tag,
            "commit": commit,
            "branch": facts.get("branch"),
            "revision_source": facts.get("source"),
            "python": facts.get("python"),
            "executable": facts.get("executable"),
            "frozen": facts.get("frozen"),
            "reload": facts.get("reload"),
            "argv0": facts.get("argv0"),
        },
    ))

    worktree = bool(facts.get("worktree"))
    rows.append(row(
        id="process_root",
        group=DIAG_GROUP_PROCESS,
        title="Repo root the API runs from",
        state=DIAG_STATE_WARN if worktree else DIAG_STATE_OK,
        detail=(
            f"{facts.get('repo_root')}"
            + (" -- a git worktree, not the main checkout" if worktree else "")
        ),
        cause=(
            "This API was started from an agent worktree. It reads .env, caches and "
            "logs relative to that checkout, not the operator's repository."
            if worktree
            else "The API resolves .env, caches and logs relative to this root."
        ),
        fix=(
            "Stop this process and start the API from the main repository (Reload backend "
            "spawns from the main repo's backend/)."
            if worktree
            else "Nothing to do."
        ),
        action=DIAG_ACTION_RELOAD_BACKEND if worktree else None,
        evidence={
            "repo_root": facts.get("repo_root"),
            "backend_dir": facts.get("backend_dir"),
            "cwd": facts.get("cwd"),
            "worktree": worktree,
            "git_common_dir": facts.get("git_common_dir"),
        },
    ))

    exists = bool(env.get("exists"))
    keys_loaded = int(env.get("keys_loaded") or 0)
    if not exists:
        state, detail = DIAG_STATE_FAIL, f"{DIAG_ENV_MISSING_PREFIX} {env.get('path')}"
        cause, fix = DIAG_ENV_MISSING_CAUSE, DIAG_ENV_MISSING_FIX
    elif keys_loaded == 0:
        state, detail = DIAG_STATE_WARN, f".env found at {env.get('path')} but it holds no keys"
        cause, fix = "The file exists but parsed to zero keys.", "Check the file's contents and encoding."
    else:
        state = DIAG_STATE_OK
        detail = f".env at {env.get('path')} · {keys_loaded} keys loaded"
        cause, fix = "Loaded at API start (load_dotenv).", "Edit the file, then Reload backend."
    rows.append(row(
        id="process_env_file",
        group=DIAG_GROUP_PROCESS,
        title=".env file",
        state=state,
        detail=detail + (" · NOVA_ENV_PATH override" if env.get("override") else ""),
        cause=cause,
        fix=fix,
        action=DIAG_ACTION_RELOAD_BACKEND if not exists else None,
        evidence={
            "path": env.get("path"),
            "exists": exists,
            "keys_loaded": keys_loaded,
            "keys": list(env.get("keys") or []),
            "override": bool(env.get("override")),
        },
    ))
    return rows


# ── Integrations ──────────────────────────────────────────────────────────────

def env_source(key: str, env_keys: set[str], environ: dict[str, str]) -> tuple[bool, str]:
    """``(is_set, source)`` -- where the process got ``key`` from. Presence only."""
    value = (environ.get(key) or "").strip().strip("'\"")
    if not value:
        return False, DIAG_ENV_SOURCE_UNSET
    return True, DIAG_ENV_SOURCE_FILE if key in env_keys else DIAG_ENV_SOURCE_PROCESS


def integration_rows(
    *,
    env_file: dict[str, Any],
    environ: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """One row per integration key: set / unset and the file it was read from."""
    environ = dict(os.environ) if environ is None else environ
    env_keys = set(env_file.get("keys") or [])
    env_exists = bool(env_file.get("exists"))
    path = env_file.get("path")
    rows: list[dict[str, Any]] = []
    for row_id, title, key in DIAG_INTEGRATION_KEYS:
        is_set, source = env_source(key, env_keys, environ)
        if key == "IBKR_ENABLED":
            enabled = (environ.get(key) or "").strip().lower() in DIAG_TRUE_VALUES
            if enabled:
                state, detail = DIAG_STATE_OK, f"{key}=true (from {source})"
            elif is_set:
                state, detail = DIAG_STATE_OFF, f"{key} is set but not true (from {source})"
            else:
                state, detail = DIAG_STATE_FAIL, f"{key} not set"
        else:
            state = DIAG_STATE_OK if is_set else DIAG_STATE_OFF
            detail = f"{key} present (from {source})" if is_set else f"{key} not set"
        if not is_set and not env_exists:
            cause = f"{DIAG_ENV_MISSING_PREFIX} {path} -- {DIAG_ENV_MISSING_CAUSE}"
            fix = DIAG_ENV_MISSING_FIX
        elif not is_set:
            cause = f"{key} is neither in {path} nor in the process environment."
            fix = f"Add {key} to {path} and Reload backend."
        else:
            cause = f"Read from {'the .env file' if source == DIAG_ENV_SOURCE_FILE else 'the process environment'}."
            fix = "Nothing to do."
        rows.append(row(
            id=row_id,
            group=DIAG_GROUP_INTEGRATIONS,
            title=title,
            state=state,
            detail=detail,
            cause=cause,
            fix=fix,
            evidence={"key": key, "set": is_set, "source": source, "file": path, "file_exists": env_exists},
        ))
    return rows


# ── Practice ──────────────────────────────────────────────────────────────────

def practice_rows(
    *,
    venue: str,
    venue_file: str,
    venue_file_exists: bool,
    venue_schema_version: int | None,
    venue_schema_expected: int,
    ledger_file: str,
    ledger_file_exists: bool,
    ledger_schema_version: int | None,
    ledger_schema_expected: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not venue_file_exists:
        v_state = DIAG_STATE_OFF
        v_detail = f"venue {venue} (from NOVA_BROKER / default; no desk-venue.json yet)"
        v_cause, v_fix = "No venue click has been persisted.", "Nothing to do -- Live is the default door."
    elif venue_schema_version != venue_schema_expected:
        v_state = DIAG_STATE_FAIL
        v_detail = f"desk-venue.json schema_version {venue_schema_version} (expected {venue_schema_expected})"
        v_cause = "The file was written by a different build; Nova refuses it and follows NOVA_BROKER."
        v_fix = "Click a venue pill once to rewrite the file, or delete it."
    else:
        v_state, v_detail = DIAG_STATE_OK, f"venue {venue} (desk-venue.json v{venue_schema_version})"
        v_cause, v_fix = "Persisted venue from the operator cache (ADR 018).", "Nothing to do."
    rows.append(row(
        id="practice_venue",
        group=DIAG_GROUP_PRACTICE,
        title="Desk venue",
        state=v_state,
        detail=v_detail,
        cause=v_cause,
        fix=v_fix,
        evidence={
            "venue": venue,
            "file": venue_file,
            "exists": venue_file_exists,
            "schema_version": venue_schema_version,
            "expected": venue_schema_expected,
        },
    ))
    if not ledger_file_exists:
        l_state, l_detail = DIAG_STATE_OFF, "no Paper ledger yet (created on the first practice order)"
        l_cause, l_fix = "practice-paper.json is written on first use.", "Nothing to do."
    elif ledger_schema_version != ledger_schema_expected:
        l_state = DIAG_STATE_FAIL
        l_detail = f"practice-paper.json schema_version {ledger_schema_version} (expected {ledger_schema_expected})"
        l_cause = "The ledger was written by a different build; the broker archives it before starting fresh."
        l_fix = "Nothing is lost -- the archive sits beside the ledger. Reset the Paper account if asked."
    else:
        l_state, l_detail = DIAG_STATE_OK, f"Paper ledger v{ledger_schema_version} at {ledger_file}"
        l_cause, l_fix = "The persistent practice ledger (ADR 020).", "Nothing to do."
    rows.append(row(
        id="practice_ledger",
        group=DIAG_GROUP_PRACTICE,
        title="Paper ledger",
        state=l_state,
        detail=l_detail,
        cause=l_cause,
        fix=l_fix,
        evidence={
            "file": ledger_file,
            "exists": ledger_file_exists,
            "schema_version": ledger_schema_version,
            "expected": ledger_schema_expected,
        },
    ))
    return rows


# ── Frontend ──────────────────────────────────────────────────────────────────

def frontend_rows(*, ui_tag: str | None, backend_tag: str | None) -> list[dict[str, Any]]:
    """The dev server's reported revision vs the backend's; a mismatch is a row."""
    ui = (ui_tag or "").strip() or None
    if ui is None:
        state, detail = DIAG_STATE_UNKNOWN, "Unknown: the UI did not report its revision"
        cause = "The checklist sends ?ui=vNNN; an older UI build does not."
        fix = "Reload the page."
    elif backend_tag is None:
        state, detail = DIAG_STATE_UNKNOWN, f"UI {ui}; backend revision unknown (git unavailable)"
        cause = "The API could not read its git revision (packaged build without VERSION, or git missing)."
        fix = "Nothing to do unless behaviour looks stale; then Reload backend."
    elif ui == backend_tag:
        state, detail = DIAG_STATE_OK, f"UI {ui} matches API {backend_tag}"
        cause, fix = "Same revision on both sides.", "Nothing to do."
    else:
        state, detail = DIAG_STATE_WARN, f"UI {ui} but API {backend_tag}"
        cause = "The page and the API were built from different commits (one of them was restarted after a pull, or the API runs from another checkout)."
        fix = "Reload backend and hard-refresh the page so both run the same revision."
    return [row(
        id="frontend_revision",
        group=DIAG_GROUP_FRONTEND,
        title="UI vs API revision",
        state=state,
        detail=detail,
        cause=cause,
        fix=fix,
        action=DIAG_ACTION_RELOAD_BACKEND if state == DIAG_STATE_WARN else None,
        evidence={"ui": ui, "api": backend_tag},
    )]
