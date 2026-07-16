"""
Backtest REST routes (Phase E).

Thin handlers — logic lives in ``backend/backtest/``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from archive.health import list_local_cold_days
from backtest.engine import run_backtest
from constants import BACKTEST_DEFAULT_SETUP, BACKTEST_SETUP_NAMES

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class BacktestRunRequest(BaseModel):
    session_date: str
    setup: str = Field(default=BACKTEST_DEFAULT_SETUP)
    symbols: list[str] | None = None


def _require_session_date(session_date: str) -> None:
    if len(session_date) != 10 or session_date[4] != "-" or session_date[7] != "-":
        raise HTTPException(status_code=400, detail="session_date must be YYYY-MM-DD")


def _validate_setup(setup: str) -> None:
    if setup not in BACKTEST_SETUP_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"setup must be one of {list(BACKTEST_SETUP_NAMES)}",
        )


@router.get("/health")
def get_backtest_health() -> dict:
    """Scorer availability and local cold-archive day count."""
    days = list_local_cold_days()
    return {
        "ok": True,
        "scorer": "nova-native",
        "vectorbt_required": False,
        "cold_day_count": len(days),
        "cold_days_sample": days[-5:] if days else [],
    }


@router.get("/days")
def get_backtest_days() -> dict:
    """List local cold archive session dates (proxy via archive.health)."""
    days = list_local_cold_days()
    return {"days": days, "count": len(days)}


@router.post("/run")
def post_backtest_run(body: BacktestRunRequest) -> dict:
    """Run a no-hindsight backtest for one archived session day."""
    _require_session_date(body.session_date)
    _validate_setup(body.setup)
    result = run_backtest(
        body.session_date,
        setup=body.setup,
        symbols=body.symbols,
    )
    if not result.get("ok") and result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result
