"""The front door's splits (``research/market_reads/splits.py``, 2026-10-12): raw Massive prices put in another day's
terms. GRML traded at $0.19 on 2026-07-15 and the desk's IBKR daily chart showed ~$9.25 for the same day, after its
1-for-50 reverse split on 2026-08-24."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

# The split list is the board rebuild's (research/leaderboard/lb_io), which needs the research harness's packages;
# CI's backend job does not install them (test_leaderboard_reconstruct_helpers.py skips the same way).
pytest.importorskip("duckdb")
pd = pytest.importorskip("pandas")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from market_reads import splits  # noqa: E402

lb_io = splits.lb_io


@pytest.fixture
def listed(monkeypatch, tmp_path):
    """GRML's 1-for-50 from Massive's list, and a 2-for-1 that only an SEC filing proved. REUS was CIK 1's ticker
    until 2018-05-01 (a 1-for-10 in 2017) and is CIK 2's now (a 1-for-20 in 2024)."""
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    ref = tmp_path / "store" / "reference"
    ref.mkdir(parents=True)
    (ref / "tickers.json").write_text(json.dumps([
        {"ticker": "REUS", "cik": "2", "name": "Now Co", "active": True},
        {"ticker": "REUS", "cik": "1", "name": "Then Co", "active": False, "delisted_utc": "2018-05-01T04:00:00Z"},
        {"ticker": "GRML", "cik": "9", "name": "Grml", "active": True}]), encoding="utf-8")
    splits.tickers.clear()
    monkeypatch.setattr(splits.tickers, "_list_date", lambda symbol, cik: None)
    massive = [lb_io.Split("GRML", date(2026, 8, 24), 50.0, 1.0), lb_io.Split("XYZ", date(2026, 3, 2), 1.0, 2.0),
               lb_io.Split("REUS", date(2017, 6, 1), 10.0, 1.0), lb_io.Split("REUS", date(2024, 6, 3), 20.0, 1.0)]
    proved = [lb_io.Split("GRML", date(2026, 9, 30), 1.0, 2.0),
              lb_io.Split("GRML", date(2026, 8, 24), 50.0, 1.0)]       # Massive lists it too: Massive's row wins
    monkeypatch.setattr(lb_io, "open_research_db", lambda _path: (None, "reference/splits.json"))
    monkeypatch.setattr(lb_io, "load_splits", lambda _research, _ref, confirmed=None: list(massive))
    monkeypatch.setattr(lb_io, "load_confirmed_splits", lambda _path: list(proved))
    splits._all.cache_clear()
    yield
    splits._all.cache_clear()


def test_the_list_joins_massive_and_sec_and_labels_each(listed):
    grml = splits.table("grml")
    assert list(grml["execution_date"]) == [date(2026, 8, 24), date(2026, 9, 30)]
    assert list(grml["source"]) == ["massive", "sec_confirmed"]
    assert list(grml["price_factor"]) == [50.0, 0.5]


def test_a_day_before_the_split_multiplies_by_it(listed):
    assert splits.factor("GRML", "2026-07-15", "2026-08-24") == 50.0       # the split day itself is in its terms
    assert splits.factor("GRML", "2026-07-15") == 25.0                      # every split known: 50 then 2-for-1
    assert splits.factor("GRML", "2026-07-15", "2026-08-21") == 1.0         # terms from before the split
    assert splits.factor("GRML", "2026-08-24") == 0.5                        # the split day's prints are post-split
    assert splits.factor("NONE", "2026-07-15") == 1.0


def test_a_reused_ticker_adjusts_by_its_own_companys_splits_only(listed):
    assert splits.factor("REUS", "2017-01-03") == 10.0           # Then Co's 1-for-10; Now Co's 2024 split is not its
    assert splits.factor("REUS", "2020-01-02") == 20.0
    every = splits.table("REUS")
    assert list(every["holder_cik"]) == ["1", "2"] and every.attrs["ticker"]["ticker_reused"] is True
    assert list(splits.table("REUS", day="2019-01-02")["execution_date"]) == [date(2024, 6, 3)]


def test_a_reused_ticker_without_splits_keeps_its_columns(listed, tmp_path):
    (tmp_path / "store" / "reference" / "tickers.json").write_text(json.dumps([
        {"ticker": "NOSP", "cik": "5", "name": "Now", "active": True},
        {"ticker": "NOSP", "cik": "4", "name": "Then", "active": False, "delisted_utc": "2010-01-04T05:00:00Z"}]),
        encoding="utf-8")
    splits.tickers.clear()
    frame = splits.table("NOSP", day="2022-01-03")
    assert frame.empty and "execution_date" in frame
    assert splits.factor("NOSP", "2022-01-03") == 1.0


def test_adjust_scales_prices_up_and_shares_down_and_says_so(listed):
    raw = pd.DataFrame({"price": [0.19], "size": [5000.0], "sequence_number": [7]})
    raw.attrs.update(symbol="GRML", day="2026-07-15")
    out = splits.adjust(raw, "GRML", "2026-07-15", "2026-09-01")
    assert out["price"].tolist() == pytest.approx([9.5])
    assert out["size"].tolist() == pytest.approx([100.0])
    assert out["sequence_number"].tolist() == [7]
    assert out.attrs["split_factor"] == 50.0 and out.attrs["adjusted_to"] == "2026-09-01"
    assert out.attrs["day"] == "2026-07-15"
    assert raw["price"].tolist() == [0.19]                                   # the read itself stays raw
