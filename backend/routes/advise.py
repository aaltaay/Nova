"""Advise rail routes -- book + worker control. No order mutations."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from advise import pool, service
from advise.service import AdviseError
from constants_advise import ADVISE_DEFAULT_DEPTH, ADVISE_MAX_DEPTH, ADVISE_MIN_DEPTH

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/advise", tags=["advise"])
ws_router = APIRouter(tags=["advise-ws"])


class RunBody(BaseModel):
    symbol: str
    depth: int = Field(default=ADVISE_DEFAULT_DEPTH, ge=ADVISE_MIN_DEPTH, le=ADVISE_MAX_DEPTH)
    force_refresh: bool = False


def _http(exc: AdviseError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/estimate")
def advise_estimate(symbol: str, depth: int = ADVISE_DEFAULT_DEPTH) -> dict:
    try:
        return service.estimate(symbol, depth)
    except AdviseError as exc:
        raise _http(exc) from exc


@router.get("/latest")
def advise_latest(symbol: str, depth: int = ADVISE_DEFAULT_DEPTH) -> dict:
    try:
        run = service.latest(symbol, depth)
    except AdviseError as exc:
        raise _http(exc) from exc
    return {"run": run}


@router.get("/history")
def advise_history(symbol: str) -> dict:
    try:
        rows = service.history(symbol)
    except AdviseError as exc:
        raise _http(exc) from exc
    return {"count": len(rows), "runs": rows}


@router.get("/runs/{run_id}")
def advise_get_run(run_id: int) -> dict:
    try:
        return service.get_run(run_id)
    except AdviseError as exc:
        raise _http(exc) from exc


@router.post("/run")
async def advise_start(body: RunBody) -> dict:
    try:
        return await service.start_run(body.symbol, body.depth, body.force_refresh)
    except AdviseError as exc:
        raise _http(exc) from exc


@router.post("/runs/{run_id}/cancel")
async def advise_cancel(run_id: int) -> dict:
    try:
        return await service.cancel_run(run_id)
    except AdviseError as exc:
        raise _http(exc) from exc


@router.post("/runs/{run_id}/retry")
async def advise_retry(run_id: int) -> dict:
    try:
        return await service.retry_run(run_id)
    except AdviseError as exc:
        raise _http(exc) from exc


@ws_router.websocket("/ws/advise/{run_id}")
async def advise_ws(websocket: WebSocket, run_id: int) -> None:
    await websocket.accept()
    try:
        snapshot = service.get_run(run_id)
    except AdviseError as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close()
        return
    await websocket.send_json({"type": "snapshot", "run": snapshot})
    if snapshot["status"] in ("complete", "failed", "cancelled"):
        await websocket.close()
        return
    queue = pool.subscribe(run_id)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=20)
            except TimeoutError:
                await websocket.send_json({"type": "ping"})
                continue
            await websocket.send_json(event)
            if event.get("type") in ("done",) or event.get("message") == "cancelled":
                break
            if event.get("type") == "error" and snapshot.get("status") != "running":
                # Keep listening; parent may still flip terminal status.
                pass
            live = None
            try:
                live = service.get_run(run_id)
            except AdviseError:
                break
            if live["status"] in ("complete", "failed", "cancelled"):
                await websocket.send_json({"type": "snapshot", "run": live})
                break
    except WebSocketDisconnect:
        logger.debug("advise ws disconnect run=%s", run_id)
    finally:
        pool.unsubscribe(run_id, queue)
