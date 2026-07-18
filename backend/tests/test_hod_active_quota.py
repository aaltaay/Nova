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
        former_slots=0,
        mover_slots=0,
        seed_slots=2,
        explore_slots=0,
    )
    assert snap.active[0] == "ZZZ"
    assert "AAA" not in snap.active or snap.active.index("ZZZ") < snap.active.index("AAA")


def test_session_focus_priority_beats_crowded_gainers():
    """Former/session-alert names keep L1 even when 40 gainers fill the table."""
    active.clear_session_state()
    gainers = [{"symbol": f"G{i:02d}", "change_pct": 50 - i} for i in range(40)]
    snap = active.build_active_set(
        discovery=[g["symbol"] for g in gainers] + ["LBGJ", "BIYA"],
        gainer_rows=gainers,
        priority_symbols=["LBGJ", "BIYA"],
        capacity=40,
        former_slots=6,
        mover_slots=14,
        seed_slots=12,
        explore_slots=8,
    )
    assert "LBGJ" in snap.active
    assert "BIYA" in snap.active
    assert snap.reasons.get("LBGJ") == "session_focus"


def test_mid_tier_under20_gainer_gets_seed_slot_not_buried_by_volume():
    """PN-class: on gainer table, low volume — must win seed head over VOL*."""
    import hod_momo_universe as uni

    active.clear_session_state()
    # Top movers fill with mega-gainers; PN is mid-tier under $20.
    gainers = [{"symbol": f"G{i:02d}", "price": 5.0, "change_pct": 0.80 - i * 0.01} for i in range(12)]
    gainers.append({"symbol": "PN", "price": 4.4, "change_pct": 0.14})
    volume_seeds = [f"VOL{i:02d}" for i in range(40)]
    # Without promotion, volume head owns seed_slots; explore starts at VOL*
    # (discovery volume-first) so mid-tier PN never reaches sticky L1.
    buried = active.build_active_set(
        discovery=volume_seeds + [g["symbol"] for g in gainers],
        gainer_rows=gainers,
        seed_symbols=volume_seeds,
        capacity=40,
        former_slots=2,
        mover_slots=12,
        seed_slots=12,
        explore_slots=8,
    )
    assert "PN" not in buried.active

    seeds = uni.seed_symbols_for_active(volume_seeds, gainers, below_price=20.0)
    discovery = uni.discovery_for_active(
        [g["symbol"] for g in gainers] + volume_seeds,
        gainers,
    )
    snap = active.build_active_set(
        discovery=discovery,
        gainer_rows=gainers,
        loser_rows=None,
        seed_symbols=seeds,
        capacity=40,
        former_slots=2,
        mover_slots=12,
        seed_slots=12,
        explore_slots=8,
    )
    assert "PN" in snap.active
    assert snap.reasons.get("PN") in {"volume_seed", "top_gainer", "discovery"}
