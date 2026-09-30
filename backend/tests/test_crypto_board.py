"""The Cryptos page's board (ADR 040): stored answers composed into the wire shape, unknowns kept unknown."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from crypto import board, clock, stats
from crypto.news import file_articles
from crypto.state import Store

ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 29, 23, 8, tzinfo=ET).timestamp()
REF = datetime(2026, 9, 29, 16, 0, tzinfo=ET).timestamp()


def sessions(end: date, n: int) -> list[str]:
    days, d = [], end
    while len(days) < n:
        if clock.open_day(d):
            days.append(d.isoformat())
        d -= timedelta(days=1)
    return sorted(days)


DAYS = sessions(date(2026, 9, 29), 70)


def coin_series(start: float, swing: float) -> dict[str, float]:
    out, price = {}, start
    for i, day in enumerate(DAYS):
        price *= 1 + (swing if i % 2 else -swing * 0.6)
        out[day] = price
    return out


BTC_16 = coin_series(95_000.0, 0.02)
BTC_16[DAYS[-1]] = 110_120.0
ETH_16 = coin_series(3_900.0, 0.03)


def follow(coin: dict[str, float], beta: float, last_close: float) -> dict[str, float]:
    """A stock whose every session return is ``beta`` times the coin's, ending at ``last_close``."""
    out, price, prev = {}, 1.0, None
    for day in DAYS:
        if prev is not None:
            price *= 1 + beta * (coin[day] / prev - 1)
        out[day] = price
        prev = coin[day]
    k = last_close / out[DAYS[-1]]
    return {d: p * k for d, p in out.items()}


def hourly(series: dict[str, float]) -> list[dict]:
    return [{"t": int(stats.close_time(d)), "o": p, "h": p, "l": p, "c": p, "v": 1.0} for d, p in series.items()]


def fifteen(at_close: float, last: float) -> list[dict]:
    rows = [{"t": int(REF), "o": at_close, "h": at_close, "l": at_close, "c": at_close, "v": 1.0}]
    t = int(REF) + 900
    while t < NOW:
        rows.append({"t": t, "o": at_close, "h": last, "l": at_close, "c": last, "v": 1.0})
        t += 900
    return rows


MARKETS = {
    "bitcoin": {"price": 112480.0, "rank": 1, "high_24h": 113120.0, "low_24h": 108960.0, "change_1h_pct": 0.4,
                "change_24h_pct": 2.84, "change_7d_pct": 5.1, "volume_24h_usd": 36e9, "market_cap_usd": 2.24e12,
                "market_cap_change_24h_usd": 6.0e10, "from_ath_pct": -7.9, "spark_7d": [1.0, 2.0]},
    "ethereum": {"price": 4212.4, "rank": 2, "change_24h_pct": 4.1, "volume_24h_usd": 20e9,
                 "market_cap_usd": 508e9, "market_cap_change_24h_usd": 2e10, "spark_7d": []},
}


