"""Desk venue selector -- the operator's settled Live / Paper / Sim choice (ADR 018, ADR 020).

Owner: this module (sole reader/writer of ``DESK_VENUE_FILE``).
Invalidation: an operator venue click only. The settled venue is deliberately
restart-independent -- that is the whole point of ADR 018 -- so no session
rollover or reconnect generation stales it.

The venue is one of ``live`` (the IBKR door: real money through the live
Gateway), ``paper`` (Nova's practice account on the live feed) and ``sim``
(the replay playground). ``desk-venue.json`` carries ``schema_version: 2``;
the ADR 018 v1 shape (``sim`` / ``ibkr``) migrates on first read -- ``ibkr``
becomes Paper, the safe direction, because Live is always an explicit click --
and is rewritten as v2. Unknown versions refuse loud.

Precedence on process start: the operator cache file wins, then the
``NOVA_BROKER`` env bootstrap default. An unreadable or unknown-version file
refuses loud and falls back to env; it never silently picks a venue.

This module answers *where the desk points*, never *whether it may spend*.
Spend arming is a separate latch with the opposite lifetime and lives in
``ibkr.safety`` -- see ADR 018. Every venue change disarms it.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from constants_sim import (
    DESK_PRACTICE_VENUES,
    DESK_VENUE_LEGACY_SCHEMA_VERSION,
    DESK_VENUE_LIVE,
    DESK_VENUE_PAPER,
    DESK_VENUE_SCHEMA_VERSION,
    DESK_VENUE_SIM,
    DESK_VENUE_V1_MIGRATION,
    DESK_VENUES,
    NOVA_BROKER_ENV,
    NOVA_BROKER_IBKR,
    PAPER_MODE_LABEL,
    PAPER_SPEND_STATUS,
    SIM_MODE_LABEL,
    SIM_SPEND_LOCKED_DISARMED,
    SIM_SPEND_STATUS,
    desk_venue_from_env,
)

logger = logging.getLogger(__name__)

_BROKER_LINE = re.compile(
    rf"^\s*{re.escape(NOVA_BROKER_ENV)}\s*=",
    re.IGNORECASE,
)

# None = follow env. Otherwise the resolved venue (persisted click or toggle).
_override: str | None = None
# Whether this process has already consulted the operator cache file.
_venue_loaded = False


def _read_venue_file() -> str | None:
    """The venue the operator cache names, or ``None`` to follow ``NOVA_BROKER``.

    A v1 file is migrated (``sim`` -> ``sim``, ``ibkr`` -> ``paper``) and
    rewritten as v2 so the next start reads the current shape. A hand-edited
    or corrupted file can carry a non-numeric version; raising here would
    abort the runtime bootstrap that makes the first ``venue()`` call, which
    is the opposite of the refuse-loud fallback this promises.
    """
    import cache as _cache

    data = _cache.load_desk_venue()
    if not data:
        return None
    try:
        version = int(data.get("schema_version") or 0)
    except (TypeError, ValueError):
        version = -1
    raw = data.get("venue")
    if version == DESK_VENUE_SCHEMA_VERSION:
        if raw in DESK_VENUES:
            return str(raw)
        logger.warning(
            "SIM: desk venue file carries no usable 'venue' (%r) -- falling back to %s",
            raw,
            NOVA_BROKER_ENV,
        )
        return None
    if version == DESK_VENUE_LEGACY_SCHEMA_VERSION:
        migrated = DESK_VENUE_V1_MIGRATION.get(raw)
        if migrated is None:
            logger.warning(
                "SIM: legacy desk venue file carries no usable 'venue' (%r) -- falling back to %s",
                raw,
                NOVA_BROKER_ENV,
            )
            return None
        rewritten = _save_venue(migrated)
        logger.info(
            "SIM: migrated desk venue file schema_version %s venue %r -> schema_version %s venue %r "
            "(rewritten=%s)",
            DESK_VENUE_LEGACY_SCHEMA_VERSION,
            raw,
            DESK_VENUE_SCHEMA_VERSION,
            migrated,
            rewritten,
        )
        return migrated
    logger.warning(
        "SIM: refusing desk venue file with unknown schema_version=%s "
        "(expected %s) -- falling back to %s, on-disk file left untouched",
        version,
        DESK_VENUE_SCHEMA_VERSION,
        NOVA_BROKER_ENV,
    )
    return None


def _load_venue() -> None:
    """Resolve the venue once per process: cache file first, env default second.

    A missing, unreadable or unknown-version file leaves ``_override`` as None
    so ``venue()`` falls back to ``NOVA_BROKER``. That fallback is safe only
    because a fresh process is never armed (ADR 018 decision 2) -- losing the
    file costs the venue, never the spend gate.
    """
    global _override, _venue_loaded
    if _venue_loaded:
        return
    _venue_loaded = True
    resolved = _read_venue_file()
    if resolved is None:
        return
    _override = resolved
    os.environ[NOVA_BROKER_ENV] = resolved
    logger.info("SIM: restored desk venue %s from the operator cache", resolved)


def _save_venue(target: str) -> bool:
    import cache as _cache

    return bool(
        _cache.save_desk_venue(
            {"schema_version": DESK_VENUE_SCHEMA_VERSION, "venue": target}
        )
    )


def venue() -> str:
    """The settled desk venue: ``live`` | ``paper`` | ``sim``."""
    if not _venue_loaded:
        _load_venue()
    if _override is not None:
        return _override
    return desk_venue_from_env()


def is_sim_mode() -> bool:
    """The Sim venue (replay playground). Every Sim-only market gate keys on this."""
    return venue() == DESK_VENUE_SIM


def is_replay_desk() -> bool:
    """The Sim venue off the live edge: every market read is the loaded replay.

    ADR 020 live-edge amendment (2026-09-21 evening): while the Sim clock
    follows the wall clock on today's date (``session_clock.live_edge``) a Sim
    tab reads the live IBKR feed exactly as a Paper tab does, so the market
    data gates -- depth, tape, L1, ticker snapshot, chart bars, sensors -- key
    on this and not on ``is_sim_mode`` alone. Order routing, the Sim feed loop
    and the status overlay still key on the venue.
    """
    if not is_sim_mode():
        return False
    from sim import session_clock

    return not session_clock.live_edge()


def is_paper_venue() -> bool:
    """Nova's practice account on the live feed (ADR 020)."""
    return venue() == DESK_VENUE_PAPER


