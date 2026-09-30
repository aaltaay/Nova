"""The Cryptos page's pure reads (ADR 040): headline rules, the clock, and the bridge arithmetic."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from crypto import clock, stats
from crypto.classify import best_item, classify_headline

ET = ZoneInfo("America/New_York")


def at(text: str) -> float:
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=ET).timestamp()


@pytest.mark.parametrize(("title", "kind"), [
    ("Spot bitcoin ETFs log fifth straight inflow day", "catalyst"),
    ("Solana network upgrade goes live on mainnet", "catalyst"),
    ("Why Solana is rising: network upgrade went live", "catalyst"),
    ("Coinbase lists SUI on its exchange", "catalyst"),
    ("Kraken to begin listing on its US platform", "catalyst"),
    ("PEPE lists on Binance", "catalyst"),
    ("Treasury firm buys 5,000 BTC", "catalyst"),
    ("Exchange hacked, $200M drained from hot wallet", "negative"),
    ("SEC charges exchange founder with fraud", "negative"),
    ("SUI token unlock: 1.3% of supply releases Thursday", "negative"),
    ("Exchange halts withdrawals after outage", "negative"),
    ("Why is Dogecoin rising today?", "noise"),
    ("XRP price prediction: will the SEC lawsuit end?", "noise"),
    ("Top 5 cryptos to buy now", "noise"),
    ("Bitcoin breaches $70,000", "noise"),
    ("Bitcoin settles above $100K", "noise"),
    ("Dogecoin whales move 1B DOGE", "noise"),
    ("$400M in longs liquidated as bitcoin slides", "noise"),
    ("Exchange charges fees on withdrawals", "news"),
    ("Cardano founder talks roadmap", "news"),
])
def test_headline_rules(title, kind):
    assert classify_headline(title) == kind


def test_a_roundup_is_noise_and_a_summary_can_carry_the_cause():
    assert classify_headline("Bitcoin, Ether, XRP and Solana climb", n_tickers=4) == "noise"
    assert classify_headline("Cardano update", "The network upgrade went live overnight") == "catalyst"
    assert classify_headline("", None) == "news"


def test_best_item_prefers_a_cause_then_news_then_noise_newest_first():
    items = [{"kind": "noise", "published_ts": 30}, {"kind": "news", "published_ts": 20},
             {"kind": "negative", "published_ts": 5}, {"kind": "catalyst", "published_ts": 10}]
    assert best_item(items)["kind"] == "catalyst"
    assert best_item([{"kind": "noise", "published_ts": 1}, {"kind": "news", "published_ts": 0}])["kind"] == "news"
    assert best_item([]) is None


@pytest.mark.parametrize(("when", "session", "phase"), [
    ("2026-09-29 23:08", "closed", "overnight"),
    ("2026-09-30 04:00", "premarket", "premarket"),
    ("2026-09-30 09:30", "regular", "regular"),
    ("2026-09-30 16:00", "after_hours", "after_hours"),
    ("2026-10-03 11:00", "closed", "overnight"),   # Saturday
    ("2026-11-26 11:00", "closed", "overnight"),   # Thanksgiving
])
def test_stock_sessions(when, session, phase):
    assert clock.stock_session(at(when)) == session
    assert clock.bridge_phase(at(when)) == phase


@pytest.mark.parametrize(("when", "close"), [
    ("2026-09-29 23:08", "2026-09-29 16:00"),
    ("2026-09-29 15:59", "2026-09-28 16:00"),
    ("2026-10-05 08:00", "2026-10-02 16:00"),   # Monday premarket reads Friday's close
    ("2026-11-27 08:00", "2026-11-25 16:00"),   # the day after Thanksgiving
])
def test_reference_close_is_the_last_regular_session_close(when, close):
    ts, day = clock.reference_close(at(when))
    assert ts == at(close) and day == close[:10]


def test_the_next_stock_event_skips_closed_days():
    nxt = clock.stock_next(at("2026-10-02 20:30"))   # Friday night
    assert nxt["kind"] == "premarket" and nxt["at"] == at("2026-10-05 04:00")


def test_funding_the_crypto_day_and_expiries():
    now = at("2026-09-29 23:08")                        # 03:08 UTC Sept 30
    assert clock.next_funding(now) == datetime(2026, 9, 30, 8, tzinfo=timezone.utc).timestamp()
    assert clock.crypto_day_start(now) == datetime(2026, 9, 30, tzinfo=timezone.utc).timestamp()
    assert clock.next_expiry(now) == (datetime(2026, 10, 2, 8, tzinfo=timezone.utc).timestamp(), False)
    assert clock.next_expiry(at("2026-10-24 12:00"))[1] is True   # Oct 30 is the month's last Friday


def test_the_clock_block_follows_daylight_time():
    summer = clock.clock(at("2026-09-29 23:08"))
    assert summer["crypto_day_start_et"] == "20:00"
    assert summer["regions"] == {"asia": True, "europe": False, "us": False}
    assert summer["lanes"]["asia"] == [[0, 240], [1200, 1440]]
    assert summer["lanes"]["europe"] == [[180, 690]]
    assert summer["lanes"]["funding"] == [[240, 240], [720, 720], [1200, 1200]]
    winter = clock.clock(at("2026-12-01 23:00"))
    assert winter["crypto_day_start_et"] == "19:00"
    assert winter["lanes"]["funding"] == [[180, 180], [660, 660], [1140, 1140]]
    weekend = clock.clock(at("2026-10-03 11:00"))
    assert weekend["lanes"]["regular"] == [] and weekend["lanes"]["asia"] == []
    assert weekend["regions"]["europe"] is False


def test_beta_and_correlation_on_a_known_line():
    coin = {f"2026-09-{d:02d}": 100.0 * (1.01 ** d) * (1 + (0.02 if d % 3 == 0 else -0.01)) for d in range(1, 30)}
    stock = {}
    prev_c = prev_s = None
    for day in sorted(coin):
        if prev_c is None:
            stock[day] = 50.0
        else:
            stock[day] = prev_s * (1 + 2.0 * (coin[day] / prev_c - 1))
        prev_c, prev_s = coin[day], stock[day]
    xs, ys = stats.aligned_returns(stock, coin, 60)
    assert len(xs) == 28
    assert stats.beta(xs, ys, 20) == pytest.approx(2.0)
    assert stats.corr(xs, ys, 20) == pytest.approx(1.0)
    assert stats.beta(xs[:10], ys[:10], 20) is None
    assert stats.beta([0.01] * 25, ys[:25], 20) is None   # a flat coin: no slope


def test_aligned_returns_pair_the_same_stretch_on_both_sides():
    stock = {"2026-09-01": 10.0, "2026-09-02": 11.0, "2026-09-03": 12.1}
    coin = {"2026-09-01": 100.0, "2026-09-03": 120.0}
    xs, ys = stats.aligned_returns(stock, coin, 60)
    assert xs == [pytest.approx(0.2)] and ys == [pytest.approx(0.21)]


def test_prices_at_close_read_the_16_00_hour():
    t16 = stats.close_time("2026-09-29")
    hourly = [{"t": int(t16) - 3600, "o": 1, "h": 1, "l": 1, "c": 99.0, "v": 1},
              {"t": int(t16), "o": 100.0, "h": 1, "l": 1, "c": 101, "v": 1}]
    assert stats.prices_at_close(hourly, ["2026-09-29"]) == {"2026-09-29": 100.0}
    assert stats.prices_at_close(hourly[:1], ["2026-09-29"]) == {"2026-09-29": 99.0}
    assert stats.prices_at_close([], ["2026-09-29"]) == {}
    assert stats.pct_change(110, 100) == pytest.approx(10.0)
    assert stats.pct_change(None, 100) is None and stats.pct_change(1, 0) is None
