"""Chart drawing persistence routes (ADR 015).

Endpoints:
  GET    /api/chart-drawings/{symbol}
  PUT    /api/chart-drawings/{symbol}
  DELETE /api/chart-drawings/{symbol}

Thin facade -- all validation and persistence lives in ``chart_drawings.py``.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import chart_drawings as _chart_drawings

router = APIRouter(tags=["chart-drawings"])


class ChartDrawingsBody(BaseModel):
    """Whole-list replace payload -- the client's ``exportDrawings()`` snapshot."""

    drawings: list[dict[str, Any]]


@router.get("/api/chart-drawings/{symbol}")
def get_chart_drawings(symbol: str):
    try:
        return {
            "symbol": symbol.strip().upper(),
            "drawings": _chart_drawings.get_drawings(symbol),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/chart-drawings/{symbol}")
def put_chart_drawings(symbol: str, body: ChartDrawingsBody):
    try:
        saved = _chart_drawings.replace_drawings(symbol, body.drawings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"symbol": symbol.strip().upper(), "drawings": saved}


@router.delete("/api/chart-drawings/{symbol}")
def delete_chart_drawings(symbol: str):
    try:
        _chart_drawings.clear_drawings(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"symbol": symbol.strip().upper(), "drawings": []}
