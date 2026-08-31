"""Per-row admission clock (2026-08-31 XAIR starvation follow-up).

``roster_ts`` is rewritten on every IB scanner push, so a busy table's
coverage age never leaves the admission grace window and integrity can never
judge it. ``admitted_ts`` is stamped once per row and must survive both a
rank-only refresh and a repriced merge.
"""
from __future__ import annotations

import asyncio
import time

import ibkr.scanner_hydrate as hydrate


def test_stub_row_stamps_admitted_ts():
    before = time.time()
    row = hydrate.stub_row("XAIR", 3, exchange="NASDAQ")
    after = time.time()
    assert before <= row["admitted_ts"] <= after
    assert row["price"] is None


def test_hydrate_rows_preserves_admitted_ts_across_rank_change():
    existing = [hydrate.stub_row("XAIR", 10)]
    original_ts = existing[0]["admitted_ts"]
    rows = asyncio.run(
        hydrate.hydrate_rows(
            ["XAIR"],
            table="gainers",
            session_key="2026-08-31",
            existing=existing,
        )
    )
    # Rank moved from 10 to 1 -- a real re-rank, not a fresh admission.
    rows2 = asyncio.run(
        hydrate.hydrate_rows(
            ["XAIR"],
            table="gainers",
            session_key="2026-08-31",
            existing=rows,
        )
    )
    assert rows2[0]["admitted_ts"] == original_ts


def test_hydrate_rows_new_symbol_gets_fresh_admitted_ts():
    rows = asyncio.run(
        hydrate.hydrate_rows(
            ["NEW1"],
            table="gainers",
            session_key="2026-08-31",
            existing=[],
        )
    )
    assert rows[0]["admitted_ts"] is not None
