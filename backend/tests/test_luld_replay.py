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


def test_the_trail_runs_to_the_playhead_and_a_scrub_back_cuts_it():
    served(t("09:36:12"))
    assert replay._result["trail"] == [{"ts": t("09:36:06"), "lower": 14.18, "upper": 17.33, "exact": True}]
    served(t("09:36:05"))                                        # before the reopening print: nothing yet
    assert replay._result["trail"] == []


def test_the_trail_answers_from_the_last_result(monkeypatch):
    monkeypatch.setattr(replay, "_playhead", lambda: t("09:36:12"))
    monkeypatch.setattr(replay, "_ask", lambda key, asof: None)  # the worker thread is not started here
    assert replay.trail("GRML")["state"] == "warming"
    served(t("09:36:12"))
    body = replay.trail("GRML")
    assert body["source"] == "replay" and body["steps"][0]["upper"] == 17.33 and body["as_of"] == t("09:36:12")


def _historical_selection(
    *,
    symbol: str = "OFAL",
    source: str = "massive",
    prev_close: float | None = 2.00,
    prints: list[dict] | None = None,
    quotes: list[tuple] | None = None,
    coverage: list[list[float]] | None = None,
    download_status: str = "complete",
) -> SimpleNamespace:
    from sim.history_quotes import QuoteSeries
    from sim.print_table import PrintTable

    span = coverage if coverage is not None else [[t("04:00:00"), t("20:00:00")]]
    p_table = PrintTable(prints or [])
    q_series = QuoteSeries(quotes) if quotes is not None else None
    spec = {
        "symbol": symbol,
        "date": DAY,
        "start": "04:00",
        "end": "20:00",
        "start_ts": span[0][0],
        "end_ts": span[-1][1],
        "source": source,
        "job_id": "job-1",
        "coverage": span,
        "trade_count": len(p_table),
        "quote_status": "complete" if q_series is not None else None,
        "download_status": download_status,
    }
    return SimpleNamespace(spec=spec, prints=p_table, quotes=q_series, prev_close=prev_close)


def test_massive_historical_replay_computes_bands_limit_state_and_avoids_live_cap_leak(monkeypatch):
    monkeypatch.setattr(replay, "_capture", lambda: None)
    sel = _historical_selection(
        prev_close=2.00,
        prints=[
            {"ts": t("09:30:02"), "price": 2.50, "size": 100.0, "conditions": "17,12", "exchange": "NASDAQ", "sets_price": True},
            {"ts": t("09:30:10"), "price": 2.55, "size": 200.0, "conditions": "12", "exchange": "NASDAQ", "sets_price": True},
        ],
        quotes=[
            (t("09:30:01"), 2.48, 100.0, 12, 2.52, 100.0, 12),
            (t("09:30:01") + 0.5, 2.48, 300.0, 12, 2.52, 400.0, 12),  # duplicate (bid, ask) is deduplicated
            (t("09:30:15"), 3.00, 100.0, 12, 3.05, 100.0, 12),        # NBB on the 3.00 (+20%) upper band
        ],
    )
    monkeypatch.setattr(replay, "_historical", lambda: sel)
    data = replay._loaded()
    assert data is not None
    replay._serve(data.key, t("09:30:12"))
    v = replay._result["view"]
    assert (v["source"], v["state"], v["lower"], v["upper"], v["exact"], v["tier_sure"]) == (
        "replay", "bands", 2.00, 3.00, True, True
    )
    assert v["anchor"]["kind"] == "open"

    replay._serve(data.key, t("09:30:20"))
    v_lim = replay._result["view"]
    assert v_lim["state"] == "limit" and v_lim["limit"]["side"] == "up"

    # Over $3.00 on a historical replay, today's cached Yahoo market cap must not make tier_sure=True.
    monkeypatch.setattr("fundamentals.peek_cached", lambda symbol: {"market_cap": 50e9})
    sel_high = _historical_selection(
        prev_close=10.00,
        prints=[{"ts": t("09:30:02"), "price": 10.00, "size": 100.0, "conditions": "17", "exchange": "NASDAQ", "sets_price": True}],
        quotes=[(t("09:30:01"), 9.95, 100.0, 12, 10.05, 100.0, 12)],
    )
    monkeypatch.setattr(replay, "_historical", lambda: sel_high)
    data_high = replay._loaded()
    replay._serve(data_high.key, t("09:30:10"))
    vh = replay._result["view"]
    assert (vh["tier"], vh["tier_sure"], vh["lower"], vh["upper"]) == (2, False, 9.00, 11.00)


