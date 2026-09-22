"""One surface for scanner rows on the wire -- REST and /ws/scanner alike.

QA C49: the REST routes stripped blocklisted symbols, attached the listing
exchange, decorated the reference columns and computed the Large Cap
composite score; ``/ws/scanner`` roster replaces and connect snapshots only
decorated. A blocklisted ticker came back on the next roster push and the
Large Cap Score turned into a dash. Both paths now call ``surface_rows``.

QA C39: a row's ``rel_volume`` names the average it divides by. Runners that
compute it from an Alpaca daily-bar average stamp ``rvol_source`` themselves;
the read-time decoration (``mover_enrich_view``) fills a missing
``rel_volume`` from the yfinance average only, so a value it filled is
stamped ``yfinance`` here.
"""
from __future__ import annotations

import logging
from typing import Any

import exchanges as _exchanges
import hod_momo as _hod_momo
import mover_enrich_view as _mover_enrich
from constants_scanner import SCANNER_RVOL_SOURCE_YFINANCE

logger = logging.getLogger(__name__)

TABLE_LARGE_CAP = "large_cap"


def surface_rows(rows: list[dict] | None, table: str | None = None) -> list[dict]:
    """Rows as every client sees them: blocklist out, exchange + reference columns in.

    ``table == "large_cap"`` also computes the composite score (ADR 014).
    Never mutates the reference columns of the cached rows (ADR 008).
    """
    kept = [r for r in (rows or []) if not _hod_momo.is_blocked(r.get("symbol", ""))]
    had_rvol = [r.get("rel_volume") is not None for r in kept]
    decorated: list[dict[str, Any]] = _mover_enrich.decorate_rows(_exchanges.attach_exchanges(kept))
    if len(decorated) == len(had_rvol):
        for row, had in zip(decorated, had_rvol, strict=True):
            if not had and row.get("rel_volume") is not None and not row.get("rvol_source"):
                row["rvol_source"] = SCANNER_RVOL_SOURCE_YFINANCE
    else:
        logger.warning(
            "scanner_surface: decorate_rows returned %d rows for %d; rvol_source left unstamped",
            len(decorated), len(had_rvol),
        )
    if table == TABLE_LARGE_CAP:
        import large_cap_admin as _lc_admin
        import large_cap_metrics as _lc_metrics

        decorated = _lc_metrics.compute_scores(decorated, weights=_lc_admin.get_score_weights())
    return decorated
