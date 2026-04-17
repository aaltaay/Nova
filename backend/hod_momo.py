"""
HOD Momo Scanner engine.

All engine state lives here — no state leaks into main.py (per backend-modularity rule).
main.py calls:
  - load_state()               at lifespan startup
  - on_trade_update(sym, price, ts, rvol, float_, gap_pct, volume, change_pct)
                               from _ws_stream_loop / _handle_trade path
  - flush_consolidated_loop()  as a background asyncio task
  - session_reset_loop()       as a background asyncio task
  - get_ws_clients()           to push alerts to connected WS clients
  - add_ws_client(ws) / remove_ws_client(ws)
  - get_today_alerts()         for initial WS payload + REST GET
  - get_configs() / update_config() / reset_config() / reset_all()
  - get_master() / update_master()
  - get_blocklist() / add_block() / remove_block()
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import cache as _cache
from constants import (
    HOD_MOMO_ALERTS_PREFIX,
    HOD_MOMO_COOLDOWN_SEC,
    HOD_MOMO_CONSOLIDATION_SEC,
    HOD_MOMO_MASTER_HOD_REQUIRED,
    HOD_MOMO_MASTER_MIN_RVOL,
    HOD_MOMO_MASTER_PREMARKET_MIN_RVOL,
    HOD_MOMO_MASTER_AFTERHOURS_MIN_RVOL,
    HOD_MOMO_MASTER_SURGE_PCT,
    HOD_MOMO_MASTER_SURGE_WINDOW_MIN,
    HOD_MOMO_SESSION_RESET_HOUR_ET,
    HOD_MOMO_STRATEGY_AUDIO_DEFAULT,
    HOD_MOMO_STRATEGY_COLORS,
    HOD_MOMO_STRATEGY_DEFAULTS,
    HOD_MOMO_STRATEGY_NAMES,
)

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")


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
    consolidation_count: int = 1
    consolidated_ids: list[str] = field(default_factory=list)


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
    return {sid: _build_default_config(sid) for sid in range(1, 12)}


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
        consolidation_count=d.get("consolidation_count", 1),
        consolidated_ids=d.get("consolidated_ids", []),
    )


# ── Persistence ────────────────────────────────────────────────────────────────

def _save_configs() -> None:
    payload = {
        "master": _master_to_dict(_master),
        "strategies": {str(sid): _config_to_dict(cfg) for sid, cfg in _configs.items()},
    }
    _cache.save_hod_momo_configs(payload)


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
                if 1 <= sid <= 11:
                    _configs[sid] = _config_from_dict(d)
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
    # Only reset once we're at or past the session-reset hour
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
    # Trim entries older than max buffer window
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
    float_shares: float | None = None
    gap_pct: float | None = None
    volume: int | None = None
    change_pct: float | None = None
    fifty_two_week_high: float | None = None


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
) -> None:
    """Called by main.py whenever fresh snapshot data arrives for a symbol.

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
    if change_pct is not None:
        snap.change_pct = change_pct
    if fifty_two_week_high is not None:
        snap.fifty_two_week_high = fifty_two_week_high


# ── Filter evaluation ──────────────────────────────────────────────────────────

def _passes(value: float | None, min_val: float, max_val: float, disabled_on_zero: bool = True) -> bool:
    """Generic min/max check. 0 = disabled when disabled_on_zero=True."""
    if value is None:
        # Unknown value: only fail if a concrete filter is active
        if (disabled_on_zero and min_val == 0 and max_val == 0):
            return True
        if not disabled_on_zero:
            return True
        return min_val == 0 and max_val == 0
    if disabled_on_zero:
        if min_val > 0 and value < min_val:
            return False
        if max_val > 0 and value > max_val:
            return False
    else:
        if value < min_val:
            return False
        if max_val > 0 and value > max_val:
            return False
    return True


def _evaluate_strategy(cfg: StrategyConfig, snap: _TickerSnap, surge_pct: float | None) -> bool:
    """Returns True if the ticker passes ALL active filters in `cfg`."""
    if not cfg.enabled:
        return False

    # Price
    if not _passes(snap.price, cfg.min_price, cfg.max_price):
        return False

    # Float (float unknown → fail if filter active)
    float_val = snap.float_shares
    if (cfg.min_float > 0 or cfg.max_float > 0) and float_val is None:
        return False
    if float_val is not None:
        if cfg.min_float > 0 and float_val < cfg.min_float:
            return False
        if cfg.max_float > 0 and float_val > cfg.max_float:
            return False

    # Volume
    if cfg.min_volume > 0 and (snap.volume is None or snap.volume < cfg.min_volume):
        return False

    # RVOL
    if not _passes(snap.rvol, cfg.min_rvol, cfg.max_rvol):
        return False

    # Gap %
    if not _passes(snap.gap_pct, cfg.min_gap_pct, cfg.max_gap_pct):
        return False

    # Change %
    if not _passes(snap.change_pct, cfg.min_change_pct, cfg.max_change_pct):
        return False

    # Surge / momentum
    if cfg.surge_pct > 0 and cfg.surge_window_min > 0:
        if surge_pct is None or surge_pct < cfg.surge_pct:
            return False

    # 52-week high proximity
    if cfg.proximity_52wk_pct > 0:
        high52 = snap.fifty_two_week_high
        if high52 is None or high52 <= 0:
            return False
        proximity = ((high52 - snap.price) / high52) * 100.0
        if proximity > cfg.proximity_52wk_pct:
            return False

    return True


