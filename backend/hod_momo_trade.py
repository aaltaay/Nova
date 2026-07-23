"""HOD Momo trade ingestion and decision recording shell (Phase 10)."""
from __future__ import annotations

import logging
import logging.handlers
import os
import time
from collections import deque

import hod_momo_market as _market
import hod_momo_metrics as _metrics
import hod_momo_state as _state
from constants import (
    HOD_MOMO_HOD_EPSILON_ABS,
    HOD_MOMO_HOD_EPSILON_PCT,
    HOD_MOMO_NEW_HOD_GRACE_SEC,
    HOD_MOMO_RVOL_USE_PACE,
    HOD_MOMO_RVOL_WARMUP_GRACE_SEC,
    HOD_MOMO_SUPPRESS_ALERTS_ON_INTEGRITY_FAIL,
    HOD_RAW_MODE,
)
import hod_momo_former as _former
import hod_momo_high as _high
from hod_momo_filters import evaluate_strategy
from hod_momo_filters import fails_hod_gate
from hod_momo_filters import passes_master_gate
from hod_momo_filters import price_surge
from hod_momo_models import (
    AlertObject,
    DecisionRecord,
    TickerSnap,
    format_alert_timestamp,
    format_trade_log_timestamp,
)
from market import pace_relative_volume
from paths import log_dir

logger = logging.getLogger(__name__)
_trade_log = logging.getLogger("hod_momo.trades")
if not _trade_log.handlers:
    _trade_handler = logging.handlers.RotatingFileHandler(
        os.path.join(str(log_dir()), "hod_momo.log"),
        maxBytes=10_000_000,
        backupCount=3,
    )
    _trade_handler.setFormatter(logging.Formatter("%(message)s"))
    _trade_log.addHandler(_trade_handler)
    _trade_log.setLevel(logging.DEBUG)
    _trade_log.propagate = False


def _note_active_quote(symbol: str, ts: float) -> None:
    try:
        import hod_momo_active as active

        active.note_quote(symbol, ts)
    except Exception:
        logger.debug("HOD Momo active quote note failed", exc_info=True)


def _note_active_evaluation(symbol: str) -> None:
    try:
        import hod_momo_active as active

        active.note_evaluation(symbol, time.time())
    except Exception:
        logger.debug("HOD Momo active evaluation note failed", exc_info=True)


