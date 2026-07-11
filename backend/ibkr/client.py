"""
IBKR IB singleton connection manager.

Connects to a user-managed IB Gateway process (paper port 4002 by default).
Nova never launches or logs in to Gateway — that requires one manual
IBKR-Mobile 2FA confirmation once per week.

State:
  _ib       -- the ib_async.IB() instance (always exists, may be disconnected)
  _mode     -- "paper" | "live" | "disconnected"
  _enabled  -- False when IBKR_ENABLED env var is absent/false (safe default)
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

try:
    from ib_async import IB
    _IB_AVAILABLE = True
except ImportError:
    IB = None  # type: ignore[assignment,misc]
    _IB_AVAILABLE = False
    logger.warning("ib_async not installed — IBKR module disabled")

from constants import (
    IBKR_HOST,
    IBKR_PAPER_PORT,
    IBKR_LIVE_PORT,
    IBKR_CLIENT_ID,
    IBKR_RECONNECT_DELAY_SEC,
)

# ── Module-level state ─────────────────────────────────────────────────────────
_ib: "IB | None" = None
_mode: str = "disconnected"
_enabled: bool = False
_reconnect_task: asyncio.Task | None = None


def _resolve_config() -> tuple[bool, str, int]:
    """Return (enabled, host, port) from env, never raises."""
    enabled = os.environ.get("IBKR_ENABLED", "false").lower() in ("1", "true", "yes")
    live_confirmed = os.environ.get("IBKR_LIVE_TRADING_CONFIRMED", "false").lower() in ("1", "true", "yes")
    host = os.environ.get("IBKR_HOST", IBKR_HOST)
    if live_confirmed:
        port = int(os.environ.get("IBKR_LIVE_PORT", str(IBKR_LIVE_PORT)))
        mode_label = "live"
    else:
        port = int(os.environ.get("IBKR_PAPER_PORT", str(IBKR_PAPER_PORT)))
        mode_label = "paper"
    return enabled, host, port, mode_label


def is_enabled() -> bool:
    return _enabled


def is_connected() -> bool:
    return _ib is not None and _ib.isConnected()


def account_mode() -> str:
    """One of: 'paper', 'live', 'disconnected'."""
    if not is_connected():
        return "disconnected"
    return _mode


def get_ib() -> "IB | None":
    """Return the IB instance if connected, else None."""
    if is_connected():
        return _ib
    return None


async def _attempt_connect(ib: "IB", host: str, port: int) -> bool:
    try:
        await ib.connectAsync(host, port, clientId=IBKR_CLIENT_ID, timeout=10)
        return True
    except Exception as exc:
        logger.debug("IBKR connect attempt failed: %s", exc)
        return False


async def reconnect_loop() -> None:
    """Background task: keep connecting while IBKR_ENABLED is set."""
    global _ib, _mode, _enabled

    enabled, host, port, mode_label = _resolve_config()
    _enabled = enabled

    if not _enabled:
        logger.info("IBKR module disabled (IBKR_ENABLED not set)")
        return

    if not _IB_AVAILABLE:
        logger.warning("IBKR module enabled but ib_async not installed — skipping")
        return

    _ib = IB()
    _mode = mode_label

    while True:
        if not _ib.isConnected():
            logger.info("IBKR: attempting connect to %s:%s (%s)", host, port, mode_label)
            ok = await _attempt_connect(_ib, host, port)
            if ok:
                logger.info("IBKR: connected in %s mode", mode_label)
            else:
                await asyncio.sleep(IBKR_RECONNECT_DELAY_SEC)
                continue
        await asyncio.sleep(5)


async def startup() -> None:
    """Called from main.py lifespan. Starts reconnect loop as a background task."""
    global _reconnect_task
    _reconnect_task = asyncio.create_task(reconnect_loop())
    logger.info("IBKR client task started")


async def shutdown() -> None:
    """Called from main.py lifespan. Cancels reconnect loop and disconnects."""
    global _reconnect_task, _ib
    if _reconnect_task:
        _reconnect_task.cancel()
        try:
            await _reconnect_task
        except asyncio.CancelledError:
            pass
    if _ib and _ib.isConnected():
        _ib.disconnect()
    logger.info("IBKR client shut down")
