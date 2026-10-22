"""The Congress page's routes (ADR 066): read-only but for the agreement; none waits on a site or the database."""
from __future__ import annotations

import re
import time

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from congress import board, consent, photos, refresh, roster, views
from congress.constants_congress import (
    CONGRESS_ERR_BAD_PARAM,
    CONGRESS_ERR_NO_PHOTO,
    CONGRESS_ERR_UNKNOWN_MEMBER,
    CONGRESS_FILTERS,
    CONGRESS_MAX_MEMBERS_PARAM,
    CONGRESS_SCHEMA_VERSION,
)
from congress.state import book, sources

router = APIRouter(tags=["congress"])
TICKER = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")


def _bad(field: str, error: str, status: int = 400, reason: str = CONGRESS_ERR_BAD_PARAM) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": {"reason": reason, "error": error, "field": field}})


def _read() -> tuple[int, dict, list, list[dict], set[str]]:
    version, reports, trades = book().snapshot()
    return version, reports, trades, roster.members(), photos.kept() if consent.given() else set()


def _sources(reports: dict, trades: list) -> list[dict]:
    out = []
    for s in sources():
        counts = board.source_counts(reports, trades, s.id) if s.id in ("house", "senate") else {}
        out.append(s.wire(counts))
    return out


@router.get("/api/congress/board")
def get_board(filter: str = "all", members: str = ""):  # noqa: A002 -- the query parameter's name on the wire
    if filter not in CONGRESS_FILTERS:
        return _bad("filter", f"filter must be one of {', '.join(CONGRESS_FILTERS)}")
    chosen = None
    if members.strip():
        ids = [m.strip() for m in members.split(",") if m.strip()]
        if len(ids) > CONGRESS_MAX_MEMBERS_PARAM or not all(photos.valid(i) for i in ids):
            return _bad("members", "members must be bioguide ids (A000000), comma-separated")
        chosen = frozenset(ids)
    now = time.time()
    refresh.start()
    version, reports, trades, members_list, kept = _read()
    blocks = board.compose(version, reports, trades, members_list, kept, refresh.today(now), filter, chosen,
                           roster.load().get("read_at"))
    return {"schema_version": CONGRESS_SCHEMA_VERSION, "generated_at": now, "enabled": refresh.enabled(),
            "consent": consent.wire(), "sources": _sources(reports, trades), **blocks}


@router.get("/api/congress/members")
def get_members():
    now = time.time()
    _, reports, trades, members_list, kept = _read()
    return {"schema_version": CONGRESS_SCHEMA_VERSION, "generated_at": now, "year": refresh.today(now).year,
            "members": views.members(reports, trades, members_list, kept, refresh.today(now))}


@router.get("/api/congress/member/{bioguide}")
def get_member(bioguide: str):
    now = time.time()
    _, reports, trades, members_list, kept = _read()
    found = views.member(bioguide, reports, trades, {m["bioguide"]: m for m in members_list}, kept, refresh.today(now))
    if found is None:
        return _bad("bioguide", f"no member {bioguide} is known", 404, CONGRESS_ERR_UNKNOWN_MEMBER)
    return {"schema_version": CONGRESS_SCHEMA_VERSION, "generated_at": now, **found}


@router.get("/api/congress/trades")
def get_trades(ticker: str = ""):
    symbol = ticker.strip().upper()
    if not TICKER.match(symbol):
        return _bad("ticker", "ticker must be 1 to 10 of A-Z, 0-9, '.' and '-'")
    _, _, trades, members_list, kept = _read()
    return {"schema_version": CONGRESS_SCHEMA_VERSION, "generated_at": time.time(),
            **views.ticker(symbol, trades, {m["bioguide"]: m for m in members_list}, kept)}


@router.get("/api/congress/photo/{bioguide}")
def get_photo(bioguide: str):
    f = photos.kept_file(bioguide)
    if f is None:
        return _bad("bioguide", f"no portrait is kept for {bioguide}", 404, CONGRESS_ERR_NO_PHOTO)
    return FileResponse(f, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@router.post("/api/congress/consent")
async def post_consent(request: Request):
    try:
        body = await request.json()
    except ValueError:
        body = None
    accept = body.get("accept") if isinstance(body, dict) else None
    if not isinstance(accept, bool):
        return _bad("accept", "accept must be true or false")
    if accept:
        consent.accept()
        refresh.wake()
    else:
        consent.withdraw()
    return {"schema_version": CONGRESS_SCHEMA_VERSION, "consent": consent.wire()}
