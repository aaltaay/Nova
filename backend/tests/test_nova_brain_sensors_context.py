"""Compact Sensor Board context -- no live OpenRouter."""
from __future__ import annotations

from nova_brain.sensors_context import bound_value, build_user_payload, compact_snapshot


def test_compact_snapshot_keeps_eighteen_and_trims_tape():
    prints = [{"price": i, "size": 1} for i in range(20)]
    raw = {
        "symbol": "ABCD",
        "count": 18,
        "sensors": [
            {
                "sensor": "tape",
                "status": "live",
                "as_of": 1.0,
                "error": None,
                "data": {"prints": prints, "note": "x" * 400},
            }
        ],
    }
    got = compact_snapshot(raw)
    assert got["symbol"] == "ABCD"
    assert got["count"] == 1
    tape = got["sensors"][0]["data"]["prints"]
    assert len(tape) == 3
    assert tape[-1]["price"] == 19
    assert len(got["sensors"][0]["data"]["note"]) == 160


def test_build_user_payload_includes_session_and_sensors():
    session = {
        "level": 1,
        "armed": False,
        "live_fire_ready": False,
        "caps": {"allowlist": ["buy_market"], "max_shares": 1},
    }
    watch = {
        "eligible": ["ABCD"],
        "symbols": [{"symbol": "ABCD", "last": 1.25, "halted": False, "position_qty": 0}],
    }
    payload = build_user_payload(
        session,
        watch,
        {"ABCD": {"symbol": "ABCD", "sensors": [{"sensor": "l2", "status": "live", "data": {}}]}},
    )
    assert payload["qty_preset"] == "default"
    assert payload["eligible"] == ["ABCD"]
    assert payload["sensors"]["ABCD"]["sensors"][0]["sensor"] == "l2"


def test_bound_value_caps_depth():
    nested = {"a": {"b": {"c": {"d": {"e": 1}}}}}
    got = bound_value(nested)
    assert got["a"]["b"]["c"]["d"] is None
