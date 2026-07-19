"""
Paper-execution control routes — Nova OS P4 control modes + emergency controls.

Endpoints:
  GET  /api/strategy/executor/status
  POST /api/strategy/executor/mode              {mode}
  POST /api/strategy/executor/arm               → confirm (legacy)
  POST /api/strategy/executor/disarm            → signal
  POST /api/strategy/executor/kill-switch
  POST /api/strategy/executor/reset-kill-switch
  GET  /api/strategy/executor/staged
  POST /api/strategy/executor/staged/{id}/approve
  POST /api/strategy/executor/staged/{id}/reject  {reason?}
  POST /api/strategy/executor/cancel-working-entry {symbol}
  GET  /api/strategy/executor/flatten-preview
  POST /api/strategy/executor/flatten           {confirm_token}
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import require_auth
from nova_os import control_mode as _control_mode
from nova_os import staged_tickets as _staged
from strategy import executor as _executor

router = APIRouter(prefix="/api/strategy/executor", tags=["executor"])


class ModeBody(BaseModel):
    mode: str


class RejectBody(BaseModel):
    reason: str = "rejected"


class SymbolBody(BaseModel):
    symbol: str


class FlattenBody(BaseModel):
    confirm_token: str = Field(..., description="Must equal FLATTEN")


@router.get("/status")
def executor_status() -> dict:
    return _executor.status()


@router.post("/mode", dependencies=[Depends(require_auth)])
def executor_set_mode(body: ModeBody) -> dict:
    try:
        _control_mode.set_mode(body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _executor.status()


@router.post("/arm", dependencies=[Depends(require_auth)])
def executor_arm() -> dict:
    try:
        return _executor.arm()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/disarm", dependencies=[Depends(require_auth)])
def executor_disarm() -> dict:
    return _executor.disarm()


@router.post("/kill-switch", dependencies=[Depends(require_auth)])
def executor_kill_switch() -> dict:
    return _executor.kill_switch()


@router.post("/reset-kill-switch", dependencies=[Depends(require_auth)])
def executor_reset_kill_switch() -> dict:
    return _executor.reset_kill_switch()


@router.get("/staged")
def executor_list_staged() -> dict:
    _staged.expire_due()
    tickets = [t.to_dict() for t in _staged.list_staged()]
    return {"count": len(tickets), "staged": tickets}


@router.post("/staged/{ticket_id}/approve", dependencies=[Depends(require_auth)])
def executor_approve_staged(ticket_id: str) -> dict:
    try:
        return _staged.approve(ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/staged/{ticket_id}/reject", dependencies=[Depends(require_auth)])
def executor_reject_staged(ticket_id: str, body: RejectBody | None = None) -> dict:
    reason = body.reason if body else "rejected"
    result = _staged.reject(ticket_id, reason=reason)
    if result is None:
        raise HTTPException(status_code=404, detail=f"staged ticket not found: {ticket_id}")
    return result


@router.post("/cancel-working-entry", dependencies=[Depends(require_auth)])
def executor_cancel_working_entry(body: SymbolBody) -> dict:
    return _executor.cancel_working_entry(body.symbol)


@router.get("/flatten-preview")
def executor_flatten_preview() -> dict:
    return _executor.flatten_preview()


@router.post("/flatten", dependencies=[Depends(require_auth)])
def executor_flatten(body: FlattenBody) -> dict:
    try:
        return _executor.flatten_positions(body.confirm_token)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
