"""Quote-spike pack: fire or propose once when last/mid jumps on the shared feed."""
from __future__ import annotations

from typing import Any, Callable

from constants_bot import (
    BOT_ACTION_KINDS,
    BOT_LEVEL_STRATEGY,
    BOT_PACK_QUOTE_SPIKE,
    BOT_QUOTE_SPIKE_COOLDOWN_SEC,
    BOT_QUOTE_SPIKE_MIN_PCT,
    BOT_QUOTE_SPIKE_WINDOW_SEC,
)

ProposeFn = Callable[[dict[str, Any]], Any]
FireFn = Callable[[str, str], Any]


def _settings(session: dict[str, Any]) -> dict[str, Any]:
    return dict(dict(session.get("pack_settings") or {}).get(BOT_PACK_QUOTE_SPIKE) or {})


def spike_kind(session: dict[str, Any]) -> str:
    kind = str(_settings(session).get("spike_kind") or "buy_market")
    return kind if kind in BOT_ACTION_KINDS else "buy_market"


def cooldown_sec(session: dict[str, Any]) -> float:
    try:
        return max(1.0, float(_settings(session).get("cooldown_sec") or BOT_QUOTE_SPIKE_COOLDOWN_SEC))
    except (TypeError, ValueError):
        return float(BOT_QUOTE_SPIKE_COOLDOWN_SEC)


def min_pct(session: dict[str, Any]) -> float:
    try:
        return max(0.1, float(_settings(session).get("min_pct") or BOT_QUOTE_SPIKE_MIN_PCT))
    except (TypeError, ValueError):
        return float(BOT_QUOTE_SPIKE_MIN_PCT)


def window_sec(session: dict[str, Any]) -> float:
    try:
        return max(0.5, float(_settings(session).get("window_sec") or BOT_QUOTE_SPIKE_WINDOW_SEC))
    except (TypeError, ValueError):
        return float(BOT_QUOTE_SPIKE_WINDOW_SEC)


def _as_px(value: Any) -> float | None:
    if value is None:
        return None
    try:
        px = float(value)
    except (TypeError, ValueError):
        return None
    return px if px > 0 else None


def quote_px(row: dict[str, Any]) -> float | None:
    """Bid/ask mid when both sides exist; otherwise shared L1 last."""
    bid = _as_px(row.get("bid"))
    ask = _as_px(row.get("ask"))
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    return _as_px(row.get("last"))


def _sample_ts(row: dict[str, Any], now: float) -> float:
    ts = _as_px(row.get("last_update_ts"))
    return float(ts) if ts is not None else float(now)


def detect_spikes(
    previous: dict[str, Any],
    watch: dict[str, Any],
    *,
    now: float,
    window_sec: float,
    min_pct: float,
) -> tuple[list[str], dict[str, Any]]:
    """Rising-edge last/mid jump of min_pct inside window_sec."""
    nxt: dict[str, Any] = {}
    spikes: list[str] = []
    cutoff = float(now) - float(window_sec)
    for row in watch.get("symbols") or []:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        prev = dict(previous.get(symbol) or {})
        samples = [dict(item) for item in (prev.get("samples") or []) if isinstance(item, dict)]
        px = quote_px(row)
        if px is None:
            nxt[symbol] = {
                "samples": [s for s in samples if float(s.get("ts") or 0) >= cutoff],
                "spiked": False,
            }
            continue
        samples.append({"ts": _sample_ts(row, now), "quote": px})
        samples = [s for s in samples if float(s.get("ts") or 0) >= cutoff]
        baseline = float(samples[0]["quote"]) if samples else 0.0
        pct = ((px - baseline) / baseline) * 100.0 if baseline > 0 else 0.0
        spiked_now = baseline > 0 and pct >= float(min_pct)
        if spiked_now and not bool(prev.get("spiked")):
            spikes.append(symbol)
        nxt[symbol] = {"samples": samples, "spiked": spiked_now, "pct": round(pct, 2)}
    return spikes, nxt


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
    if (session.get("active_pack") or "") != BOT_PACK_QUOTE_SPIKE:
        return previous
    spikes, nxt = detect_spikes(
        previous,
        watch,
        now=now,
        window_sec=window_sec(session),
        min_pct=min_pct(session),
    )
    kind = spike_kind(session)
    cool = cooldown_sec(session)
    level = int(session.get("level") or 0)
    live = bool(session.get("live_fire_ready"))
    for symbol in spikes:
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
        pct = row.get("pct")
        reason = "quote spike"
        if pct is not None:
            reason = f"quote spike +{pct:g}% in {window_sec(session):g}s"
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
