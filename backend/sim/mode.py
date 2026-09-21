"""Desk venue selector -- the operator's settled Sim / IBKR choice (ADR 018).

Owner: this module (sole reader/writer of ``DESK_VENUE_FILE``).
Invalidation: an operator venue click only. The settled venue is deliberately
restart-independent -- that is the whole point of ADR 018 -- so no session
rollover or reconnect generation stales it.

Precedence on process start: the operator cache file wins, then the
``NOVA_BROKER`` env bootstrap default. An unreadable or unknown-version file
refuses loud and falls back to env; it never silently picks a venue.

This module answers *where the desk points*, never *whether it may spend*.
Spend arming is a separate latch with the opposite lifetime and lives in
``ibkr.safety`` -- see ADR 018.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from constants_sim import (
    DESK_VENUE_SCHEMA_VERSION,
    NOVA_BROKER_ENV,
    NOVA_BROKER_IBKR,
    NOVA_BROKER_SIM,
    SIM_MODE_LABEL,
    SIM_SPEND_LOCKED_DISARMED,
    SIM_SPEND_STATUS,
    nova_broker_from_env,
)

logger = logging.getLogger(__name__)

_BROKER_LINE = re.compile(
    rf"^\s*{re.escape(NOVA_BROKER_ENV)}\s*=",
    re.IGNORECASE,
)

# None = follow env. True/False = resolved venue (persisted click or toggle).
_override: bool | None = None
# Whether this process has already consulted the operator cache file.
_venue_loaded = False


def _load_venue() -> None:
    """Resolve the venue once per process: cache file first, env default second.

    A missing, unreadable or unknown-version file leaves ``_override`` as None
    so ``is_sim_mode`` falls back to ``NOVA_BROKER``. That fallback is safe
    only because a fresh process is never armed (ADR 018 decision 2) -- losing
    the file costs the venue, never the spend gate.
    """
    global _override, _venue_loaded
    if _venue_loaded:
        return
    _venue_loaded = True
    import cache as _cache

    data = _cache.load_desk_venue()
    if not data:
        return
    # A hand-edited or corrupted file can carry a non-numeric version. Raising
    # here would abort the runtime bootstrap that makes the first is_sim_mode()
    # call, which is the opposite of the refuse-loud fallback this promises.
    try:
        version = int(data.get("schema_version") or 0)
    except (TypeError, ValueError):
        version = -1
    if version != DESK_VENUE_SCHEMA_VERSION:
        logger.warning(
            "SIM: refusing desk venue file with unknown schema_version=%s "
            "(expected %s) -- falling back to %s, on-disk file left untouched",
            version,
            DESK_VENUE_SCHEMA_VERSION,
            NOVA_BROKER_ENV,
        )
        return
    venue = data.get("venue")
    if venue not in (NOVA_BROKER_SIM, NOVA_BROKER_IBKR):
        logger.warning(
            "SIM: desk venue file carries no usable 'venue' (%r) -- falling back to %s",
            venue,
            NOVA_BROKER_ENV,
        )
        return
    _override = venue == NOVA_BROKER_SIM
    os.environ[NOVA_BROKER_ENV] = venue
    logger.info("SIM: restored desk venue %s from the operator cache", venue)


def _save_venue(enabled: bool) -> bool:
    import cache as _cache

    return bool(
        _cache.save_desk_venue(
            {
                "schema_version": DESK_VENUE_SCHEMA_VERSION,
                "venue": NOVA_BROKER_SIM if enabled else NOVA_BROKER_IBKR,
            }
        )
    )


def is_sim_mode() -> bool:
    if not _venue_loaded:
        _load_venue()
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
    """Settle the desk venue. Always persists the click; never arms anything.

    ``persist=True`` additionally rewrites the ``NOVA_BROKER`` bootstrap default
    in ``.env``. That is no longer how the venue survives a restart (ADR 018
    decision 6 moved the store to the operator cache) -- it only changes what a
    clone with no cache file starts on.

    Changing venue always disarms. Carrying an arm across a venue change is the
    same class of bug as carrying it across a restart: the operator armed one
    desk and would be handed a different one already armed.
    """
    global _override, _venue_loaded
    _override = bool(enabled)
    _venue_loaded = True
    os.environ[NOVA_BROKER_ENV] = NOVA_BROKER_SIM if enabled else NOVA_BROKER_IBKR
    persisted = _save_venue(bool(enabled))
    bootstrap_persisted = False
    if persist:
        bootstrap_persisted = persist_nova_broker(
            NOVA_BROKER_SIM if enabled else NOVA_BROKER_IBKR
        )
    from ibkr import safety as _safety

    _safety.set_armed(False, reason="venue changed")
    if enabled:
        # A live Session Record keeps running into Sim. It used to be stopped
        # here because Sim piped SIM1 ticks into the recorder; SIM1 is gone
        # (ADR 019), only live IBKR callbacks feed a capture, and Record holds its
        # own lines (capture.feed_hold), so practising no longer ends a recording.
        from sim.feed import start_sim_feed_threadsafe

        start_sim_feed_threadsafe()
    else:
        from sim.feed import stop_sim_feed_threadsafe

        stop_sim_feed_threadsafe()
    logger.info(
        "SIM: venue %s persisted=%s bootstrap=%s",
        "sim" if enabled else "ibkr",
        persisted,
        bootstrap_persisted,
    )
    return status_payload() | {
        "persisted": persisted,
        "bootstrap_persisted": bootstrap_persisted,
    }


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
    from ibkr.safety import armed as _armed_now

    sim = is_sim_mode()
    armed = _armed_now()
    # `spend_status` is the *effective* state everywhere else, so it must not
    # read `sim_armed` while the latch is off -- a consumer reading it would
    # believe practice orders are enabled while validation rejects them. Mirrors
    # the /api/ibkr/status overlay.
    if not sim:
        spend_status = None
    else:
        spend_status = SIM_SPEND_STATUS if armed else SIM_SPEND_LOCKED_DISARMED
    return {
        "armed": armed,
        "sim": sim,
        "broker": NOVA_BROKER_SIM if sim else NOVA_BROKER_IBKR,
        "mode": SIM_MODE_LABEL if sim else None,
        "spend_status": spend_status,
    }


def reset_for_tests() -> None:
    global _override, _venue_loaded
    _override = None
    _venue_loaded = False
    os.environ.pop(NOVA_BROKER_ENV, None)
    # The venue is durable by design, so clearing memory is not enough: a left
    # -behind file would make the next test resolve the previous test's venue.
    # conftest pins NOVA_CACHE_DIR to a temp dir, so this only ever unlinks a
    # test-owned file (persisted-state.mdc).
    try:
        from constants_sim import DESK_VENUE_FILE

        Path(DESK_VENUE_FILE).unlink(missing_ok=True)
    except OSError:
        logger.debug("SIM: could not clear desk venue file in reset", exc_info=True)
    from ibkr import safety as _safety

    _safety.set_armed(False, reason="test reset")
    from sim import broker as _broker
    from sim import feed as _feed

    _broker.reset_for_tests()
    _feed.reset_for_tests()
