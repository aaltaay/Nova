"""Filing an issue from the desk over HTTP. Nothing here places, stages or cancels an order.

  GET  /api/issues/draft                 a fresh draft: the kinds, the context and the dump it
                                         would attach (scrubbed), the title Nova would write,
                                         whether the desk can file by itself (and as whom)
  GET  /api/issues/draft/{draft_id}/dump the draft's dump, exactly as it would be uploaded
  POST /api/issues                       {schema_version, kind, title, details, context | null,
                                          draft_id, attach_dump} -> the issue

A refusal is ``{"detail": {"reason": CODE, "error": "...", "field": KEY | null,
"new_issue_url": URL | null}}``; ``new_issue_url`` is GitHub's new-issue page prefilled with
the same issue, for the operator to submit there. The POST needs the desk's API key even on
loopback (``auth.py``): it publishes on a public repository as the operator.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from constants_issue_report import (
    ISSUE_REPORT_BODY_MAX_BYTES,
    ISSUE_REPORT_DETAILS_MAX,
    ISSUE_REPORT_KINDS,
    ISSUE_REPORT_REPO,
    ISSUE_REPORT_SCHEMA_VERSION,
    ISSUE_REPORT_TITLE_MAX,
)
from issue_report import compose, context, drafts, gh_filer

logger = logging.getLogger(__name__)
router = APIRouter(tags=["issues"])

_STATUS = {"ISSUE_INVALID": 400, "ISSUE_DRAFT_EXPIRED": 409, "ISSUE_FILER_UNAVAILABLE": 503,
           "ISSUE_FILE_FAILED": 502, "ISSUE_FILE_UNCONFIRMED": 502}
_DUMP_SECTIONS = ["Desk checklist: every check's state and cause", "Engine log: the latest warnings and errors",
                  "Errors the desk windows reported", "The windows open now: page and symbol"]


def _refusal(code: str, message: str, *, field: str | None = None, url: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=_STATUS.get(code, 400),
                        content={"detail": {"reason": code, "error": message, "field": field, "new_issue_url": url}})


@router.get("/api/issues/draft")
async def issue_draft() -> dict[str, Any]:
    draft, filer = await asyncio.gather(asyncio.to_thread(drafts.build), asyncio.to_thread(gh_filer.status))
    dump = draft.dump
    return {
        "schema_version": ISSUE_REPORT_SCHEMA_VERSION,
        "repo": ISSUE_REPORT_REPO,
        "public": True,
        "filer": filer,
        "kinds": [{"id": k, "label": label, "github_label": gl} for k, (label, gl) in ISSUE_REPORT_KINDS.items()],
        "context": draft.context,
        "context_lines": compose.context_lines(draft.context),
        "limits": {"title_max": ISSUE_REPORT_TITLE_MAX, "details_max": ISSUE_REPORT_DETAILS_MAX},
        "draft_id": draft.id,
        "created_at": draft.created,
        "auto_title": compose.auto_title("bug", "", dump, draft.context, draft.created),
        "dump": {"file_name": dump.file_name, "bytes": len(dump.text.encode("utf-8")), "summary": dump.summary,
                 "sections": _DUMP_SECTIONS},
    }


@router.get("/api/issues/draft/{draft_id}/dump", response_class=PlainTextResponse)
async def issue_draft_dump(draft_id: str) -> str:
    draft = drafts.get(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="this draft has expired -- open the form again")
    return draft.dump.text


def _compose(form: dict[str, Any], draft: drafts.Draft | None, filed_at: float,
             link: compose.DumpLink | None) -> compose.Composed:
    return compose.compose_issue(kind=form.get("kind"), title=form.get("title"), details=form.get("details"),
                                 context=form.get("context"), filed_at=filed_at, scrubber=context.scrubber(),
                                 dump=draft.dump if draft else None, dump_link=link)


async def _upload(draft: drafts.Draft) -> compose.DumpLink:
    """The dump as a secret gist, and a copy on the desk; a failed upload still files the issue."""
    saved = await asyncio.to_thread(drafts.save_copy, draft.dump)
    try:
        url = await asyncio.to_thread(gh_filer.create_gist, draft.dump.file_name, draft.dump.text,
                                      f"Nova desk dump for {ISSUE_REPORT_REPO} -- {draft.dump.file_name}")
        return compose.DumpLink(draft.dump.file_name, url, None, saved)
    except gh_filer.FilerError as refusal:
        return compose.DumpLink(draft.dump.file_name, None, refusal.message, saved)


@router.post("/api/issues", status_code=201, response_model=None)
async def file_issue(request: Request) -> dict[str, Any] | JSONResponse:
    raw = await request.body()
    if len(raw) > ISSUE_REPORT_BODY_MAX_BYTES:
        return _refusal("ISSUE_INVALID", f"the request is larger than {ISSUE_REPORT_BODY_MAX_BYTES} bytes")
    try:
        form = json.loads(raw)
    except ValueError:
        return _refusal("ISSUE_INVALID", "the request is not JSON")
    if not isinstance(form, dict):
        return _refusal("ISSUE_INVALID", "the request is not a JSON object")
    if form.get("schema_version") != ISSUE_REPORT_SCHEMA_VERSION:
        return _refusal("ISSUE_INVALID", f"schema_version must be {ISSUE_REPORT_SCHEMA_VERSION}", field="schema_version")
    draft = None
    if form.get("attach_dump"):
        draft = drafts.get(form.get("draft_id"))
        if draft is None:
            return _refusal("ISSUE_DRAFT_EXPIRED", "the dump you previewed has expired -- Nova built a new one; "
                            "look it over and file again", field="draft_id")
    filed_at = time.time()
    try:
        # Check the form before anything is uploaded.
        _compose(form, draft, filed_at, None)
    except compose.IssueError as refusal:
        return _refusal(refusal.code, refusal.message, field=refusal.field)
    link = await _upload(draft) if draft is not None else None
    issue = _compose(form, draft, filed_at, link)
    try:
        created = await asyncio.to_thread(gh_filer.file_issue, issue.title, issue.body, issue.labels)
    except gh_filer.FilerError as refusal:
        url = None if refusal.code == "ISSUE_FILE_UNCONFIRMED" else compose.new_issue_url(issue)
        return _refusal(refusal.code, refusal.message, url=url)
    logger.info("issue_report: filed %s #%s (%s), dump %s, %d value(s) removed from the typed text",
                issue.kind, created["number"], created["url"], (link.url or link.error) if link else "not attached",
                issue.removed)
    return {
        "schema_version": ISSUE_REPORT_SCHEMA_VERSION,
        "number": created["number"],
        "url": created["url"],
        "kind": issue.kind,
        "title": issue.title,
        "labels": issue.labels,
        "auto_title": issue.auto_title,
        "auto_description": issue.auto_description,
        "removed": issue.removed,
        "dump": None if link is None else {"file_name": link.file_name, "url": link.url, "error": link.error,
                                           "saved": link.saved},
        "via": "gh",
    }