def _passes_master_gate(symbol: str, snap: _TickerSnap) -> bool:
    """Global pre-check that every symbol must pass before strategy evaluation."""
    # HOD check
    if _master.hod_required:
        session_high = _session_highs.get(symbol, 0.0)
        if snap.price < session_high:
            return False

    # RVOL
    eff_min_rvol = _effective_min_rvol()
    if eff_min_rvol > 0 and (snap.rvol is None or snap.rvol < eff_min_rvol):
        return False

    # Momentum surge
    if _master.surge_pct > 0 and _master.surge_window_min > 0:
        surge = _price_surge(symbol, _master.surge_window_min, "low_to_current")
        if surge is None or surge < _master.surge_pct:
            return False

    return True


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
    rvol: float | None = None,
    float_shares: float | None = None,
    gap_pct: float | None = None,
    volume: int | None = None,
    change_pct: float | None = None,
    fifty_two_week_high: float | None = None,
) -> None:
    """Called synchronously from the trade-processing path in main.py.

    Updates internal state and queues any triggered alerts onto the asyncio broadcast queue.
    """
    if not _configs:
        return

    # Update rolling price buffer
    _update_price_buffer(symbol, price, ts)

    # Update session high
    prev_high = _session_highs.get(symbol, 0.0)
    if price > prev_high:
        _session_highs[symbol] = price

    # Update snapshot store
    update_ticker_snapshot(
        symbol, price,
        rvol=rvol,
        float_shares=float_shares,
        gap_pct=gap_pct,
        volume=volume,
        change_pct=change_pct,
        fifty_two_week_high=fifty_two_week_high,
    )

    # Blocklist check
    if symbol.upper() in _blocklist:
        return

    snap = _ticker_snaps[symbol]

    # Master gate
    if not _passes_master_gate(symbol, snap):
        return

    # Pre-compute surge values for all active surge windows
    _surge_cache: dict[tuple[int, str], float | None] = {}

    def _get_surge(window_min: int, method: str) -> float | None:
        key = (window_min, method)
        if key not in _surge_cache:
            _surge_cache[key] = _price_surge(symbol, window_min, method) if window_min > 0 else None
        return _surge_cache[key]

    now_ts = time.time()
    queue = get_broadcast_queue()

    for strategy_id, cfg in _configs.items():
        if not cfg.enabled:
            continue

        # Former Momo list check (only gates if the list is non-empty for this strategy)
        if cfg.former_momo_list and symbol.upper() not in [s.upper() for s in cfg.former_momo_list]:
            continue

        # Cooldown check
        key = (symbol, strategy_id)
        if now_ts < _cooldown.get(key, 0.0):
            continue

        surge = _get_surge(cfg.surge_window_min, cfg.surge_method) if cfg.surge_window_min > 0 else None

        if not _evaluate_strategy(cfg, snap, surge):
            continue

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
        )

        # Set cooldown
        _cooldown[key] = now_ts + _master.cooldown_sec

        # Queue for consolidation
        emit_after = now_ts + _master.consolidation_sec
        bucket = _pending_consolidation.setdefault(symbol, [])
        bucket.append((emit_after, alert))

        logger.debug("HOD Momo: queued alert %s / strategy %d", symbol, strategy_id)

        # Put on broadcast queue for async flush
        try:
            queue.put_nowait(("pending", alert))
        except asyncio.QueueFull:
            pass


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
                # Partition into ready (window expired) and still-pending
                ready = [a for emit_ts, a in bucket if now >= emit_ts]
                still_pending = [(et, a) for et, a in bucket if now < et]
                _pending_consolidation[symbol] = still_pending

                if not ready:
                    continue

                if len(ready) == 1:
                    to_emit.append(ready[0])
                else:
                    # Consolidate into first alert
                    primary = ready[0]
                    primary.consolidation_count = len(ready)
                    primary.consolidated_ids = [a.id for a in ready[1:]]
                    to_emit.append(primary)

            for alert in to_emit:
                _today_alerts.insert(0, alert)  # newest first
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
                # Clear the "pending" marker from broadcast queue if any
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


def add_block(symbol: str) -> list[str]:
    _blocklist.add(symbol.upper())
    _cache.save_hod_momo_blocklist(list(_blocklist))
    return get_blocklist()


def remove_block(symbol: str) -> list[str]:
    _blocklist.discard(symbol.upper())
    _cache.save_hod_momo_blocklist(list(_blocklist))
    return get_blocklist()


# ── Startup ────────────────────────────────────────────────────────────────────

def load_state() -> None:
    """Called once at lifespan startup. Loads persisted configs, blocklist, and today's alerts."""
    global _configs, _master, _blocklist, _today_alerts, _session_date

    # Initialise configs with defaults first, then overlay from disk
    _configs = _build_default_configs()
    _load_configs_from_disk()

    # Load blocklist
    bl = _cache.load_hod_momo_blocklist()
    _blocklist = {s.upper() for s in bl}

    # Load today's alerts
    alerts_raw, _ = _cache.load_hod_momo_snapshot()
    _today_alerts = [_alert_from_dict(a) for a in alerts_raw]

    # Initialise session date so rollover detection works
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
