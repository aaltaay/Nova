"""Bot-callable Advise read path with spend guards. Never places."""
from __future__ import annotations

from typing import Any

from bot.audit import record as audit
from bot.autonomy import assert_not_dark
from bot.errors import BotError
from bot.persist import save_session
from constants_bot import BOT_REASON_ADVISE_CAP, BOT_REASON_ADVISE_OFF


def _advise_state(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row.get("advise") or {})


def assert_advise_allowed() -> dict[str, Any]:
    row = assert_not_dark()
    advise = _advise_state(row)
    if not advise.get("enabled"):
        raise BotError("Advise is off for this bot session", 409, BOT_REASON_ADVISE_OFF)
    return row


def _charge(row: dict[str, Any], usd: float) -> None:
    advise = _advise_state(row)
    used = int(advise.get("calls_used") or 0)
    spent = float(advise.get("usd_spent") or 0)
    call_cap = int(advise.get("call_cap") or 0)
    usd_cap = float(advise.get("usd_cap") or 0)
    if used + 1 > call_cap:
        raise BotError(f"Advise call cap {call_cap} reached", 409, BOT_REASON_ADVISE_CAP)
    if spent + usd > usd_cap + 1e-9:
        raise BotError(
            f"Advise session cap ${usd_cap:.2f} would be exceeded (spent ${spent:.2f} + ${usd:.2f})",
            409,
            BOT_REASON_ADVISE_CAP,
        )
    advise["calls_used"] = used + 1
    advise["usd_spent"] = spent + usd
    row["advise"] = advise
    save_session(row)


async def start(symbol: str, depth: int | None, *, force_refresh: bool = False) -> dict[str, Any]:
    from advise import service as advise_service

    row = assert_advise_allowed()
    estimate = advise_service.estimate(symbol, depth)
    usd = float(estimate.get("est_usd") or 0)
    cached = None
    if not force_refresh:
        cached = advise_service.latest(symbol, depth)
        if cached and cached.get("from_book") and cached.get("status") == "complete":
            audit(action="advise", outcome="book", advise_spend=0.0, inputs={"symbol": symbol})
            return {**cached, "advise_spend": 0.0, "places": False}
    _charge(row, usd)
    run = await advise_service.start_run(symbol, depth, force_refresh)
    audit(action="advise", outcome="started", advise_spend=usd, inputs={"symbol": symbol, "run_id": run.get("id")})
    return {**run, "advise_spend": usd, "places": False}


def latest(symbol: str, depth: int | None = None) -> dict[str, Any] | None:
    from advise import service as advise_service

    assert_advise_allowed()
    run = advise_service.latest(symbol, depth)
    if run is None:
        return None
    return {**run, "places": False}
