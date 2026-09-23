"""``/api/perf/*`` (ADR 026). Read-only except the window reports it takes in."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError, field_validator

from constants_perf import (
    PERF_CLIENT_MAX_BODY_BYTES,
    PERF_CLIENT_MAX_KEYS,
    PERF_CLIENT_MAX_PROCESSES,
    PERF_CLIENT_TOP_SCRIPTS,
    PERF_LIVE_DEFAULT_SEC,
    PERF_RING_SEC,
    PERF_SCHEMA_VERSION,
    PERF_STALLS_DIR_NAME,
)
from perf import recorder

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/perf", tags=["perf"])

_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_STALL_ID = re.compile(r"^\d{10,16}-(ib|http)$")
_TEXT = 200


class Frames(BaseModel):
    count: int = Field(ge=0)
    slow: int = Field(ge=0)
    p95_ms: float | None = Field(default=None, ge=0)


class Script(BaseModel):
    source: str = Field(max_length=_TEXT)
    invoker: str = Field(default="", max_length=_TEXT)
    ms: float = Field(ge=0)


class LongFrames(BaseModel):
    count: int = Field(ge=0)
    blocking_ms: float = Field(ge=0)
    max_ms: float = Field(ge=0)
    top: list[Script] = Field(default_factory=list, max_length=PERF_CLIENT_TOP_SCRIPTS)


class SocketCount(BaseModel):
    messages: int = Field(ge=0)
    bytes: int = Field(ge=0)


class Process(BaseModel):
    type: str = Field(max_length=64)
    window_id: str | None = Field(default=None, max_length=64)
    pid: int = Field(ge=0)
    cpu_pct: float = Field(ge=0)
    working_set_mb: float = Field(ge=0)


class ClientReport(BaseModel):
    schema_version: Literal[1]
    window_id: str
    role: Literal["main", "popout", "browser", "electron"]
    visible: bool | None = None
    interval_sec: float = Field(ge=0, le=3600)
    ui_tag: str | None = Field(default=None, max_length=64)
    frames: Frames | None = None
    long_frames: LongFrames | None = None
    sockets: dict[str, SocketCount] = Field(default_factory=dict)
    renders: dict[str, int] = Field(default_factory=dict)
    heap_mb: float | None = Field(default=None, ge=0)
    dom_nodes: int | None = Field(default=None, ge=0)
    processes: list[Process] | None = Field(default=None, max_length=PERF_CLIENT_MAX_PROCESSES)

    @field_validator("window_id")
    @classmethod
    def _window_id(cls, v: str) -> str:
        if not _ID.match(v):
            raise ValueError("window_id must be 1-64 of [A-Za-z0-9_.:-]")
        return v

    @field_validator("sockets", "renders")
    @classmethod
    def _keys(cls, v: dict) -> dict:
        if len(v) > PERF_CLIENT_MAX_KEYS:
            raise ValueError(f"at most {PERF_CLIENT_MAX_KEYS} keys")
        for key in v:
            if not _ID.match(key):
                raise ValueError(f"bad key {key!r}")
        return v


@router.get("/live")
async def perf_live(seconds: float = Query(default=PERF_LIVE_DEFAULT_SEC, gt=0, le=PERF_RING_SEC)) -> dict:
    return {
        "schema_version": PERF_SCHEMA_VERSION,
        "generated_at": time.time(),
        "recorder": recorder.status(),
        "samples": recorder.samples(seconds),
        "stalls": recorder.stall_summaries(),
        "clients": recorder.clients(),
    }


@router.get("/stalls")
async def perf_stalls() -> dict:
    return {"schema_version": PERF_SCHEMA_VERSION, "stalls": recorder.stall_summaries()}


@router.get("/stalls/{stall_id}")
async def perf_stall(stall_id: str) -> dict:
    if not _STALL_ID.match(stall_id):
        raise HTTPException(status_code=404, detail="unknown stall id")
    report = recorder.stall_report(stall_id)
    if report is not None:
        return report
    root = recorder.status().get("dir")
    if root:
        report = await asyncio.to_thread(_read_stall_file, Path(root) / PERF_STALLS_DIR_NAME, stall_id)
        if report is not None:
            return report
    raise HTTPException(status_code=404, detail="unknown stall id")


def _read_stall_file(stalls_dir: Path, stall_id: str) -> dict | None:
    """A stall report kept on disk, found by listing its folder.

    The request's id is only compared with file names; it never becomes part
    of a path (CodeQL py/path-injection).
    """
    try:
        paths = list(stalls_dir.glob("*.json"))
    except OSError:
        logger.warning("perf: cannot list %s", stalls_dir, exc_info=True)
        return None
    for path in paths:
        if path.stem != stall_id:
            continue
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("perf: unreadable stall report %s", path, exc_info=True)
            return None
    return None


@router.post("/client")
async def perf_client(request: Request) -> dict:
    body = await request.body()
    if len(body) > PERF_CLIENT_MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail=f"report over {PERF_CLIENT_MAX_BODY_BYTES} bytes")
    try:
        report = ClientReport.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False, include_context=False)) from exc
    recorder.record_client(report.model_dump())
    return {"ok": True}
