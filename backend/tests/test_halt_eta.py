"""LULD / halt ETA clock states (issue #190 -- second-precise + late honesty)."""
from __future__ import annotations

from ibkr.halt_eta import (
    KIND_LULD,
    KIND_REGULATORY,
    KIND_UNKNOWN,
    LABEL_EXTENDED,
    LABEL_STILL,
    classify_halt_code,
    format_clock,
    halt_chip_view,
    kind_badge,
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


def test_kind_badge_luld_news_unk():
    assert kind_badge(KIND_LULD) == "LULD"
    assert kind_badge(KIND_REGULATORY) == "NEWS"
    assert kind_badge(KIND_UNKNOWN) == "UNK"


def test_format_clock_second_precise():
    assert format_clock(0) == "0:00"
    assert format_clock(102) == "1:42"
    assert format_clock(198) == "3:18"
    assert format_clock(3661) == "1:01:01"


def test_luld_0_to_5_minutes_second_precise():
    start = 1_000_000.0
    view = halt_chip_view(kind=KIND_LULD, halt_start=start, now=start)
    assert view is not None
    assert view["label"] == "LULD · 0:00 · 5:00 left"
    assert view["phase"] == "luld_pause"
    assert view["badge"] == "LULD"

    mid = halt_chip_view(kind=KIND_LULD, halt_start=start, now=start + 102)
    assert mid is not None
    assert mid["label"] == "LULD · 1:42 · 3:18 left"

    late = halt_chip_view(kind=KIND_LULD, halt_start=start, now=start + 270)
    assert late is not None
    assert late["label"] == "LULD · 4:30 · 0:30 left"


def test_luld_5_to_10_minutes_is_auction():
    start = 1_000_000.0
    at_five = halt_chip_view(kind=KIND_LULD, halt_start=start, now=start + 300)
    assert at_five is not None
    assert at_five["label"] == "Auction · 5:00 · 5:00 left"
    assert at_five["phase"] == "luld_auction"

    at_seven = halt_chip_view(kind=KIND_LULD, halt_start=start, now=start + 420)
    assert at_seven is not None
    assert at_seven["label"] == "Auction · 7:00 · 3:00 left"


def test_luld_over_10_minutes_drops_confident_countdown():
    start = 1_000_000.0
    at_ten = halt_chip_view(kind=KIND_LULD, halt_start=start, now=start + 600)
    assert at_ten is not None
    assert at_ten["label"] == LABEL_EXTENDED
    assert at_ten["phase"] == "luld_extended"
    assert "left" not in at_ten["label"]

    later = halt_chip_view(kind=KIND_LULD, halt_start=start, now=start + 1800)
    assert later is not None
    assert later["label"] == LABEL_EXTENDED
    assert luld_label(1800) == LABEL_STILL
    assert "~" not in later["label"]


def test_late_start_is_elapsed_only_no_eta():
    start = 1_000_000.0
    view = halt_chip_view(
        kind=KIND_LULD, halt_start=start, now=start + 102, start_late=True,
    )
    assert view is not None
    assert view["label"] == "LULD · 1:42"
    assert "left" not in view["label"]
    assert view["start_late"] is True


def test_late_start_with_official_rss_start_allows_countdown():
    official = 1_000_000.0
    observed = official + 90
    view = halt_chip_view(
        kind=KIND_LULD,
        halt_start=observed,
        now=official + 102,
        start_late=True,
        official_halt_start=official,
    )
    assert view is not None
    assert view["label"] == "LULD · 1:42 · 3:18 left"
    assert view["has_official_start"] is True
    assert view["halt_start_source"] == "nasdaq_trade_halt_rss"


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
    assert view["label"] == "NEWS · HALTED"
    assert view["badge"] == "NEWS"
    assert "no timed" in view["rule"]
    assert "left" not in view["label"]
    assert view["reason"].startswith("General halt")


def test_unknown_kind_is_unk_halted():
    view = halt_chip_view(kind=KIND_UNKNOWN, halt_start=10.0, now=100.0)
    assert view is not None
    assert view["label"] == "UNK · HALTED"
    assert view["badge"] == "UNK"


def test_halt_start_source_is_observed_not_sip_without_rss():
    view = halt_chip_view(kind=KIND_LULD, halt_start=1.0, now=2.0)
    assert view is not None
    assert view["halt_start_source"] == "observed_ticker_halted"
    assert "sip" not in view["halt_start_source"].lower()
