"""Provider-aware chart bars facade.

When discovery is IBKR, chart bars come from IBKR only -- never silently from
Alpaca. The HTTP path is store-first (ADR 012): return archived IBKR bars
immediately and schedule a paced fill. Alpaca is used only when
discovery_provider is explicitly alpaca.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from bars import fetch_bars as fetch_alpaca_bars
from constants import (
    CHART_DEFAULT_BARS,
    CHART_DEFAULT_TIMEFRAME,
    CHART_TIMEFRAMES,
    IBKR_BARS_WARM_TIMEFRAMES,
)
from ibkr import client as _ibkr_client

logger = logging.getLogger(__name__)


def _store_read(symbol: str, timeframe: str, limit: int) -> dict | None:
    from bars_store import read

    return read(symbol, timeframe, limit)


def _schedule_ibkr_fill(
    symbol: str,
    timeframe: str,
    limit: int,
    *,
    priority: str,
) -> None:
    from ibkr.historical_service import schedule_fill

    schedule_fill(symbol, timeframe, limit, priority=priority)


def _empty_filling(symbol: str, timeframe: str) -> dict:
    from bars_store import empty_filling

    return empty_filling(symbol, timeframe)


def _store_series_settled(
    timeframe: str, bar_count: int, coverage: dict | None
) -> bool:
    from bars_store import is_coverage_fresh, store_series_complete

    return store_series_complete(timeframe, bar_count) and is_coverage_fresh(
        coverage, timeframe
    )


def fetch_chart_bars(
    symbol: str,
    timeframe: str = CHART_DEFAULT_TIMEFRAME,
    limit: int = CHART_DEFAULT_BARS,
    *,
    discovery_provider: str,
    interactive: bool = False,
) -> dict:
    """Return ``{symbol, timeframe, bars, source, coverage}``.

    Single-feed rule: when ``discovery_provider == \"ibkr\"``, candles are
    IBKR-sourced (store and/or live historical). There is no silent Alpaca
    fallback. An empty store while Gateway is down is still HTTP 503.

    Sim: IBKR historical is the global chart base for real tickers. Capture overlays scrubbed intraday (not daily+) when that day+ticker is selected. SIM1 stays local/synthetic.
    """
    symbol = symbol.upper()
    from sim.mode import is_sim_mode

    if is_sim_mode():
        from constants_sim import SIM_SYMBOL
        from sim import market as _sim_market
        from sim import replay as _sim_replay

        # Lock 2026-09-19: IBKR is global chart base for real tickers.
        # Capture overlays scrubbed intraday when that day+ticker is selected.
        # SIM1 has no IBKR contract — always local/capture/sim.
        replay_sym = str(
            (_sim_replay.status_payload() or {}).get("replay_symbol") or ""
        ).strip().upper()
        capture_overlay = (
            _sim_replay.is_capture_replay()
            and replay_sym
            and symbol == replay_sym
        )
        _daily_tfs = frozenset({"1Day", "1Week", "1Month"})

        if symbol == SIM_SYMBOL:
            return _sim_market.chart_bars(symbol, timeframe, limit)

        if capture_overlay and timeframe not in _daily_tfs:
            # Scrubbed session tape bars from capture; daily+ still IBKR below.
            return _sim_market.chart_bars(symbol, timeframe, limit)

        # Real ticker, no capture overlay (or daily+): fall through to IBKR.
        # (Do not 503 — IBKR historical is the Sim global base.)

    if discovery_provider == "ibkr":
        stored = _store_read(symbol, timeframe, limit)
        ready = _ibkr_client.is_ready()
        if stored and stored.get("bars"):
            coverage = dict(stored.get("coverage") or {})
            # A complete+fresh series needs no fill: do not queue pacing debt
            # for a no-op. Incomplete or stale data still fills.
            if ready and not _store_series_settled(
                timeframe, len(stored["bars"]), stored.get("coverage")
            ):
                # Pane already painted something -- this is a reconciliation
                # refresh, not a blank-screen wait. "warm" sheds on any
                # pacing wait so it cannot starve a genuinely empty pane's
                # open_chart fill of the shared 60-req/10-min IB budget
                # (PROBLEM_LOG 2026-08-26 chart hist starvation).
                _schedule_ibkr_fill(
                    symbol, timeframe, limit,
                    priority="warm" if interactive else "background",
                )
                coverage["filling"] = True
            else:
                coverage["filling"] = False
            stored["coverage"] = coverage
            stored.setdefault("source", "ibkr")
            return stored
        if ready:
            # Store is genuinely empty -- this is the blank-screen case that
            # should win the budget over already-painted stale panes.
            _schedule_ibkr_fill(
                symbol, timeframe, limit,
                priority="open_chart" if interactive else "background",
            )
            return _empty_filling(symbol, timeframe)
        reason = _ibkr_client.session_reason()
        if not _ibkr_client.is_connected():
            detail = (
                "Chart bars require IB Gateway (discovery=ibkr). "
                "Connect Gateway -- Nova will not fall back to Alpaca."
            )
        else:
            detail = (
                f"Chart bars unavailable: IBKR session not usable ({reason}). "
                "Nova will not fall back to Alpaca."
            )
        raise HTTPException(status_code=503, detail=detail)

    payload = fetch_alpaca_bars(symbol, timeframe, limit)
    payload.setdefault("source", "alpaca")
    return payload


def parse_batch_timeframes(raw: str | None) -> list[str]:
    """Split ``1Min,5Min,1Day`` into validated timeframe ids (order preserved)."""
    if not raw or not str(raw).strip():
        return list(IBKR_BARS_WARM_TIMEFRAMES)
    seen: set[str] = set()
    out: list[str] = []
    for part in str(raw).split(","):
        tf = part.strip()
        if not tf or tf in seen:
            continue
        if tf not in CHART_TIMEFRAMES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid timeframe '{tf}'. Valid values: {list(CHART_TIMEFRAMES)}",
            )
        seen.add(tf)
        out.append(tf)
    if not out:
        raise HTTPException(status_code=400, detail="No valid timeframes in batch request")
    return out


def fetch_chart_bars_batch(
    symbol: str,
    timeframes: list[str],
    limit: int = CHART_DEFAULT_BARS,
    *,
    discovery_provider: str,
    interactive: bool = True,
) -> dict:
    """Fetch multiple timeframes; per-tf errors stay in ``errors`` (no stale fill)."""
    symbol = symbol.upper()
    results: dict[str, dict] = {}
    errors: dict[str, dict] = {}
    for tf in timeframes:
        try:
            results[tf] = fetch_chart_bars(
                symbol,
                tf,
                limit,
                discovery_provider=discovery_provider,
                interactive=interactive,
            )
        except HTTPException as exc:
            errors[tf] = {"status_code": exc.status_code, "detail": str(exc.detail)}
    return {
        "symbol": symbol,
        "timeframes": list(timeframes),
        "results": results,
        "errors": errors,
    }
