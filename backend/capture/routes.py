"""Capture HTTP routes."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from capture.mode import set_capture_mode, status_payload
from capture.recorder import status as recorder_status
from capture.sessions import list_sessions

router = APIRouter(tags=["capture"])


class CaptureToggleRequest(BaseModel):
    enabled: bool
    symbol: str | None = Field(default=None, description="Symbol to record; set Monday morning")


@router.get("/api/capture")
def get_capture() -> dict:
    return {**status_payload(), "recorder": recorder_status()}


@router.post("/api/capture")
def post_capture(body: CaptureToggleRequest) -> dict:
    out = set_capture_mode(body.enabled, symbol=body.symbol)
    return {**out, "recorder": recorder_status()}


@router.get("/api/capture/sessions")
def get_capture_sessions() -> dict:
    """List recorded days/tickers under the capture root for Sim replay pickers."""
    return list_sessions()