def is_practice_venue() -> bool:
    """Paper or Sim: orders go to the practice broker, never to IBKR."""
    return venue() in DESK_PRACTICE_VENUES


def desk_connected() -> bool:
    """Tape/depth door: Sim is usable without Gateway; Paper and Live need the live feed."""
    if is_sim_mode():
        return True
    from ibkr import client as _client

    return _client.is_connected()


def desk_mode_label() -> str:
    """What the executor status reports as ``ibkr_mode``: the venue on Paper / Sim, IBKR's port label on Live.

    The Auto Paper controls enable on ``ibkr_mode == "paper"``. On Nova's Paper
    venue that must be the venue itself, not the live Gateway's port label
    (``live``) -- the Gateway only feeds it (ADR 020).
    """
    current = venue()
    if current in DESK_PRACTICE_VENUES:
        return current
    from ibkr import client as _client

    return _client.account_mode()


def set_venue(target: str, *, persist: bool = True) -> dict:
    """Settle the desk venue. Never arms anything.

    ``persist`` writes the click to the operator cache (``desk-venue.json``),
    which is how the venue survives a restart (ADR 018 decision 6). The
    ``NOVA_BROKER`` bootstrap line in ``.env`` is not touched here -- it only
    decides what a clone with no cache file starts on (``set_sim_mode``).

    Changing venue always disarms. Carrying an arm across a venue change is the
    same class of bug as carrying it across a restart: the operator armed one
    desk and would be handed a different one already armed. The Sim feed runs
    only on the Sim venue; Paper reads the live market exactly like Live.
    """
    global _override, _venue_loaded
    key = (target or "").strip().lower()
    if key not in DESK_VENUES:
        raise ValueError(f"unknown desk venue {target!r} (expected one of {', '.join(DESK_VENUES)})")
    _override = key
    _venue_loaded = True
    os.environ[NOVA_BROKER_ENV] = key
    persisted = _save_venue(key) if persist else False
    from ibkr import safety as _safety

    _safety.set_armed(False, reason="venue changed")
    # Buy: Nova never carries into another venue either (ADR 037 decision 3).
    from stock_mode import store as _stock_mode

    _stock_mode.venue_changed(key)
    if key == DESK_VENUE_SIM:
        # A live Session Record keeps running into Sim. It used to be stopped
        # here because Sim piped SIM1 ticks into the recorder; SIM1 is gone
        # (ADR 019), only live IBKR callbacks feed a capture, and Record holds its
        # own lines (capture.feed_hold), so practising no longer ends a recording.
        from sim.feed import start_sim_feed_threadsafe

        start_sim_feed_threadsafe()
    else:
        from sim.feed import stop_sim_feed_threadsafe

        stop_sim_feed_threadsafe()
    logger.info("SIM: venue %s persisted=%s", key, persisted)
    return status_payload() | {"persisted": persisted}


