"""
HOD Momo Scanner engine.

All engine state lives here — no state leaks into main.py (per backend-modularity rule).
main.py calls:
  - load_state()               at lifespan startup
  - on_trade_update(sym, price, ts, volume)
                               from _ws_stream_loop / _handle_trade path
                               (RVOL/float/gap/change come from the enrichment loop)
  - update_ticker_snapshot(...)from hod_momo_enrichment.py (rich per-symbol data)
  - flush_consolidated_loop()  as a background asyncio task
  - session_reset_loop()       as a background asyncio task
  - get_ws_clients()           to push alerts to connected WS clients
  - add_ws_client(ws) / remove_ws_client(ws)
  - get_today_alerts()         for initial WS payload + REST GET
  - get_configs() / update_config() / reset_config() / reset_all()
  - get_master() / update_master()
  - get_blocklist() / add_block() / remove_block()
  - mark_needs_fundamentals(sym) called by enrichment when symbol qualifies
  - get_fundamentals_queue()   consumed by hod_momo_enrichment
  - get_debug_counters() / get_debug_symbol(sym) / get_debug_recent(limit) / get_debug_snaps(limit)

Data shapes (dataclasses + serialization) live in hod_momo_models.py, and
pure per-strategy gate evaluation lives in hod_momo_filters.py — both are
stateless and imported below. Debug-payload formatting lives in
hod_momo_debug.py. This file owns every piece of *mutable* engine state
(price buffers, session highs, cooldowns, configs, alerts, counters) and
the trade-update ingestion path that reads/writes it, since the test suite
exercises that state directly (see backend/tests/test_hod_momo_engine.py).
"""

from __future__ import annotations

import asyncio
import json
import logging
import logging.handlers
import os
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

import cache as _cache
import hod_momo_debug as _debug
from constants import (
    HOD_MOMO_ALERT_SAVE_INTERVAL_SEC,
    HOD_MOMO_CONFIG_SCHEMA_VERSION,
    HOD_MOMO_FORMER_MOMO_STRATEGY_ID,
    HOD_MOMO_MASTER_SURGE_PCT,
    HOD_MOMO_RVOL_USE_PACE,
    HOD_MOMO_RVOL_WARMUP_GRACE_SEC,
    HOD_MOMO_SESSION_RESET_HOUR_ET,
    HOD_MOMO_STRATEGY_ID_MAX,
)
from hod_momo_filters import evaluate_strategy as _evaluate_strategy
from hod_momo_filters import fails_hod_gate as _fails_hod_gate
from hod_momo_filters import passes_master_gate as _passes_master_gate
from hod_momo_filters import price_surge as _price_surge
from hod_momo_models import AlertObject, DecisionRecord, MasterGateConfig, StrategyConfig
from hod_momo_models import TickerSnap as _TickerSnap
from hod_momo_models import (
    alert_from_dict as _alert_from_dict,
    alert_to_dict as _alert_to_dict,
    build_default_config as _build_default_config,
    build_default_configs as _build_default_configs,
    config_from_dict as _config_from_dict,
    config_to_dict as _config_to_dict,
    format_alert_timestamp as _format_alert_timestamp,
    format_trade_log_timestamp as _format_trade_log_timestamp,
    master_from_dict as _master_from_dict,
    master_to_dict as _master_to_dict,
)
import hod_momo_metrics as _metrics
from market import pace_relative_volume

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

# ── Dedicated rotating log for per-trade debug lines ──────────────────────────
from paths import log_dir as _nova_log_dir

_log_dir = str(_nova_log_dir())
_trade_log = logging.getLogger("hod_momo.trades")
if not _trade_log.handlers:
    _trade_handler = logging.handlers.RotatingFileHandler(
        os.path.join(_log_dir, "hod_momo.log"),
        maxBytes=10_000_000,
        backupCount=3,
    )
    _trade_handler.setFormatter(logging.Formatter("%(message)s"))
    _trade_log.addHandler(_trade_handler)
    _trade_log.setLevel(logging.DEBUG)
    _trade_log.propagate = False


