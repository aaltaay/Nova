"""Finnhub earnings calendar: lane mapping, range windows, cache, and fail-loud."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import finnhub_http
import earnings_calendar as ec

ET = ZoneInfo("America/New_York")


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload or {}

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "EARNINGS_CALENDAR_CACHE_FILE", str(tmp_path / "earnings-calendar.json"))
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    ec.reset_for_testing()
    finnhub_http.reset_for_testing()
    yield
    ec.reset_for_testing()
    finnhub_http.reset_for_testing()


def _finnhub_payload(rows):
    return {"earningsCalendar": rows}


def test_fetch_finnhub_maps_hour_to_session(monkeypatch):
    rows = [
        {"symbol": "nvda", "date": "2026-09-01", "hour": "amc", "epsEstimate": 1.12},
        {"symbol": "CPB", "date": "2026-09-01", "hour": "bmo"},
        {"symbol": "AI", "date": "2026-09-01", "hour": "dmh"},
        {"symbol": "GTLB", "date": "2026-09-01", "hour": ""},
        {"symbol": "", "date": "2026-09-01", "hour": "bmo"},  # dropped: no symbol
        {"symbol": "NOPE", "date": None, "hour": "bmo"},       # dropped: no date
    ]
    monkeypatch.setattr(ec.requests, "get", lambda *a, **k: _FakeResponse(200, _finnhub_payload(rows)))
    out = ec._fetch_finnhub("2026-09-01", "2026-10-01", "key")
    by_symbol = {r["symbol"]: r for r in out}
    assert by_symbol["NVDA"]["session"] == "amc"  # uppercased
    assert by_symbol["CPB"]["session"] == "bmo"
    assert by_symbol["AI"]["session"] == "intraday"
    assert by_symbol["GTLB"]["session"] == "intraday"
    assert len(out) == 4


def test_fetch_finnhub_http_error_returns_none(monkeypatch):
    monkeypatch.setattr(ec.requests, "get", lambda *a, **k: _FakeResponse(500))
    assert ec._fetch_finnhub("2026-09-01", "2026-10-01", "key") is None


def test_fetch_finnhub_429_honours_retry_after_and_skips(monkeypatch):
    calls = []

    def _get(*a, **k):
        calls.append(1)
        return _FakeResponse(429, headers={"Retry-After": "90"})

    monkeypatch.setattr(ec.requests, "get", _get)
    assert ec._fetch_finnhub("2026-09-01", "2026-10-01", "key") is None
    assert finnhub_http.is_blocked()
    assert ec._fetch_finnhub("2026-09-01", "2026-10-01", "key") is None
    assert calls == [1]  # second call skipped while cooldown is live


def test_fetch_finnhub_network_exception_returns_none(monkeypatch):
    def _raise(*a, **k):
        raise ConnectionError("boom")
    monkeypatch.setattr(ec.requests, "get", _raise)
    assert ec._fetch_finnhub("2026-09-01", "2026-10-01", "key") is None


def test_get_calendar_rows_missing_key_with_cache_is_token():
    ec._cache_rows = [{"symbol": "NVDA", "date": "2026-09-01", "session": "amc"}]
    ec._cache_ts = 10**12
    rows, _, error = ec.get_calendar_rows()
    assert error == "missing_key"
    assert rows[0]["symbol"] == "NVDA"


def test_get_calendar_rows_missing_key_no_cache_is_loud_error():
    rows, as_of, error = ec.get_calendar_rows()
    assert rows == []
    assert as_of == 0.0
    assert error is not None
    assert "FINNHUB_API_KEY" in error


def test_get_calendar_rows_fetches_once_then_serves_cache(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "key")
    calls = []

    def _fake_get(*a, **k):
        calls.append(1)
        return _FakeResponse(200, _finnhub_payload([
            {"symbol": "NVDA", "date": "2026-09-01", "hour": "amc"},
        ]))

    monkeypatch.setattr(ec.requests, "get", _fake_get)
    rows1, ts1, err1 = ec.get_calendar_rows()
    rows2, ts2, err2 = ec.get_calendar_rows()

    assert len(calls) == 1  # second call served from the in-memory cache (TTL not expired)
    assert err1 is None and err2 is None
    assert rows1 == rows2
    assert ts1 == ts2


def test_get_calendar_rows_429_serves_stale_with_rate_limited(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "key")
    monkeypatch.setattr(
        ec.requests, "get",
        lambda *a, **k: _FakeResponse(200, _finnhub_payload([
            {"symbol": "NVDA", "date": "2026-09-01", "hour": "amc"},
        ])),
    )
    rows1, _, err1 = ec.get_calendar_rows()
    assert err1 is None and len(rows1) == 1
    ec._cache_ts = 0.0
    monkeypatch.setattr(
        ec.requests, "get",
        lambda *a, **k: _FakeResponse(429, headers={"Retry-After": "30"}),
    )
    rows2, _, err2 = ec.get_calendar_rows()
    assert err2 == "rate_limited"
    assert rows2 == rows1


def test_get_calendar_rows_http_failure_falls_back_to_stale(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "key")
    monkeypatch.setattr(
        ec.requests, "get",
        lambda *a, **k: _FakeResponse(200, _finnhub_payload([
            {"symbol": "NVDA", "date": "2026-09-01", "hour": "amc"},
        ])),
    )
    rows1, _, err1 = ec.get_calendar_rows()
    assert err1 is None and len(rows1) == 1

    # Force expiry, then simulate Finnhub going down -- must serve the stale snapshot.
    ec._cache_ts = 0.0
    monkeypatch.setattr(ec.requests, "get", lambda *a, **k: _FakeResponse(500))
    rows2, _, err2 = ec.get_calendar_rows()
    assert err2 is None
    assert rows2 == rows1


def test_disk_snapshot_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "key")
    monkeypatch.setattr(
        ec.requests, "get",
        lambda *a, **k: _FakeResponse(200, _finnhub_payload([
            {"symbol": "NVDA", "date": "2026-09-01", "hour": "amc"},
        ])),
    )
    ec.get_calendar_rows()

    # Fresh process (no in-memory cache) must read the persisted snapshot.
    ec.reset_for_testing()
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    rows, ts, err = ec.get_calendar_rows()
    assert err == "missing_key"
    assert rows[0]["symbol"] == "NVDA"
    assert ts > 0


def test_disk_snapshot_unknown_schema_version_is_refused(tmp_path, monkeypatch):
    import json
    path = tmp_path / "earnings-calendar.json"
    monkeypatch.setattr(ec, "EARNINGS_CALENDAR_CACHE_FILE", str(path))
    path.write_text(json.dumps({"schema_version": 99, "ts": 1.0, "rows": [{"symbol": "X"}]}))
    ec.reset_for_testing()
    rows, ts, err = ec.get_calendar_rows()
    assert rows == []
    assert ts == 0.0
    assert err is not None  # no key, no usable snapshot -- loud, not a silent empty list


def test_build_earnings_view_groups_by_day_and_lane(monkeypatch):
    monkeypatch.setattr(ec, "now_et", lambda: datetime(2026, 9, 1, 8, 0, tzinfo=ET))
    ec._cache_rows = [
        {"symbol": "CPB", "date": "2026-09-01", "session": "bmo",
         "eps_estimate": 0.62, "eps_actual": None, "revenue_estimate": None,
         "revenue_actual": None, "quarter": 3, "year": 2026},
        {"symbol": "NVDA", "date": "2026-09-01", "session": "amc",
         "eps_estimate": 1.12, "eps_actual": None, "revenue_estimate": None,
         "revenue_actual": None, "quarter": 3, "year": 2026},
        {"symbol": "HRL", "date": "2026-09-02", "session": "bmo",
         "eps_estimate": 0.4, "eps_actual": None, "revenue_estimate": None,
         "revenue_actual": None, "quarter": 3, "year": 2026},
    ]
    ec._cache_ts = 1.0
    monkeypatch.setattr("earnings_enrich_hooks.warm", lambda syms: None)
    monkeypatch.setattr("earnings_logos.warm", lambda syms: None)

    view = ec.build_earnings_view("today")
    assert view["range"] == "today"
    assert len(view["days"]) == 1
    day = view["days"][0]
    assert day["label"] == "Today · Tue Sep 1"
    assert day["count"] == 2
    assert [r["symbol"] for r in day["bmo"]] == ["CPB"]
    assert [r["symbol"] for r in day["amc"]] == ["NVDA"]

    week_view = ec.build_earnings_view("week")
    assert len(week_view["days"]) == 2
    assert week_view["days"][1]["label"] == "Tomorrow · Wed Sep 2"


def test_build_earnings_view_decorates_from_fundamentals_cache(monkeypatch):
    from fundamentals import _fundamentals_cache

    monkeypatch.setattr(ec, "now_et", lambda: datetime(2026, 9, 1, 8, 0, tzinfo=ET))
    ec._cache_rows = [
        {"symbol": "NVDA", "date": "2026-09-01", "session": "amc",
         "eps_estimate": 1.12, "eps_actual": None, "revenue_estimate": None,
         "revenue_actual": None, "quarter": 3, "year": 2026},
    ]
    ec._cache_ts = 1.0
    monkeypatch.setitem(_fundamentals_cache, "NVDA", {
        "company_name": "NVIDIA", "sector": "Technology", "market_cap": 3_100_000_000_000,
    })
    monkeypatch.setattr("earnings_enrich_hooks.warm", lambda syms: None)
    monkeypatch.setattr("earnings_logos.warm", lambda syms: None)
    monkeypatch.setattr("earnings_logos.get_cached_logo_url", lambda s: "https://static.example/nvda.png" if s == "NVDA" else None)

    view = ec.build_earnings_view("today")
    row = view["days"][0]["amc"][0]
    assert row["company_name"] == "NVIDIA"
    assert row["sector"] == "Technology"
    assert row["market_cap"] == 3_100_000_000_000
    assert row["logo_url"] == "https://static.example/nvda.png"


def test_build_earnings_view_warms_todays_symbols_only(monkeypatch):
    monkeypatch.setattr(ec, "now_et", lambda: datetime(2026, 9, 1, 8, 0, tzinfo=ET))
    ec._cache_rows = [
        {"symbol": "NVDA", "date": "2026-09-01", "session": "amc",
         "eps_estimate": None, "eps_actual": None, "revenue_estimate": None,
         "revenue_actual": None, "quarter": 3, "year": 2026},
        {"symbol": "HRL", "date": "2026-09-02", "session": "bmo",
         "eps_estimate": None, "eps_actual": None, "revenue_estimate": None,
         "revenue_actual": None, "quarter": 3, "year": 2026},
    ]
    ec._cache_ts = 1.0
    warmed = []
    logo_warmed = []
    monkeypatch.setattr("earnings_enrich_hooks.warm", lambda syms: warmed.append(list(syms)))
    monkeypatch.setattr("earnings_logos.warm", lambda syms: logo_warmed.append(sorted(syms)))

    ec.build_earnings_view("week")
    assert warmed == [["NVDA"]]
    assert logo_warmed == [["HRL", "NVDA"]]
