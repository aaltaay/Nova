"""The imperative shell: read live modules, feed the pure collectors (ADR 021).

Every read is wrapped so one broken module yields an ``unknown`` row that
says why, never a 500 for the whole checklist.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

from constants_diagnostics import (
    DIAG_GROUP_GATEWAY,
    DIAG_GROUP_MARKET_DATA,
    DIAG_GROUP_PERFORMANCE,
    DIAG_GROUP_PRACTICE,
    DIAG_GROUP_RECORDER,
    DIAG_GROUPS,
    DIAG_PORT_PROBE_TIMEOUT_SEC,
    DIAG_SCHEMA_VERSION,
)
from diagnostics import (
    collect,
    collect_borrow,
    collect_catalysts,
    collect_gateway,
    collect_leaderboard,
    collect_perf,
    process_info,
)
from diagnostics.rows import counts, unknown_row

logger = logging.getLogger(__name__)

Collector = Callable[[], list[dict[str, Any]]]


def _safe(group: str, row_id: str, title: str, fn: Collector) -> list[dict[str, Any]]:
    try:
        return fn()
    except Exception as exc:
        logger.exception("diagnostics: %s collector failed", row_id)
        return [unknown_row(id=row_id, group=group, title=title, why=f"{type(exc).__name__}: {exc}")]


def _read_schema_version(path: str) -> tuple[bool, int | None]:
    p = Path(path)
    if not p.is_file():
        return False, None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        raw = data.get("schema_version") if isinstance(data, dict) else None
        return True, int(raw) if raw is not None else None
    except (OSError, ValueError, TypeError):
        logger.warning("diagnostics: could not read schema_version from %s", path, exc_info=True)
        return True, None


def _gateway_inputs() -> dict[str, Any]:
    from ibkr import attach_retry as _attach
    from ibkr import client as _client
    from ibkr import gateway_heal as _heal
    from ibkr import port_diagnostics as _ports
    from ibkr import second_factor as _second_factor
    from ibkr import session_errors as _se
    from ibkr.gateway_paths import _ibc_launcher

    enabled = _client.is_enabled()
    host = os.environ.get("IBKR_HOST", "127.0.0.1")
    live_port, paper_port = _heal.port_for_mode("live"), _heal.port_for_mode("paper")
    ports: dict[str, Any] = {"host": host, "live_port": live_port, "paper_port": paper_port}
    if enabled:
        ports["live_reachable"] = _ports.probe_port(host, live_port, timeout=DIAG_PORT_PROBE_TIMEOUT_SEC)
        ports["paper_reachable"] = _ports.probe_port(host, paper_port, timeout=DIAG_PORT_PROBE_TIMEOUT_SEC)
    else:
        ports["live_reachable"] = None
        ports["paper_reachable"] = None
    sf = _second_factor.current_state()
    ibc = {
        "second_factor_pending": sf.pending,
        "second_factor_age_sec": sf.age_sec,
        "second_factor_stale": sf.stale,
        "launcher_present": _ibc_launcher() is not None,
    }
    if sf.pending or sf.stale:
        # Only while a phone prompt is open: why the saved login was lost.
        # One wevtutil per boot at most (cached in ibkr.windows_restarts).
        from ibkr import relogin_reason as _relogin

        ibc["relogin"] = _relogin.current()
    return {
        "enabled": enabled,
        "session": _client.session_snapshot(),
        "ports": ports,
        "ibc": ibc,
        "last_error": _se.last_error(),
        "attach": _attach.status(),
        "heal": _heal.heal_status(),
    }


def _market_data_inputs() -> dict[str, Any]:
    from ibkr import client as _client
    from ibkr import session_errors as _se
    from ibkr import tape_stream as _tape
    from ibkr import ticks as _ticks
    from ibkr.depth import state as _depth_state

    return {
        "usable": _client.is_ready(),
        "delayed": bool(_se.is_delayed_data()),
        "live_md_blocked": bool(_se.live_market_data_blocked()),
        "data_farm": _se.get_data_farm_status(),
        "max_tickers": bool(_se.max_tickers_hit()),
        "budget": _ticks.ticker_budget_status(),
        "depth_symbols": [s for s in _depth_state.subscribed_symbols() if _depth_state.is_live(s)],
        # Read-only peek at the tape line map: this IBKR session's lines only (#562).
        "tape_symbols": sorted(s for s in list(getattr(_tape, "_tickers", {})) if _tape.is_subscribed(s)),
    }


def _leaderboard_inputs() -> dict[str, Any]:
    from leaderboard import auto_record, recorder, store

    return {"recorder": recorder.status(), "auto": auto_record.status(), "store_path": str(store.path())}


def _catalyst_feed_status() -> dict[str, Any]:
    from catalysts import feed, live_finnhub

    return {**feed.get_feed().status(), "finnhub": live_finnhub.status()}


def _borrow_feed_status() -> dict[str, Any]:
    from move_reason import borrow_feed

    return borrow_feed.get_feed().status()


def _recorder_inputs() -> dict[str, Any]:
    from capture import keepalive as _keepalive
    from capture import mode as _mode

    payload = _mode.status_payload()
    recording = list(payload.get("capture_symbols") or [])
    return {
        "recording": recording,
        "sessions": dict(payload.get("sessions") or {}),
        "resume": [dict(r) for r in _keepalive._resume.values()],
        "stopped": [dict(r) for r in _keepalive._stopped.values()],
        "error": payload.get("error"),
    }


def _practice_inputs() -> dict[str, Any]:
    from constants_practice import PRACTICE_LEDGER_SCHEMA_VERSION
    from constants_sim import DESK_VENUE_FILE, DESK_VENUE_SCHEMA_VERSION
    from practice.persist import paper_ledger_path
    from sim.mode import venue

    venue_exists, venue_version = _read_schema_version(DESK_VENUE_FILE)
    ledger_file = paper_ledger_path()
    ledger_exists, ledger_version = _read_schema_version(ledger_file)
    return {
        "venue": venue(),
        "venue_file": DESK_VENUE_FILE,
        "venue_file_exists": venue_exists,
        "venue_schema_version": venue_version,
        "venue_schema_expected": int(DESK_VENUE_SCHEMA_VERSION),
        "ledger_file": ledger_file,
        "ledger_file_exists": ledger_exists,
        "ledger_schema_version": ledger_version,
        "ledger_schema_expected": int(PRACTICE_LEDGER_SCHEMA_VERSION),
    }


def _perf_rows(now: float) -> list[dict[str, Any]]:
    from constants_perf import PERF_DIAG_DROP_RECENT_SEC, PERF_DIAG_WINDOW_SEC
    from perf import recorder

    return collect_perf.perf_rows(
        running=bool(recorder.status()["running"]),
        window=recorder.samples(PERF_DIAG_WINDOW_SEC, now=now),
        drop_window=recorder.samples(PERF_DIAG_DROP_RECENT_SEC, now=now),
        stalls=recorder.stall_summaries(),
        clients=recorder.clients(),
        now=now,
        window_sec=PERF_DIAG_WINDOW_SEC,
        drop_window_sec=PERF_DIAG_DROP_RECENT_SEC,
    )


def gather(*, ui_tag: str | None = None, now: float | None = None) -> dict[str, Any]:
    """The full ``GET /api/diagnostics`` payload."""
    ts = time.time() if now is None else float(now)
    facts = process_info.process_facts(now=ts)
    rows: list[dict[str, Any]] = []
    rows += collect.process_rows(facts)
    rows += collect.integration_rows(env_file=facts["env_file"])
    rows += _safe(DIAG_GROUP_GATEWAY, "gateway", "Gateway", lambda: collect_gateway.gateway_rows(**_gateway_inputs()))
    rows += _safe(DIAG_GROUP_MARKET_DATA, "market_data", "Market data", lambda: collect_gateway.market_data_rows(**_market_data_inputs()))
    rows += _safe(DIAG_GROUP_RECORDER, "recorder", "Recorder", lambda: collect_gateway.recorder_rows(**_recorder_inputs()))
    rows += _safe(DIAG_GROUP_RECORDER, "leaderboard_recorder", "Scanner board recorder",
                  lambda: collect_leaderboard.leaderboard_rows(**_leaderboard_inputs()))
    rows += _safe(DIAG_GROUP_RECORDER, "catalyst_feed", "Catalyst feed",
                  lambda: collect_catalysts.catalyst_feed_rows(status=_catalyst_feed_status(), now=ts))
    rows += _safe(DIAG_GROUP_RECORDER, "borrow_feed", "Borrow feed",
                  lambda: collect_borrow.borrow_feed_rows(status=_borrow_feed_status(), now=ts))
    rows += _safe(DIAG_GROUP_PRACTICE, "practice", "Practice", lambda: collect.practice_rows(**_practice_inputs()))
    rows += collect.frontend_rows(ui_tag=ui_tag, backend_tag=facts.get("release_tag"))
    rows += _safe(DIAG_GROUP_PERFORMANCE, "perf_recorder", "Performance recorder", lambda: _perf_rows(ts))
    return {
        "schema_version": DIAG_SCHEMA_VERSION,
        "generated_at": ts,
        "groups": [{"id": gid, "title": title} for gid, title in DIAG_GROUPS],
        "counts": counts(rows),
        "rows": rows,
        "process": {
            "pid": facts.get("pid"),
            "instance_id": facts.get("instance_id"),
            "release_tag": facts.get("release_tag"),
            "repo_root": facts.get("repo_root"),
            "env_file": facts.get("env_file"),
        },
    }