# ── Module-level state ─────────────────────────────────────────────────────────

# Rolling (unix_ts, price) buffer per symbol — trimmed to max surge window
_price_buffer: dict[str, deque[tuple[float, float]]] = {}

# Session high-of-day per symbol (reset at session rollover)
_session_highs: dict[str, float] = {}

# Cooldown: maps (symbol, strategy_id) -> unix timestamp when next alert is allowed
_cooldown: dict[tuple[str, int], float] = {}

# Pending consolidation: symbol -> list of (emit_after_ts, AlertObject)
_pending_consolidation: dict[str, list[tuple[float, AlertObject]]] = {}

# Strategy configs (keyed by strategy_id 1-11)
_configs: dict[int, StrategyConfig] = {}

# Master gate config
_master: MasterGateConfig = MasterGateConfig()

# Blocklist
_blocklist: set[str] = set()

# Current session date string (YYYY-MM-DD in ET) — used for rollover detection
_session_date: str = ""

# Today's alert list (in-memory, periodically saved to disk)
_today_alerts: list[AlertObject] = []

# Connected WS clients for the HOD Momo feed
_hod_ws_clients: set[Any] = set()

# ── Debug state ────────────────────────────────────────────────────────────────

_total_trades_seen: int = 0
_gate_counters: dict[str, int] = defaultdict(int)
# last 500 decisions across all symbols
_recent_decisions: deque[DecisionRecord] = deque(maxlen=500)
# last 20 decisions per symbol
_per_symbol_decisions: dict[str, deque[DecisionRecord]] = {}

# Fundamentals request queue — enrichment loop drains this
_fundamentals_queue: deque[str] = deque()
_fundamentals_queued: set[str] = set()

# Startup timestamp — used for RVOL warmup grace period
_startup_ts: float = 0.0


# ── Persistence ────────────────────────────────────────────────────────────────

def _save_configs() -> None:
    payload = {
        "schema_version": HOD_MOMO_CONFIG_SCHEMA_VERSION,
        "master": _master_to_dict(_master),
        "strategies": {str(sid): _config_to_dict(cfg) for sid, cfg in _configs.items()},
    }
    _cache.save_hod_momo_configs(payload)


def _migrate_loaded_configs(data: dict) -> bool:
    """Apply one-time schema migrations. Returns True if config was changed."""
    global _master, _configs
    version = int(data.get("schema_version") or 1)
    changed = False
    if version < 2:
        # v2: Warrior parity — master surge off (strategies own momentum).
        if abs(float(_master.surge_pct) - 3.0) < 1e-9:
            _master.surge_pct = HOD_MOMO_MASTER_SURGE_PCT
            changed = True
            logger.info(
                "HOD Momo: migrated master surge_pct 3.0 → %s (schema v2 Warrior parity)",
                HOD_MOMO_MASTER_SURGE_PCT,
            )
    if version < 3:
        # v3: Running Up Alert (strategy 12) + requires_hod on StrategyConfig.
        if 12 not in _configs:
            _configs[12] = _build_default_config(12)
        logger.info("HOD Momo: schema v3 — Running Up Alert + 5-min RVOL fields")
        changed = True
    return changed


def _load_configs_from_disk() -> bool:
    """Returns True if configs were found and loaded."""
    data = _cache.load_hod_momo_configs()
    if not data:
        return False
    global _master, _configs
    try:
        if "master" in data:
            _master = _master_from_dict(data["master"])
        if "strategies" in data:
            for sid_str, d in data["strategies"].items():
                sid = int(sid_str)
                if 1 <= sid <= HOD_MOMO_STRATEGY_ID_MAX:
                    _configs[sid] = _config_from_dict(d)
        added = False
        for sid in range(1, HOD_MOMO_STRATEGY_ID_MAX + 1):
            if sid not in _configs:
                _configs[sid] = _build_default_config(sid)
                added = True
        if _migrate_loaded_configs(data) or added:
            _save_configs()
        return True
    except Exception:
        logger.warning("HOD Momo: failed to load configs from disk — using defaults")
        return False


