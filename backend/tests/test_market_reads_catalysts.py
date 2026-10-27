"""News items and catalyst verdicts through the front door (``research/market_reads/catalysts.py``): Finnhub's
four-hours-early Benzinga copies are left out exactly as the research readers leave them out (#516), an ``at`` cutoff
never reads an item published after it, the newest rules version wins by number, and a stock-day with no verdict is
unknown -- never "no news"."""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("pandas")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from market_reads import catalysts  # noqa: E402

ET = ZoneInfo("America/New_York")
V7, V10 = "catalyst-rules-v7-2026-09-24", "catalyst-rules-v10-2026-11-01"


def ts(stamp: str) -> float:
    return datetime.fromisoformat(stamp).replace(tzinfo=ET).timestamp()


ITEMS = [  # item_id, source, published, title, publisher, ticker
    ("alpaca:1", "alpaca", "2026-09-08 17:00", "IRD wins contract", "benzinga", "IRD"),
    ("finnhub:2", "finnhub", "2026-09-08 18:00", "IRD wins contract (copy)", "Benzinga", "IRD"),
    ("edgar:3", "edgar", "2026-09-09 08:05", "8-K", "SEC EDGAR", "IRD"),
    ("massive:4", "massive", "2026-09-09 09:45", "IRD shares jump", "GlobeNewswire Inc.", "IRD"),
    ("alpaca:5", "alpaca", "2026-09-09 07:00", "Other news", "benzinga", "OTHR"),
]
TARGETS = [("IRD", "2026-09-09", ts("2026-09-08 16:00"), ts("2026-09-09 09:30"), ts("2026-09-09 20:00"), "pillars"),
           ("RUN", "2026-07-01", ts("2026-06-30 16:00"), ts("2026-07-01 08:12"), ts("2026-07-01 20:00"), "leaderboard")]
