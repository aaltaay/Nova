"""``GET /api/diagnostics`` and ``GET /api/diagnostics/bundle`` (ADR 021).

Read-only. Thin handlers -- the shell is ``diagnostics.gather``, which runs on
a worker thread: it probes both Gateway ports over TCP, and a dark port costs
the whole probe timeout (Windows retries the refused connect). On the HTTP
loop that froze every desk socket and REST reply for each 5 s poll of the open
checklist.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from constants_diagnostics import DIAG_UI_TAG_PARAM
from diagnostics.bundle import render_bundle
from diagnostics.gather import gather

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


@router.get("")
async def diagnostics_checklist(ui: str | None = Query(default=None, alias=DIAG_UI_TAG_PARAM)) -> dict:
    """The grouped checklist of facts: every row with state, cause, fix, evidence."""
    return await asyncio.to_thread(gather, ui_tag=ui)


@router.get("/bundle", response_class=PlainTextResponse)
async def diagnostics_bundle(ui: str | None = Query(default=None, alias=DIAG_UI_TAG_PARAM)) -> str:
    """The same checklist as plain text for copy/paste into an issue."""
    return render_bundle(await asyncio.to_thread(gather, ui_tag=ui))