_alerts_dirty: bool = False
_last_alert_save_mono: float = 0.0


def _save_alerts(*, force: bool = False) -> None:
    """Persist today's alerts, rate-limited so hot sessions do not freeze the event loop.

    Serializing 3k+ alerts to disk on every emit blocked asyncio (WS / scanners felt frozen).
    """
    global _alerts_dirty, _last_alert_save_mono
    now = time.monotonic()
    if not force and (now - _last_alert_save_mono) < HOD_MOMO_ALERT_SAVE_INTERVAL_SEC:
        _alerts_dirty = True
        return
    _cache.save_hod_momo_snapshot([_alert_to_dict(a) for a in _today_alerts], time.time())
    _last_alert_save_mono = now
    _alerts_dirty = False


def flush_pending_alert_save() -> None:
    """Write if a deferred save is outstanding (call from flush loop / shutdown)."""
    global _alerts_dirty
    if _alerts_dirty:
        _save_alerts(force=True)


# ── Session management ─────────────────────────────────────────────────────────

def _current_date_et() -> str:
    return datetime.now(_ET).strftime("%Y-%m-%d")


def _check_and_reset_session() -> bool:
    """If the ET date has rolled past HOD_MOMO_SESSION_RESET_HOUR_ET, reset session state.

    Returns True if a reset occurred.
    """
    global _session_date, _today_alerts, _session_highs, _cooldown, _pending_consolidation
    now_et = datetime.now(_ET)
    if now_et.hour < HOD_MOMO_SESSION_RESET_HOUR_ET:
        return False
    current = now_et.strftime("%Y-%m-%d")
    if current == _session_date:
        return False
    logger.info("HOD Momo: session rollover → %s (was %s)", current, _session_date)
    _session_date = current
    _today_alerts = []
    _session_highs = {}
    _cooldown = {}
    _pending_consolidation = {}
    _metrics.clear_volume_buffers()
    return True


# ── Time helpers ───────────────────────────────────────────────────────────────

def _in_premarket_et() -> bool:
    now = datetime.now(_ET)
    h = now.hour + now.minute / 60.0
    return 4.0 <= h < 9.5


def _in_afterhours_et() -> bool:
    now = datetime.now(_ET)
    h = now.hour + now.minute / 60.0
    return 16.0 <= h < 20.0


def _effective_min_rvol() -> float:
    """Return the RVOL threshold for the current session window."""
    if _in_afterhours_et():
        return _master.afterhours_min_rvol
    if _in_premarket_et():
        return _master.premarket_min_rvol
    return _master.min_rvol


# ── Rolling price buffer ───────────────────────────────────────────────────────

_MAX_BUFFER_MINUTES = 60  # keep at most 60 minutes of price history per symbol


def _update_price_buffer(symbol: str, price: float, ts: float) -> None:
    buf = _price_buffer.setdefault(symbol, deque())
    buf.append((ts, price))
    cutoff = ts - _MAX_BUFFER_MINUTES * 60
    while buf and buf[0][0] < cutoff:
        buf.popleft()


# ── Snapshot store (lightweight per-symbol data for filter evaluation) ─────────

_ticker_snaps: dict[str, _TickerSnap] = {}