VERDICTS = [
    ("IRD", "2026-09-09", "target", V7, "noise_only", None, None, None, None, None, None, "alpaca", 1),
    ("IRD", "2026-09-09", "target", V10, "catalyst", "contract", "strong", "alpaca:1", "alpaca",
     ts("2026-09-08 17:00"), "IRD wins contract", "alpaca,edgar,massive", 2),
    ("RUN", "2026-07-01", "target", V7, "none_found", None, None, None, None, None, None, "alpaca,edgar,massive", 0),
]


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CATALYST_DIR", str(tmp_path))
    db = sqlite3.connect(tmp_path / "catalysts.sqlite3")
    db.executescript(catalysts._STORE.SCHEMA)
    db.execute(f"PRAGMA user_version = {catalysts.SCHEMA_VERSION}")
    for item_id, source, published, title, publisher, ticker in ITEMS:
        db.execute("INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (item_id, source, ts(published), title, None, f"https://x/{item_id}", publisher, 1, None, None, 0))
        db.execute("INSERT INTO item_tickers VALUES (?,?,?)", (item_id, ticker, ts(published)))
    db.executemany("INSERT INTO targets VALUES (?,?,?,?,?,?)", TARGETS)
    db.executemany("INSERT INTO verdicts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", VERDICTS)
    db.execute("INSERT INTO checks VALUES (?,?,?,?,?,?,?)", ("IRD", "2026-09-09", "finnhub", "out_of_range", None, None, 0))
    db.commit()
    db.close()
    return tmp_path


def test_items_leave_out_finnhubs_early_benzinga_copies(store):
    frame = catalysts.items("ird", date_from="2026-09-08", date_to="2026-09-09")
    assert list(frame["item_id"]) == ["alpaca:1", "edgar:3", "massive:4"]          # oldest first
    assert frame.attrs["excluded_finnhub_benzinga"] == 1
    assert frame.iloc[0]["published_et"] == "2026-09-08 17:00:00"
    assert frame.attrs["checks"] == [{"session_date": "2026-09-09", "source": "finnhub", "status": "out_of_range",
                                      "n_items": None}]
    assert "UNKNOWN" in frame.attrs["coverage"]


def test_an_at_cutoff_never_reads_a_later_item(store):
    frame = catalysts.items("IRD", date_from="2026-09-08", at="2026-09-09 09:30")
    assert "massive:4" not in set(frame["item_id"]) and len(frame) == 2


def test_limit_keeps_the_newest_and_sources_filter(store):
    assert list(catalysts.items("IRD", limit=2)["item_id"]) == ["edgar:3", "massive:4"]
    assert list(catalysts.items("IRD", sources=["edgar"])["item_id"]) == ["edgar:3"]
    with pytest.raises(ValueError, match="the store holds"):
        catalysts.items("IRD", sources=["twitter"])


def test_verdicts_read_the_newest_rules_version_by_number(store):
    frame = catalysts.verdicts(symbol="IRD", day="2026-09-09")
    assert len(frame) == 1 and frame.iloc[0]["rules_version"] == V10 and frame.iloc[0]["strength"] == "strong"
    assert frame.iloc[0]["cutoff_et"] == "2026-09-09 09:30:00" and frame.iloc[0]["origin"] == "pillars"
    assert frame.iloc[0]["window_start_et"] == "2026-09-08 16:00:00"
    assert len(catalysts.verdicts(symbol="IRD", rules_version="all")) == 2
    assert catalysts.verdicts(symbol="IRD", rules_version=V7).iloc[0]["verdict"] == "noise_only"
    assert frame.attrs["warning"] and V10 in frame.attrs["warning"]                 # not the live classifier's


def test_for_pairs_answers_every_pair_and_unknown_is_none(store, monkeypatch):
    monkeypatch.setattr(catalysts, "_PARAM_CHUNK", 3)
    out = catalysts.for_pairs([("2026-09-09", "IRD"), ("2026-07-01", "run"), ("2026-09-09", "NOPE")])
    assert out[("2026-09-09", "IRD")]["verdict"] == "catalyst" and out[("2026-09-09", "IRD")]["rules_version"] == V10
    assert out[("2026-07-01", "RUN")]["verdict"] == "none_found"
    assert out[("2026-07-01", "RUN")]["cutoff_et"] == "2026-07-01 08:12:00"       # a mover's own cutoff
    assert out[("2026-09-09", "NOPE")] is None
    assert catalysts.for_pairs([("2026-09-09", "IRD")], cutoff_kind="entry") == {("2026-09-09", "IRD"): None}


def test_a_verdict_search_needs_no_symbol_and_filters_after_the_newest_version(store):
    frame = catalysts.search_verdicts("2026-06-01", "2026-09-30")
    assert list(frame["symbol"]) == ["IRD", "RUN"]                                  # newest day first
    assert frame.attrs["categories"] == {"contract": 1} and frame.attrs["matched"] == 2
    assert list(catalysts.search_verdicts("2026-06-01", "2026-09-30", category=["CONTRACT"])["symbol"]) == ["IRD"]
    assert list(catalysts.search_verdicts("2026-06-01", "2026-09-30", verdict=["none_found"])["symbol"]) == ["RUN"]
    assert list(catalysts.search_verdicts("2026-06-01", "2026-09-30", words=["Wins"])["symbol"]) == ["IRD"]
    # IRD's older v7 verdict was noise_only: the filter reads the newest version, so it is never found
    assert catalysts.search_verdicts("2026-06-01", "2026-09-30", verdict=["noise_only"]).empty
    with pytest.raises(ValueError, match="date_from and date_to"):
        catalysts.search_verdicts("2026-06-01", None)
    with pytest.raises(ValueError, match="at most"):
        catalysts.search_verdicts("2020-01-01", "2026-09-30")


def test_a_headline_search_spans_stocks_and_keeps_the_honest_clock(store):
    frame = catalysts.search_items("2026-09-08", "2026-09-09", ["contract", "other"])
    assert list(frame["item_id"]) == ["alpaca:5", "alpaca:1"]                      # newest first; the copy left out
    assert list(frame["symbol"]) == ["OTHR", "IRD"] and frame.iloc[1]["published_et"] == "2026-09-08 17:00:00"
    assert list(catalysts.search_items("2026-09-08", "2026-09-09", ["contract"], limit=1)["item_id"]) == ["alpaca:1"]
    with pytest.raises(ValueError, match="names words"):
        catalysts.search_items("2026-09-08", "2026-09-09", [" "])


def test_another_schema_version_refuses(store):
    db = sqlite3.connect(store / "catalysts.sqlite3")
    db.execute("PRAGMA user_version = 9")
    db.commit()
    db.close()
    with pytest.raises(RuntimeError, match="refusing to read"):
        catalysts.verdicts(symbol="IRD")


def test_a_missing_store_says_where_it_looked(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CATALYST_DIR", str(tmp_path / "nowhere"))
    with pytest.raises(LookupError, match="not on disk"):
        catalysts.items("IRD")
