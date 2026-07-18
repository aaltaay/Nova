"""Tests for HOD Momo pure data models / serialization helpers."""
from __future__ import annotations

from datetime import datetime, timezone

from hod_momo_models import (
    AlertObject,
    MasterGateConfig,
    StrategyConfig,
    alert_from_dict,
    alert_to_dict,
    build_default_config,
    build_default_configs,
    config_from_dict,
    config_to_dict,
    format_alert_timestamp,
    format_trade_log_timestamp,
    master_from_dict,
    master_to_dict,
)


def test_build_default_configs_covers_all_strategy_ids():
    configs = build_default_configs()
    assert set(configs.keys()) == set(range(1, 13))
    for sid, cfg in configs.items():
        assert isinstance(cfg, StrategyConfig)
        assert cfg.strategy_id == sid


def test_former_momo_default_disabled():
    """Former Momo stays off until we own a Warrior-aligned list fill path."""
    cfg = build_default_config(1)
    assert cfg.enabled is False
    assert cfg.audio is False


def test_config_round_trip_preserves_fields():
    cfg = build_default_config(9)
    cfg.min_rvol = 3.5
    cfg.former_momo_list = ["AAPL", "TSLA"]
    d = config_to_dict(cfg)
    restored = config_from_dict(d)
    assert restored == cfg


def test_master_round_trip_preserves_fields():
    m = MasterGateConfig(min_rvol=4.0, surge_pct=7.5)
    restored = master_from_dict(master_to_dict(m))
    assert restored == m


def test_alert_round_trip_preserves_fields():
    alert = AlertObject(
        id="123-TEST-1",
        timestamp="2026-07-15T00:00:00.000Z",
        ticker="TEST",
        strategy_id=1,
        strategy_name="Former Momo",
        price=1.23,
        change_pct=10.0,
        rvol=5.0,
        float_shares=1_000_000.0,
        gap_pct=2.0,
        volume=500_000,
        momentum_pct=3.3,
    )
    restored = alert_from_dict(alert_to_dict(alert))
    assert restored == alert


def test_format_alert_timestamp_matches_legacy_utcfromtimestamp_output():
    ts = 1752600000.0
    expected = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    assert format_alert_timestamp(ts) == expected
    assert format_alert_timestamp(ts).endswith(".000Z")
    assert "+00:00" not in format_alert_timestamp(ts)


def test_format_trade_log_timestamp_is_23_chars_no_offset_suffix():
    stamp = format_trade_log_timestamp()
    assert len(stamp) == 23
    assert "+" not in stamp
