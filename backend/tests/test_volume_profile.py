"""Volume profile on the 5-minute chart (ADR 058): the profile's method, the service's sources, the route."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ibkr.historical_service import HistoricalShed
from volume_profile import routes, service
from volume_profile.profile import Bar, build

ET = ZoneInfo("America/New_York")
TODAY = date(2026, 9, 30)
YESTERDAY = date(2026, 9, 29)


def at(day: date, h: int, m: int) -> float:
    return datetime.combine(day, time(h, m), tzinfo=ET).timestamp()


def flat(t: float, price: float, v: float) -> Bar:
    return Bar(t=t, o=price, h=price, l=price, c=price, v=v)


def session_bars(day: date, n: int = 390) -> list[Bar]:
    start = at(day, 9, 30)
    return [Bar(t=start + i * 60, o=10 + i * 0.01, h=10.02 + i * 0.01, l=9.99 + i * 0.01, c=10.01 + i * 0.01, v=100)
            for i in range(n)]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    service.reset_for_testing()
    monkeypatch.setattr("sim.mode.is_replay_desk", lambda: False)
    yield
    service.reset_for_testing()


def test_build_finds_the_poc_and_grows_the_value_area_toward_the_heavier_side():
    # One bar spread over 100-101 puts 1 share in each of 10 rows; flat bars stack the rest (the desk's own test).
    p = build([Bar(t=0, o=100, h=101, l=100, c=101, v=10), flat(60, 100.45, 50), flat(120, 100.55, 30),
               flat(180, 100.35, 20), flat(240, 100.75, 5)], rows=10)
    assert p is not None
    assert [round(u + d) for u, d in zip(p.up, p.down, strict=True)] == [1, 1, 1, 21, 51, 31, 1, 6, 1, 1]
    assert p.poc_row == 4 and p.poc == pytest.approx(100.45)
    # 51 held; the two rows above (32) beat the two below (22), and 83 of 115 is past 70%.
    assert (p.val_row, p.vah_row) == (4, 6)
    assert p.val == pytest.approx(100.4) and p.vah == pytest.approx(100.7)


def test_build_is_none_without_volume_and_a_poc_tie_goes_to_the_middle():
    assert build([]) is None
    assert build([flat(0, 10, 0)]) is None
    tie = build([flat(0, 10.05, 5), flat(60, 10.45, 5), flat(120, 10.95, 5), Bar(180, 10, 11, 10, 10, 0.0001)], rows=10)
    assert tie is not None and tie.poc_row == 4


def test_build_splits_volume_on_up_and_down_bars():
    p = build([Bar(0, 10, 10, 10, 10, 70), Bar(60, 10.2, 10.2, 10, 10, 30)], rows=2)
    assert p is not None
    assert p.up[0] == pytest.approx(70)
    assert sum(p.down) == pytest.approx(30)


def test_today_reads_the_chart_store_from_the_anchor_and_never_ibkr(monkeypatch):
    seen = {}

    def stored(symbol, start, end):
        seen.update(symbol=symbol, start=start, end=end)
        return session_bars(TODAY, 60)

    async def no_ibkr(*_a):
        raise AssertionError("today's profile never asks IBKR")

    monkeypatch.setattr(service, "_stored_minutes", stored)
    monkeypatch.setattr(service, "_ibkr_minutes", no_ibkr)
    out = asyncio.run(service.profile("AAPL", "today", TODAY, None))
    assert seen == {"symbol": "AAPL", "start": at(TODAY, 9, 30), "end": at(TODAY, 20, 0)}
    assert out["kind"] == "today" and out["day"] == "2026-09-30" and out["source"] == "bars_1m"
    # 62 cents of range: a row is never thinner than a cent, so 62 rows, not 400.
    assert out["bars"] == 60 and len(out["histogram"]) == 62 and out["row_size"] == pytest.approx(0.01)
    assert out["error"] is None and out["val"] <= out["poc"] <= out["vah"]


def test_both_profiles_read_the_real_chart_store(tmp_path, monkeypatch):
    import archive.db as archive_db
    import bars_store
    from ibkr.historical_derive import unix_to_iso

    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()

    def minutes(day: date, h: int, m: int, n: int, price: float) -> list[dict]:
        start = at(day, h, m)
        return [{"t": unix_to_iso(start + i * 60), "o": price, "h": price + 0.05, "l": price - 0.05,
                 "c": price + 0.01, "v": 1000} for i in range(n)]

    # Yesterday's whole session, an 08:00 premarket stretch and 120 minutes from 09:30 today.
    bars = minutes(YESTERDAY, 9, 30, 390, 50.0) + minutes(TODAY, 8, 0, 30, 49.0) + minutes(TODAY, 9, 30, 120, 51.0)
    bars_store.write_payload({"symbol": "AAPL", "timeframe": "1Min", "bars": bars})

    async def no_ibkr(*_a):
        raise AssertionError("the store held both")

    monkeypatch.setattr(service, "_ibkr_minutes", no_ibkr)
    today = asyncio.run(service.profile("AAPL", "today", TODAY, None))
    assert today["bars"] == 120 and today["low"] == pytest.approx(50.95)       # the premarket stretch is before 09:30
    early = asyncio.run(service.profile("AAPL", "today", TODAY, at(TODAY, 8, 0)))
    assert early["bars"] == 150 and early["low"] == pytest.approx(48.95)
    yesterday = asyncio.run(service.profile("AAPL", "yesterday", TODAY, None))
    assert yesterday["bars"] == 390 and yesterday["poc"] == pytest.approx(50.0, abs=0.02)


def test_today_with_no_bars_is_a_stated_empty(monkeypatch):
    monkeypatch.setattr(service, "_stored_minutes", lambda *_a: [])
    out = asyncio.run(service.profile("AAPL", "today", TODAY, at(TODAY, 10, 45)))
    assert out["histogram"] == [] and out["poc"] is None and out["error"]
    assert out["from"] == at(TODAY, 10, 45)


def test_an_anchor_outside_the_day_is_refused():
    with pytest.raises(service.BadRequest):
        asyncio.run(service.profile("AAPL", "today", TODAY, at(TODAY, 3, 0)))


def test_yesterday_comes_from_the_store_when_it_holds_the_session(monkeypatch):
    calls = []
    monkeypatch.setattr(service, "_stored_minutes", lambda s, a, b: calls.append((a, b)) or session_bars(YESTERDAY))

    async def no_ibkr(*_a):
        raise AssertionError("the store held the session")

    monkeypatch.setattr(service, "_ibkr_minutes", no_ibkr)
    out = asyncio.run(service.profile("AAPL", "yesterday", TODAY, None))
    assert out["day"] == "2026-09-29" and out["bars"] == 390
    assert calls == [(at(YESTERDAY, 9, 30), at(YESTERDAY, 16, 0))]
    again = asyncio.run(service.profile("AAPL", "yesterday", TODAY, None))
    assert again is out and len(calls) == 1       # kept in memory


def test_yesterday_of_a_monday_is_the_friday_before(monkeypatch):
    friday = date(2026, 10, 16)
    monkeypatch.setattr(service, "_stored_minutes", lambda *_a: session_bars(friday))
    out = asyncio.run(service.profile("AAPL", "yesterday", date(2026, 10, 19), None))
    assert out["day"] == "2026-10-16" and out["from"] == at(friday, 9, 30)


def test_yesterday_asks_ibkr_once_when_the_store_lacks_it(monkeypatch):
    monkeypatch.setattr(service, "_stored_minutes", lambda *_a: session_bars(YESTERDAY, 12))
    asked = []

    async def ibkr(symbol, day):
        asked.append((symbol, day))
        await asyncio.sleep(0.01)
        return session_bars(YESTERDAY)

    monkeypatch.setattr(service, "_ibkr_minutes", ibkr)

    async def two_windows():
        return await asyncio.gather(service.profile("AAPL", "yesterday", TODAY, None),
                                    service.profile("AAPL", "yesterday", TODAY, None))

    a, b = asyncio.run(two_windows())
    assert asked == [("AAPL", YESTERDAY)]
    assert a["bars"] == b["bars"] == 390 and not a["filling"]


def test_yesterday_waits_while_the_budget_says_not_now(monkeypatch):
    monkeypatch.setattr(service, "_stored_minutes", lambda *_a: [])

    async def shed(*_a):
        raise HistoricalShed("an open chart is loading")

    monkeypatch.setattr(service, "_ibkr_minutes", shed)
    out = asyncio.run(service.profile("AAPL", "yesterday", TODAY, None))
    assert out["filling"] is True and out["histogram"] == []
    assert "an open chart is loading" in out["error"]
    assert ("AAPL", "2026-09-29") not in service._cache   # asked again next time


def _replay(monkeypatch, *, massive_symbol: str | None, bars: list[dict] | None = None, source: str = "massive"):
    """A Sim replay desk: its chart's 1-minute bars, and which stock's Massive window is loaded."""
    from ibkr.historical_derive import unix_to_iso

    monkeypatch.setattr("sim.mode.is_replay_desk", lambda: True)
    monkeypatch.setattr(service, "_stored_minutes", lambda *_a: pytest.fail("today on a replay never reads live bars"))
    rows = bars if bars is not None else [
        {"t": unix_to_iso(b.t), "o": b.o, "h": b.h, "l": b.l, "c": b.c, "v": b.v} for b in session_bars(TODAY, 90)]
    asked = []

    def replay_bars(symbol, timeframe, limit):
        asked.append((symbol, timeframe))
        return {"symbol": symbol, "timeframe": timeframe, "bars": rows, "source": source}

    monkeypatch.setattr("sim.chart_replay.fetch_replay_bars", replay_bars)
    spec = {"symbol": massive_symbol, "source": "massive"} if massive_symbol else None
    monkeypatch.setattr("sim.history_playback.status", lambda: spec)
    monkeypatch.setattr("sim.history_playback.is_massive", lambda s: bool(s))
    return asked


def test_today_on_a_replay_is_the_replays_own_bars(monkeypatch):
    asked = _replay(monkeypatch, massive_symbol="AAPL")
    out = asyncio.run(service.profile("AAPL", "today", TODAY, at(TODAY, 10, 0)))
    assert asked == [("AAPL", "1Min")]
    assert out["feed"] == "massive" and out["bars"] == 60      # 10:00 to the playhead's last bar (10:59)
    assert out["from"] == at(TODAY, 10, 0)


def test_yesterday_on_a_massive_replay_reads_the_same_massive_files(monkeypatch):
    _replay(monkeypatch, massive_symbol="AAPL")
    read = []

    async def massive(symbol, day):
        read.append((symbol, day))
        return session_bars(day)

    monkeypatch.setattr(service, "_massive_minutes", massive)
    monkeypatch.setattr(service, "_ibkr_minutes", lambda *_a: pytest.fail("a Massive replay never asks IBKR"))
    out = asyncio.run(service.profile("AAPL", "yesterday", TODAY, None))
    assert read == [("AAPL", YESTERDAY)]
    assert out["feed"] == "massive" and out["bars"] == 390 and out["day"] == "2026-09-29"
    assert asyncio.run(service.profile("AAPL", "yesterday", TODAY, None)) is out     # kept in memory


def test_a_slow_massive_read_says_filling_then_answers(monkeypatch):
    _replay(monkeypatch, massive_symbol="AAPL")
    monkeypatch.setattr(service, "VP_MASSIVE_WAIT_SEC", 0.01)
    started = []

    async def slow(symbol, day):
        started.append(day)
        await asyncio.sleep(0.05)
        return session_bars(day)

    monkeypatch.setattr(service, "_massive_minutes", slow)

    async def ask_twice():
        first = await service.profile("AAPL", "yesterday", TODAY, None)
        await asyncio.sleep(0.1)
        return first, await service.profile("AAPL", "yesterday", TODAY, None)

    first, later = asyncio.run(ask_twice())
    assert first["filling"] is True and "Massive files" in first["error"] and first["histogram"] == []
    assert later["bars"] == 390 and started == [YESTERDAY]


def test_a_missing_massive_day_is_a_stated_empty(monkeypatch):
    _replay(monkeypatch, massive_symbol="AAPL")

    async def none(*_a):
        return None

    monkeypatch.setattr(service, "_massive_minutes", none)
    out = asyncio.run(service.profile("AAPL", "yesterday", TODAY, None))
    assert out["filling"] is False and "no 1-minute bars for 2026-09-29" in out["error"]


def test_yesterday_on_another_replay_is_ibkrs_as_live(monkeypatch):
    _replay(monkeypatch, massive_symbol="MSFT", source="ibkr")
    monkeypatch.setattr(service, "_stored_minutes", lambda *_a: session_bars(YESTERDAY))
    monkeypatch.setattr(service, "_massive_minutes", lambda *_a: pytest.fail("AAPL is not the Massive window"))
    out = asyncio.run(service.profile("AAPL", "yesterday", TODAY, None))
    assert out["feed"] == "ibkr" and out["bars"] == 390


def test_massive_minutes_reads_the_days_minute_file(tmp_path, monkeypatch):
    import gzip

    from volume_profile.massive_minutes import session_minutes

    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    path = tmp_path / "minute_aggs_v1" / "2026" / "09" / "2026-09-29.csv.gz"
    path.parent.mkdir(parents=True)
    rows = [("AAPL", 9, 29, 330.0), ("AAPL", 9, 30, 331.0), ("AAPL", 15, 59, 332.0), ("AAPL", 16, 0, 333.0),
            ("MSFT", 9, 30, 400.0)]
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write("ticker,volume,open,close,high,low,window_start,transactions\n")
        for ticker, h, m, price in rows:
            fh.write(f"{ticker},500,{price},{price},{price + 0.1},{price - 0.1},{int(at(YESTERDAY, h, m)) * 10**9},3\n")
    bars = session_minutes("aapl", YESTERDAY)
    assert [b.t for b in bars] == [at(YESTERDAY, 9, 30), at(YESTERDAY, 15, 59)]     # 09:30-16:00 only, AAPL only
    assert bars[0].c == 331.0 and bars[0].v == 500
    assert session_minutes("AAPL", TODAY) is None                                      # that day's file is not on disk


class _FakeBar:
    def __init__(self, t: float):
        from datetime import timezone

        self.date = datetime.fromtimestamp(t, timezone.utc)
        self.open, self.high, self.low, self.close, self.volume = 10.0, 10.1, 9.9, 10.05, 500.0


class _FakeIb:
    def __init__(self):
        self.calls: list[dict] = []

    async def qualifyContractsAsync(self, contract):
        return [contract]

    async def reqHistoricalDataAsync(self, contract, **kw):
        self.calls.append(kw)
        return [_FakeBar(at(YESTERDAY, 9, 30) + i * 60) for i in range(390)]


def test_the_ibkr_request_is_the_regular_session_in_the_one_budget(monkeypatch):
    from datetime import timezone

    from ibkr import historical_service
    from volume_profile import ibkr_minutes

    historical_service.reset_for_testing()
    ib = _FakeIb()
    monkeypatch.setattr("ibkr.client.get_ib", lambda: ib)
    bars = asyncio.run(ibkr_minutes.session_minutes("aapl", YESTERDAY, timeout=5))
    assert len(bars) == 390 and bars[0].t == at(YESTERDAY, 9, 30)
    (kw,) = ib.calls
    assert kw["endDateTime"] == datetime.combine(YESTERDAY, time(16, 0), tzinfo=ET).astimezone(timezone.utc)
    assert (kw["durationStr"], kw["barSizeSetting"], kw["whatToShow"], kw["useRTH"]) == ("23400 S", "1 min", "TRADES", True)
    assert historical_service.pacing_snapshot()["window_used"] == 1
    # The same request again inside IBKR's identical-request window waits; so does any while an open chart loads.
    with pytest.raises(HistoricalShed):
        asyncio.run(ibkr_minutes.session_minutes("AAPL", YESTERDAY, timeout=5))
    historical_service.reset_for_testing()
    monkeypatch.setattr(historical_service, "_open_chart_depth", 1)
    with pytest.raises(HistoricalShed, match="open chart"):
        asyncio.run(ibkr_minutes.session_minutes("AAPL", YESTERDAY, timeout=5))
    assert len(ib.calls) == 1
    historical_service.reset_for_testing()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def test_route_answers_the_schema_and_refuses_bad_queries(monkeypatch):
    monkeypatch.setattr(service, "_stored_minutes", lambda *_a: session_bars(TODAY, 30))
    client = _client()
    ok = client.get("/api/volume-profile/aapl", params={"kind": "today", "day": "2026-09-30"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["schema_version"] == 1 and body["enabled"] is True and body["symbol"] == "AAPL"
    assert len(body["histogram"][0]) == 3
    assert client.get("/api/volume-profile/AAPL", params={"kind": "week"}).status_code == 422
    assert client.get("/api/volume-profile/AAPL", params={"kind": "today", "day": "30/09"}).status_code == 422
    assert client.get("/api/volume-profile/%24%24", params={"kind": "today"}).status_code == 422
    early = {"kind": "today", "day": "2026-09-30", "anchor": at(TODAY, 2, 0)}
    assert client.get("/api/volume-profile/AAPL", params=early).status_code == 422