def test_ibkr_historical_replay_without_quotes_stays_approximate(monkeypatch):
    monkeypatch.setattr(replay, "_capture", lambda: None)
    sel = _historical_selection(
        source="ibkr",
        prev_close=2.00,
        prints=[
            {"ts": t("09:30:02"), "price": 2.50, "size": 100.0, "conditions": "O X", "exchange": "NASDAQ", "sets_price": True},
        ],
        quotes=None,
    )
    monkeypatch.setattr(replay, "_historical", lambda: sel)
    data = replay._loaded()
    replay._serve(data.key, t("09:30:10"))
    v = replay._result["view"]
    assert (v["state"], v["lower"], v["upper"], v["exact"]) == ("bands", 2.00, 3.00, False)
    assert v["reference_source"] == "open" and v["spread"] is not None


def test_historical_replay_nbbo_only_and_incomplete_windows(monkeypatch):
    monkeypatch.setattr(replay, "_capture", lambda: None)
    # 1. Empty running import reports warming.
    sel_empty = _historical_selection(prints=[], quotes=None, download_status="running")
    monkeypatch.setattr(replay, "_historical", lambda: sel_empty)
    monkeypatch.setattr(replay, "_playhead", lambda: t("09:31:00"))
    v_empty = replay.view("OFAL")
    assert v_empty["state"] == "warming" and "historical replay" in v_empty["reason"]

    # 2. NBBO-only window has no trades to average after the open grace window.
    sel_nbbo = _historical_selection(
        prints=[],
        quotes=[(t("09:30:01"), 2.48, 100.0, 12, 2.52, 100.0, 12)],
    )
    monkeypatch.setattr(replay, "_historical", lambda: sel_nbbo)
    data_nbbo = replay._loaded()
    replay._serve(data_nbbo.key, t("09:36:00"))
    v_nbbo = replay._result["view"]
    assert v_nbbo["state"] == "unknown" and "No trades" in v_nbbo["reason"]

    # 3. Incomplete mid-session window (10:00-10:10) warms for 5 minutes and seeds approximate bands.
    sel_mid = _historical_selection(
        prints=[
            {"ts": t("10:00:05"), "price": 2.50, "size": 100.0, "conditions": "12", "exchange": "NASDAQ", "sets_price": True},
            {"ts": t("10:04:00"), "price": 2.50, "size": 100.0, "conditions": "12", "exchange": "NASDAQ", "sets_price": True},
        ],
        quotes=[(t("10:00:01"), 2.48, 100.0, 12, 2.52, 100.0, 12)],
        coverage=[[t("10:00:00"), t("10:10:00")]],
    )
    monkeypatch.setattr(replay, "_historical", lambda: sel_mid)
    data_mid = replay._loaded()
    replay._serve(data_mid.key, t("10:02:00"))
    assert replay._result["view"]["state"] == "warming"
    replay._serve(data_mid.key, t("10:05:30"))
    v_seeded = replay._result["view"]
    assert (v_seeded["state"], v_seeded["exact"], v_seeded["reference_source"]) == ("bands", False, "seeded")

    # 4. A window that saw the open (exact) and ends at 09:40 marks a gap when scrubbed past its coverage.
    sel_gap = _historical_selection(
        prints=[{"ts": t("09:30:02"), "price": 2.50, "size": 100.0, "conditions": "17", "exchange": "NASDAQ", "sets_price": True}],
        quotes=[(t("09:30:01"), 2.48, 100.0, 12, 2.52, 100.0, 12)],
        coverage=[[t("09:30:00"), t("09:40:00")]],
    )
    monkeypatch.setattr(replay, "_historical", lambda: sel_gap)
    data_gap = replay._loaded()
    replay._serve(data_gap.key, t("09:35:00"))
    assert replay._result["view"]["exact"] is True and replay._result["view"]["gap"] is None
    replay._serve(data_gap.key, t("09:45:00"))
    assert replay._result["view"]["exact"] is False and replay._result["view"]["gap"] is not None

