"""Order flow per minute (``research/market_reads/order_flow.py``): one stock's rows of the day's trades_flow_v1 table,
summed to a bucket, with dark-pool, retail and sweep shares in percent points of volume."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from market_reads import order_flow  # noqa: E402

COLS = ("n", "vol", "dvol", "np_vol", "off_n", "off_vol", "rb_n", "rb_vol", "rs_n", "rs_vol", "mid_vol", "iso_n",
        "iso_vol", "odd_n", "odd_vol", "big_n", "big_vol", "blk_vol", "max_sz", "ext_vol")


def _row(ticker, m, vol, off, rb, rs, iso, odd, max_sz=500):
    row = dict.fromkeys(COLS, 0)
    row.update(ticker=ticker, m=m, n=10, vol=vol, dvol=vol * 5.0, off_vol=off, rb_vol=rb, rs_vol=rs, iso_vol=iso,
               odd_vol=odd, max_sz=max_sz)
    return row


@pytest.fixture
def flow(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    rows = [_row("AAA", 570, 1000, 400, 100, 50, 200, 30), _row("AAA", 571, 3000, 600, 0, 300, 900, 60, 2000),
            _row("AAA", 575, 2000, 1000, 500, 0, 0, 10), _row("BBB", 570, 9999, 0, 0, 0, 0, 0)]
    path = order_flow.flow_file("2025-03-03")
    path.parent.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def test_one_stocks_minutes_with_shares_of_volume(flow):
    frame = order_flow.order_flow("aaa", "2025-03-03")
    assert list(frame["time_et"]) == ["09:30", "09:31", "09:35"]
    first = frame.iloc[0]
    assert first["off_pct"] == 40.0 and first["sweep_pct"] == 20.0 and first["odd_pct"] == 3.0
    assert first["retail_imbalance"] == pytest.approx(50 / 150, abs=1e-3)
    assert frame.iloc[1]["retail_imbalance"] == -1.0


def test_buckets_sum_and_the_window_is_et_minutes(flow):
    five = order_flow.order_flow("AAA", "2025-03-03", bucket="5m")
    assert list(five["time_et"]) == ["09:30", "09:35"] and list(five["vol"]) == [4000, 2000]
    assert five.iloc[0]["max_sz"] == 2000
    window = order_flow.order_flow("AAA", "2025-03-03", start="09:31", end="09:35")
    assert list(window["time_et"]) == ["09:31"]
    assert window.attrs["day_total"]["vol"] == 3000.0


def test_a_missing_day_or_bucket_is_refused(flow):
    with pytest.raises(LookupError, match="no trades_flow_v1 file"):
        order_flow.order_flow("AAA", "2025-03-04")
    with pytest.raises(ValueError, match="bucket"):
        order_flow.order_flow("AAA", "2025-03-03", bucket="2m")
    assert order_flow.order_flow("ZZZ", "2025-03-03").empty
