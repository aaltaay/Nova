"""Day-one pack: fire once when a LULD/halted name resumes."""
from __future__ import annotations

from typing import Any, Callable

from constants_bot import BOT_HALT_RESUME_COOLDOWN_SEC, BOT_PACK_HALT_LULD


def resume_kind(session: dict[str, Any]) -> str:
    settings = dict(session.get("pack_settings") or {}).get(BOT_PACK_HALT_LULD) or {}
    return str(settings.get("resume_kind") or "buy_market")


def cooldown_sec(session: dict[str, Any]) -> float:
    settings = dict(session.get("pack_settings") or {}).get(BOT_PACK_HALT_LULD) or {}
    try:
        return max(1.0, float(settings.get("cooldown_sec") or BOT_HALT_RESUME_COOLDOWN_SEC))
    except (TypeError, ValueError):
        return float(BOT_HALT_RESUME_COOLDOWN_SEC)


def detect_resumes(
    previous: dict[str, bool],
    watch: dict[str, Any],
) -> tuple[list[str], dict[str, bool]]:
    """Return symbols that transitioned halted->clear, plus the new halt map."""
    nxt: dict[str, bool] = {}
    resumes: list[str] = []
    for row in watch.get("symbols") or []:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        halted = bool(row.get("halted"))
        nxt[symbol] = halted
        if previous.get(symbol) is True and not halted:
            resumes.append(symbol)
    return resumes, nxt


def tick(
    *,
    session: dict[str, Any],
    watch: dict[str, Any],
    previous: dict[str, bool],
    last_fire: dict[str, float],
    now: float,
    fire: Callable[[str, str], Any],
) -> dict[str, bool]:
    if (session.get("active_pack") or "") != BOT_PACK_HALT_LULD:
        return previous
    if not session.get("live_fire_ready"):
        return detect_resumes(previous, watch)[1]
    resumes, nxt = detect_resumes(previous, watch)
    kind = resume_kind(session)
    cool = cooldown_sec(session)
    for symbol in resumes:
        last = float(last_fire.get(symbol) or 0)
        if now - last < cool:
            continue
        fire(kind, symbol)
        last_fire[symbol] = now
    return nxt
