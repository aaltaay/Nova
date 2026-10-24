"""Seconds bars built from trades (research/market_reads/reads.py ``bars``): which prints count in the volume.

CINC 2022-08-08 09:30:02 printed its opening cross twice: once as the opening trade (conditions 17,9,41) and again
as the official-open record (condition 16), 29,248 shares each. The 10-second bar counted both, so it showed about
29k shares that never traded. Official open / close (16 / 15) and corrected-close (38) records repeat a print and
carry no volume; every other trade still counts, and only price-setting prints set the open / high / low / close.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))

from market_reads import reads  # noqa: E402

T0 = 1659965402_000_000_000      # 2022-08-08 09:30:02 ET in SIP nanoseconds


def _prints() -> pd.DataFrame:
    rows = [
        (T0, 31.04, 29248, "17,9,41", 0),   # the opening cross: counts, sets the price
        (T0 + 11_000, 31.04, 29248, "16", 0),   # the official-open record repeating it: no volume
        (T0 + 700_000, 31.00, 200, "14,41", 0),
        (T0 + 900_000, 30.58, 100, None, 0),
        (T0 + 1_000_000, 31.04, 37, "37", 0),   # an odd lot: volume yes, price no
        (T0 + 2_000_000, 99.00, 500, None, 10),  # a cancel record: no trade at all
    ]
    frame = pd.DataFrame(rows, columns=["sip_timestamp", "price", "size", "conditions", "correction"])
    frame["sets_price"] = reads.sets_price(frame["conditions"], frame["correction"])
    return frame


def test_an_official_open_record_does_not_double_the_opening_cross(monkeypatch):
    monkeypatch.setattr(reads, "trades", lambda *a, **k: _prints())
    bars = reads.bars("CINC", "2022-08-08", "10s")
    assert len(bars) == 1
    bar = bars.iloc[0]
    assert int(bar.volume) == 29248 + 200 + 100 + 37
    assert int(bar.transactions) == 4
    assert (bar.open, bar.high, bar.low, bar.close) == (31.04, 31.04, 30.58, 30.58)


def test_repeat_records_are_matched_as_whole_codes():
    conditions = pd.Series(["16", "15", "38", "17,9,41", "116", "1,6", None, "12,16"])
    assert reads.repeats_a_print(conditions).tolist() == [True, True, True, False, False, False, False, True]
