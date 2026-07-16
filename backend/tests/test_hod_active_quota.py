"""HOD active-set quota: volume seeds must not be starved by movers."""
from __future__ import annotations

import hod_momo_active as active


def test_volume_seed_off_table_enters_reserved_pool():
    """A HOT_BY_VOLUME seed absent from gainers still gets an active L1 slot."""
    active.clear_session_state()
    gainers = [{"symbol": f"G{i:02d}", "change_pct": 50 - i} for i in range(40)]
    # Ranked volume seeds — first ones should win seed quota even vs 40 gainers.
    seeds = ["VOL1", "VOL2", "VOL3"] + [f"S{i:02d}" for i in range(20)]
    snap = active.build_active_set(
        discovery=seeds + [g["symbol"] for g in gainers],
        gainer_rows=gainers,
        seed_symbols=seeds,
        capacity=40,
        mover_slots=18,
        seed_slots=14,
        explore_slots=8,
    )
    assert "VOL1" in snap.active
    assert "VOL2" in snap.active
    assert snap.reasons.get("VOL1") == "volume_seed"
    # Not every gainer can fill all 40 slots anymore.
    gainer_count = sum(1 for s in snap.active if s.startswith("G"))
    assert gainer_count <= 25
    assert len(snap.active) == 40


def test_open_ticker_always_included():
    active.clear_session_state()
    snap = active.build_active_set(
        discovery=["AAA", "BBB"],
        gainer_rows=[{"symbol": "AAA", "change_pct": 10}],
        seed_symbols=["SEED1"],
        detail_symbols=["OPEN"],
        capacity=5,
    )
    assert snap.active[0] == "OPEN" or "OPEN" in snap.active
    assert snap.reasons["OPEN"] == "open_ticker"


def test_seed_rank_order_preserved_over_alpha_sort():
    active.clear_session_state()
    # ZZZ is first in ranked volume scan; AAA would win alphabetical sort.
    seeds = ["ZZZ", "MMM", "AAA"]
    snap = active.build_active_set(
        discovery=seeds,
        seed_symbols=seeds,
        capacity=2,
        mover_slots=0,
        seed_slots=2,
        explore_slots=0,
    )
    assert snap.active[0] == "ZZZ"
    assert "AAA" not in snap.active or snap.active.index("ZZZ") < snap.active.index("AAA")
