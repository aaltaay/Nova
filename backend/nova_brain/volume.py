"""Volume pack: fire or propose once when day-volume rate jumps on the shared feed."""
from __future__ import annotations

from typing import Any, Callable

from constants_bot import (
    BOT_ACTION_KINDS,
    BOT_LEVEL_STRATEGY,
    BOT_PACK_VOLUME,
    BOT_VOLUME_BASELINE_SEC,
    BOT_VOLUME_COOLDOWN_SEC,
    BOT_VOLUME_MIN_MULT,
    BOT_VOLUME_WINDOW_SEC,
)
from volume_boost_detect import measure_spike

ProposeFn = Callable[[dict[str, Any]], Any]
FireFn = Callable[[str, str], Any]


def _settings(session: dict[str, Any]) -> dict[str, Any]:
    return dict(dict(session.get("pack_settings") or {}).get(BOT_PACK_VOLUME) or {})


def volume_kind(session: dict[str, Any]) -> str:
    kind = str(_settings(session).get("volume_kind") or "buy_market")
    return kind if kind in BOT_ACTION_KINDS else "buy_market"


def cooldown_sec(session: dict[str, Any]) -> float:
    try:
        return max(1.0, float(_settings(session).get("cooldown_sec") or BOT_VOLUME_COOLDOWN_SEC))
    except (TypeError, ValueError):
        return float(BOT_VOLUME_COOLDOWN_SEC)


def min_mult(session: dict[str, Any]) -> float:
    try:
        return max(1.0, float(_settings(session).get("min_mult") or BOT_VOLUME_MIN_MULT))
    except (TypeError, ValueError):
        return float(BOT_VOLUME_MIN_MULT)


def window_sec(session: dict[str, Any]) -> float:
    try:
        return max(1.0, float(_settings(session).get("window_sec") or BOT_VOLUME_WINDOW_SEC))
    except (TypeError, ValueError):
        return float(BOT_VOLUME_WINDOW_SEC)


def baseline_sec(session: dict[str, Any]) -> float:
    try:
        return max(1.0, float(_settings(session).get("baseline_sec") or BOT_VOLUME_BASELINE_SEC))
    except (TypeError, ValueError):
        return float(BOT_VOLUME_BASELINE_SEC)


def _as_vol(value: Any) -> int | None:
    if value is None:
        return None
    try:
        vol = int(value)
    except (TypeError, ValueError):
        return None
    return vol if vol >= 0 else None


def _as_ts(value: Any, now: float) -> float:
    if value is None:
        return float(now)
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return float(now)
    return ts if ts > 0 else float(now)


def detect_boosts(
    previous: dict[str, Any],
    watch: dict[str, Any],
    *,
    now: float,
    window_sec: float,
    baseline_sec: float,
    min_mult: float,
) -> tuple[list[str], dict[str, Any]]:
    """Rising-edge last-window volume rate vs the prior baseline rate."""
    nxt: dict[str, Any] = {}
    boosts: list[str] = []
    cutoff = float(now) - float(window_sec) - float(baseline_sec)
    for row in watch.get("symbols") or []:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        prev = dict(previous.get(symbol) or {})
        samples = [dict(item) for item in (prev.get("samples") or []) if isinstance(item, dict)]
        vol = _as_vol(row.get("volume"))
        if vol is None:
            nxt[symbol] = {
                "samples": [s for s in samples if float(s.get("ts") or 0) >= cutoff],
                "boosted": False,
            }
            continue
        samples.append({"ts": _as_ts(row.get("last_update_ts"), now), "volume": vol})
        samples = [s for s in samples if float(s.get("ts") or 0) >= cutoff]
        pairs: list[tuple[float, int]] = []
        for item in samples:
            sample_vol = _as_vol(item.get("volume"))
            if sample_vol is None:
                continue
            pairs.append((float(item.get("ts") or 0), sample_vol))
        metrics = measure_spike(
            pairs,
            now,
            spike_sec=window_sec,
            baseline_sec=baseline_sec,
            min_spike_shares=1,
            min_baseline_shares=1,
        )
        boosted_now = metrics is not None and metrics.ratio >= float(min_mult)
        if boosted_now and not bool(prev.get("boosted")):
            boosts.append(symbol)
        row_out: dict[str, Any] = {"samples": samples, "boosted": boosted_now}
        if metrics is not None:
            row_out["mult"] = metrics.ratio
        nxt[symbol] = row_out
    return boosts, nxt


def tick(
    *,
    session: dict[str, Any],
    watch: dict[str, Any],
    previous: dict[str, Any],
    last_fire: dict[str, float],
    now: float,
    fire: FireFn,
    propose: ProposeFn | None = None,
) -> dict[str, Any]:
    if (session.get("active_pack") or "") != BOT_PACK_VOLUME:
        return previous
    boosts, nxt = detect_boosts(
        previous,
        watch,
        now=now,
        window_sec=window_sec(session),
        baseline_sec=baseline_sec(session),
        min_mult=min_mult(session),
    )
    kind = volume_kind(session)
    cool = cooldown_sec(session)
    level = int(session.get("level") or 0)
    live = bool(session.get("live_fire_ready"))
    for symbol in boosts:
        last = float(last_fire.get(symbol) or 0)
        if now - last < cool:
            continue
        if live:
            fire(kind, symbol)
            last_fire[symbol] = now
            continue
        if level >= BOT_LEVEL_STRATEGY or propose is None:
            continue
        row = nxt.get(symbol) or {}
        mult = row.get("mult")
        reason = "volume boost"
        if mult is not None:
            reason = (
                f"volume boost {mult:g}x vs {baseline_sec(session):g}s baseline"
            )
        propose(
            {
                "symbol": symbol,
                "side": "BUY",
                "kind": kind,
                "reason": reason,
                "confidence": 0.6,
            }
        )
        last_fire[symbol] = now
    return nxt
