"""LULD / halt ETA clock states (issue #173)."""
from __future__ import annotations

from ibkr.halt_eta import (
    KIND_LULD,
    KIND_REGULATORY,
    KIND_UNKNOWN,
    LABEL_STILL,
    classify_halt_code,
    halt_chip_view,
    luld_label,
    parse_halt_code,
)


def test_parse_halt_code_nan_and_strings():
    assert parse_halt_code(None) is None
    assert parse_halt_code(float("nan")) is None
    assert parse_halt_code("nope") is None
    assert parse_halt_code(2.0) == 2
    assert parse_halt_code(-1) == -1


def test_classify_tick_49_codes():
    assert classify_halt_code(None) is None
    assert classify_halt_code(0) is None
    assert classify_halt_code(-1) is None
    assert classify_halt_code(2) == KIND_LULD
    assert classify_halt_code(1) == KIND_REGULATORY
    assert classify_halt_code(3) == KIND_UNKNOWN


def test_luld_0_to_5_minutes():
    start = 1_000_000.0
    view = halt_chip_view(kind=KIND_LULD, halt_start=start, now=start)
    assert view is not None
    assert view["label"] == "LULD · ~5m left"
    assert view["phase"] == "luld_pause"
    assert "countdown" in view["rule"] or "5m" in view["rule"]

    mid = halt_chip_view(kind=KIND_LULD, halt_start=start, now=start + 90)
    assert mid is not None
    assert mid["label"] == "LULD · ~4m left"

    late = halt_chip_view(kind=KIND_LULD, halt_start=start, now=start + 270)
    assert late is not None
    assert late["label"] == "LULD · ~1m left"


def test_luld_5_to_10_minutes_extended():
    start = 1_000_000.0
    at_five = halt_chip_view(kind=KIND_LULD, halt_start=start, now=start + 300)
    assert at_five is not None
    assert at_five["label"] == "Extended · ~5m"
    assert at_five["phase"] == "luld_extended"

    at_seven = halt_chip_view(kind=KIND_LULD, halt_start=start, now=start + 420)
    assert at_seven is not None
    assert at_seven["label"] == "Extended · ~3m"


def test_luld_over_10_minutes_drops_confident_countdown():
    start = 1_000_000.0
    at_ten = halt_chip_view(kind=KIND_LULD, halt_start=start, now=start + 600)
    assert at_ten is not None
    assert at_ten["label"] == LABEL_STILL
    assert at_ten["phase"] == "luld_still"
    assert "~" not in at_ten["label"] or "left" not in at_ten["label"]

    later = halt_chip_view(kind=KIND_LULD, halt_start=start, now=start + 1800)
    assert later is not None
    assert later["label"] == LABEL_STILL
    # Must not keep minting ~Xm forever.
    assert luld_label(1800) == LABEL_STILL


def test_cleared_or_not_halted_hides_chip():
    assert halt_chip_view(kind=None, halt_start=1.0, now=2.0, halted=False) is None
    assert halt_chip_view(kind=KIND_LULD, halt_start=1.0, now=2.0, halted=False) is None
    assert halt_chip_view(kind=None, halt_start=1.0, now=2.0, halted=True) is None


def test_regulatory_has_reason_and_no_timer():
    start = 1_000_000.0
    view = halt_chip_view(
        kind=KIND_REGULATORY, halt_start=start, now=start + 400,
    )
    assert view is not None
    assert view["label"] == "HALTED · news/regulatory"
    assert "no timed" in view["rule"]
    assert "~" not in view["label"]
    assert view["reason"].startswith("General halt")


def test_unknown_kind_is_halted_eta_unknown():
    view = halt_chip_view(kind=KIND_UNKNOWN, halt_start=10.0, now=100.0)
    assert view is not None
    assert view["label"] == "HALTED · ETA unknown"
    assert "~" not in view["label"] or "ETA" in view["label"]


def test_halt_start_source_is_observed_not_sip():
    view = halt_chip_view(kind=KIND_LULD, halt_start=1.0, now=2.0)
    assert view is not None
    assert view["halt_start_source"] == "observed_ticker_halted"
    assert "sip" not in view["halt_start_source"].lower()
