"""
HOD Momo data models — dataclasses and pure serialization helpers.

Split out of hod_momo.py (backend-modularity rule) to isolate the alert
engine's data shapes from its stateful trade-processing logic. Nothing in
this module reads or writes module-level state; every function here is a
pure transformation of its arguments, which makes it trivially unit
testable on its own.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from scanner_wire import wire_safe

from constants import (
    HOD_MOMO_MASTER_AFTERHOURS_MIN_RVOL,
    HOD_MOMO_MASTER_HOD_REQUIRED,
    HOD_MOMO_MASTER_MIN_PRICE,
    HOD_MOMO_MASTER_MIN_RVOL,
    HOD_MOMO_MASTER_MIN_VOLUME,
    HOD_MOMO_MASTER_PREMARKET_MIN_RVOL,
    HOD_MOMO_MASTER_SURGE_PCT,
    HOD_MOMO_MASTER_SURGE_WINDOW_MIN,
    HOD_MOMO_COOLDOWN_SEC,
    HOD_MOMO_CONSOLIDATION_SEC,
    HOD_MOMO_INVENTED_CHANGE_BEFORE_TS,
    HOD_MOMO_STRATEGY_AUDIO_DEFAULT,
    HOD_MOMO_STRATEGY_COLORS,
    HOD_MOMO_STRATEGY_DEFAULTS,
    HOD_MOMO_STRATEGY_ID_MAX,
    HOD_MOMO_STRATEGY_NAMES,
)


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
    # momentum Running Up: False → may fire without a new HOD
    requires_hod: bool = True


@dataclass
class MasterGateConfig:
    hod_required: bool = HOD_MOMO_MASTER_HOD_REQUIRED
    surge_pct: float = HOD_MOMO_MASTER_SURGE_PCT
    surge_window_min: int = HOD_MOMO_MASTER_SURGE_WINDOW_MIN
    # Tradeable floor (2026-09-22): volume today, price and a known RVOL must
    # clear these before any strategy is evaluated. 0 turns a floor off.
    min_volume: float = HOD_MOMO_MASTER_MIN_VOLUME
    min_price: float = HOD_MOMO_MASTER_MIN_PRICE
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
    change_pct: float | None     # None when the snapshot had none -- never an invented 0.0
    rvol: float | None
    float_shares: float | None
    gap_pct: float | None
    volume: int | None
    momentum_pct: float | None   # surge % that triggered (if applicable)
    rvol_source: str | None = None  # "alpaca" | "yfinance" | "yfinance_pace" | ...
    rvol_5min: float | None = None  # momentum Rel Vol (5 min %)
    consolidation_count: int = 1
    consolidated_ids: list[str] = field(default_factory=list)
    # Actual burst duration in seconds (momentum "(3 in 5sec)"); None if single fire.
    consolidation_span_sec: int | None = None
    # Unix time when the alert was created (for span math / display collapse).
    created_ts: float = 0.0


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


@dataclass
class TickerSnap:
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
    # Epoch seconds (time.time()) of the last enrichment update. It is served
    # by the debug endpoints and aged by the browser; a monotonic clock read
    # "1790012783s ago" there (QA C34).
    last_enriched: float = 0.0


# ── Default config builder ─────────────────────────────────────────────────────

def build_default_config(strategy_id: int) -> StrategyConfig:
    name = HOD_MOMO_STRATEGY_NAMES[strategy_id]
    color = HOD_MOMO_STRATEGY_COLORS[strategy_id]
    audio = HOD_MOMO_STRATEGY_AUDIO_DEFAULT[strategy_id]
    overrides = HOD_MOMO_STRATEGY_DEFAULTS.get(strategy_id, {})
    cfg = StrategyConfig(strategy_id=strategy_id, name=name, color=color, audio=audio)
    for k, v in overrides.items():
        if hasattr(cfg, k):
            # Copy mutable defaults (e.g. former_momo_list) so every config
            # instance owns its own list instead of sharing the module-level one.
            setattr(cfg, k, list(v) if isinstance(v, list) else v)
    return cfg


def build_default_configs() -> dict[int, StrategyConfig]:
    return {sid: build_default_config(sid) for sid in range(1, HOD_MOMO_STRATEGY_ID_MAX + 1)}


# ── Serialization helpers ──────────────────────────────────────────────────────

def config_to_dict(cfg: StrategyConfig) -> dict:
    return asdict(cfg)


def config_from_dict(d: dict) -> StrategyConfig:
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


def master_to_dict(m: MasterGateConfig) -> dict:
    return asdict(m)


def master_from_dict(d: dict) -> MasterGateConfig:
    m = MasterGateConfig()
    for k, v in d.items():
        if hasattr(m, k):
            setattr(m, k, v)
    return m


def _timestamp_or_from_created(timestamp: str | None, created_ts: float) -> str:
    """Prefer ISO timestamp; heal empty values from created_ts (unix seconds)."""
    if timestamp:
        return str(timestamp)
    if created_ts and created_ts > 0:
        return format_alert_timestamp(float(created_ts))
    return ""


def alert_to_dict(a: AlertObject) -> dict:
    """Wire/persist shape of an alert; a non-finite float is None (QA C32)."""
    payload = asdict(a)
    payload["timestamp"] = _timestamp_or_from_created(
        payload.get("timestamp"),
        float(payload.get("created_ts") or 0.0),
    )
    return wire_safe(payload)


def new_alert(
    *,
    symbol: str,
    strategy_id: int,
    strategy_name: str,
    price: float,
    snap: TickerSnap,
    momentum_pct: float | None,
    trade_ts: float,
    created_ts: float,
) -> AlertObject:
    """One freshly raised alert.

    ``id`` comes from ``created_ts`` -- when Nova raised the alert -- not the
    trade timestamp: a stale print re-evaluated minutes later reused the same
    trade time, so distinct alerts shared an id (41 React duplicate-key errors
    per strip walk, QA V16) and the dated archive, which merges by id, kept
    only one of them. ``timestamp`` stays the trigger print's time.
    ``change_pct`` is the snapshot's own value: None stays None (QA C33).
    """
    return AlertObject(
        id=f"{int(created_ts * 1000)}-{symbol}-{strategy_id}",
        timestamp=format_alert_timestamp(trade_ts),
        ticker=symbol,
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        price=price,
        change_pct=snap.change_pct,
        rvol=snap.rvol,
        float_shares=snap.float_shares,
        gap_pct=snap.gap_pct,
        volume=snap.volume,
        momentum_pct=momentum_pct,
        rvol_source=snap.rvol_source,
        rvol_5min=snap.rvol_5min,
        created_ts=created_ts,
    )


def restored_change_pct(d: dict) -> float | None:
    """A stored alert's change, with the pre-fix fill-in read as unknown.

    Before QA C33's fix an alert stored ``snap.change_pct or 0.0``: 626 of
    one morning's alerts said "CHG 0.0%" for a snapshot that had no change.
    An exact 0.0 on an alert created before the cutoff is that fill-in.
    """
    change = d.get("change_pct")
    if isinstance(change, bool) or not isinstance(change, (int, float)):
        return None if change is None else change
    try:
        created = float(d.get("created_ts") or 0.0)
    except (TypeError, ValueError):
        created = 0.0
    if change == 0 and created < HOD_MOMO_INVENTED_CHANGE_BEFORE_TS:
        return None
    return change


def alert_from_dict(d: dict) -> AlertObject:
    created_ts = float(d.get("created_ts") or 0.0)
    return AlertObject(
        id=d.get("id", ""),
        timestamp=_timestamp_or_from_created(d.get("timestamp"), created_ts),
        ticker=d.get("ticker", ""),
        strategy_id=d.get("strategy_id", 0),
        strategy_name=d.get("strategy_name", ""),
        price=d.get("price", 0.0),
        change_pct=restored_change_pct(d),
        rvol=d.get("rvol"),
        float_shares=d.get("float_shares"),
        gap_pct=d.get("gap_pct"),
        volume=d.get("volume"),
        momentum_pct=d.get("momentum_pct"),
        rvol_source=d.get("rvol_source"),
        rvol_5min=d.get("rvol_5min"),
        consolidation_count=d.get("consolidation_count", 1),
        consolidated_ids=d.get("consolidated_ids", []),
        consolidation_span_sec=d.get("consolidation_span_sec"),
        created_ts=created_ts,
    )


# ── Timestamp formatting ────────────────────────────────────────────────────────
#
# Both helpers use timezone-aware UTC construction (datetime.now(timezone.utc) /
# datetime.fromtimestamp(ts, tz=timezone.utc)) instead of the deprecated
# datetime.utcnow() / datetime.utcfromtimestamp(). Since neither format string
# below includes %z/%Z, the aware-vs-naive distinction does not change the
# rendered string — output is byte-identical to the pre-fix behavior.

def format_alert_timestamp(ts: float) -> str:
    """ISO-8601 millisecond timestamp for AlertObject.timestamp, e.g. 2026-07-15T05:13:00.000Z."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def format_trade_log_timestamp() -> str:
    """Current UTC time truncated to milliseconds, for the per-trade debug log line."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:23]
