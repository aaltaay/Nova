"""
Paper-execution control routes (Phase D) -- arm/disarm/kill-switch/status for
backend/strategy/executor.py. These are the ONLY endpoints that can turn
automated order placement on. Every response includes the plain-language
disclosure of exactly what "armed" does, per the transparency principle in
knowledge/obsidian/03-Nova-Decisions/Automation-Strategy-Backbone.md.

Endpoints:
  GET  /api/strategy/executor/status         -- armed / kill-switch / open positions
  POST /api/strategy/executor/arm             -- start placing paper bracket orders
  POST /api/strategy/executor/disarm          -- back to display-only signals
  POST /api/strategy/executor/kill-switch     -- disarm + cancel open bracket orders
  POST /api/strategy/executor/reset-kill-switch -- clear the tripped flag (does not re-arm)
"""
from __future__ import annotations

from fastapi import APIRouter

from strategy import executor as _executor

router = APIRouter(prefix="/api/strategy/executor", tags=["executor"])


@router.get("/status")
def executor_status() -> dict:
    return _executor.status()


@router.post("/arm")
def executor_arm() -> dict:
    return _executor.arm()


@router.post("/disarm")
def executor_disarm() -> dict:
    return _executor.disarm()


@router.post("/kill-switch")
def executor_kill_switch() -> dict:
    return _executor.kill_switch()


@router.post("/reset-kill-switch")
def executor_reset_kill_switch() -> dict:
    return _executor.reset_kill_switch()
