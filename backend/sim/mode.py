"""Sim mode selector -- env NOVA_BROKER=sim plus an optional process toggle.

Owner: this module. Invalidation: process start or set_sim_mode().
No persisted operator cache (in-memory + optional .env rewrite only).
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from constants_sim import (
    NOVA_BROKER_ENV,
    NOVA_BROKER_IBKR,
    NOVA_BROKER_SIM,
    SIM_MODE_LABEL,
    SIM_SPEND_STATUS,
    SIM_SYMBOL,
    nova_broker_from_env,
)

logger = logging.getLogger(__name__)

_BROKER_LINE = re.compile(
    rf"^\s*{re.escape(NOVA_BROKER_ENV)}\s*=",
    re.IGNORECASE,
)

# None = follow env. True/False = process override (Settings toggle).
_override: bool | None = None


def is_sim_mode() -> bool:
    if _override is not None:
        return _override
    return nova_broker_from_env() == NOVA_BROKER_SIM


def desk_connected() -> bool:
    """Tape/depth/account door: sim is usable without Gateway."""
    if is_sim_mode():
        return True
    from ibkr import client as _client

    return _client.is_connected()


def set_sim_mode(enabled: bool, *, persist: bool = False) -> dict:
    """Process-local toggle. persist=True rewrites NOVA_BROKER in .env."""
    global _override
    _override = bool(enabled)
    os.environ[NOVA_BROKER_ENV] = NOVA_BROKER_SIM if enabled else NOVA_BROKER_IBKR
    persisted = False
    if persist:
        persisted = persist_nova_broker(NOVA_BROKER_SIM if enabled else NOVA_BROKER_IBKR)
    if enabled:
        from sim.feed import start_sim_feed_threadsafe

        start_sim_feed_threadsafe()
    else:
        from sim.feed import stop_sim_feed_threadsafe

        stop_sim_feed_threadsafe()
    logger.info("SIM: mode %s persist=%s", "on" if enabled else "off", persisted)
    return status_payload() | {"persisted": persisted}


def persist_nova_broker(value: str, env_path: Path | None = None) -> bool:
    from paths import env_file_path

    path = env_path if env_path is not None else env_file_path()
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        lines = text.splitlines(keepends=True)
        found = False
        out: list[str] = []
        for line in lines:
            bare = line.lstrip("\ufeff")
            if _BROKER_LINE.match(bare.rstrip("\r\n")):
                nl = "\r\n" if line.endswith("\r\n") else "\n"
                out.append(f"{NOVA_BROKER_ENV}={value}{nl}")
                found = True
            else:
                out.append(line)
        if not found:
            if out and not out[-1].endswith(("\n", "\r")):
                out[-1] = out[-1] + "\n"
            out.append(f"{NOVA_BROKER_ENV}={value}\n")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(out), encoding="utf-8")
        return True
    except OSError:
        logger.warning("SIM: could not persist %s=%s", NOVA_BROKER_ENV, value, exc_info=True)
        return False


def status_payload() -> dict:
    return {
        "sim": is_sim_mode(),
        "sim_symbol": SIM_SYMBOL if is_sim_mode() else None,
        "broker": NOVA_BROKER_SIM if is_sim_mode() else NOVA_BROKER_IBKR,
        "mode": SIM_MODE_LABEL if is_sim_mode() else None,
        "spend_status": SIM_SPEND_STATUS if is_sim_mode() else None,
    }


def reset_for_tests() -> None:
    global _override
    _override = None
    os.environ.pop(NOVA_BROKER_ENV, None)
    from sim import broker as _broker
    from sim import feed as _feed
    from sim import market as _market

    _broker.reset_for_tests()
    _market.reset_for_tests()
    _feed.reset_for_tests()
