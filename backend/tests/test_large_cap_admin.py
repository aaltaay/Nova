"""Large Cap tunable config (ADR 014 Step 8) -- schema_version + refuse-loud."""
from __future__ import annotations

import pytest

import large_cap_admin as admin


def test_default_config_matches_constants():
    cfg = admin.get_config()
    assert cfg["market_cap_above"] == 50_000
    assert cfg["above_volume"] == 1_000_000
    assert cfg["scan_code"] == "TOP_VOLUME_RATE"
    assert cfg["stock_type_filter"] == "CORP"


def test_update_config_persists_and_round_trips():
    updated = admin.update_config({"market_cap_above": 10_000, "above_volume": 500_000})
    assert updated["market_cap_above"] == 10_000
    assert updated["above_volume"] == 500_000
    filters = admin.get_large_cap_filters()
    assert filters["market_cap_above"] == 10_000
    assert filters["above_volume"] == 500_000


def test_update_config_rejects_non_positive_market_cap():
    with pytest.raises(ValueError):
        admin.update_config({"market_cap_above": 0})


def test_update_config_rejects_negative_volume():
    with pytest.raises(ValueError):
        admin.update_config({"above_volume": -1})


def test_update_config_rejects_empty_scan_code():
    with pytest.raises(ValueError):
        admin.update_config({"scan_code": ""})


def test_score_weights_default_and_update():
    weights = admin.get_score_weights()
    assert set(weights) == {"rvol", "atr_expansion", "change_20d_pct"}
    admin.update_config({"score_weights": {"rvol": 1.0, "atr_expansion": 0.0, "change_20d_pct": 0.0}})
    assert admin.get_score_weights()["rvol"] == 1.0


def test_unknown_schema_version_is_refused_loud(monkeypatch, caplog):
    import cache as cache_mod

    monkeypatch.setattr(
        cache_mod, "load_large_cap_config",
        lambda: {"schema_version": 999, "market_cap_above": 1},
    )
    admin.reset_for_testing()
    admin._loaded = False
    cfg = admin.get_config()
    # Refused -- defaults kept, not the poisoned value.
    assert cfg["market_cap_above"] == 50_000