def on_trade_update(
    symbol: str,
    price: float,
    ts: float,
    volume: int | None = None,
    day_high: float | None = None,
) -> None:
    """Evaluate one provider-selected trade/snapshot update."""
    state = _state.get_state()
    if not state.configs:
        return

    state.total_trades_seen += 1
    state.last_trade_ts = float(ts) if ts else time.time()
    state.active_symbol_name = symbol
    _market.update_price_buffer(symbol, price, ts)
    _market.request_surge_seed(symbol)
    _note_active_quote(symbol, state.last_trade_ts)

    # HOD truth: tick-6 / bar seed only — never invent session high from last.
    if day_high is None:
        try:
            from ibkr import ticks as _ticks

            day_high = _ticks.get_day_high(symbol)
        except Exception:
            day_high = None
    if day_high is not None:
        _high.apply_day_high(symbol, day_high)
    _high.raise_observed_high(symbol, price, now_ts=float(ts) if ts else None)

    snap = state.ticker_snaps.setdefault(symbol, TickerSnap())
    snap.price = price
    if volume is not None:
        snap.volume = volume
        _metrics.update_cum_volume(symbol, volume, ts)
        if snap.avg_volume is not None and snap.avg_volume > 0 and volume > 0:
            if HOD_MOMO_RVOL_USE_PACE:
                paced = pace_relative_volume(volume, snap.avg_volume)
                if paced is not None:
                    snap.rvol = paced
                    snap.rvol_source = "ibkr_pace"
            else:
                snap.rvol = round(volume / snap.avg_volume, 2)
                snap.rvol_source = "ibkr"
            snap.rvol_5min = _metrics.compute_symbol_rvol_5min(
                symbol,
                snap.avg_volume,
                ts=ts,
            )

    if symbol.upper() in state.blocklist:
        state.gate_counters["blocklist"] += 1
        _record_decision(ts, symbol, price, snap, "blocklist", [])
        _note_active_evaluation(symbol)
        state.active_symbol_name = ""
        return

    effective_min_rvol = _market.effective_min_rvol()
    in_warmup_grace = bool(state.startup_ts) and (
        time.monotonic() - state.startup_ts
    ) < HOD_MOMO_RVOL_WARMUP_GRACE_SEC
    gate_ok, gate_reason = passes_master_gate(
        snap,
        state.master,
        effective_min_rvol,
        in_warmup_grace,
        state.price_buffer.get(symbol),
    )
    if not gate_ok:
        state.gate_counters[gate_reason.split("(")[0]] += 1
        _record_decision(ts, symbol, price, snap, gate_reason, [])
        _note_active_evaluation(symbol)
        state.active_symbol_name = ""
        return

    state.gate_counters["passed_master"] += 1
    surge_cache: dict[tuple[int, str], float | None] = {}

    def get_surge(window_min: int, method: str) -> float | None:
        key = (window_min, method)
        if key not in surge_cache:
            surge_cache[key] = (
                price_surge(state.price_buffer.get(symbol), window_min, method)
                if window_min > 0
                else None
            )
        return surge_cache[key]

    now_ts = time.time()
    strategy_decisions: list[dict] = []
    any_fired = False
    for strategy_id, config in state.configs.items():
        if not config.enabled:
            strategy_decisions.append(
                {
                    "id": strategy_id,
                    "name": config.name,
                    "passed": False,
                    "blocked_by": "disabled",
                }
            )
            continue

        former_block = _former.former_momo_block_reason(strategy_id, symbol, config)
        if former_block:
            strategy_decisions.append(
                {
                    "id": strategy_id,
                    "name": config.name,
                    "passed": False,
                    "blocked_by": former_block,
                }
            )
            continue

        # Mute removed: consolidation window alone batches Warrior "(N in Xs)".
        cooldown_sec = float(state.master.cooldown_sec or 0.0)
        if cooldown_sec > 0:
            cooldown_key = (symbol, strategy_id)
            if now_ts < state.cooldown.get(cooldown_key, 0.0):
                strategy_decisions.append(
                    {
                        "id": strategy_id,
                        "name": config.name,
                        "passed": False,
                        "blocked_by": "cooldown",
                    }
                )
                continue

        hod_block = fails_hod_gate(
            snap.price,
            state.session_highs.get(symbol, 0.0),
            config,
            state.master.hod_required,
            high_seeded=_high.is_high_seeded(symbol),
            epsilon_abs=HOD_MOMO_HOD_EPSILON_ABS,
            epsilon_pct=HOD_MOMO_HOD_EPSILON_PCT,
            new_hod_age_sec=_high.last_new_hod_age_sec(
                symbol, now_ts=float(ts) if ts else None,
            ),
            new_hod_grace_sec=HOD_MOMO_NEW_HOD_GRACE_SEC,
        )
        if hod_block:
            strategy_decisions.append(
                {
                    "id": strategy_id,
                    "name": config.name,
                    "passed": False,
                    "blocked_by": hod_block,
                }
            )
            state.gate_counters[f"strategy_{strategy_id}_hod"] += 1
            continue

        surge = (
            get_surge(config.surge_window_min, config.surge_method)
            if config.surge_window_min > 0
            else None
        )
        if HOD_RAW_MODE:
            passed, blocked_by = True, ""
        else:
            passed, blocked_by = evaluate_strategy(
                config,
                snap,
                surge,
                lambda: _market.mark_needs_fundamentals(
                    state.active_symbol_name
                ),
            )
        if passed and HOD_MOMO_SUPPRESS_ALERTS_ON_INTEGRITY_FAIL:
            try:
                from integrity_live import hod_integrity_is_failing

                if hod_integrity_is_failing():
                    passed = False
                    blocked_by = "integrity_fail_suppress"
                    state.gate_counters["integrity_fail_suppress"] = (
                        state.gate_counters.get("integrity_fail_suppress", 0) + 1
                    )
            except Exception:
                logger.debug(
                    "HOD Momo integrity suppress check failed",
                    exc_info=True,
                )

        strategy_decisions.append(
            {
                "id": strategy_id,
                "name": config.name,
                "passed": passed,
                "blocked_by": blocked_by,
            }
        )
        if not passed:
            state.gate_counters[f"strategy_{strategy_id}_blocked"] += 1
            continue

        state.gate_counters[f"strategy_{strategy_id}_fired"] += 1
        any_fired = True
        alert = AlertObject(
            id=f"{int(ts * 1000)}-{symbol}-{strategy_id}",
            timestamp=format_alert_timestamp(ts),
            ticker=symbol,
            strategy_id=strategy_id,
            strategy_name=config.name,
            price=price,
            change_pct=snap.change_pct or 0.0,
            rvol=snap.rvol,
            float_shares=snap.float_shares,
            gap_pct=snap.gap_pct,
            volume=snap.volume,
            momentum_pct=surge,
            rvol_source=snap.rvol_source,
            rvol_5min=snap.rvol_5min,
            created_ts=now_ts,
        )
        if cooldown_sec > 0:
            state.cooldown[(symbol, strategy_id)] = now_ts + cooldown_sec
        bucket = state.pending_consolidation.setdefault(symbol, [])
        emit_after = (
            bucket[0][0]
            if bucket
            else now_ts + state.master.consolidation_sec
        )
        bucket.append((emit_after, alert))
        logger.debug(
            "HOD Momo: queued alert %s / strategy %d",
            symbol,
            strategy_id,
        )

    _record_decision(
        ts,
        symbol,
        price,
        snap,
        None,
        strategy_decisions,
        would_fire=any_fired,
    )
    snap_summary = (
        f"rvol={snap.rvol} float={snap.float_shares} "
        f"gap={snap.gap_pct} change={snap.change_pct} vol={snap.volume}"
    )
    fired_ids = [
        str(item["id"]) for item in strategy_decisions if item["passed"]
    ]
    blocked_summary = "; ".join(
        f"{item['id']}:{item['blocked_by']}"
        for item in strategy_decisions
        if not item["passed"] and item["blocked_by"] not in ("disabled",)
    )
    _trade_log.debug(
        "%s TRADE %s price=%.4g snap={%s} gate=passed fired=[%s] blocked=[%s]",
        format_trade_log_timestamp(),
        symbol,
        price,
        snap_summary,
        ",".join(fired_ids) if fired_ids else "none",
        blocked_summary or "none",
    )
    _note_active_evaluation(symbol)
    state.active_symbol_name = ""


def _record_decision(
    ts: float,
    symbol: str,
    price: float,
    snap: TickerSnap,
    gate_blocked: str | None,
    strategies: list[dict],
    would_fire: bool = False,
) -> None:
    state = _state.get_state()
    record = DecisionRecord(
        ts=ts,
        symbol=symbol,
        price=price,
        snap={
            "price": snap.price,
            "rvol": snap.rvol,
            "float_shares": snap.float_shares,
            "gap_pct": snap.gap_pct,
            "change_pct": snap.change_pct,
            "volume": snap.volume,
            "fifty_two_week_high": snap.fifty_two_week_high,
            "last_enriched": snap.last_enriched,
            **_high.high_debug(symbol),
        },
        gate_blocked=gate_blocked,
        strategies=strategies,
        would_fire=would_fire,
    )
    state.recent_decisions.append(record)
    state.per_symbol_decisions.setdefault(
        symbol,
        deque(maxlen=20),
    ).append(record)
