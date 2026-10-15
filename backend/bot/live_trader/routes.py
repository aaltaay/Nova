"""The Live Trader bot's routes (ADR 055): its cards, the hosts' settings, the answers to its asks. Thin handlers.

Loopback only, like every bot route; writes need the API key. Each answers the cards (``view.build``). A host's key
turned off while its bot holds positions sells them on the watcher's next pass -- the desk asks first. Shapes:
architecture/schema/bot.md ("The Live Trader bot").
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import require_bot_auth
from bot.http import require_loopback
from bot.live_trader import settings, view, watcher
from bot.live_trader.constants_live_trader import LT_AUDIT_ACTION, LT_ERR_ASK_GONE
from bot.live_trader.settings import SettingsError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["bot-live-traders"], dependencies=[Depends(require_loopback)])
_write = [Depends(require_bot_auth)]


class AskAnswer(BaseModel):
    approve: bool


def _error(status: int, code: str, message: str, field: str | None = None) -> JSONResponse:
    detail = {"reason": code, "error": message}
    if field:
        detail["field"] = field
    return JSONResponse(status_code=status, content={"detail": detail})


def _audit_settings(host: str, before: dict[str, Any], after: dict[str, Any], keys: tuple = settings.FIELDS) -> None:
    from bot.audit import record

    changed = {k: (before.get(k), after.get(k)) for k in keys if before.get(k) != after.get(k)}
    if not changed:
        return
    words = ", ".join(f"{k} {a!r} -> {b!r}" for k, (a, b) in changed.items())
    try:
        record(action=LT_AUDIT_ACTION, outcome="settings", reason=f"{host}: {words}",
               inputs={"host": host, "from": {k: a for k, (a, _b) in changed.items()},
                       "to": {k: b for k, (_a, b) in changed.items()}, "venue": "paper"})
    except Exception:
        logger.warning("Live Trader bot: the settings line for %s was not written", host, exc_info=True)


def _keys_left() -> None:
    """With no strategy On and no host key left on, the Bot switch goes off, as it does for a strategy (ADR 042)."""
    from bot import activation
    from bot.arming import is_desk_active
    from bot.persist import load_session
    from bot.setup_levels import at_strategy

    row = load_session()
    if is_desk_active(row) and not at_strategy(row) and not activation.live_trader_keys():
        activation.deactivate_now("no_setup", "no strategy is On and no Live Trader key is on any more")


@router.get("/api/bot/live-traders")
def live_traders() -> dict[str, Any]:
    return view.build()


@router.get("/api/bot/live-traders/asks")
def live_trader_asks() -> dict[str, Any]:
    """What every desk window polls for the asks' toasts and the Bot switch's question: memory reads only."""
    return view.asks_now()


@router.patch("/api/bot/live-traders/{name}", dependencies=_write)
def patch_host(name: str, body: dict[str, Any] = Body(...)) -> Any:  # noqa: B008 -- FastAPI's own idiom
    try:
        before, after = settings.patch_host(name, body)
    except SettingsError as exc:
        return _error(exc.status, exc.code, exc.message, exc.field)
    host = name.strip().upper()
    if before["key"] and not after["key"]:
        watcher.request_sell_host(host)     # what its bot holds is sold on the next pass (the desk asked first)
    _audit_settings(host, before, after)
    if before["key"] and not after["key"]:
        _keys_left()
    return view.build()


@router.patch("/api/bot/live-traders", dependencies=_write)
def patch_all(body: dict[str, Any] = Body(...)) -> Any:  # noqa: B008 -- FastAPI's own idiom
    unknown = sorted(set(body) - {"sell_all_at"})
    if unknown:
        return _error(400, "LIVE_TRADER_INVALID", f"unknown field {unknown[0]!r}", unknown[0])
    try:
        before, after = settings.patch_sell_all(body.get("sell_all_at"))
    except SettingsError as exc:
        return _error(exc.status, exc.code, exc.message, exc.field)
    _audit_settings("ALL", {"sell_all_at": before}, {"sell_all_at": after}, keys=("sell_all_at",))
    return view.build()


@router.post("/api/bot/live-traders/{name}/asks/{ask_id}", dependencies=_write)
def answer_ask(name: str, ask_id: str, body: AskAnswer) -> Any:
    if not watcher.answer_ask(ask_id, body.approve):
        return _error(409, LT_ERR_ASK_GONE, "that ask is gone: it expired, was answered, or the host closed first")
    return view.build()
