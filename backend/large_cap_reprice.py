"""L1-tick repricing for the Large Cap swing table (ADR 014).

Mirrors ``ibkr/discovery.reprice_mover_row`` for the base price / prev_close
/ change_pct fields, then layers on swing metrics (RVOL / ATR expansion /
5d-20d change / 20d high-low) and checks the 20-day breakout alert trigger.
Pure function over the row list -- the caller (``ibkr_bridge.apply_l1_quote``)
owns ``state.large_cap_cache`` and decides whether to write the result back.
"""
from __future__ import annotations

from ibkr.discovery import reprice_mover_row

PATCH_FIELDS = (
    "change_pct", "change_abs", "volume", "rvol", "atr_expansion",
    "change_5d_pct", "change_20d_pct", "high_20d", "low_20d", "days_to_earnings",
    "market_cap", "float",
)


def apply_l1_tick(
    rows: list[dict], sym: str, quote: dict, now: float,
) -> tuple[list[dict], dict | None]:
    """Reprice *sym* within *rows*. Returns ``(new_rows, patch_fields | None)``."""
    import large_cap_alerts as _alerts
    import large_cap_metrics as _metrics

    patch: dict | None = None
    new_rows: list[dict] = []
    for row in rows:
        if (row.get("symbol") or "").upper() != sym:
            new_rows.append(row)
            continue
        repriced = reprice_mover_row(row, quote)
        metrics = _metrics.build_row_metrics(
            sym,
            price=repriced.get("price"),
            prev_close=repriced.get("prev_close"),
            volume=repriced.get("volume"),
        )
        repriced = {**repriced, **metrics, "quote_ts": now}
        _alerts.check_breakout(
            sym,
            price=repriced.get("price"),
            high_20d=repriced.get("high_20d"),
            low_20d=repriced.get("low_20d"),
            rvol=repriced.get("rvol"),
        )
        patch = {field: repriced.get(field) for field in PATCH_FIELDS}
        new_rows.append(repriced)
    return new_rows, patch
