"""Tick-49 observe: first start sticks, late honesty, clear on resume."""
from __future__ import annotations

from ibkr import halt_status
from ibkr import nasdaq_halt_feed
from ibkr.halt_eta import KIND_LULD, KIND_REGULATORY, KIND_UNKNOWN


class _Ticker:
    def __init__(self, halted=None):
        self.halted = halted


def setup_function(_fn):
    halt_status.reset()
    nasdaq_halt_feed.reset()


def test_first_luld_tick_without_prior_clear_is_late():
    snap, changed = halt_status.observe_code("reto", 2, now=1_000.0)
    assert changed is True
    assert snap is not None
    assert snap["halted"] is True
    assert snap["kind"] == KIND_LULD
    assert snap["halt_start"] == 1_000.0
    assert snap["start_late"] is True
    assert snap["halt_start_source"] == "observed_ticker_halted"
    assert snap["source"] == "ibkr_ticker_halted"
    assert snap["exchange"]["status"] == "pending"
    assert snap["exchange"]["matched"] is False
    assert snap["exchange"]["trade_resume"] is None
    assert "sip" not in snap["halt_start_source"].lower()


def test_watched_clear_then_halt_is_on_time():
    halt_status.observe_code("RETO", 0, now=900.0)
    snap, changed = halt_status.observe_code("RETO", 2, now=1_000.0)
    assert changed is True
    assert snap is not None
    assert snap["start_late"] is False
    assert snap["halt_start"] == 1_000.0


def test_same_halt_keeps_original_start():
    halt_status.observe_code("RETO", 0, now=900.0)
    halt_status.observe_code("RETO", 2.0, now=1_000.0)
    snap, changed = halt_status.observe_code("reto", 2, now=1_200.0)
    assert changed is False
    assert snap is not None
    assert snap["halt_start"] == 1_000.0


def test_code_zero_clears_immediately():
    halt_status.observe_code("RETO", 2, now=1_000.0)
    snap, changed = halt_status.observe_code("RETO", 0, now=1_010.0)
    assert changed is True
    assert snap is None
    assert halt_status.snapshot("RETO") is None


def test_nan_and_unavailable_are_not_halts():
    snap, changed = halt_status.observe_from_ticker("RETO", _Ticker(float("nan")))
    assert snap is None and changed is False
    snap, changed = halt_status.observe_code("RETO", -1)
    assert snap is None and changed is False
    snap, changed = halt_status.observe_from_ticker("RETO", _Ticker())
    assert snap is None and changed is False


def test_regulatory_and_unknown_codes():
    snap, _ = halt_status.observe_code("NEWS", 1, now=50.0)
    assert snap is not None
    assert snap["kind"] == KIND_REGULATORY
    halt_status.reset()
    snap, _ = halt_status.observe_code("ODD", 7, now=50.0)
    assert snap is not None
    assert snap["kind"] == KIND_UNKNOWN


def test_rss_match_overlays_official_fields():
    from pathlib import Path

    xml = Path(__file__).with_name("fixtures").joinpath("nasdaq_trade_halts.xml")
    nasdaq_halt_feed.refresh(now=10.0, xml_text=xml.read_text(encoding="utf-8"))
    # NEWS1 is still open (no trade_resume) -- official start may restore countdown.
    halt_status.observe_code("NEWS1", 1, now=1_800_000_000.0)
    snap = halt_status.snapshot("NEWS1", now=1_800_000_000.0)
    assert snap is not None
    ex = snap["exchange"]
    assert ex["status"] == "ok"
    assert ex["matched"] is True
    assert ex["reason_code"] == "T1"
    assert ex["official_halt_start"] is not None
    assert ex["trade_resume"] is None
    assert snap["start_late"] is True


def test_late_start_stale_resumed_rss_does_not_restore_countdown():
    from pathlib import Path

    from ibkr.halt_eta import halt_chip_view

    xml = Path(__file__).with_name("fixtures").joinpath("nasdaq_trade_halts.xml")
    nasdaq_halt_feed.refresh(now=10.0, xml_text=xml.read_text(encoding="utf-8"))
    # ZTG is a completed LUDP. Reconnect mid-halt must not treat that old
    # official_halt_start as this halt's clock.
    snap, _ = halt_status.observe_code("ZTG", 2, now=1_800_000_000.0)
    assert snap is not None
    assert snap["start_late"] is True
    ex = snap["exchange"]
    assert ex["matched"] is True
    assert ex["official_halt_start"] is None
    assert ex["quote_resume"] is None
    assert ex["trade_resume"] is None
    view = halt_chip_view(
        kind=KIND_LULD,
        halt_start=snap["halt_start"],
        now=1_800_000_000.0,
        start_late=True,
        official_halt_start=ex["official_halt_start"],
    )
    assert view is not None
    assert "left" not in view["label"]
    assert view["has_official_start"] is False


def test_dlxy_open_row_reaches_chip_not_stale_resume():
    from datetime import datetime
    from pathlib import Path
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    xml = Path(__file__).with_name("fixtures").joinpath(
        "nasdaq_trade_halts_dlxy_dup.xml",
    )
    nasdaq_halt_feed.refresh(now=10.0, xml_text=xml.read_text(encoding="utf-8"))
    now = datetime(2026, 9, 16, 14, 30, 0, tzinfo=et).timestamp()
    snap, _ = halt_status.observe_code("DLXY", 2, now=now)
    assert snap is not None
    ex = snap["exchange"]
    assert ex["matched"] is True
    assert ex["trade_resume"] is None
    assert ex["official_halt_start"] == datetime(
        2026, 9, 16, 14, 28, 0, tzinfo=et,
    ).timestamp()


def test_on_time_halt_keeps_future_rss_resume_schedule():
    from datetime import datetime
    from pathlib import Path
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    xml = Path(__file__).with_name("fixtures").joinpath("nasdaq_trade_halts.xml")
    nasdaq_halt_feed.refresh(now=10.0, xml_text=xml.read_text(encoding="utf-8"))
    official = datetime(2026, 9, 16, 10, 30, 0, tzinfo=et).timestamp()
    halt_status.observe_code("ZTG", 0, now=official - 30)
    snap, _ = halt_status.observe_code("ZTG", 2, now=official)
    assert snap is not None
    assert snap["start_late"] is False
    assert snap["exchange"]["trade_resume"] == datetime(
        2026, 9, 16, 10, 40, 0, tzinfo=et,
    ).timestamp()


def test_rss_miss_stays_pending_and_invents_nothing():
    from pathlib import Path

    xml = Path(__file__).with_name("fixtures").joinpath("nasdaq_trade_halts.xml")
    nasdaq_halt_feed.refresh(now=10.0, xml_text=xml.read_text(encoding="utf-8"))
    snap, _ = halt_status.observe_code("AAPL", 2, now=50.0)
    assert snap is not None
    assert snap["exchange"]["status"] == "pending"
    assert snap["exchange"]["matched"] is False
    assert snap["exchange"]["trade_resume"] is None
    assert snap["exchange"]["quote_resume"] is None
