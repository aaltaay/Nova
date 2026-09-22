"""``GET /api/diagnostics`` and ``GET /api/diagnostics/bundle`` (ADR 021).

Read-only. Thin handlers -- the shell is ``diagnostics.gather``.
"""
from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from constants_diagnostics import DIAG_UI_TAG_PARAM
from diagnostics.bundle import render_bundle
from diagnostics.gather import gather

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


@router.get("")
async def diagnostics_checklist(ui: str | None = Query(default=None, alias=DIAG_UI_TAG_PARAM)) -> dict:
    """The grouped checklist of facts: every row with state, cause, fix, evidence."""
    return gather(ui_tag=ui)


@router.get("/bundle", response_class=PlainTextResponse)
async def diagnostics_bundle(ui: str | None = Query(default=None, alias=DIAG_UI_TAG_PARAM)) -> str:
    """The same checklist as plain text for copy/paste into an issue."""
    return render_bundle(gather(ui_tag=ui))
