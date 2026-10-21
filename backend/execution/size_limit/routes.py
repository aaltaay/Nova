"""The order size limit on the wire: ``GET`` and ``PUT /api/order-size-limit`` (ADR 064).

Shape: ``architecture/schema/execution.md``. ``PUT`` saves the setting off the loop; the next order the
door reads meets the new numbers at once.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from constants_order_size_limit import (
    ORDER_SIZE_LIMIT_API_PATH,
    ORDER_SIZE_LIMIT_MAX_RISK_USD,
    ORDER_SIZE_LIMIT_MAX_SHARES,
    ORDER_SIZE_LIMIT_MIN_RISK_USD,
    ORDER_SIZE_LIMIT_MIN_SHARES,
    ORDER_SIZE_LIMIT_REASON_INVALID,
    ORDER_SIZE_LIMIT_VENUES,
)
from execution.size_limit import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["order-size-limit"])


def view() -> dict[str, Any]:
    return {"schema_version": 1, "settings": settings.current(),
            "rules": {"venues": list(ORDER_SIZE_LIMIT_VENUES),
                      "min_shares": ORDER_SIZE_LIMIT_MIN_SHARES, "max_shares": ORDER_SIZE_LIMIT_MAX_SHARES,
                      "min_risk_usd": ORDER_SIZE_LIMIT_MIN_RISK_USD, "max_risk_usd": ORDER_SIZE_LIMIT_MAX_RISK_USD}}


@router.get(ORDER_SIZE_LIMIT_API_PATH)
async def get_order_size_limit() -> dict[str, Any]:
    return await asyncio.to_thread(view)


@router.put(ORDER_SIZE_LIMIT_API_PATH)
async def put_order_size_limit(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Send the change as JSON") from exc
    try:
        before, after = await asyncio.to_thread(settings.update, body)
    except settings.Invalid as exc:
        raise HTTPException(status_code=400, detail=str(exc),
                            headers={"X-Nova-Reason": ORDER_SIZE_LIMIT_REASON_INVALID}) from exc
    except OSError as exc:
        logger.exception("ORDER SIZE LIMIT: could not save the setting")
        raise HTTPException(status_code=503, detail=(f"Nova could not save the order size limit "
                                                     f"({type(exc).__name__}: {exc}); the setting is unchanged")) from exc
    logger.info("ORDER SIZE LIMIT: changed from %s to %s", before["venues"], after["venues"])
    return await asyncio.to_thread(view)
