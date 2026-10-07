"""LULD on a Session Record replay (ADR 047): the bands at the playhead, a scrub back, the study reader."""
from __future__ import annotations

import gzip
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from luld import replay, study

ET = ZoneInfo("America/New_York")
DAY = "2026-09-22"


def t(hms: str) -> float:
    return datetime.fromisoformat(f"{DAY}T{hms}").replace(tzinfo=ET).timestamp()


def capture() -> SimpleNamespace:
    prints = [
        {"ts": t("09:36:06"), "price": 15.75, "conditions": "5 X", "exchange": "NASDAQ", "sets_price": True},
        {"ts": t("09:36:10"), "price": 15.70, "conditions": "", "exchange": "NASDAQ", "sets_price": True},
        {"ts": t("09:36:20"), "price": 14.18, "conditions": "", "exchange": "NASDAQ", "sets_price": True},
    ]
    quotes = [
        {"ts": t("09:36:07"), "bid": 15.60, "ask": 15.80},
        {"ts": t("09:36:18"), "bid": 14.10, "ask": 14.18},      # the offer on the 14.18 lower band
    ]
    return SimpleNamespace(key=f"{DAY}|GRML", symbol="GRML", prints=prints, quotes=quotes, prev_close=10.85,
                           spans=[])


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    replay.reset_for_tests()
    data = capture()
    monkeypatch.setattr(replay, "_capture", lambda: data)
    monkeypatch.setattr(replay, "_halts", lambda day, symbol: [])
    monkeypatch.setattr("fundamentals.peek_cached", lambda symbol: {"market_cap": 90e6})
    yield data
    replay.reset_for_tests()


def served(asof: float) -> dict:
    replay._serve(f"{DAY}|GRML", asof)
    return replay._result["view"]


def test_the_band_at_the_playhead_comes_from_the_recordings_reopening_print():
    v = served(t("09:36:12"))
    assert (v["source"], v["state"], v["lower"], v["upper"], v["exact"]) == ("replay", "bands", 14.18, 17.33, True)
    assert v["anchor"]["kind"] == "reopen"


def test_the_limit_state_counts_down_on_the_replay_and_a_scrub_back_starts_over():
    v = served(t("09:36:25"))
    assert v["state"] == "limit" and v["limit"]["side"] == "down" and v["limit"]["pause_at"] == t("09:36:33")
    v = served(t("09:36:08"))                                   # back before the limit state
    assert v["state"] == "bands" and v["limit"] is None


def test_another_stock_or_no_recording_says_why(monkeypatch):
    v = replay.view("ABC")
    assert v["state"] == "unknown" and "Session Record" in v["reason"]
    monkeypatch.setattr(replay, "_capture", lambda: None)
    assert "none is loaded" in replay.view("GRML")["reason"]


def test_the_study_reads_several_tickers_in_one_pass(tmp_path, monkeypatch):
    rows = ["ticker,price", "AAA,1", "BBB,2", "BBB,3", "CCC,4", "DDD,5", "DDD,6"]
    path = tmp_path / "day.csv.gz"
    with gzip.open(path, "wb") as fh:
        fh.write("\n".join(rows).encode())                      # Massive's newlines; none after the last line
    monkeypatch.setattr(study, "READ_CHUNK", 7)                  # stretches cross chunk boundaries
    got: dict[str, list[bytes]] = {}
    for ticker, header, lines in study.ticker_blocks(path, ["DDD", "BBB", "ZZZ", "AAB"]):
        assert header == ["ticker", "price"]
        got.setdefault(ticker, []).extend(lines)
    assert got == {"BBB": [b"BBB,2", b"BBB,3"], "DDD": [b"DDD,5", b"DDD,6"]}


def test_the_study_compares_each_band_the_sip_flagged():
    trades = [(t("09:36:06"), 15.75, True, "5", "12"), (t("09:36:10"), 15.70, True, "", "12")]
    quotes = [(t("09:36:07"), 15.60, 15.80, 1, "1"),
              (t("09:36:18"), 14.10, 14.18, 8, "1"),               # NBB under, NBO equal to the lower band
              (t("09:36:19"), 14.10, 14.18, 8, "1")]               # the same touch: counted once
    out = study.evaluate("GRML", DAY, trades, quotes, prev_close=10.85, pauses=[t("09:36:33")])
    assert len(out["touches"]) == 1
    touch = out["touches"][0]
    assert (touch["side"], touch["sip"], touch["no_exit"], touch["no_exit_exact"]) == ("lower", 14.18, 14.18, True)
    assert out["pauses"][0]["pinned_ask"] == 14.18
    summary = study.summarize([out])
    assert summary["variants"]["no_exit"]["exact"] == 1