def update_ticker_snapshot(
    symbol: str,
    price: float,
    rvol: float | None = None,
    float_shares: float | None = None,
    gap_pct: float | None = None,
    volume: int | None = None,
    change_pct: float | None = None,
    fifty_two_week_high: float | None = None,
    rvol_source: str | None = None,
    avg_volume: float | None = None,
    rvol_5min: float | None = None,
) -> None:
    """Called by hod_momo_enrichment.py whenever fresh snapshot data arrives.

    Merges in non-None values so callers can do partial updates.
    """
    snap = _ticker_snaps.setdefault(symbol, _TickerSnap())
    snap.price = price
    if rvol is not None:
        snap.rvol = rvol
    if float_shares is not None:
        snap.float_shares = float_shares
    if gap_pct is not None:
        snap.gap_pct = gap_pct
    if volume is not None:
        snap.volume = volume
        _metrics.update_cum_volume(symbol, volume, time.time())
    if change_pct is not None:
        snap.change_pct = change_pct
    if fifty_two_week_high is not None:
        snap.fifty_two_week_high = fifty_two_week_high
    if rvol_source is not None:
        snap.rvol_source = rvol_source
    if avg_volume is not None:
        snap.avg_volume = avg_volume
    if rvol_5min is not None:
        snap.rvol_5min = rvol_5min
    elif snap.avg_volume is not None:
        snap.rvol_5min = _metrics.compute_symbol_rvol_5min(symbol, snap.avg_volume)
    snap.last_enriched = time.monotonic()


# ── Fundamentals queue ─────────────────────────────────────────────────────────

def mark_needs_fundamentals(symbol: str) -> None:
    """Request that hod_momo_enrichment fetches float/52wk-high for this symbol."""
    if symbol not in _fundamentals_queued:
        _fundamentals_queued.add(symbol)
        _fundamentals_queue.append(symbol)


def get_fundamentals_queue() -> deque[str]:
    return _fundamentals_queue


def pop_fundamentals_request() -> str | None:
    try:
        sym = _fundamentals_queue.popleft()
        _fundamentals_queued.discard(sym)
        return sym
    except IndexError:
        return None


# Thread-local-ish helper: set briefly during on_trade_update so that
# mark_needs_fundamentals called from _evaluate_strategy has the symbol.
_active_symbol_name: str = ""


def _active_symbol() -> str:
    return _active_symbol_name


# ── Alert emission ─────────────────────────────────────────────────────────────

_alert_broadcast_queue: asyncio.Queue | None = None


def get_broadcast_queue() -> asyncio.Queue:
    global _alert_broadcast_queue
    if _alert_broadcast_queue is None:
        _alert_broadcast_queue = asyncio.Queue()
    return _alert_broadcast_queue


