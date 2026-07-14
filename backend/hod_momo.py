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
"""

from __future__ import annotations

import asyncio
import json
import logging
import logging.handlers
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

import cache as _cache
from constants import (
    HOD_MOMO_ALERTS_PREFIX,
    HOD_MOMO_COOLDOWN_SEC,
    HOD_MOMO_CONSOLIDATION_SEC,
    HOD_MOMO_CONFIG_SCHEMA_VERSION,
    HOD_MOMO_FORMER_MOMO_STRATEGY_ID,
    HOD_MOMO_MASTER_HOD_REQUIRED,
    HOD_MOMO_MASTER_MIN_RVOL,
    HOD_MOMO_MASTER_PREMARKET_MIN_RVOL,
    HOD_MOMO_MASTER_AFTERHOURS_MIN_RVOL,
    HOD_MOMO_MASTER_SURGE_PCT,
    HOD_MOMO_MASTER_SURGE_WINDOW_MIN,
    HOD_MOMO_RVOL_WARMUP_GRACE_SEC,
    HOD_MOMO_SESSION_RESET_HOUR_ET,
    HOD_MOMO_STRATEGY_AUDIO_DEFAULT,
    HOD_MOMO_STRATEGY_COLORS,
    HOD_MOMO_STRATEGY_DEFAULTS,
    HOD_MOMO_STRATEGY_ID_MAX,
    HOD_MOMO_STRATEGY_NAMES,
)
import hod_momo_metrics as _metrics

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


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class StrategyConfig:
    strategy_id: int
    name: str
    color: str
    enabled: bool = True
    audio: bool = True
    notes: str = ""
    # Price filter (0 = disabled)
    min_price: float = 0.0
    max_price: float = 0.0
    # Float filter (0 = disabled)
    min_float: float = 0.0
    max_float: float = 0.0
    # Volume / RVOL filters
    min_volume: float = 0.0
    min_rvol: float = 0.0
    max_rvol: float = 0.0
    # Gap filter (0 = disabled)
    min_gap_pct: float = 0.0
    max_gap_pct: float = 0.0
    # Change filter (0 = disabled)
    min_change_pct: float = 0.0
    max_change_pct: float = 0.0
    # Squeeze / momentum
    surge_pct: float = 0.0
    surge_window_min: int = 0
    surge_method: str = "low_to_current"   # "low_to_current" | "fixed_start"
    # 52-week high proximity (0 = disabled; e.g. 5 = within 5% of 52wk high)
    proximity_52wk_pct: float = 0.0
    # Former Momo ticker list (only used / non-empty for strategy #1)
    former_momo_list: list[str] = field(default_factory=list)
    # Warrior Running Up: False → may fire without a new HOD
    requires_hod: bool = True


@dataclass
class MasterGateConfig:
    hod_required: bool = HOD_MOMO_MASTER_HOD_REQUIRED
    surge_pct: float = HOD_MOMO_MASTER_SURGE_PCT
    surge_window_min: int = HOD_MOMO_MASTER_SURGE_WINDOW_MIN
    min_rvol: float = HOD_MOMO_MASTER_MIN_RVOL
    premarket_min_rvol: float = HOD_MOMO_MASTER_PREMARKET_MIN_RVOL
    afterhours_min_rvol: float = HOD_MOMO_MASTER_AFTERHOURS_MIN_RVOL
    cooldown_sec: float = HOD_MOMO_COOLDOWN_SEC
    consolidation_sec: float = HOD_MOMO_CONSOLIDATION_SEC


@dataclass
class AlertObject:
    id: str                      # "<timestamp_ms>-<symbol>-<strategy_id>"
    timestamp: str               # ISO-8601
    ticker: str
    strategy_id: int
    strategy_name: str
    price: float
    change_pct: float
    rvol: float | None
    float_shares: float | None
    gap_pct: float | None
    volume: int | None
    momentum_pct: float | None   # surge % that triggered (if applicable)
    rvol_source: str | None = None  # "alpaca" | "yfinance" | "yfinance_pace" | ...
    rvol_5min: float | None = None  # Warrior Rel Vol (5 min %)
    consolidation_count: int = 1
    consolidated_ids: list[str] = field(default_factory=list)


@dataclass
class DecisionRecord:
    """One record per on_trade_update call that makes it past the blocklist."""
    ts: float
    symbol: str
    price: float
    snap: dict                   # snapshot fields at decision time
    gate_blocked: str | None     # "blocklist" | "master_hod" | "master_rvol" | "master_surge" | None
    strategies: list[dict]       # [{id, name, passed, blocked_by}]
    would_fire: bool


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


# ── Default config builder ─────────────────────────────────────────────────────

def _build_default_config(strategy_id: int) -> StrategyConfig:
    name = HOD_MOMO_STRATEGY_NAMES[strategy_id]
    color = HOD_MOMO_STRATEGY_COLORS[strategy_id]
    audio = HOD_MOMO_STRATEGY_AUDIO_DEFAULT[strategy_id]
    overrides = HOD_MOMO_STRATEGY_DEFAULTS.get(strategy_id, {})
    cfg = StrategyConfig(strategy_id=strategy_id, name=name, color=color, audio=audio)
    for k, v in overrides.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg


def _build_default_configs() -> dict[int, StrategyConfig]:
    return {sid: _build_default_config(sid) for sid in range(1, HOD_MOMO_STRATEGY_ID_MAX + 1)}


# ── Serialization helpers ──────────────────────────────────────────────────────

def _config_to_dict(cfg: StrategyConfig) -> dict:
    return asdict(cfg)


def _config_from_dict(d: dict) -> StrategyConfig:
    cfg = StrategyConfig(
        strategy_id=d["strategy_id"],
        name=d.get("name", HOD_MOMO_STRATEGY_NAMES.get(d["strategy_id"], "")),
        color=d.get("color", HOD_MOMO_STRATEGY_COLORS.get(d["strategy_id"], "#FFFFFF")),
    )
    for k, v in d.items():
        if k in ("strategy_id", "name", "color"):
            continue
        if hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg


def _master_to_dict(m: MasterGateConfig) -> dict:
    return asdict(m)


def _master_from_dict(d: dict) -> MasterGateConfig:
    m = MasterGateConfig()
    for k, v in d.items():
        if hasattr(m, k):
            setattr(m, k, v)
    return m


def _alert_to_dict(a: AlertObject) -> dict:
    return asdict(a)


def _alert_from_dict(d: dict) -> AlertObject:
    return AlertObject(
        id=d.get("id", ""),
        timestamp=d.get("timestamp", ""),
        ticker=d.get("ticker", ""),
        strategy_id=d.get("strategy_id", 0),
        strategy_name=d.get("strategy_name", ""),
        price=d.get("price", 0.0),
        change_pct=d.get("change_pct", 0.0),
        rvol=d.get("rvol"),
        float_shares=d.get("float_shares"),
        gap_pct=d.get("gap_pct"),
        volume=d.get("volume"),
        momentum_pct=d.get("momentum_pct"),
        rvol_source=d.get("rvol_source"),
        rvol_5min=d.get("rvol_5min"),
        consolidation_count=d.get("consolidation_count", 1),
        consolidated_ids=d.get("consolidated_ids", []),
    )


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


def _save_alerts() -> None:
    _cache.save_hod_momo_snapshot([_alert_to_dict(a) for a in _today_alerts], time.time())


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
    if _in_premarket_et() or _in_afterhours_et():
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


def _price_surge(symbol: str, window_min: int, method: str) -> float | None:
    """Compute the surge % over the last `window_min` minutes.

    low_to_current: (current - min_in_window) / min_in_window * 100
    fixed_start:    (current - price_at_window_start) / price_at_window_start * 100

    Returns None if there is insufficient data.
    """
    buf = _price_buffer.get(symbol)
    if not buf:
        return None
    now_ts = buf[-1][0]
    current_price = buf[-1][1]
    cutoff = now_ts - window_min * 60
    window_prices = [p for t, p in buf if t >= cutoff]
    if len(window_prices) < 2:
        return None
    if method == "fixed_start":
        start_price = window_prices[0]
    else:
        start_price = min(window_prices)
    if start_price <= 0:
        return None
    return (current_price - start_price) / start_price * 100.0


# ── Snapshot store (lightweight per-symbol data for filter evaluation) ─────────

@dataclass
class _TickerSnap:
    price: float = 0.0
    rvol: float | None = None
    rvol_5min: float | None = None
    avg_volume: float | None = None  # for 5-min RVOL typical bar
    float_shares: float | None = None
    gap_pct: float | None = None
    volume: int | None = None
    change_pct: float | None = None
    fifty_two_week_high: float | None = None
    rvol_source: str | None = None   # "alpaca" | "yfinance" | "yfinance_pace" | ...
    last_enriched: float = 0.0   # monotonic timestamp of last enrichment update


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


# ── Filter evaluation — returns (passed, reason) ──────────────────────────────

def _passes(value: float | None, min_val: float, max_val: float) -> tuple[bool, str]:
    """Generic min/max check. 0 = disabled.
    Returns (True, '') on pass, (False, '<field>:<detail>') on fail.
    """
    if value is None:
        if min_val == 0 and max_val == 0:
            return True, ""
        return False, f"value_unknown(min={min_val},max={max_val})"
    if min_val > 0 and value < min_val:
        return False, f"below_min({value:.4g}<{min_val})"
    if max_val > 0 and value > max_val:
        return False, f"above_max({value:.4g}>{max_val})"
    return True, ""


def _evaluate_strategy(
    cfg: StrategyConfig,
    snap: _TickerSnap,
    surge_pct: float | None,
) -> tuple[bool, str]:
    """Returns (passed, blocked_by_reason). blocked_by_reason is '' on pass."""
    if not cfg.enabled:
        return False, "disabled"

    ok, reason = _passes(snap.price, cfg.min_price, cfg.max_price)
    if not ok:
        return False, f"price:{reason}"

    float_val = snap.float_shares
    if cfg.min_float > 0 or cfg.max_float > 0:
        if float_val is None:
            mark_needs_fundamentals(_active_symbol())  # best-effort
            return False, "float:unknown"
        if cfg.min_float > 0 and float_val < cfg.min_float:
            return False, f"float:below_min({float_val:.3g}<{cfg.min_float:.3g})"
        if cfg.max_float > 0 and float_val > cfg.max_float:
            return False, f"float:above_max({float_val:.3g}>{cfg.max_float:.3g})"

    if cfg.min_volume > 0 and (snap.volume is None or snap.volume < cfg.min_volume):
        return False, f"volume:below_min({snap.volume}<{cfg.min_volume})"

    ok, reason = _passes(snap.rvol, cfg.min_rvol, cfg.max_rvol)
    if not ok:
        return False, f"rvol:{reason}"

    ok, reason = _passes(snap.gap_pct, cfg.min_gap_pct, cfg.max_gap_pct)
    if not ok:
        return False, f"gap_pct:{reason}"

    ok, reason = _passes(snap.change_pct, cfg.min_change_pct, cfg.max_change_pct)
    if not ok:
        return False, f"change_pct:{reason}"

    if cfg.surge_pct > 0 and cfg.surge_window_min > 0:
        if surge_pct is None or surge_pct < cfg.surge_pct:
            return False, f"surge:{surge_pct} < {cfg.surge_pct}% in {cfg.surge_window_min}min"

    if cfg.proximity_52wk_pct > 0:
        high52 = snap.fifty_two_week_high
        if high52 is None or high52 <= 0:
            mark_needs_fundamentals(_active_symbol())
            return False, "52wk_high:unknown"
        proximity = ((high52 - snap.price) / high52) * 100.0
        if proximity > cfg.proximity_52wk_pct:
            return False, f"52wk_proximity:{proximity:.2f}%>{cfg.proximity_52wk_pct}%"

    return True, ""


# Thread-local-ish helper: set briefly during on_trade_update so that
# mark_needs_fundamentals called from _evaluate_strategy has the symbol.
_active_symbol_name: str = ""


def _active_symbol() -> str:
    return _active_symbol_name


def _passes_master_gate(symbol: str, snap: _TickerSnap) -> tuple[bool, str]:
    """Global pre-check before strategy evaluation (RVOL + optional master surge).

    HOD is enforced per-strategy via ``StrategyConfig.requires_hod`` so Warrior
    Running Up alerts can fire without a new high of day.
    """
    eff_min_rvol = _effective_min_rvol()
    if eff_min_rvol > 0:
        if snap.rvol is None:
            if _startup_ts and (time.monotonic() - _startup_ts) < HOD_MOMO_RVOL_WARMUP_GRACE_SEC:
                pass
            else:
                return False, "master_rvol:unknown"
        elif snap.rvol < eff_min_rvol:
            return False, f"master_rvol({snap.rvol:.2f}<{eff_min_rvol})"

    if _master.surge_pct > 0 and _master.surge_window_min > 0:
        surge = _price_surge(symbol, _master.surge_window_min, "low_to_current")
        if surge is None:
            return False, f"master_surge:insufficient_data(window={_master.surge_window_min}min)"
        if surge < _master.surge_pct:
            return False, f"master_surge({surge:.2f}%<{_master.surge_pct}%)"

    return True, ""


def _fails_hod_gate(symbol: str, snap: _TickerSnap, cfg: StrategyConfig) -> str | None:
    """Return a block reason if this strategy requires HOD and price is below it."""
    if not (cfg.requires_hod and _master.hod_required):
        return None
    session_high = _session_highs.get(symbol, 0.0)
    if snap.price < session_high:
        return f"hod(price={snap.price:.4g}<hod={session_high:.4g})"
    return None


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
        if snap.avg_volume is not None:
            snap.rvol_5min = _metrics.compute_symbol_rvol_5min(symbol, snap.avg_volume, ts=ts)

    # Blocklist check — record and bail
    if symbol.upper() in _blocklist:
        _gate_counters["blocklist"] += 1
        _record_decision(ts, symbol, price, snap, "blocklist", [])
        _active_symbol_name = ""
        return

    # Master gate
    gate_ok, gate_reason = _passes_master_gate(symbol, snap)
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
            _surge_cache[key] = _price_surge(symbol, window_min, method) if window_min > 0 else None
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

        hod_block = _fails_hod_gate(symbol, snap, cfg)
        if hod_block:
            strategy_decisions.append({"id": strategy_id, "name": cfg.name, "passed": False, "blocked_by": hod_block})
            _gate_counters[f"strategy_{strategy_id}_hod"] += 1
            continue

        surge = _get_surge(cfg.surge_window_min, cfg.surge_method) if cfg.surge_window_min > 0 else None
        passed, blocked_by = _evaluate_strategy(cfg, snap, surge)
        strategy_decisions.append({"id": strategy_id, "name": cfg.name, "passed": passed, "blocked_by": blocked_by})

        if not passed:
            _gate_counters[f"strategy_{strategy_id}_blocked"] += 1
            continue

        _gate_counters[f"strategy_{strategy_id}_fired"] += 1
        any_fired = True

        # Build alert
        ts_iso = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S.000Z")
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
        )

        _cooldown[key] = now_ts + _master.cooldown_sec
        emit_after = now_ts + _master.consolidation_sec
        bucket = _pending_consolidation.setdefault(symbol, [])
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
        datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:23],
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
                    primary = ready[0]
                    primary.consolidation_count = len(ready)
                    primary.consolidated_ids = [a.id for a in ready[1:]]
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
    snaps_populated = sum(
        1 for s in _ticker_snaps.values()
        if s.rvol is not None or s.change_pct is not None
    )
    return {
        "total_trades_seen": _total_trades_seen,
        "universe_size": len(_ticker_snaps),
        "snaps_populated": snaps_populated,
        "counters": dict(_gate_counters),
        "session_highs_tracked": len(_session_highs),
        "fundamentals_queue_depth": len(_fundamentals_queue),
        "pending_symbols": len(_pending_consolidation),
        "alerts_today": len(_today_alerts),
    }


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
    return {
        "symbol": sym,
        "snap": {
            "price": snap.price if snap else None,
            "rvol": snap.rvol if snap else None,
            "float_shares": snap.float_shares if snap else None,
            "gap_pct": snap.gap_pct if snap else None,
            "change_pct": snap.change_pct if snap else None,
            "volume": snap.volume if snap else None,
            "fifty_two_week_high": snap.fifty_two_week_high if snap else None,
            "rvol_source": snap.rvol_source if snap else None,
            "last_enriched": snap.last_enriched if snap else 0.0,
        },
        "session_high": _session_highs.get(sym),
        "decisions": decisions,
        "would_fire_now": _would_fire_now(sym) if snap else None,
    }


def _would_fire_now(symbol: str) -> dict:
    snap = _ticker_snaps.get(symbol)
    if not snap:
        return {"gate": "no_snap", "strategies": []}
    gate_ok, gate_reason = _passes_master_gate(symbol, snap)
    if not gate_ok:
        return {"gate": gate_reason, "strategies": []}
    results = []
    for strategy_id, cfg in _configs.items():
        if not cfg.enabled:
            continue
        surge = _price_surge(symbol, cfg.surge_window_min, cfg.surge_method) if cfg.surge_window_min > 0 else None
        passed, reason = _evaluate_strategy(cfg, snap, surge)
        results.append({"id": strategy_id, "name": cfg.name, "passed": passed, "blocked_by": reason})
    return {"gate": "passed", "strategies": results}


def get_debug_recent(limit: int = 100) -> list[dict]:
    records = list(_recent_decisions)[-limit:]
    return [
        {
            "ts": r.ts,
            "symbol": r.symbol,
            "price": r.price,
            "rvol": r.snap.get("rvol"),
            "gap_pct": r.snap.get("gap_pct"),
            "change_pct": r.snap.get("change_pct"),
            "gate_blocked": r.gate_blocked,
            "strategies_fired": [d["id"] for d in r.strategies if d.get("passed")],
            "would_fire": r.would_fire,
        }
        for r in records
    ]


def get_debug_snaps(limit: int = 50) -> list[dict]:
    """Return top-N snapshots sorted by recency of enrichment."""
    enriched = [
        (sym, snap) for sym, snap in _ticker_snaps.items()
        if snap.rvol is not None or snap.change_pct is not None
    ]
    enriched.sort(key=lambda x: x[1].last_enriched, reverse=True)
    return [
        {
            "symbol": sym,
            "price": snap.price,
            "rvol": snap.rvol,
            "float_shares": snap.float_shares,
            "gap_pct": snap.gap_pct,
            "change_pct": snap.change_pct,
            "volume": snap.volume,
            "rvol_source": snap.rvol_source,
            "last_enriched": snap.last_enriched,
        }
        for sym, snap in enriched[:limit]
    ]


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
