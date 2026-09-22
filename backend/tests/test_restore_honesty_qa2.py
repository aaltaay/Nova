"""Restored rows never carry an invented figure (QA pass two, 2026-09-22).

- C36: an after-hours row restored from a snapshot had its gap copied into
  its change ("-16.71%" over "+$0.44").
- C33 residue: 626 HOD alerts raised before the fix stored "CHG 0.0%" for a
  snapshot that had no change; restores and the history view read it as
  unknown.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cache  # noqa: E402
import hod_momo_persist  # noqa: E402
from constants_hod_momo import HOD_MOMO_INVENTED_CHANGE_BEFORE_TS  # noqa: E402
from hod_momo_models import alert_from_dict, restored_change_pct  # noqa: E402

BEFORE = HOD_MOMO_INVENTED_CHANGE_BEFORE_TS - 3600
AFTER = HOD_MOMO_INVENTED_CHANGE_BEFORE_TS + 3600


def test_an_after_hours_change_is_the_price_against_the_prior_close():
    row = {"symbol": "QNME", "price": 1.0001, "prev_close": 0.5583, "gap_percent": -0.1671, "change_pct": -0.1671}
    out = cache._normalize_gapper_row(row)
    assert out["change_abs"] == pytest.approx(0.4418)
    assert out["change_pct"] == pytest.approx(0.4418 / 0.5583)
    assert out["gap_percent"] == -0.1671  # the gap itself is untouched


def test_a_row_with_nothing_to_measure_keeps_its_own_change_never_a_zero():
    out = cache._normalize_gapper_row({"symbol": "NONE", "gap_percent": 0.12})
    assert out["change_pct"] is None
    assert out["change_abs"] is None
    legacy = cache._normalize_gapper_row({"symbol": "OLD", "current_price": 2.0, "previous_close": 1.6, "gap_percent": 0.25})
    assert legacy["price"] == 2.0 and legacy["prev_close"] == 1.6
    assert legacy["change_pct"] == pytest.approx(0.25)


@pytest.mark.parametrize(
    ("stored", "created", "expected"),
    [
        (0.0, BEFORE, None),     # the pre-fix fill-in
        (0, 0, None),            # a legacy alert with no raise time predates the fix
        (0.0, AFTER, 0.0),       # after the cutoff an exact 0.0 is read as stored
        (0.0412, BEFORE, 0.0412),
        (None, BEFORE, None),
    ],
)
def test_restored_change(stored, created, expected):
    assert restored_change_pct({"change_pct": stored, "created_ts": created}) == expected


def test_today_restore_reads_the_fill_in_as_unknown():
    alert = alert_from_dict({"id": "1-CHNR-1", "ticker": "CHNR", "price": 2.0, "change_pct": 0.0, "created_ts": BEFORE})
    assert alert.change_pct is None


def test_history_view_reads_the_fill_in_as_unknown(monkeypatch):
    archive = {"alerts": [
        {"id": "a", "ticker": "CHNR", "change_pct": 0.0, "created_ts": BEFORE},
        {"id": "b", "ticker": "GRML", "change_pct": 0.31, "created_ts": BEFORE},
    ]}
    monkeypatch.setattr(hod_momo_persist._cache, "load_hod_momo_snapshot_for_date", lambda _d: archive)
    rows = hod_momo_persist.get_history_alerts("2026-09-22")
    assert [r["change_pct"] for r in rows] == [None, 0.31]
    # The archive on disk is not rewritten by a read.
    assert archive["alerts"][0]["change_pct"] == 0.0
