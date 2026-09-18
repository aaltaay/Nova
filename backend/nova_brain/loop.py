"""Claim + heartbeat + one active pack. Never raises autonomy."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from constants_bot import (
    BOT_BRAIN_POLL_SEC,
    BOT_LEVEL_EYES,
    BOT_LEVEL_STRATEGY,
    BOT_PACK_HALT_LULD,
    BOT_PACK_LLM_DECIDE,
    BOT_PACK_QUOTE_SPIKE,
    BOT_PACK_STUBS,
)
from nova_brain.client import BotApiClient
from nova_brain.halt_luld import tick as halt_tick
from nova_brain.llm_decide import tick as llm_tick
from nova_brain.quote_spike import tick as quote_tick

logger = logging.getLogger("nova_brain")


def step(
    client: BotApiClient,
    *,
    halt_prev: dict[str, bool],
    last_fire: dict[str, float],
    last_llm: dict[str, float] | None = None,
    quote_prev: dict[str, Any] | None = None,
    now: float | None = None,
) -> dict[str, bool]:
    llm_state = last_llm if last_llm is not None else {}
    qp = quote_prev if quote_prev is not None else {}
    session = client.session_get()
    level = int(session.get("level") or 0)
    pack = str(session.get("active_pack") or BOT_PACK_HALT_LULD)
    ts = time.time() if now is None else now
    if pack == BOT_PACK_LLM_DECIDE:
        if level < BOT_LEVEL_EYES:
            return halt_prev
        if level >= BOT_LEVEL_STRATEGY and session.get("armed"):
            client.claim()
            session = client.heartbeat()
        watch = client.watch()
        llm_tick(client, session=session, now=ts, last=llm_state, watch=watch)
        return halt_prev
    if pack == BOT_PACK_QUOTE_SPIKE:
        if level < BOT_LEVEL_EYES:
            return halt_prev
        if level >= BOT_LEVEL_STRATEGY and session.get("armed"):
            client.claim()
            session = client.heartbeat()
        watch = client.watch()
        nxt = quote_tick(
            session=session,
            watch=watch,
            previous=qp,
            last_fire=last_fire,
            now=ts,
            fire=client.fire,
            propose=client.propose if level < BOT_LEVEL_STRATEGY else None,
        )
        if quote_prev is not None:
            quote_prev.clear()
            quote_prev.update(nxt)
        return halt_prev
    if level < BOT_LEVEL_STRATEGY or not session.get("armed"):
        return halt_prev
    client.claim()
    session = client.heartbeat()
    if pack in BOT_PACK_STUBS:
        logger.info("nova-brain: pack %s is a stub -- heartbeat only", pack)
        return halt_prev
    watch = client.watch()
    return halt_tick(
        session=session,
        watch=watch,
        previous=halt_prev,
        last_fire=last_fire,
        now=ts,
        fire=client.fire,
    )


def run_forever(*, client: BotApiClient | None = None, poll_sec: float | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    api = client or BotApiClient()
    if not api.api_key:
        logger.error("NOVA_API_KEY is required -- nova-brain will not start")
        raise SystemExit(2)
    misses = 0
    seen_ok = False
    halt_prev: dict[str, bool] = {}
    last_fire: dict[str, float] = {}
    last_llm: dict[str, float] = {}
    quote_prev: dict = {}
    delay = BOT_BRAIN_POLL_SEC if poll_sec is None else poll_sec
    logger.info("nova-brain starting against %s as %s", api.base, api.brain_id)
    while True:
        try:
            halt_prev = step(
                api,
                halt_prev=halt_prev,
                last_fire=last_fire,
                last_llm=last_llm,
                quote_prev=quote_prev,
            )
            misses = 0
            seen_ok = True
        except requests.RequestException as exc:
            misses += 1
            logger.warning("nova-brain: API unreachable (%s) miss=%s", exc, misses)
            if seen_ok and misses >= 8:
                logger.info("nova-brain: API gone -- exiting")
                return
        except SystemExit:
            raise
        except Exception:
            logger.exception("nova-brain: tick failed")
        time.sleep(delay)
