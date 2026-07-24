"""
IBKR connect attempts + alternate-port self-heal (bidirectional, refused-only).

Extracted from client.py so the connection manager stays under the module
size limit. Session acceptance (account-kind match) stays in client.py.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from constants import IBKR_CONNECT_TIMEOUT_SEC
from ibkr import gateway_heal as _heal
from metrics.op_metrics import timed

if TYPE_CHECKING:
    from ib_async import IB

logger = logging.getLogger(__name__)

AcceptSession = Callable[["IB", str], tuple[bool, str]]
AttemptConnect = Callable[["IB", str, int, int], Awaitable[tuple[bool, str]]]


def safe_disconnect(ib: Any) -> None:
    """Best-effort teardown — call even when isConnected() is False (half-open)."""
    if ib is None:
        return
    try:
        ib.disconnect()
    except Exception:
        logger.debug("IBKR: disconnect during reset failed", exc_info=True)


async def attempt_connect(
    ib: "IB", host: str, port: int, client_id: int,
) -> tuple[bool, str]:
    """Connect with a hard asyncio wall. Returns (ok, failure_reason)."""
    wall = float(IBKR_CONNECT_TIMEOUT_SEC)
    inner = max(1.0, wall - 0.5)
    try:
        async with timed("ibkr.connect"):
            await asyncio.wait_for(
                ib.connectAsync(host, port, clientId=client_id, timeout=inner),
                timeout=wall,
            )
        return True, "ok"
    except asyncio.TimeoutError:
        logger.warning(
            "IBKR: connect timed out after %.1fs to %s:%s (clientId=%s) — "
            "Gateway may be wedged or clientId in use (Error 326)",
            wall,
            host,
            port,
            client_id,
        )
        safe_disconnect(ib)
        return False, _heal.classify_connect_failure(None, timed_out=True)
    except Exception as exc:
        msg = str(exc) or type(exc).__name__
        logger.warning(
            "IBKR: connect failed to %s:%s (clientId=%s): %s",
            host,
            port,
            client_id,
            msg,
        )
        safe_disconnect(ib)
        return False, _heal.classify_connect_failure(exc, timed_out=False)


async def try_connect_alternate_port(
    ib: "IB",
    host: str,
    preferred_mode: str,
    client_id: int,
    preferred_reason: str,
    *,
    accept_session: AcceptSession,
) -> str | None:
    """If preferred port was refused, try the alternate paper/live port.

    Timeout / Error 326 is NOT heal-eligible — the preferred Gateway may still
    be up (wedged handshake or clientId conflict). Account-kind match is
    enforced by ``accept_session`` after a successful alternate connect.
    """
    if not _heal.self_heal_enabled():
        return None
    if _heal.self_heal_suppressed():
        logger.info(
            "IBKR: self-heal suppressed (intentional gateway-mode switch in "
            "progress) — surfacing %s failure honestly instead of auto-heal",
            preferred_mode,
        )
        return None
    if preferred_reason != "refused":
        return None

    alt_mode = _heal.alternate_mode(preferred_mode)
    if not _heal.heal_target_allowed(from_mode=preferred_mode, to_mode=alt_mode):
        return None

    alt_port = _heal.port_for_mode(alt_mode)
    preferred_port = _heal.port_for_mode(preferred_mode)
    logger.info(
        "IBKR: preferred %s:%s failed (%s); trying %s:%s (bidirectional self-heal)",
        preferred_mode,
        preferred_port,
        preferred_reason,
        alt_mode,
        alt_port,
    )
    ok, _alt_reason = await attempt_connect(ib, host, alt_port, client_id)
    if not ok:
        return None

    session_ok, _session_reason = accept_session(ib, alt_mode)
    if not session_ok:
        safe_disconnect(ib)
        return None

    _heal.apply_runtime_gateway_mode(alt_mode)  # type: ignore[arg-type]
    persisted = _heal.persist_gateway_mode(alt_mode)  # type: ignore[arg-type]
    _heal.record_heal(
        from_mode=preferred_mode,
        to_mode=alt_mode,  # type: ignore[arg-type]
        reason=preferred_reason,
        preferred_port=preferred_port,
        healed_port=alt_port,
        persisted=persisted,
    )
    return alt_mode