def on_trade_update(
    symbol: str,
    price: float,
    ts: float,
    volume: int | None = None,
) -> None:
    """Called synchronously from the trade-processing path in main.py.

    Only price/volume come from the WS message. RVOL / float / gap / change /
    52wk-high come from the enrichment loop via update_ticker_snapshot().
    """
    global _total_trades_seen, _active_symbol_name

    if not _configs:
        return

    _total_trades_seen += 1
    _active_symbol_name = symbol

    # Update rolling price buffer
    _update_price_buffer(symbol, price, ts)

    # Update session high
    prev_high = _session_highs.get(symbol, 0.0)
    if price > prev_high:
        _session_highs[symbol] = price

    # Merge price/volume into snapshot (enrichment keeps other fields current)
    snap = _ticker_snaps.setdefault(symbol, _TickerSnap())
    snap.price = price
    if volume is not None:
        snap.volume = volume
        _metrics.update_cum_volume(symbol, volume, ts)
        # IBKR table ticks carry consolidated cum volume — recompute pace RVOL
        # so AH names are not stuck on thin yfinance/IEX values (~1.3x vs 30x).
        if snap.avg_volume is not None and snap.avg_volume > 0 and volume > 0:
            if HOD_MOMO_RVOL_USE_PACE:
                paced = pace_relative_volume(volume, snap.avg_volume)
                if paced is not None:
                    snap.rvol = paced
                    snap.rvol_source = "ibkr_pace"
            else:
                snap.rvol = round(volume / snap.avg_volume, 2)
                snap.rvol_source = "ibkr"
            snap.rvol_5min = _metrics.compute_symbol_rvol_5min(symbol, snap.avg_volume, ts=ts)

    # Blocklist check — record and bail
    if symbol.upper() in _blocklist:
        _gate_counters["blocklist"] += 1
        _record_decision(ts, symbol, price, snap, "blocklist", [])
        _active_symbol_name = ""
        return

    # Master gate
    eff_min_rvol = _effective_min_rvol()
    in_warmup_grace = bool(_startup_ts) and (time.monotonic() - _startup_ts) < HOD_MOMO_RVOL_WARMUP_GRACE_SEC
    gate_ok, gate_reason = _passes_master_gate(
        snap, _master, eff_min_rvol, in_warmup_grace, _price_buffer.get(symbol)
    )
    if not gate_ok:
        # Increment the first word of the reason as the counter key
        counter_key = gate_reason.split("(")[0]
        _gate_counters[counter_key] += 1
        _record_decision(ts, symbol, price, snap, gate_reason, [])
        _active_symbol_name = ""
        return

    _gate_counters["passed_master"] += 1

    # Pre-compute surge values for all active surge windows
    _surge_cache: dict[tuple[int, str], float | None] = {}

    def _get_surge(window_min: int, method: str) -> float | None:
        key = (window_min, method)
        if key not in _surge_cache:
            _surge_cache[key] = (
                _price_surge(_price_buffer.get(symbol), window_min, method) if window_min > 0 else None
            )
        return _surge_cache[key]

    now_ts = time.time()
    queue = get_broadcast_queue()
    strategy_decisions: list[dict] = []
    any_fired = False

    for strategy_id, cfg in _configs.items():
        if not cfg.enabled:
            strategy_decisions.append({"id": strategy_id, "name": cfg.name, "passed": False, "blocked_by": "disabled"})
            continue

        # Former Momo (strategy 1): Warrior tags known former runners only.
        # Empty list must NOT mean "every symbol" — that spam is not Warrior parity.
        if strategy_id == HOD_MOMO_FORMER_MOMO_STRATEGY_ID:
            if not cfg.former_momo_list:
                strategy_decisions.append({
                    "id": strategy_id, "name": cfg.name, "passed": False,
                    "blocked_by": "former_momo_list_empty",
                })
                continue
            allow = {s.upper() for s in cfg.former_momo_list}
            if symbol.upper() not in allow:
                strategy_decisions.append({
                    "id": strategy_id, "name": cfg.name, "passed": False,
                    "blocked_by": "not_in_former_momo_list",
                })
                continue
        elif cfg.former_momo_list and symbol.upper() not in [s.upper() for s in cfg.former_momo_list]:
            strategy_decisions.append({"id": strategy_id, "name": cfg.name, "passed": False, "blocked_by": "not_in_former_momo_list"})
            continue

        # Cooldown check
        key = (symbol, strategy_id)
        if now_ts < _cooldown.get(key, 0.0):
            strategy_decisions.append({"id": strategy_id, "name": cfg.name, "passed": False, "blocked_by": "cooldown"})
            continue

        hod_block = _fails_hod_gate(snap.price, _session_highs.get(symbol, 0.0), cfg, _master.hod_required)
        if hod_block:
            strategy_decisions.append({"id": strategy_id, "name": cfg.name, "passed": False, "blocked_by": hod_block})
            _gate_counters[f"strategy_{strategy_id}_hod"] += 1
            continue

        surge = _get_surge(cfg.surge_window_min, cfg.surge_method) if cfg.surge_window_min > 0 else None
        passed, blocked_by = _evaluate_strategy(
            cfg, snap, surge, lambda: mark_needs_fundamentals(_active_symbol())
        )
        strategy_decisions.append({"id": strategy_id, "name": cfg.name, "passed": passed, "blocked_by": blocked_by})

        if not passed:
            _gate_counters[f"strategy_{strategy_id}_blocked"] += 1
            continue

        _gate_counters[f"strategy_{strategy_id}_fired"] += 1
        any_fired = True

        # Build alert
        ts_iso = _format_alert_timestamp(ts)
        alert_id = f"{int(ts * 1000)}-{symbol}-{strategy_id}"
        alert = AlertObject(
            id=alert_id,
            timestamp=ts_iso,
            ticker=symbol,
            strategy_id=strategy_id,
            strategy_name=cfg.name,
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

        _cooldown[key] = now_ts + _master.cooldown_sec
        # Warrior-style window: first alert in the burst sets emit time; later
        # same-ticker fires join that bucket instead of each getting a new deadline.
        bucket = _pending_consolidation.setdefault(symbol, [])
        if bucket:
            emit_after = bucket[0][0]
        else:
            emit_after = now_ts + _master.consolidation_sec
        bucket.append((emit_after, alert))

        logger.debug("HOD Momo: queued alert %s / strategy %d", symbol, strategy_id)

        try:
            queue.put_nowait(("pending", alert))
        except asyncio.QueueFull:
            pass

    _record_decision(ts, symbol, price, snap, None, strategy_decisions, would_fire=any_fired)

    # Structured trade log line
    snap_summary = (
        f"rvol={snap.rvol} float={snap.float_shares} "
        f"gap={snap.gap_pct} change={snap.change_pct} vol={snap.volume}"
    )
    fired_ids = [str(d["id"]) for d in strategy_decisions if d["passed"]]
    blocked_summary = "; ".join(
        f"{d['id']}:{d['blocked_by']}" for d in strategy_decisions if not d["passed"] and d["blocked_by"] not in ("disabled",)
    )
    _trade_log.debug(
        "%s TRADE %s price=%.4g snap={%s} gate=passed fired=[%s] blocked=[%s]",
        _format_trade_log_timestamp(),
        symbol, price, snap_summary,
        ",".join(fired_ids) if fired_ids else "none",
        blocked_summary or "none",
    )

    _active_symbol_name = ""


def _record_decision(
    ts: float,
    symbol: str,
    price: float,
    snap: _TickerSnap,
    gate_blocked: str | None,
    strategies: list[dict],
    would_fire: bool = False,
) -> None:
    snap_dict = {
        "price": snap.price,
        "rvol": snap.rvol,
        "float_shares": snap.float_shares,
        "gap_pct": snap.gap_pct,
        "change_pct": snap.change_pct,
        "volume": snap.volume,
        "fifty_two_week_high": snap.fifty_two_week_high,
        "last_enriched": snap.last_enriched,
    }
    rec = DecisionRecord(
        ts=ts, symbol=symbol, price=price,
        snap=snap_dict, gate_blocked=gate_blocked,
        strategies=strategies, would_fire=would_fire,
    )
    _recent_decisions.append(rec)
    per_sym = _per_symbol_decisions.setdefault(symbol, deque(maxlen=20))
    per_sym.append(rec)


# ── Consolidation flush loop ───────────────────────────────────────────────────

async def flush_consolidated_loop() -> None:
    """Background asyncio task: checks pending consolidation buckets every second,
    emits consolidated alerts when their window has expired."""
    queue = get_broadcast_queue()
    while True:
        try:
            await asyncio.sleep(1.0)
            now = time.time()
            to_emit: list[AlertObject] = []

            for symbol in list(_pending_consolidation.keys()):
                bucket = _pending_consolidation[symbol]
                ready = [a for emit_ts, a in bucket if now >= emit_ts]
                still_pending = [(et, a) for et, a in bucket if now < et]
                _pending_consolidation[symbol] = still_pending

                if not ready:
                    continue

                if len(ready) == 1:
                    to_emit.append(ready[0])
                else:
                    # Newest price/strategy wins; badge uses real first→last span.
                    primary = ready[-1]
                    primary.consolidation_count = len(ready)
                    primary.consolidated_ids = [a.id for a in ready[:-1]]
                    first_ts = min((a.created_ts or 0.0) for a in ready) or now
                    last_ts = max((a.created_ts or 0.0) for a in ready) or now
                    span = int(round(max(0.0, last_ts - first_ts)))
                    primary.consolidation_span_sec = max(1, span) if span > 0 else 1
                    to_emit.append(primary)

            for alert in to_emit:
                _today_alerts.insert(0, alert)
                _save_alerts()
                payload = json.dumps({"type": "alert", "alert": _alert_to_dict(alert)})
                dead: list = []
                for ws in list(_hod_ws_clients):
                    try:
                        await ws.send_text(payload)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    _hod_ws_clients.discard(ws)
                try:
                    queue.get_nowait()
                except Exception:
                    pass

            flush_pending_alert_save()

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("HOD Momo flush loop error: %s", exc)


# ── Session reset loop ─────────────────────────────────────────────────────────

async def session_reset_loop() -> None:
    """Background asyncio task: checks for session rollover every 30 seconds."""
    while True:
        try:
            await asyncio.sleep(30.0)
            _check_and_reset_session()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("HOD Momo session reset loop error: %s", exc)


# ── WebSocket client management ────────────────────────────────────────────────

def add_ws_client(ws: Any) -> None:
    _hod_ws_clients.add(ws)


def remove_ws_client(ws: Any) -> None:
    _hod_ws_clients.discard(ws)


def get_ws_clients() -> set:
    return _hod_ws_clients


# ── Public query API ───────────────────────────────────────────────────────────

def get_today_alerts() -> list[dict]:
    return [_alert_to_dict(a) for a in _today_alerts]


def get_ws_initial_payload() -> dict:
    """Full day's alerts (newest first). UI virtualizes rows — do not truncate here."""
    all_alerts = get_today_alerts()
    return {
        "type": "initial",
        "alerts": all_alerts,
        "total": len(all_alerts),
    }


def get_configs() -> dict:
    return {
        "master": _master_to_dict(_master),
        "strategies": {str(sid): _config_to_dict(cfg) for sid, cfg in _configs.items()},
    }


def update_config(strategy_id: int, patch: dict) -> dict | None:
    cfg = _configs.get(strategy_id)
    if cfg is None:
        return None
    for k, v in patch.items():
        if hasattr(cfg, k) and k not in ("strategy_id",):
            setattr(cfg, k, v)
    _save_configs()
    return _config_to_dict(cfg)


def reset_config(strategy_id: int) -> dict | None:
    if strategy_id not in range(1, 12):
        return None
    _configs[strategy_id] = _build_default_config(strategy_id)
    _save_configs()
    return _config_to_dict(_configs[strategy_id])


def reset_all() -> dict:
    global _configs, _master
    _configs = _build_default_configs()
    _master = MasterGateConfig()
    _save_configs()
    return get_configs()


def get_master() -> dict:
    return _master_to_dict(_master)


def update_master(patch: dict) -> dict:
    for k, v in patch.items():
        if hasattr(_master, k):
            setattr(_master, k, v)
    _save_configs()
    return _master_to_dict(_master)


def get_blocklist() -> list[str]:
    return sorted(_blocklist)


def is_blocked(symbol: str) -> bool:
    return symbol.upper() in _blocklist


# Optional hook set by main.py at startup to invalidate the asset/universe cache
# when the blocklist changes. Avoids a circular-import at module level.
_on_blocklist_changed: Callable[[], None] | None = None


def add_block(symbol: str) -> list[str]:
    _blocklist.add(symbol.upper())
    _cache.save_hod_momo_blocklist(list(_blocklist))
    if _on_blocklist_changed:
        _on_blocklist_changed()
    return get_blocklist()


def remove_block(symbol: str) -> list[str]:
    _blocklist.discard(symbol.upper())
    _cache.save_hod_momo_blocklist(list(_blocklist))
    if _on_blocklist_changed:
        _on_blocklist_changed()
    return get_blocklist()


# ── Debug API ──────────────────────────────────────────────────────────────────

def get_debug_counters() -> dict:
    return _debug.build_debug_counters(
        _total_trades_seen,
        _ticker_snaps,
        _gate_counters,
        _session_highs,
        _fundamentals_queue,
        _pending_consolidation,
        _today_alerts,
    )


def get_debug_symbol(symbol: str) -> dict:
    sym = symbol.upper()
    snap = _ticker_snaps.get(sym)
    decisions = [
        {
            "ts": r.ts,
            "price": r.price,
            "snap": r.snap,
            "gate_blocked": r.gate_blocked,
            "strategies": r.strategies,
            "would_fire": r.would_fire,
        }
        for r in list(_per_symbol_decisions.get(sym, []))
    ]
    would_fire = _would_fire_now(sym) if snap else None
    return _debug.build_debug_symbol(sym, snap, decisions, _session_highs.get(sym), would_fire)


def _would_fire_now(symbol: str) -> dict:
    snap = _ticker_snaps.get(symbol)
    if not snap:
        return {"gate": "no_snap", "strategies": []}
    eff_min_rvol = _effective_min_rvol()
    in_warmup_grace = bool(_startup_ts) and (time.monotonic() - _startup_ts) < HOD_MOMO_RVOL_WARMUP_GRACE_SEC
    gate_ok, gate_reason = _passes_master_gate(
        snap, _master, eff_min_rvol, in_warmup_grace, _price_buffer.get(symbol)
    )
    if not gate_ok:
        return {"gate": gate_reason, "strategies": []}
    results = []
    for strategy_id, cfg in _configs.items():
        if not cfg.enabled:
            continue
        surge = (
            _price_surge(_price_buffer.get(symbol), cfg.surge_window_min, cfg.surge_method)
            if cfg.surge_window_min > 0 else None
        )
        passed, reason = _evaluate_strategy(
            cfg, snap, surge, lambda: mark_needs_fundamentals(_active_symbol())
        )
        results.append({"id": strategy_id, "name": cfg.name, "passed": passed, "blocked_by": reason})
    return {"gate": "passed", "strategies": results}


def get_debug_recent(limit: int = 100) -> list[dict]:
    return _debug.build_debug_recent(_recent_decisions, limit)


def get_debug_snaps(limit: int = 50) -> list[dict]:
    """Return top-N snapshots sorted by recency of enrichment."""
    return _debug.build_debug_snaps(_ticker_snaps, limit)


def peek_rvol_5min(symbol: str) -> float | None:
    """Return cached Warrior 5-min RVOL for an open/HOD-watched symbol, if any."""
    snap = _ticker_snaps.get(symbol.upper())
    return snap.rvol_5min if snap else None


# ── Startup ────────────────────────────────────────────────────────────────────

def load_state() -> None:
    """Called once at lifespan startup. Loads persisted configs, blocklist, and today's alerts."""
    global _configs, _master, _blocklist, _today_alerts, _session_date, _startup_ts

    _startup_ts = time.monotonic()

    _configs = _build_default_configs()
    _load_configs_from_disk()

    bl = _cache.load_hod_momo_blocklist()
    _blocklist = {s.upper() for s in bl}

    alerts_raw, _ = _cache.load_hod_momo_snapshot()
    _today_alerts = [_alert_from_dict(a) for a in alerts_raw]

    _check_and_reset_session()
    if not _session_date:
        _session_date = _current_date_et()

    logger.info(
        "HOD Momo: loaded %d alerts, %d blocked symbols, %d strategies",
        len(_today_alerts), len(_blocklist), len(_configs),
    )


def get_history_alerts(date_str: str) -> list[dict]:
    """Load alerts for a past date from disk."""
    data = _cache.load_hod_momo_snapshot_for_date(date_str)
    return data.get("alerts", [])
