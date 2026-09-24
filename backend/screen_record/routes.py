"""The trading screen recording over HTTP (ADR 035).

``POST /api/screen-record`` takes the desktop app's status report (its
``view()``; shape in AGENTS.md §3); ``GET /api/screen-record`` answers the
newest one with its age, for agents and the checklist. Neither starts, stops
or pauses anything.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from constants_screen_record import (
    SCREEN_RECORD_DIR_SOURCES,
    SCREEN_RECORD_MAX_DISPLAYS,
    SCREEN_RECORD_MAX_PROBLEMS,
    SCREEN_RECORD_REPORT_MAX_BODY_BYTES,
    SCREEN_RECORD_SCHEMA_VERSION,
    SCREEN_RECORD_STATES,
)
from screen_record import store

router = APIRouter(tags=["screen-record"])


class Display(BaseModel):
    model_config = ConfigDict(extra="allow")
    index: int = Field(ge=1, le=SCREEN_RECORD_MAX_DISPLAYS)
    recording: bool
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    error: str | None = Field(default=None, max_length=500)


class Disk(BaseModel):
    model_config = ConfigDict(extra="allow")
    free_bytes: float | None = Field(default=None, ge=0)
    error: str | None = Field(default=None, max_length=500)


class Report(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: int
    state: str
    recording: bool
    since: float | None = Field(default=None, ge=0)
    error: str | None = Field(default=None, max_length=500)
    dir: str = Field(max_length=500)
    dir_source: str
    dir_note: str | None = Field(default=None, max_length=500)
    mime: str | None = Field(default=None, max_length=80)
    fps: float = Field(ge=0)
    displays: list[Display] = Field(default_factory=list, max_length=SCREEN_RECORD_MAX_DISPLAYS)
    disk: Disk = Field(default_factory=Disk)
    problems: list[dict] = Field(default_factory=list, max_length=SCREEN_RECORD_MAX_PROBLEMS)
    restarts: int = Field(default=0, ge=0)

    @field_validator("schema_version")
    @classmethod
    def _version(cls, v: int) -> int:
        if v != SCREEN_RECORD_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCREEN_RECORD_SCHEMA_VERSION}")
        return v

    @field_validator("state")
    @classmethod
    def _state(cls, v: str) -> str:
        if v not in SCREEN_RECORD_STATES:
            raise ValueError(f"must be one of {', '.join(SCREEN_RECORD_STATES)}")
        return v

    @field_validator("dir_source")
    @classmethod
    def _source(cls, v: str) -> str:
        if v not in SCREEN_RECORD_DIR_SOURCES:
            raise ValueError(f"must be one of {', '.join(SCREEN_RECORD_DIR_SOURCES)}")
        return v


@router.get("/api/screen-record")
def screen_record_status() -> dict:
    return store.status()


@router.post("/api/screen-record")
async def screen_record_report(request: Request) -> dict:
    body = await request.body()
    if len(body) > SCREEN_RECORD_REPORT_MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail=f"report over {SCREEN_RECORD_REPORT_MAX_BODY_BYTES} bytes")
    try:
        raw = json.loads(body)
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(status_code=422, detail="report is not JSON") from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="report must be an object")
    try:
        store.record(Report.model_validate(raw).model_dump())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False, include_context=False)) from exc
    return {"ok": True}