@pytest.fixture
def st() -> Store:
    s = Store()
    s.want(NOW - 30)
    s.put("markets", "coingecko", MARKETS, NOW - 10)
    s.put("global", "coingecko", {"total_cap_usd": 3.94e12, "total_cap_change_24h_pct": 2.61,
                                  "btc_dominance_pct": 57.8, "total_volume_usd": 148.2e9}, NOW - 10)
    s.put("volume:BTC", "coingecko", [30e9] * 30, NOW - 100)
    s.put("volume:ETH", "coingecko", [10e9] * 30, NOW - 100)
    s.put("perps", "hyperliquid", {"BTC": {"funding_8h_pct": 0.012, "open_interest_usd": 2e9},
                                   "ETH": {"funding_8h_pct": 0.018, "open_interest_usd": 1e9},
                                   "kPEPE": {"funding_8h_pct": 0.052, "open_interest_usd": None}}, NOW - 5)
    s.put("fear_greed", "fear_greed", {"value": 68, "label": "Greed", "week_ago": 54, "at": NOW - 3600}, NOW - 60)
    s.put("news", "alpaca", file_articles([
        {"created_at": "2026-09-30T01:36:00Z", "headline": "Spot bitcoin ETFs log fifth straight inflow day",
         "symbols": ["BTCUSD"], "source": "benzinga", "url": "https://example.invalid/a"},
        {"created_at": "2026-09-30T02:10:00Z", "headline": "Why is Dogecoin rising today?", "symbols": ["DOGEUSD"]},
        {"created_at": "2026-09-29T23:05:00Z", "headline": "SUI token unlock: 1.3% of supply releases Thursday",
         "symbols": ["SUIUSD"]},
    ]), NOW - 20)
    s.put("listing:BTC", "ibkr", {"listed": True, "venue": "PAXOS"}, NOW - 500)
    s.put("listing:BNB", "ibkr", {"listed": False, "venue": None}, NOW - 500)
    s.put("candles:BTC:15m", "coinbase", fifteen(110_120.0, 112_480.0), NOW - 5)
    s.put("candles:ETH:15m", "coinbase", fifteen(ETH_16[DAYS[-1]], ETH_16[DAYS[-1]] * 1.0302), NOW - 5)
    s.put("hourly:BTC", "coinbase", hourly(BTC_16), NOW - 600)
    s.put("hourly:ETH", "coinbase", hourly(ETH_16), NOW - 600)
    s.put("closes:MARA", "ibkr", follow(BTC_16, 2.4, 21.34), NOW - 900)
    s.put("closes:ETHA", "ibkr", follow(ETH_16, 1.0, 31.62), NOW - 900)
    s.put("closes:IBIT", "ibkr", follow(BTC_16, 1.0, 63.84), NOW - 900)
    s.put("closes:QQQ", "ibkr", follow(BTC_16, 0.5, 600.0), NOW - 900)
    s.put("bridge_quotes", "ibkr", {"MARA": 23.0, "ETHA": 32.2, "IBIT": None}, NOW - 30)
    s.put("expiries", "deribit", [{"at": datetime(2026, 10, 2, 8, tzinfo=timezone.utc).timestamp(),
                                   "open_interest": 36_000.0, "notional_usd": 4.1e9}], NOW - 900)
    return s


def test_the_board_has_the_documented_shape(st):
    out = board.compose(st, NOW)
    assert out["schema_version"] == 1 and out["enabled"] is True and out["loading"] is False
    assert set(out) == {"schema_version", "generated_at", "enabled", "loading", "replay_desk", "clock", "market",
                        "coins", "leverage", "flows", "bridge", "next", "news", "sources"}
    assert [c["symbol"] for c in out["coins"]][:3] == ["BTC", "ETH", "SOL"]


def test_coins_carry_their_numbers_and_unknowns_stay_null(st):
    coins = {c["symbol"]: c for c in board.compose(st, NOW)["coins"]}
    btc = coins["BTC"]
    assert btc["price"] == 112480.0 and btc["volume_x_30d"] == pytest.approx(1.2)
    assert btc["funding_8h_pct"] == 0.012 and btc["ibkr"] == {"listed": True, "venue": "PAXOS"} and btc["etf"] == "IBIT"
    assert btc["why"]["kind"] == "catalyst" and btc["news_checked"] is True
    sol = coins["SOL"]
    assert sol["price"] is None and sol["volume_x_30d"] is None and sol["funding_8h_pct"] is None
    assert sol["why"] is None and sol["news_checked"] is True     # Alpaca looked: no news found
    assert sol["ibkr"] is None                                    # never asked: unknown
    assert coins["BNB"]["ibkr"] == {"listed": False, "venue": None} and coins["BNB"]["chart"] is False
    assert coins["PEPE"]["funding_8h_pct"] == 0.052               # kPEPE is PEPE's perpetual
    assert coins["DOGE"]["why"]["kind"] == "noise" and coins["SUI"]["why"]["kind"] == "negative"


def test_market_numbers_are_worked_out_from_coingecko_only(st):
    m = board.compose(st, NOW)["market"]
    assert m["total_cap_usd"] == 3.94e12 and m["fear_greed"]["value"] == 68
    total_then = 3.94e12 / 1.0261
    expected = (2.24e12 / 3.94e12 - (2.24e12 - 6.0e10) / total_then) * 100
    assert m["btc_dominance_change_24h_pt"] == pytest.approx(expected)
    assert m["eth_btc"] == pytest.approx(4212.4 / 112480.0)
    assert m["eth_btc_change_24h_pct"] == pytest.approx((1.041 / 1.0284 - 1) * 100)
    assert m["volume_x_30d"] == pytest.approx(56e9 / 40e9)
    assert m["btc_qqq_corr_30d"] == pytest.approx(1.0)


