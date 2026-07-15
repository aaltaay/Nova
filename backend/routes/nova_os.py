"""
Nova OS API — policy / events (P1) + decide (P2). READ-ish for decide:
`decide()` evaluates and journals a receipt but never places an order.

Endpoints:
  GET /api/nova-os/policy            -- vocabulary + decide tunables + loss policy
  GET /api/nova-os/events            -- recent append-only receipts
  GET /api/nova-os/decide/{symbol}   -- full gate audit for one symbol
  GET /api/nova-os/decide            -- decide top watchlist candidates
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from alpaca import _get_discovery_provider
from chart_bars import fetch_chart_bars as _fetch_chart_bars
from constants import (
    NOVA_OS_ACTIONS,
    NOVA_OS_CATALYST_MIN_CONFIDENCE,
    NOVA_OS_CITATIONS,
    NOVA_OS_CONFIRM_TIMEOUT_SEC,
    NOVA_OS_DECIDE_DEFAULT_LIMIT,
    NOVA_OS_DECISIONS,
    NOVA_OS_DEFAULT_MODE,
    NOVA_OS_EVENTS_DEFAULT_LIMIT,
    NOVA_OS_FLATTEN_CONFIRM_TOKEN,
    NOVA_OS_LOSS_POLICY_DOWNGRADE_AFTER_LOSSES,
    NOVA_OS_LOSS_POLICY_HALT_AFTER_LOSSES,
    NOVA_OS_MAX_CONCURRENT_POSITIONS,
    NOVA_OS_MIN_FIRST_MINUTE_VOLUME,
    NOVA_OS_MODES,
    NOVA_OS_PRIMARY_SETUP,
    NOVA_OS_REASON_CODES,
    NOVA_OS_WATCHLIST_MAX_RANK,
)
from nova_os import codes
from nova_os.decide import decide
from nova_os.events import get_events
from strategy.watchlist import build_watchlist

router = APIRouter(prefix="/api/nova-os", tags=["nova-os"])

_NOTE = "Signal only. Nova OS decide endpoints never place, modify, or cancel orders."


def _universe() -> list[dict]:
    import main as _main
    seen: dict[str, dict] = {g["symbol"]: g for g in _main._gainer_cache if g.get("symbol")}
    for g in _main._gapper_cache:
        if g.get("symbol"):
            seen[g["symbol"]] = g
    return list(seen.values())


def _find_candidate(symbol: str) -> dict | None:
    symbol = symbol.upper()
    for row in _universe():
        if row.get("symbol") == symbol:
            return row
    return None


@router.get("/policy")
def nova_os_policy() -> dict:
    """Stable vocabulary + decide tunables the UI validates against."""
    return {
        "policy_version": codes.policy_version(),
        "default_mode": NOVA_OS_DEFAULT_MODE,
        "modes": list(NOVA_OS_MODES),
        "decisions": list(NOVA_OS_DECISIONS),
        "actions": list(NOVA_OS_ACTIONS),
        "reason_codes": list(NOVA_OS_REASON_CODES),
        "citations": list(NOVA_OS_CITATIONS),
        "primary_setup": NOVA_OS_PRIMARY_SETUP,
        "decide": {
            "min_first_minute_volume": NOVA_OS_MIN_FIRST_MINUTE_VOLUME,
            "watchlist_max_rank": NOVA_OS_WATCHLIST_MAX_RANK,
            "catalyst_min_confidence": NOVA_OS_CATALYST_MIN_CONFIDENCE,
        },
        "loss_policy": {
            "downgrade_after_losses": NOVA_OS_LOSS_POLICY_DOWNGRADE_AFTER_LOSSES,
            "halt_after_losses": NOVA_OS_LOSS_POLICY_HALT_AFTER_LOSSES,
        },
        "confirm_timeout_sec": NOVA_OS_CONFIRM_TIMEOUT_SEC,
        "max_concurrent_positions": NOVA_OS_MAX_CONCURRENT_POSITIONS,
        "flatten_confirm_token": NOVA_OS_FLATTEN_CONFIRM_TOKEN,
    }


@router.get("/events")
def nova_os_events(
    limit: int = NOVA_OS_EVENTS_DEFAULT_LIMIT,
    symbol: str | None = Query(None, description="Filter to one symbol"),
    kind: str | None = Query(None, description="Filter by event kind (decision/action/system)"),
) -> dict:
    rows = get_events(limit=limit, symbol=symbol, kind=kind)
    return {"count": len(rows), "events": rows}


@router.get("/decide/{symbol}")
def nova_os_decide_one(symbol: str) -> dict:
    """Full gate-by-gate decision for one symbol (signal only)."""
    candidate = _find_candidate(symbol)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"{symbol.upper()} not in scanner cache")

    universe = _universe()
    ranked = build_watchlist(universe, limit=max(NOVA_OS_WATCHLIST_MAX_RANK, 20))
    rank = next((i + 1 for i, e in enumerate(ranked) if e.symbol == symbol.upper()), None)

    provider = _get_discovery_provider()
    try:
        bars_payload = _fetch_chart_bars(
            symbol.upper(), "1Min", 60, discovery_provider=provider, interactive=False,
        )
        bars = bars_payload.get("bars", [])
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Bars unavailable: {exc}") from exc

    decision = decide(candidate, bars, watchlist_rank=rank, mode=NOVA_OS_DEFAULT_MODE)
    return {"note": _NOTE, **decision.to_dict()}


@router.get("/decide")
def nova_os_decide_watchlist(
    limit: int = Query(NOVA_OS_DECIDE_DEFAULT_LIMIT, ge=1, le=20),
) -> dict:
    """Run decide() against the top-N watchlist candidates (signal only)."""
    universe = _universe()
    ranked = build_watchlist(universe, limit=limit)
    provider = _get_discovery_provider()
    decisions = []
    for i, entry in enumerate(ranked):
        row = next((r for r in universe if r.get("symbol") == entry.symbol), {"symbol": entry.symbol})
        try:
            bars_payload = _fetch_chart_bars(
                entry.symbol, "1Min", 60, discovery_provider=provider, interactive=False,
            )
            bars = bars_payload.get("bars", [])
        except Exception:
            bars = []
        decisions.append(
            decide(row, bars, watchlist_rank=i + 1, mode=NOVA_OS_DEFAULT_MODE).to_dict()
        )
    return {"note": _NOTE, "count": len(decisions), "decisions": decisions}
