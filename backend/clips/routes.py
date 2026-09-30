"""Share clips over HTTP (ADR 039).

``POST /api/clips`` takes the desktop app's clip view (its ``view()``; shape in
AGENTS.md §3, "Share clips"); ``GET /api/clips`` answers the newest one with its
age, for agents and the checklist. Neither starts, stops, exports nor deletes
anything.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from clips import store
from constants_clips import (
    CLIPS_DIR_SOURCES,
    CLIPS_MAX_OPEN,
    CLIPS_MAX_ROWS,
    CLIPS_OPEN_STATES,
    CLIPS_REPORT_MAX_BODY_BYTES,
    CLIPS_SCHEMA_VERSION,
)

router = APIRouter(tags=["clips"])


class OpenClip(BaseModel):
    model_config = ConfigDict(extra="allow")
    clip_id: str = Field(max_length=80)
    symbol: str = Field(max_length=12)
    started_ts: float = Field(ge=0)
    state: str
    hq: dict | None = None

    @field_validator("state")
    @classmethod
    def _state(cls, v: str) -> str:
        if v not in CLIPS_OPEN_STATES:
            raise ValueError(f"must be one of {', '.join(CLIPS_OPEN_STATES)}")
        return v


class View(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: int
    generated_at: float = Field(ge=0)
    dir: str = Field(max_length=500)
    dir_source: str
    dir_error: str | None = Field(default=None, max_length=500)
    hq_max: int = Field(ge=0)
    hq_in_use: int = Field(ge=0)
    open: list[OpenClip] = Field(default_factory=list, max_length=CLIPS_MAX_OPEN)
    clips: list[dict] = Field(default_factory=list, max_length=CLIPS_MAX_ROWS)

    @field_validator("schema_version")
    @classmethod
    def _version(cls, v: int) -> int:
        if v != CLIPS_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {CLIPS_SCHEMA_VERSION}")
        return v

    @field_validator("dir_source")
    @classmethod
    def _source(cls, v: str) -> str:
        if v not in CLIPS_DIR_SOURCES:
            raise ValueError(f"must be one of {', '.join(CLIPS_DIR_SOURCES)}")
        return v


@router.get("/api/clips")
def clips_status() -> dict:
    return store.status()


@router.post("/api/clips")
async def clips_report(request: Request) -> dict:
    body = await request.body()
    if len(body) > CLIPS_REPORT_MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail=f"view over {CLIPS_REPORT_MAX_BODY_BYTES} bytes")
    try:
        raw = json.loads(body)
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(status_code=422, detail="view is not JSON") from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="view must be an object")
    try:
        store.record(View.model_validate(raw).model_dump())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False, include_context=False)) from exc
    return {"ok": True}
