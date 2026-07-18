"""discovery=ibkr avg_volume must be yfinance-only (single-market-data-feed rule)."""
from __future__ import annotations

import fundamentals
import hod_momo_enrichment as enrichment
from runtime_state import ScannerRuntimeState, set_runtime_state_for_testing


def test_ibkr_avg_volume_ignores_alpaca_iex_bars_cache():
    """Live bug: universe_enrichment_loop's discovery=ibkr branch read
    state.avg_volume_cache (Alpaca IEX-feed daily bars) before falling back to
    yfinance. IEX captures only a sliver of consolidated volume for thin
    microcaps, so that cache silently understated avg_volume and blew up pace
    RVOL 100x-3000x+ for exactly the low-float names this scanner targets
    (live-observed: ATPC avg_volume_cache=13,620 vs. live yfinance=3,375,816,
    a 248x gap that a background refresh alone could not fix because this
    30s-cadence loop kept re-applying the stale Alpaca figure). ibkr_avg_volume
    must never consult avg_volume_cache, even when it is populated.
    """
    state = ScannerRuntimeState()
    state.avg_volume_cache = {"ATPC": 13_620.44}
    previous = set_runtime_state_for_testing(state)
    try:
        fundamentals._fundamentals_cache["ATPC"] = {"average_volume": 3_375_816}
        assert enrichment.ibkr_avg_volume("ATPC") == 3_375_816.0
    finally:
        set_runtime_state_for_testing(previous)
        fundamentals._fundamentals_cache.pop("ATPC", None)


def test_ibkr_avg_volume_none_when_yfinance_unknown():
    fundamentals._fundamentals_cache.pop("ZZZZ", None)
    assert enrichment.ibkr_avg_volume("ZZZZ") is None


def test_ibkr_avg_volume_none_when_yfinance_zero():
    fundamentals._fundamentals_cache["ZZZZ"] = {"average_volume": 0}
    try:
        assert enrichment.ibkr_avg_volume("ZZZZ") is None
    finally:
        fundamentals._fundamentals_cache.pop("ZZZZ", None)
