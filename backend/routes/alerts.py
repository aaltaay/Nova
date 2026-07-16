"""Outbound alerts API — channel CRUD, test fire, dispatch status."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from alerts import channels_store, dispatch

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class ChannelCreate(BaseModel):
    type: str
    name: str = ""
    enabled: bool = True
    webhook_url: str | None = None
    bot_token: str | None = None
    chat_id: str | None = None


class ChannelUpdate(BaseModel):
    type: str | None = None
    name: str | None = None
    enabled: bool | None = None
    webhook_url: str | None = None
    bot_token: str | None = None
    chat_id: str | None = None


class TestRequest(BaseModel):
    channel_id: str | None = None
    message: str | None = None


@router.get("/channels")
def list_channels() -> dict:
    return {"channels": channels_store.list_channels()}


@router.post("/channels")
def create_channel(body: ChannelCreate) -> dict:
    try:
        ch = channels_store.create_channel(body.model_dump(exclude_none=True))
        return {"ok": True, "channel": ch}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/channels/{channel_id}")
def update_channel(channel_id: str, body: ChannelUpdate) -> dict:
    try:
        ch = channels_store.update_channel(channel_id, body.model_dump(exclude_unset=True))
        return {"ok": True, "channel": ch}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/channels/{channel_id}")
def delete_channel(channel_id: str) -> dict:
    if not channels_store.delete_channel(channel_id):
        raise HTTPException(status_code=404, detail="channel not found")
    return {"ok": True}


@router.post("/test")
def test_alert(body: TestRequest) -> dict:
    if body.channel_id:
        ch = channels_store.get_channel(body.channel_id)
        if ch is None:
            raise HTTPException(status_code=404, detail="channel not found")
        if not ch.enabled:
            raise HTTPException(status_code=400, detail="channel is disabled")
        result = dispatch.dispatch_test(ch, body.message)
        return {"ok": result.get("ok", False), "results": [result]}
    from constants import ALERTS_EVENT_TYPE_TEST

    results = dispatch.dispatch_alert(
        {"type": ALERTS_EVENT_TYPE_TEST, "text": body.message or "Nova test alert"},
        channel_ids=None,
    )
    ok = all(r.get("ok") for r in results) if results else False
    return {"ok": ok, "results": results}


@router.get("/status")
def alert_status() -> dict[str, Any]:
    errors = [e for e in dispatch.get_status() if not e.get("ok")]
    return {
        "error_count": len(errors),
        "recent_errors": errors[:20],
        "recent": dispatch.get_status()[:20],
    }