def test_leverage_sorts_funding_and_states_the_missing_liquidations(st):
    lev = board.compose(st, NOW)["leverage"]
    assert [f["symbol"] for f in lev["funding"]] == ["PEPE", "ETH", "BTC"]
    assert lev["open_interest_usd"] == 3e9 and lev["btc_open_interest_usd"] == 2e9
    assert lev["liquidations_24h"] is None and "No free source" in lev["liquidations_note"]


def test_the_bridge_reads_beta_implied_move_and_ahead_or_behind(st):
    bridge = board.compose(st, NOW)["bridge"]
    assert bridge["reference_close_at"] == REF and bridge["phase"] == "overnight"
    assert bridge["btc_since_close_pct"] == pytest.approx((112480 / 110120 - 1) * 100)
    rows = {r["symbol"]: r for r in bridge["rows"]}
    mara = rows["MARA"]
    assert mara["beta"] == pytest.approx(2.4) and mara["close"] == pytest.approx(21.34)
    assert mara["since_close_pct"] == pytest.approx((23 / 21.34 - 1) * 100)
    assert mara["implied_pct"] == pytest.approx(bridge["btc_since_close_pct"] * 2.4)
    assert mara["read"] == "ahead" and mara["gap_pt"] > 0.5
    assert rows["ETHA"]["driver"] == "ETH" and rows["ETHA"]["read"] == "behind"
    ibit = rows["IBIT"]
    assert ibit["last"] is None and ibit["since_close_pct"] is None and ibit["read"] is None
    assert rows["COIN"]["close"] is None and rows["COIN"]["beta"] is None   # IBKR never answered for it
    assert bridge["error"] is None


def test_the_bridge_says_why_when_ibkr_is_down(st):
    st.source_down("ibkr", "IBKR is not connected")
    out = board.compose(st, NOW)
    assert out["bridge"]["error"] == "IBKR is not connected"
    ibkr = next(s for s in out["sources"] if s["id"] == "ibkr")
    assert ibkr["ok"] is False and ibkr["error"] == "IBKR is not connected"


def test_next_events_are_soonest_first_with_the_expiry_notional(st):
    events = board.compose(st, NOW)["next"]
    # 23:08 ET: funding and the premarket both at 04:00, the new crypto day at 20:00, Friday's expiry.
    assert [e["kind"] for e in events] == ["funding", "stocks", "crypto_day", "expiry"]
    assert [e["at"] for e in events] == sorted(e["at"] for e in events)
    assert events[1]["title"] == "US premarket opens"
    assert events[3]["title"] == "Weekly options expiry" and events[3]["detail"] == "BTC $4.1B open on Deribit"


def test_at_midnight_utc_the_crypto_day_and_funding_are_one_event(st):
    events = board.compose(st, datetime(2026, 9, 30, 19, 0, tzinfo=ET).timestamp())["next"]
    assert events[0]["kind"] == "crypto_day" and events[0]["title"] == "New crypto day · funding settles"
    assert "funding" not in [e["kind"] for e in events]


def test_news_ranks_causes_first(st):
    news = board.compose(st, NOW)["news"]
    assert [n["kind"] for n in news] == ["catalyst", "negative", "noise"]
    assert news[0]["symbol"] == "BTC" and news[0]["source"] == "Benzinga"


def test_loading_until_the_core_reads_are_tried_and_stale_answers_expire():
    s = Store()
    s.want(NOW)
    assert board.compose(s, NOW)["loading"] is True
    for key in board.CORE_KEYS:
        s.fail(key, "coingecko", "HTTP 500", NOW + 1)
    assert board.compose(s, NOW + 2)["loading"] is False
    s.put("markets", "coingecko", MARKETS, NOW - 2000)
    assert board.compose(s, NOW)["coins"][0]["price"] is None   # older than any max age: unknown


def test_a_disabled_board_is_not_loading():
    out = board.compose(Store(), NOW, enabled=False)
    assert out["enabled"] is False and out["loading"] is False and out["coins"][0]["price"] is None
