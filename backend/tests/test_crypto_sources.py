"""The Cryptos page's public sources (ADR 040): each parser on an answer shaped like the source documents it,
and each failure stated rather than read as zeros."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import requests

from crypto import coinbase, coingecko, feeds, web
from crypto.web import SourceError

MARKETS = [
    {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "current_price": 112480, "market_cap": 2.24e12,
     "market_cap_rank": 1, "total_volume": 38.2e9, "high_24h": 113120, "low_24h": 108960,
     "price_change_percentage_24h": 2.84, "market_cap_change_24h": 6.2e10, "ath_change_percentage": -7.9,
     "last_updated": "2026-09-30T03:08:00.000Z", "sparkline_in_7d": {"price": [float(p) for p in range(100, 268)]},
     "price_change_percentage_1h_in_currency": 0.4, "price_change_percentage_24h_in_currency": 2.84,
     "price_change_percentage_7d_in_currency": 5.1},
    {"id": "pepe", "current_price": "0.00001084", "market_cap_rank": None, "total_volume": None,
     "price_change_percentage_24h": 14.2},
    "not-a-row",
    {"symbol": "no-id"},
]


def test_markets_keep_every_field_and_leave_unknowns_null():
    out = coingecko.parse_markets(MARKETS)
    assert set(out) == {"bitcoin", "pepe"}
    btc = out["bitcoin"]
    assert btc["price"] == 112480 and btc["rank"] == 1 and btc["change_7d_pct"] == 5.1
    assert btc["market_cap_change_24h_usd"] == 6.2e10 and btc["from_ath_pct"] == -7.9
    assert len(btc["spark_7d"]) == 84 and btc["spark_7d"][0] == 100.0 and btc["spark_7d"][-1] == 267.0
    assert btc["updated_at"] == datetime(2026, 9, 30, 3, 8, tzinfo=timezone.utc).timestamp()
    pepe = out["pepe"]
    assert pepe["price"] == pytest.approx(1.084e-5)
    assert pepe["rank"] is None and pepe["volume_24h_usd"] is None and pepe["spark_7d"] == []
    assert pepe["change_24h_pct"] == 14.2   # the plain 24 h field when the currency one is missing


@pytest.mark.parametrize("body", [{"error": "x"}, [], ["junk"]])
def test_markets_refuse_an_answer_they_cannot_read(body):
    with pytest.raises(SourceError):
        coingecko.parse_markets(body)


def test_global_reads_cap_volume_and_dominance():
    body = {"data": {"total_market_cap": {"usd": 3.94e12}, "total_volume": {"usd": 148.2e9},
                     "market_cap_percentage": {"btc": 57.8, "eth": 12.9},
                     "market_cap_change_percentage_24h_usd": 2.61}}
    assert coingecko.parse_global(body) == {"total_cap_usd": 3.94e12, "total_volume_usd": 148.2e9,
                                            "btc_dominance_pct": 57.8, "total_cap_change_24h_pct": 2.61}
    with pytest.raises(SourceError):
        coingecko.parse_global({"data": {"total_volume": {"usd": 1}}})


def test_volume_history_drops_the_running_day_and_keeps_thirty():
    day = 86_400_000
    rows = [[i * day, 1e9 + i] for i in range(40)] + [[40 * day + 3_600_000, 5e9]]
    out = coingecko.parse_volume_history({"total_volumes": rows})
    assert len(out) == 30 and out[0] == 1e9 + 10 and out[-1] == 1e9 + 39


def test_coinbase_candles_come_back_oldest_first_one_per_bucket():
    body = [[1800, 9, 12, 10, 11, 5], [900, 8, 11, 9, 10, 4], [900, 8, 11, 9, 10.5, 4], [0, 1, 2], ["x"] * 6,
            [2700, 12, 11, 11, 11, 1]]   # low above high: skipped
    out = coinbase.parse_candles(body)
    assert [c["t"] for c in out] == [900, 1800]
    assert out[0] == {"t": 900, "o": 9.0, "h": 11.0, "l": 8.0, "c": 10.5, "v": 4.0}
    with pytest.raises(SourceError, match="NotFound"):
        coinbase.parse_candles({"message": "NotFound"})


def test_coinbase_history_pages_never_ask_for_more_than_300_rows(monkeypatch):
    asked = []

    def fake(url, params=None, **_):
        start = datetime.strptime(params["start"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        end = datetime.strptime(params["end"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        asked.append((start, end))
        t = int(end) - int(end) % 3600
        rows = []
        while t >= start:
            rows.append([t, 1, 2, 1.5, 1.6, 10])
            t -= 3600
        return rows

    monkeypatch.setattr(coinbase, "get_json", fake)
    now = 1_790_000_000.0
    out = coinbase.fetch_history("BTC-USD", 3600, 100 * 86400, now=now, sleep=lambda s: None)
    assert all((end - start) / 3600 + 1 <= 300 for start, end in asked)
    assert len(asked) == 9
    assert out[0]["t"] >= now - 100 * 86400 - 3600 and out == sorted(out, key=lambda c: c["t"])
    assert len({c["t"] for c in out}) == len(out)


def test_four_hour_candles_fold_hours_on_utc_boundaries():
    hours = [{"t": 14400 + i * 3600, "o": 10 + i, "h": 20 + i, "l": 5 - i, "c": 11 + i, "v": 1.0} for i in range(6)]
    out = coinbase.aggregate(hours, 14400)
    assert [c["t"] for c in out] == [14400, 28800]
    assert out[0] == {"t": 14400, "o": 10, "h": 23, "l": 2, "c": 14, "v": 4.0}
    assert out[1]["o"] == 14 and out[1]["c"] == 16 and out[1]["v"] == 2.0


def test_unknown_volume_stays_unknown_through_parse_and_fold():
    rows = [[7200, 1, 2, 1.5, 1.6, None], [3600, 1, 2, 1.5, 1.6, 10]]
    candles = coinbase.parse_candles(rows)
    assert [c["v"] for c in candles] == [10.0, None]
    folded = coinbase.aggregate(candles, 14400)
    assert len(folded) == 1 and folded[0]["v"] is None


def test_price_at_uses_the_bucket_open_then_the_close_before_it():
    candles = [{"t": 0, "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 1}, {"t": 900, "o": 1.6, "h": 2, "l": 1, "c": 1.7, "v": 1}]
    assert coinbase.price_at(candles, 900, 900) == 1.6
    assert coinbase.price_at(candles, 1800, 900) == 1.7
    assert coinbase.price_at(candles, 5000, 900) is None


def test_fear_greed_reads_today_and_a_week_ago():
    rows = [{"value": str(68 - i), "value_classification": "Greed", "timestamp": str(1_790_000_000 - i * 86400)}
            for i in range(8)]
    assert feeds.parse_fear_greed({"data": rows}) == {"value": 68, "label": "Greed", "week_ago": 61,
                                                      "at": 1_790_000_000.0}
    assert feeds.parse_fear_greed({"data": rows[:1]})["week_ago"] is None
    with pytest.raises(SourceError):
        feeds.parse_fear_greed({"data": []})


def test_hyperliquid_funding_is_the_hourly_rate_times_eight():
    body = [{"universe": [{"name": "BTC"}, {"name": "kPEPE"}, {"name": "OLD", "isDelisted": True}, {"name": 3}]},
            [{"funding": "0.000015", "openInterest": "20000", "markPx": "112480"},
             {"funding": "-0.00000125", "openInterest": "1000000", "oraclePx": "0.0108"},
             {"funding": "0.1"}, {}]]
    out = feeds.parse_perps(body)
    assert set(out) == {"BTC", "kPEPE"}
    assert out["BTC"]["funding_8h_pct"] == pytest.approx(0.012)
    assert out["BTC"]["open_interest_usd"] == pytest.approx(20000 * 112480)
    assert out["kPEPE"]["funding_8h_pct"] == pytest.approx(-0.001)
    assert out["kPEPE"]["open_interest_usd"] == pytest.approx(10800)
    with pytest.raises(SourceError):
        feeds.parse_perps({"universe": []})


def test_stablecoins_supply_week_change_and_daily_nets():
    day = 86400
    rows = [{"date": str(1_780_000_000 - (20 - i) * day), "totalCirculatingUSD": {"peggedUSD": 300e9 + i * 1e9}}
            for i in range(21)]
    rows.append({"date": "junk"})
    out = feeds.parse_stablecoins(rows)
    assert out["supply_usd"] == 320e9 and out["change_7d_usd"] == 7e9
    assert len(out["daily"]) == 10 and all(d["net_usd"] == 1e9 for d in out["daily"])
    with pytest.raises(SourceError):
        feeds.parse_stablecoins([rows[0]])


def test_deribit_expiries_group_open_interest_by_the_date_in_the_name():
    body = {"result": [
        {"instrument_name": "BTC-2OCT26-110000-C", "open_interest": 100.0, "underlying_price": 112000},
        {"instrument_name": "BTC-2OCT26-100000-P", "open_interest": 50.0, "underlying_price": 112000},
        {"instrument_name": "BTC-30OCT26-120000-C", "open_interest": 10.0},
        {"instrument_name": "BTC-PERPETUAL", "open_interest": 999.0},
        {"instrument_name": "BTC-31FOO26-1-C", "open_interest": 1.0},
    ]}
    out = feeds.parse_option_expiries(body)
    oct2 = datetime(2026, 10, 2, 8, tzinfo=timezone.utc).timestamp()
    assert out[0] == {"at": oct2, "open_interest": 150.0, "notional_usd": 150 * 112000}
    assert out[1]["notional_usd"] is None   # no underlying price: no notional, never a guess
    assert feeds.expiry_at("BTC-2OCT26-110000-C") == oct2
    assert feeds.expiry_at("BTC-31SEP26-1-C") is None


class _Resp:
    def __init__(self, status, body=None, bad_json=False):
        self.status_code = status
        self._body = body
        self._bad = bad_json

    def json(self):
        if self._bad:
            raise ValueError("no json")
        return self._body


@pytest.mark.parametrize(("resp", "message"), [
    (_Resp(429), "HTTP 429 (rate limited)"),
    (_Resp(451), "HTTP 451 (refused from this network)"),
    (_Resp(500), "HTTP 500"),
    (_Resp(200, bad_json=True), "answered something that is not JSON"),
])
def test_http_failures_read_as_a_short_reason(monkeypatch, resp, message):
    monkeypatch.setattr(web.requests, "get", lambda *a, **k: resp)
    with pytest.raises(SourceError, match=message.replace("(", r"\(").replace(")", r"\)")):
        web.get_json("https://example.invalid")


def test_a_timeout_says_how_long_it_waited(monkeypatch):
    def slow(*a, **k):
        raise requests.Timeout("slow")

    monkeypatch.setattr(web.requests, "get", slow)
    with pytest.raises(SourceError, match="timed out after 10 s"):
        web.get_json("https://example.invalid")


def test_num_reads_numbers_and_numeric_strings_only():
    assert web.num("1.5") == 1.5 and web.num(2) == 2.0
    assert web.num(True) is None and web.num("nan") is None and web.num("x") is None and web.num(None) is None


def test_stablecoin_daily_nets_pair_consecutive_days_even_with_a_short_history():
    rows = [{"date": str(1_780_000_000 + i * 86400), "totalCirculatingUSD": {"peggedUSD": 100e9 + i * 1e9}}
            for i in range(5)]
    out = feeds.parse_stablecoins(rows)
    assert [d["net_usd"] for d in out["daily"]] == [1e9] * 4
    assert out["change_7d_usd"] is None   # less than a week on file: unknown, not zero
