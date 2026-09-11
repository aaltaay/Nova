"""D-024 -- in-process maps stay bounded and report sizes on /api/metrics/ops."""
from __future__ import annotations

import time

import fundamentals as fund
import process_maps
from constants import FUNDAMENTALS_CACHE_MAX_ENTRIES, IBKR_QUALIFIED_CONTRACTS_MAX
from ibkr import discovery
from ibkr import tape_stream as tape


def test_qualified_contracts_clear_and_lru():
    discovery._qualified_contracts.clear()
    discovery.remember_qualified_contract("AAA", object())
    assert discovery.qualified_contract_count() == 1
    n = discovery.clear_qualified_contracts(reason="test")
    assert n == 1
    assert discovery.qualified_contract_count() == 0

    for i in range(IBKR_QUALIFIED_CONTRACTS_MAX + 5):
        discovery.remember_qualified_contract(f"S{i}", object())
    assert discovery.qualified_contract_count() == IBKR_QUALIFIED_CONTRACTS_MAX
    assert "S0" not in discovery._qualified_contracts
    assert f"S{IBKR_QUALIFIED_CONTRACTS_MAX + 4}" in discovery._qualified_contracts
    discovery._qualified_contracts.clear()


def test_tape_idle_maps_prune_after_guard():
    tape.reset_for_tests()
    tape._cancelled_at["OLD"] = time.time() - tape.IBKR_TAPE_RESUBSCRIBE_GUARD_SEC - 1
    tape._subscribe_locks["OLD"] = __import__("asyncio").Lock()
    tape._cancelled_at["HOT"] = time.time()
    dropped = tape.prune_idle_maps()
    assert dropped["cancelled_at"] == 1
    assert "OLD" not in tape._cancelled_at
    assert "OLD" not in tape._subscribe_locks
    assert "HOT" in tape._cancelled_at
    tape.reset_for_tests()


def test_fundamentals_evicts_expired_and_caps(monkeypatch):
    fund._fundamentals_cache.clear()
    fund._fundamentals_cache_ts.clear()
    fund._fundamentals_cache_ttl.clear()
    now = time.monotonic()
    fund._store_cache("OLD", {"company_name": "gone"}, now - 10_000, 1.0)
    fund._store_cache("NEW", {"company_name": "keep"}, now, 900.0)
    fund.evict_stale(now)
    assert "OLD" not in fund._fundamentals_cache
    assert "NEW" in fund._fundamentals_cache

    for i in range(FUNDAMENTALS_CACHE_MAX_ENTRIES + 3):
        fund._store_cache(f"X{i}", {"company_name": str(i)}, now + i, 900.0)
    assert fund.cache_size() == FUNDAMENTALS_CACHE_MAX_ENTRIES
    assert "X0" not in fund._fundamentals_cache
    fund._fundamentals_cache.clear()
    fund._fundamentals_cache_ts.clear()
    fund._fundamentals_cache_ttl.clear()


def test_process_maps_snapshot_has_d024_keys():
    sizes = process_maps.snapshot()
    assert set(sizes) >= {
        "discovery_qualified_contracts",
        "tape_subscribe_locks",
        "tape_cancelled_at",
        "fundamentals_cache",
        "bar_builder_open",
    }
    assert all(isinstance(v, int) and v >= 0 for v in sizes.values())
