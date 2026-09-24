"""The operator's focus over HTTP (ADR 033): desk windows report, agents and bots read.

``POST /sensors/focus`` takes one report -- a desk window's (``role`` main |
popout | browser) or the Electron main process's (``role`` electron); ``GET
/sensors/focus`` is sensor 19. Read-only with respect to trading.
"""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError, field_validator

from constants_sensors import (
    FOCUS_MAX_TABS,
    FOCUS_MAX_WINDOWS,
    FOCUS_PAGES,
    FOCUS_REASONS,
    FOCUS_REPORT_MAX_BODY_BYTES,
    FOCUS_SCHEMA_VERSION,
    FOCUS_SYMBOL_SOURCES,
)
from sensors import focus_store
from sensors.registry import read_one

router = APIRouter(tags=["sensors"])

_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_SYMBOL = re.compile(r"^[A-Z][A-Z0-9./-]{0,11}$")


def _id(value: str | None) -> str | None:
    if value is not None and not _ID.match(value):
        raise ValueError("must be 1-64 of [A-Za-z0-9_.:-]")
    return value


def _symbol(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    value = value.strip().upper()
    if not _SYMBOL.match(value):
        raise ValueError(f"not a ticker: {value!r}")
    return value


def _check_version(value: int) -> int:
    if value != FOCUS_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {FOCUS_SCHEMA_VERSION}")
    return value


def _one_of(value: str | None, allowed: tuple[str, ...]) -> str | None:
    if value is not None and value not in allowed:
        raise ValueError(f"must be one of {', '.join(allowed)}")
    return value


class WindowReport(BaseModel):
    schema_version: int
    role: str
    window_id: str
    instance_id: str
    focused: bool
    visible: bool
    page: str | None = None
    tab: str | None = None
    symbol: str | None = None
    symbol_source: str | None = None
    trader_tabs: list[str] = Field(default_factory=list, max_length=FOCUS_MAX_TABS)
    last_input_ts: float | None = Field(default=None, ge=0)
    reason: str
    ui_tag: str | None = Field(default=None, max_length=64)

    @field_validator("schema_version")
    @classmethod
    def _version(cls, v: int) -> int:
        return _check_version(v)

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        return _one_of(v, ("main", "popout", "browser"))

    @field_validator("window_id", "instance_id", "tab")
    @classmethod
    def _ids(cls, v: str | None) -> str | None:
        return _id(v)

    @field_validator("symbol")
    @classmethod
    def _sym(cls, v: str | None) -> str | None:
        return _symbol(v)

    @field_validator("trader_tabs")
    @classmethod
    def _tabs(cls, v: list[str]) -> list[str]:
        return [s for s in (_symbol(t) for t in v) if s]

    @field_validator("page")
    @classmethod
    def _page(cls, v: str | None) -> str | None:
        return _one_of(v, FOCUS_PAGES)

    @field_validator("symbol_source")
    @classmethod
    def _source(cls, v: str | None) -> str | None:
        return _one_of(v, FOCUS_SYMBOL_SOURCES)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        return _one_of(v, FOCUS_REASONS)


class Display(BaseModel):
    id: str = Field(max_length=32)
    label: str | None = Field(default=None, max_length=120)
    index: int = Field(ge=1, le=FOCUS_MAX_WINDOWS)
    count: int = Field(ge=1, le=FOCUS_MAX_WINDOWS)
    primary: bool
    scale_factor: float | None = Field(default=None, gt=0, le=8)


class OsWindow(BaseModel):
    window_id: str
    focused: bool
    visible: bool
    minimized: bool
    display: Display | None = None

    @field_validator("window_id")
    @classmethod
    def _wid(cls, v: str) -> str:
        return _id(v)


class ElectronReport(BaseModel):
    schema_version: int
    role: str
    window_id: str
    app_focused: bool
    focused_window_id: str | None = None
    windows: list[OsWindow] = Field(default_factory=list, max_length=FOCUS_MAX_WINDOWS)
    reason: str

    @field_validator("schema_version")
    @classmethod
    def _version(cls, v: int) -> int:
        return _check_version(v)

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        return _one_of(v, ("electron",))

    @field_validator("window_id", "focused_window_id")
    @classmethod
    def _ids(cls, v: str | None) -> str | None:
        return _id(v)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        return _one_of(v, FOCUS_REASONS)


@router.get("/sensors/focus")
def sensor_focus() -> dict:
    return read_one("focus", None)


@router.post("/sensors/focus")
async def sensor_focus_report(request: Request) -> dict:
    body = await request.body()
    if len(body) > FOCUS_REPORT_MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail=f"report over {FOCUS_REPORT_MAX_BODY_BYTES} bytes")
    try:
        raw = json.loads(body)
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(status_code=422, detail="report is not JSON") from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="report must be an object")
    try:
        if raw.get("role") == "electron":
            focus_store.record_electron(ElectronReport.model_validate(raw).model_dump())
        else:
            focus_store.record_window(WindowReport.model_validate(raw).model_dump())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False, include_context=False)) from exc
    return {"ok": True}
