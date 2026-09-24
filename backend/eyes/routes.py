"""The eyes' routes (ADR 029). Read-only towards the market: nothing here places,
stages or cancels an order. The desk draws the eyes through ``/ws/setups`` (the
Sim eyes off the live edge); these routes are for agents and tools.

  GET  /api/eyes/journal             the journal's writer and its days
  GET  /api/eyes/at?date=&at=        every setup card as the live eyes had it at ``at`` (epoch seconds)
  GET  /api/eyes/sim                 what the Sim eyes are following
  GET  /api/eyes/backtests           recent backtest runs, newest first
  POST /api/eyes/backtests           {setup?, templates?: [id], sessions?: [{date, symbol}]} -> 202 {run_id}
  GET  /api/eyes/backtests/{run_id}  a run's manifest and summary
"""
from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException

from eyes import backtest, journal, reader
from eyes.sim_eyes import get_sim_eyes

router = APIRouter(tags=["eyes"])
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@router.get("/api/eyes/journal")
def journal_status() -> dict[str, Any]:
    return {"writer": journal.status(), "days": reader.days(journal.journal_dir())}


@router.get("/api/eyes/at")
def eyes_at(date: str, at: float) -> dict[str, Any]:
    """The live journal of ``date`` folded to ``at`` (``eyes/playback.py``): never a line after it."""
    if not _DATE.match(date):
        raise HTTPException(400, {"reason": "EYES_DATE_INVALID", "error": "date is YYYY-MM-DD"})
    from eyes.playback import board_at, template_window
    from setup_scanner.hooks import default_levels
    from setup_templates.store import get_store

    return board_at(journal.journal_dir() / f"{date}.jsonl", date, at, levels=default_levels(),
                    window_of=template_window(get_store()))


@router.get("/api/eyes/sim")
def sim_status() -> dict[str, Any]:
    return get_sim_eyes().status()


@router.get("/api/eyes/backtests")
def list_backtests() -> dict[str, Any]:
    return {"dir": str(backtest.backtests_dir()), "runs": backtest.list_runs()}


@router.post("/api/eyes/backtests", status_code=202)
def start_backtest(payload: Annotated[dict[str, Any] | None, Body()] = None) -> dict[str, Any]:
    """An unknown template is refused by the templates' own handler (``setup_templates.routes.install``)."""
    payload = payload or {}
    template_ids = payload.get("templates")
    if template_ids is not None and not (isinstance(template_ids, list) and all(isinstance(t, str) for t in template_ids)):
        raise HTTPException(400, {"reason": "BACKTEST_INVALID", "error": "templates is a list of template ids"})
    sessions = None
    if payload.get("sessions") is not None:
        raw = payload["sessions"]
        if not isinstance(raw, list) or not all(
                isinstance(s, dict) and _DATE.match(str(s.get("date") or "")) and str(s.get("symbol") or "").strip()
                for s in raw):
            raise HTTPException(400, {"reason": "BACKTEST_INVALID",
                                      "error": "sessions is a list of {date: YYYY-MM-DD, symbol}"})
        sessions = [(str(s["date"]), str(s["symbol"]).strip().upper()) for s in raw]
    setup = payload.get("setup") or "first_pullback"
    if not isinstance(setup, str):
        raise HTTPException(400, {"reason": "BACKTEST_INVALID", "error": "setup is a setup id"})
    return backtest.start(template_ids=template_ids, sessions=sessions, setup=setup)


@router.get("/api/eyes/backtests/{run_id}")
def get_backtest(run_id: str) -> dict[str, Any]:
    manifest = backtest.read_manifest(run_id)
    if manifest is None:
        raise HTTPException(404, {"reason": "BACKTEST_UNKNOWN", "error": "no backtest run by that id"})
    return {"manifest": manifest, "summary": backtest.read_summary(run_id)}
