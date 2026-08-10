"""
IBKR connect attempts + alternate-port self-heal (follow listening Gateway).

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
from ibkr.port_diagnostics import probe_port
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


def _probe_pair(host: str, preferred_port: int, alt_port: int) -> tuple[bool, bool]:
    return probe_port(host, preferred_port), probe_port(host, alt_port)


async def try_connect_alternate_port(
    ib: "IB",
    host: str,
    preferred_mode: str,
    client_id: int,
    preferred_reason: str,
    *,
    accept_session: AcceptSession,
) -> str | None:
    """If preferred Gateway is dark and alternate listens, attach and persist.

    Probe-based: refuse always heals; timeout / preferred_dark heals only when
    preferred TCP is dark and alternate is up. Timeout while preferred still
    listens is NOT heal-eligible (wedged handshake / Error 326).
    Account-kind match is enforced by ``accept_session`` after connect.
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

    alt_mode = _heal.alternate_mode(preferred_mode)
    if not _heal.heal_target_allowed(from_mode=preferred_mode, to_mode=alt_mode):
        return None

    alt_port = _heal.port_for_mode(alt_mode)
    preferred_port = _heal.port_for_mode(preferred_mode)
    preferred_up, alternate_up = _probe_pair(host, preferred_port, alt_port)
    if not _heal.alternate_heal_eligible(
        preferred_reason,
        preferred_reachable=preferred_up,
        alternate_reachable=alternate_up,
    ):
        logger.info(
            "IBKR: alternate heal not eligible (reason=%s preferred_up=%s "
            "alternate_up=%s)",
            preferred_reason,
            preferred_up,
            alternate_up,
        )
        return None

    logger.info(
        "IBKR: preferred %s:%s failed (%s; preferred_up=%s); trying %s:%s "
        "(follow-Gateway self-heal)",
        preferred_mode,
        preferred_port,
        preferred_reason,
        preferred_up,
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


async def maybe_heal_from_port_probes(
    ib: "IB",
    host: str,
    preferred_mode: str,
    client_id: int,
    *,
    accept_session: AcceptSession,
) -> str | None:
    """Fast path: preferred dark + alternate up → attach before preferred dial."""
    preferred_port = _heal.port_for_mode(preferred_mode)
    alt_port = _heal.port_for_mode(_heal.alternate_mode(preferred_mode))
    preferred_up, alternate_up = _probe_pair(host, preferred_port, alt_port)
    if not _heal.alternate_heal_eligible(
        "preferred_dark",
        preferred_reachable=preferred_up,
        alternate_reachable=alternate_up,
    ):
        return None
    logger.info(
        "IBKR: preferred %s:%s dark; alternate %s listening — follow-Gateway "
        "heal before preferred dial",
        preferred_mode,
        preferred_port,
        alt_port,
    )
    return await try_connect_alternate_port(
        ib,
        host,
        preferred_mode,
        client_id,
        "preferred_dark",
        accept_session=accept_session,
    )
