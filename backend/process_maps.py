"""In-process map sizes for /api/metrics/ops (D-024 soak numbers)."""
from __future__ import annotations


def snapshot() -> dict[str, int]:
    from archive import bar_builder
    from fundamentals import cache_size as fundamentals_size
    from ibkr import discovery, tape_stream

    tape_stream.prune_idle_maps()
    return {
        "discovery_qualified_contracts": discovery.qualified_contract_count(),
        "tape_subscribe_locks": len(tape_stream._subscribe_locks),
        "tape_cancelled_at": len(tape_stream._cancelled_at),
        "fundamentals_cache": fundamentals_size(),
        "bar_builder_open": len(bar_builder._open),
    }