def set_sim_mode(enabled: bool, *, persist: bool = False) -> dict:
    """Legacy Sim toggle (``POST /api/sim``), kept as a wrapper over ``set_venue``.

    On is the Sim venue; off is the IBKR door, which is the Live venue --
    exactly what ``ibkr`` meant before ADR 020. ``persist=True`` additionally
    rewrites the ``NOVA_BROKER`` bootstrap default in ``.env``; that is no
    longer how the venue survives a restart (ADR 018 decision 6 moved the
    store to the operator cache) -- it only changes what a clone with no cache
    file starts on.
    """
    target = DESK_VENUE_SIM if enabled else DESK_VENUE_LIVE
    payload = set_venue(target)
    bootstrap_persisted = persist_nova_broker(target) if persist else False
    logger.info(
        "SIM: venue %s persisted=%s bootstrap=%s",
        target,
        payload["persisted"],
        bootstrap_persisted,
    )
    return payload | {"bootstrap_persisted": bootstrap_persisted}


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


def practice_spend_status(current: str, armed: bool) -> str | None:
    """Effective spend status a practice venue reports, ``None`` on the IBKR door.

    Must not read ``sim_armed`` / ``paper_armed`` while the latch is off -- a
    consumer reading it would believe practice orders are enabled while
    validation rejects them. One vocabulary for ``GET /api/sim``, the
    ``/api/ibkr/status`` overlay and ``ibkr.safety``.
    """
    if current == DESK_VENUE_SIM:
        return SIM_SPEND_STATUS if armed else SIM_SPEND_LOCKED_DISARMED
    if current == DESK_VENUE_PAPER:
        return PAPER_SPEND_STATUS if armed else SIM_SPEND_LOCKED_DISARMED
    return None


def status_payload() -> dict:
    from ibkr.safety import armed as _armed_now

    current = venue()
    armed = _armed_now()
    sim = current == DESK_VENUE_SIM
    if sim:
        mode = SIM_MODE_LABEL
    elif current == DESK_VENUE_PAPER:
        mode = PAPER_MODE_LABEL
    else:
        mode = None
    return {
        "armed": armed,
        "venue": current,
        "practice": current in DESK_PRACTICE_VENUES,
        "sim": sim,
        # Who fills: the practice broker on Paper / Sim (named by venue), IBKR on Live.
        "broker": NOVA_BROKER_IBKR if current == DESK_VENUE_LIVE else current,
        "mode": mode,
        "spend_status": practice_spend_status(current, armed),
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
