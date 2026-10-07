"""``GET /api/short-proof``: the Live short proof's checklist (ADR 048 step 6). Read-only."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from short_proof import view as _view

router = APIRouter(prefix="/api", tags=["shorts"])


@router.get("/short-proof")
def short_proof() -> dict[str, Any]:
    """The operator's steps before a short may go to Live, each ticked from what Nova sees."""
    return _view.view()
