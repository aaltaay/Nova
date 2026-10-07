"""What on Paper counts toward the Live short proof (ADR 048 step 6). Pure: order rows and readings in, runs out.

- **A short day:** a filled short entry (``short_entry``), on its practice day (from 04:00 ET).
- **Flatten:** a fill the ticket's Flatten sent (origin ``ticket_flatten``) that covered a short.
- **The 15:55 cover:** a fill Nova's day cover sent (origin ``day_cover``) that covered a short.
- **Freeze all orders:** the kill switch tripped while Paper held a short, and the sweep kept that short's buy
  stop resting (ADR 048 gap 6). Every short Paper held must have kept one.
- **A Gateway drop:** IBKR's session dropped while Paper held a short, and when it was back each such short
  still had its buy stop working on Paper, or was flat.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
_EPS = 1e-9
_STOPS = frozenset({"STP", "STP LMT", "TRAIL", "TRAIL LIMIT"})


def practice_day(ts: float) -> str:
    """The practice day (from 04:00 ET) of ``ts``, as ``YYYY-MM-DD``."""
    from practice.clock import day_start_ts

    return datetime.fromtimestamp(day_start_ts(float(ts)), ET).date().isoformat()


def _filled(row: dict[str, Any]) -> bool:
    return str(row.get("status") or "") == "Filled" and row.get("fill_ts") is not None


def short_fills(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """``[{day, order_id, symbol, ts}]`` for each filled short entry, oldest first."""
    out = [{"day": practice_day(float(r["fill_ts"])), "order_id": int(r["order_id"]),
            "symbol": str(r.get("symbol") or "").upper(), "ts": float(r["fill_ts"])}
           for r in rows if _filled(r) and r.get("short_entry")]
    return sorted(out, key=lambda f: f["ts"])


def covers(rows: Iterable[dict[str, Any]], origin: str) -> list[dict[str, Any]]:
    """Fills sent with ``origin`` that covered a short: ``[{at, symbol, qty, order_id, key}]``, oldest first."""
    out = []
    for r in rows:
        if not _filled(r) or r.get("order_origin") != origin or str(r.get("side") or "").upper() != "BUY":
            continue
        if r.get("position_side") != "short" or r.get("effect") != "closes":
            continue
        out.append({"at": float(r["fill_ts"]), "symbol": str(r.get("symbol") or "").upper(),
                    "qty": float(r.get("filled_qty") or r.get("qty") or 0), "order_id": int(r["order_id"]),
                    "key": f"{origin}:{int(r['order_id'])}"})
    return sorted(out, key=lambda c: c["at"])


def shorts_held(held: dict[str, float]) -> dict[str, float]:
    """The shorts in ``{SYMBOL: signed qty}``, as positive share counts."""
    return {sym: -qty for sym, qty in held.items() if qty < -_EPS}


def _buy_stop(rows: Iterable[dict[str, Any]], symbol: str) -> dict[str, Any] | None:
    for row in rows:
        if str(row.get("symbol") or "").upper() != symbol or str(row.get("side") or "").upper() != "BUY":
            continue
        if str(row.get("order_type") or "").upper() in _STOPS:
            return row
    return None


def freeze(at: float, shorts: dict[str, float], kept: list[dict[str, Any]]) -> tuple[bool, dict[str, Any]] | None:
    """The freeze drill from Paper's shorts at the trip and the stops the sweep kept; None with no short open."""
    if not shorts:
        return None
    missing = [sym for sym in sorted(shorts) if _buy_stop(kept, sym) is None]
    symbol = sorted(shorts)[0]
    if missing:
        detail = (f"Freeze all orders ran with {', '.join(missing)} short on Paper, and no buy stop of "
                  f"{'that short' if len(missing) == 1 else 'those shorts'} was kept resting")
    else:
        detail = (f"Freeze all orders ran with {', '.join(sorted(shorts))} short on Paper and kept "
                  f"{'its buy stop' if len(shorts) == 1 else 'their buy stops'} resting")
    run = {"at": at, "symbol": symbol, "qty": shorts[symbol], "symbols": sorted(shorts), "detail": detail,
           "kept": [int(k["order_id"]) for k in kept if k.get("order_id") is not None], "key": f"freeze:{int(at)}"}
    return not missing, run


def gateway_back(since: float, back: float, shorts: dict[str, float], held: dict[str, float],
                 working: list[dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
    """The Gateway drop drill when IBKR's session is back: each short open at the drop is protected or flat."""
    unprotected = [sym for sym in sorted(shorts)
                   if held.get(sym, 0.0) < -_EPS and _buy_stop(working, sym) is None]
    symbol = sorted(shorts)[0]
    gone = round(back - since)
    if unprotected:
        detail = (f"IBKR's session dropped for {gone} s with {', '.join(sorted(shorts))} short on Paper; when it "
                  f"was back, {', '.join(unprotected)} had no buy stop working")
    else:
        detail = (f"IBKR's session dropped for {gone} s with {', '.join(sorted(shorts))} short on Paper; when it "
                  "was back each short still had its buy stop working, or was covered")
    run = {"at": since, "back_at": back, "symbol": symbol, "qty": shorts[symbol], "symbols": sorted(shorts),
           "detail": detail, "key": f"gateway_drop:{int(since)}"}
    return not unprotected, run
