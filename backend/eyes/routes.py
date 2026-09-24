"""The eyes' routes (ADR 029). Read-only towards the market: nothing here places,
stages or cancels an order, and nothing here is drawn by the desk yet.

  GET  /api/eyes/journal             the journal's writer and its days
  GET  /api/eyes/sim                 what the Sim eyes are following
  GET  /api/eyes/backtests           recent backtest runs, newest first
  POST /api/eyes/backtests           {templates?: [id], sessions?: [{date, symbol}]} -> 202 {run_id}
  GET  /api/eyes/backtests/{run_id}  a run's manifest and summary
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from eyes import backtest, journal, reader
from eyes.sim_eyes import get_sim_eyes
from setup_templates.catalogue import TemplateError

router = APIRouter(tags=["eyes"])
_RUN_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@router.get("/api/eyes/journal")
def journal_status() -> dict[str, Any]:
    return {"writer": journal.status(), "days": reader.days(journal.journal_dir())}


@router.get("/api/eyes/sim")
def sim_status() -> dict[str, Any]:
    return get_sim_eyes().status()


@router.get("/api/eyes/backtests")
def list_backtests() -> dict[str, Any]:
    return {"dir": str(backtest.backtests_dir()), "runs": backtest.list_runs()}


@router.post("/api/eyes/backtests", status_code=202)
def start_backtest(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
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
    try:
        return backtest.start(template_ids=template_ids, sessions=sessions)
    except TemplateError as exc:
        raise HTTPException(404, {"reason": exc.code, "error": str(exc), "field": exc.field}) from exc


@router.get("/api/eyes/backtests/{run_id}")
def get_backtest(run_id: str) -> dict[str, Any]:
    if not _RUN_ID.match(run_id):
        raise HTTPException(404, {"reason": "BACKTEST_UNKNOWN", "error": f"no backtest run {run_id!r}"})
    manifest = backtest.read_manifest(run_id)
    if manifest is None:
        raise HTTPException(404, {"reason": "BACKTEST_UNKNOWN", "error": f"no backtest run {run_id!r}"})
    return {"manifest": manifest, "summary": backtest.read_summary(run_id)}
