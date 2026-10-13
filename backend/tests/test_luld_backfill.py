"""A stock Nova starts following mid-session: its band at once from IBKR's trades before its first print
(ADR 047 amendment, 2026-10-13; ``luld/backfill.py``, ``ibkr/historical_trades.py``)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from luld import backfill, live

ET = ZoneInfo("America/New_York")
DAY = "2026-10-13"


def t(hms: str) -> float:
    return datetime.fromisoformat(f"{DAY}T{hms}").replace(tzinfo=ET).timestamp()


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("NOVA_LULD", "1")
    live.reset_for_tests()
    monkeypatch.setattr(live, "_ensure_thread", lambda: None)
    monkeypatch.setattr(live, "_halted", lambda symbols, now: {})
    monkeypatch.setattr(live, "_line_held", lambda symbol: True)
    monkeypatch.setattr(live, "_feed_gaps", lambda now: [])
    monkeypatch.setattr(live, "_board_close", {})
    monkeypatch.setattr("sim.prior_close.previous_close", lambda symbol, day: 3.5)
    monkeypatch.setattr("fundamentals.peek_cached", lambda symbol: {"market_cap": 100e6})
    monkeypatch.delenv("NOVA_LULD_BACKFILL", raising=False)
    yield
    live.reset_for_tests()


@pytest.fixture
def ib_tasks(monkeypatch):
    """The IB loop's tasks, held: a test runs each when it chooses (the answer then sits on the worker's queue)."""
    spawned: list[tuple[str, object]] = []
    monkeypatch.setattr("ibkr.loop_supervisor.spawn_ib", lambda name, factory: spawned.append((name, factory)))
    return spawned


def answer(monkeypatch, result=None, exc: Exception | None = None) -> list[dict]:
    """What ``recent_trades`` answers; the calls it got."""
    calls: list[dict] = []

    async def fake(symbol, end, back_sec, *, max_pages, headroom, timeout):
        calls.append({"symbol": symbol, "end": end, "back_sec": back_sec, "max_pages": max_pages})
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr("ibkr.historical_trades.recent_trades", fake)
    return calls


def drain() -> None:
    while not live._q.empty():
        live.process(live._q.get_nowait())


def run(spawned, at: str = "09:43:08", monkeypatch=None) -> None:
    """Run the IB loop's tasks, their answers arriving at ``at``."""
    backfill._clock = lambda: t(at)
    try:
        while spawned:
            _name, factory = spawned.pop(0)
            asyncio.run(factory())
    finally:
        backfill._clock = __import__("time").time
    drain()


def first_print(hms: str = "09:43:06.4", price: float = 4.20, exchange_ts: float | None = None, cond: str = "") -> None:
    live.enqueue_print({"symbol": "FLYE", "receive_ts": t(hms), "price": price, "sets_price": True, "conditions": cond,
                        "exchange": "NASDAQ", "exchange_ts": t("09:43:06") if exchange_ts is None else exchange_ts})
    drain()


def trades(n: int = 29, price: float = 4.0, end: str = "09:43:06") -> list[dict]:
    return [{"ts": t(end) - 10.0 * (n - k), "price": price, "exchange": "NASDAQ", "conditions": "",
             "sets_price": True} for k in range(n)]


def test_flye_a_stock_opened_mid_session_shows_an_approximate_band_within_seconds(monkeypatch, ib_tasks):
    odd_lot = {"ts": t("09:43:00"), "price": 9.99, "exchange": "NASDAQ", "conditions": "I", "sets_price": False}
    calls = answer(monkeypatch, {"trades": [*trades(), odd_lot], "since": t("09:33:06"), "complete": True, "pages": 1})
    first_print()
    assert [name for name, _ in ib_tasks] == ["luld.backfill.FLYE"]
    v = live.view("FLYE", t("09:43:07"))
    assert v["state"] == "warming" and v["backfill"]["state"] == "asking"
    assert "reading IBKR's trades of the 10 minutes before" in v["reason"]
    run(ib_tasks)
    # IBKR's second of the first print: its trades from there on Nova heard live.
    assert calls == [{"symbol": "FLYE", "end": t("09:43:06"), "back_sec": 600.0, "max_pages": 4}]
    v = live.view("FLYE", t("09:43:08"))
    assert (v["state"], v["exact"], v["reference_source"]) == ("bands", False, "backfill")
    # Seeded five minutes into IBKR's ten (09:38:16, the first trade after 09:38:06); the 9.99 odd lot never counts
    # and the 4.20 Nova heard moves the mean under 1%.
    assert (v["reference"], v["reference_since"]) == (4.0, t("09:38:16"))
    assert v["reference_words"] == "IBKR's trades of the 10 minutes before Nova began watching, under the published rules"
    assert v["spread"] is not None and v["text"].startswith("LULD ≈")
    assert {k: v["backfill"][k] for k in ("state", "trades", "pages", "complete")} == \
        {"state": "seeded", "trades": 29, "pages": 1, "complete": True}
    assert v["watching_since"] == t("09:43:06.4")
    body = live.trail("FLYE", t("09:43:08"))
    assert len(body["steps"]) == 1 and body["steps"][0]["exact"] is False
    assert not live._trackers["FLYE"].keeps_journal                        # the rebuilt one keeps no inputs


def test_premarket_or_an_opening_print_never_asks(monkeypatch, ib_tasks):
    answer(monkeypatch, {"trades": [], "since": 0, "complete": True, "pages": 0})
    first_print("09:20:00", exchange_ts=t("09:20:00"))
    assert ib_tasks == []                                                   # it will see the open
    live.reset_for_tests()
    first_print("09:30:00.2", cond="O X", exchange_ts=t("09:30:00"))
    assert ib_tasks == [] and live.view("FLYE", t("09:30:01"))["backfill"] is None
    assert not live._trackers["FLYE"].keeps_journal                        # nothing will rebuild it
    live.reset_for_tests()
    monkeypatch.setenv("NOVA_LULD_BACKFILL", "0")
    first_print()
    assert ib_tasks == []


def test_shed_by_an_open_chart_it_asks_again_two_seconds_later(monkeypatch, ib_tasks):
    from ibkr.historical_service import HistoricalShed

    answer(monkeypatch, exc=HistoricalShed("an open chart is loading"))
    first_print()
    run(ib_tasks, "09:43:07")
    live.tick(t("09:43:07"))
    assert ib_tasks == []
    answer(monkeypatch, {"trades": trades(), "since": t("09:33:06"), "complete": True, "pages": 1})
    live.tick(t("09:43:09"))
    run(ib_tasks, "09:43:09.5")
    assert live.view("FLYE", t("09:43:10"))["reference_source"] == "backfill"


def test_three_failures_give_up_and_the_band_waits_for_novas_own_tape(monkeypatch, ib_tasks):
    answer(monkeypatch, exc=TimeoutError("no answer"))
    first_print()
    run(ib_tasks, "09:43:07")
    for at in ("09:43:22", "09:43:38"):
        live.tick(t(at))
        run(ib_tasks, at + ".5")
    live.tick(t("09:44:00"))
    assert ib_tasks == []
    v = live.view("FLYE", t("09:44:01"))
    assert v["backfill"]["state"] == "failed" and v["state"] == "warming"
    assert not live._trackers["FLYE"].keeps_journal
    assert "it needs 5 minutes of trades first (until 09:48:06 ET)" in v["reason"]
    assert "TimeoutError: no answer" in v["reason"]


def test_a_stock_banded_by_its_own_tape_first_needs_no_backfill(monkeypatch, ib_tasks):
    answer(monkeypatch, {"trades": trades(), "since": t("09:33:06"), "complete": True, "pages": 1})
    first_print()
    live.enqueue_print({"symbol": "FLYE", "receive_ts": t("09:43:07"), "price": 4.5, "sets_price": True,
                        "conditions": "5", "exchange": "NASDAQ", "exchange_ts": t("09:43:07")})   # a reopening print
    drain()
    run(ib_tasks, "09:43:07.5")
    v = live.view("FLYE", t("09:43:08"))
    assert (v["reference_source"], v["exact"]) == ("reopen", True)
    assert v["backfill"]["state"] == "not_needed" and "own tape" in v["backfill"]["reason"]
    assert not live._trackers["FLYE"].keeps_journal


def test_an_answer_for_a_forgotten_tracker_never_seeds_the_next(monkeypatch, ib_tasks):
    answer(monkeypatch, {"trades": trades(price=9.0), "since": t("09:33:06"), "complete": True, "pages": 1})
    first_print()
    old = ib_tasks.pop()
    live._forget("FLYE")
    first_print("10:20:00", exchange_ts=t("10:20:00"))
    run([old], "10:20:00.5")                                                # the old answer lands now
    drain()
    v = live.view("FLYE", t("10:20:01"))
    assert v["reference"] is None and v["backfill"]["state"] == "asking"


def test_an_answer_that_never_comes_frees_the_request_in_flight(monkeypatch, ib_tasks):
    answer(monkeypatch, {"trades": trades(), "since": t("09:33:06"), "complete": True, "pages": 1})
    first_print()
    ib_tasks.clear()                                                        # its queue item is lost
    live.tick(t("09:44:40"))
    assert backfill._in_flight == set()
    live.tick(t("09:45:00"))
    run(ib_tasks, "09:45:00.5")
    assert live.view("FLYE", t("09:45:01"))["reference_source"] == "backfill"


def test_an_incomplete_backfill_says_how_far_back_it_reaches(monkeypatch, ib_tasks):
    answer(monkeypatch, {"trades": trades(n=20, end="09:43:06")[-20:], "since": t("09:39:46"), "complete": False,
                         "pages": 5})
    first_print()
    run(ib_tasks)
    v = live.view("FLYE", t("09:43:08"))
    assert v["backfill"]["complete"] is False
    assert v["reference_words"].endswith("(its 20 trades reach back only to 09:39:46 ET)")


# -- the paced read: ibkr/historical_trades.py -------------------------------------------------------------------------

def _tick(ts: float, price: float = 4.0, cond: str = "", unreported: bool = False):
    return SimpleNamespace(time=datetime.fromtimestamp(ts, timezone.utc), price=price, size=100, exchange="NASDAQ",
                           specialConditions=cond, tickAttribLast=SimpleNamespace(unreported=unreported, pastLimit=False))


class FakeIB:
    """IBKR's last ``PAGE_TICKS`` trades before each page's end, from a list of tick times; 1-minute bars."""

    def __init__(self, times: list[float], page: int = 1000, bars: list | None = None):
        self.times = sorted(times)
        self.page = page
        self.ends: list[float] = []
        self.bars = bars or []
        self.bar_asks: list[dict] = []

    async def reqHistoricalDataAsync(self, contract, **kw):
        self.bar_asks.append(kw)
        return self.bars

    async def qualifyContractsAsync(self, contract):
        return [contract]

    async def reqHistoricalTicksAsync(self, contract, start, end, n, what, use_rth, ignore_size):
        end_ts = end.timestamp()
        self.ends.append(end_ts)
        upto = [x for x in self.times if x <= end_ts]
        return [_tick(x) for x in upto[-self.page:]]


@pytest.fixture
def ib(monkeypatch):
    from ibkr import historical_service

    historical_service.reset_for_testing()
    holder: dict[str, FakeIB] = {}
    monkeypatch.setattr("ibkr.client.get_ib", lambda: holder.get("ib"))
    yield holder
    historical_service.reset_for_testing()


def read(end: float, back: float = 300.0, **kw):
    from ibkr import historical_trades

    opts = {"max_pages": 5, "headroom": 20, "timeout": 5.0, **kw}
    return asyncio.run(historical_trades.recent_trades("FLYE", end, back, **opts))


def test_one_page_covers_a_quiet_stock_and_the_first_prints_second_is_left_out(ib):
    end = t("09:43:06")
    ib["ib"] = FakeIB([end - 400, end - 200, end - 100, end - 1, end, end + 0.5])
    got = read(end + 0.7)                                                   # IBKR's second is a whole one
    assert [r["ts"] for r in got["trades"]] == [end - 200, end - 100, end - 1]
    assert (got["complete"], got["since"], got["pages"]) == (True, end - 300, 1)


def test_a_busy_stock_pages_back_until_the_five_minutes_are_covered(ib):
    end = t("09:43:06")
    times = [end - 300 - 5 + k * 0.1 for k in range(3050)]                  # ten trades a second
    ib["ib"] = FakeIB(times)
    got = read(end)
    assert got["pages"] == 4 and got["complete"] is True
    assert len(got["trades"]) == len([x for x in times if end - 300 < x < end])
    stamps = [r["ts"] for r in got["trades"]]
    assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps)     # no trade counted twice


def test_out_of_pages_it_returns_what_it_read_marked_incomplete(ib):
    end = t("09:43:06")
    times = [end - 300 + k * 0.05 for k in range(6000)]
    ib["ib"] = FakeIB(times)
    got = read(end, max_pages=2)
    assert got["pages"] == 2 and got["complete"] is False
    assert got["since"] == got["trades"][0]["ts"] > end - 300


def test_odd_lots_and_unreported_prints_are_marked_as_not_setting_a_price(ib, monkeypatch):
    end = t("09:43:06")

    class Odd(FakeIB):
        async def reqHistoricalTicksAsync(self, *a):
            return [_tick(end - 3, cond="I"), _tick(end - 2, unreported=True), _tick(end - 1)]

    ib["ib"] = Odd([])
    got = read(end)
    assert [r["sets_price"] for r in got["trades"]] == [False, False, True]


def test_an_open_chart_or_a_spent_budget_sheds_the_first_page(ib, monkeypatch):
    from ibkr import historical_service
    from ibkr.historical_service import HistoricalShed

    end = t("09:43:06")
    ib["ib"] = FakeIB([end - 10])
    monkeypatch.setattr(historical_service, "_open_chart_depth", 1)
    with pytest.raises(HistoricalShed, match="open chart"):
        read(end)
    monkeypatch.setattr(historical_service, "_open_chart_depth", 0)
    pacing, _slots = historical_service.budget()
    for k in range(40):
        pacing.record(f"S{k}", "1Min", "1 D")
    with pytest.raises(HistoricalShed, match="fewer than 21"):
        read(end)


def test_every_page_spends_the_shared_pacing_budget_and_stops_before_the_headroom(ib):
    from ibkr import historical_service

    end = t("09:43:06")
    ib["ib"] = FakeIB([end - 300 + k * 0.05 for k in range(6000)])
    pacing, _slots = historical_service.budget()
    for k in range(37):
        pacing.record(f"S{k}", "1Min", "1 D")
    got = read(end)
    assert got["pages"] == 3 and got["complete"] is False                  # 40 used: a fourth would leave 19
    assert pacing.snapshot()["window_used"] == 40


def _bar(hms: str, average: float, count: int):
    return SimpleNamespace(date=datetime.fromisoformat(f"{DAY}T{hms}").replace(tzinfo=ET), average=average,
                           barCount=count)


def test_pages_short_of_ten_minutes_read_the_missed_minutes_from_1_minute_bars(ib):
    from ibkr import historical_service

    end = t("09:43:06")
    times = [end - 300 + k * 0.05 for k in range(6000)]                    # 20 a second: four pages reach 200 s
    bars = [_bar("09:32:00", 3.9, 50), _bar("09:33:00", 4.0, 60), _bar("09:40:00", 4.2, 900)]
    ib["ib"] = FakeIB(times, bars=bars)
    got = read(end, back=600.0, max_pages=4)
    assert got["complete"] is False and got["pages"] == 4
    assert got["minutes"] == [{"ts": t("09:33:00"), "average": 4.0, "count": 60}]   # only bars before ``since``
    assert got["minutes_note"] is None and ib["ib"].bar_asks[0]["barSizeSetting"] == "1 min"
    assert historical_service.budget()[0].snapshot()["window_used"] == 5   # IBKR's most for one stock in 2 s


def test_no_bars_when_the_budget_is_spent_and_the_trades_stand(ib):
    from ibkr import historical_service

    end = t("09:43:06")
    ib["ib"] = FakeIB([end - 300 + k * 0.05 for k in range(6000)], bars=[_bar("09:33:00", 4.0, 60)])
    pacing, _slots = historical_service.budget()
    for k in range(36):
        pacing.record(f"S{k}", "1Min", "1 D")
    got = read(end, back=600.0, max_pages=4)
    assert got["pages"] == 4 and got["minutes"] == [] and "historical requests left" in got["minutes_note"]


def test_minute_rows_turn_bars_into_trades_for_the_minutes_the_pages_missed():
    start, since, end = t("09:33:06"), t("09:38:30"), t("09:43:06")
    bars = [{"ts": t("09:33:00"), "average": 4.0, "count": 60},      # 54 s of it after ``start``
            {"ts": t("09:35:00"), "average": 4.1, "count": 10},
            {"ts": t("09:38:00"), "average": 4.2, "count": 60}]      # 30 s of it before ``since``
    rows = backfill.minute_rows(bars, start, since, end)
    assert [(r[0], r[1]) for r in rows[::1]].count((t("09:33:33"), 4.0)) == 54
    assert rows.count((t("09:35:30"), 4.1, True, "", "")) == 10
    assert rows.count((t("09:38:15"), 4.2, True, "", "")) == 30 and len(rows) == 94
    # The bar that ends at the first print's second gives only its share up to there.
    assert backfill.minute_rows([{"ts": t("09:43:00"), "average": 4.3, "count": 12}], t("09:33:06"), t("09:43:03"),
                                t("09:43:06")) == [(t("09:43:01.5"), 4.3, True, "", "")] * 6


def test_a_busy_stock_is_rebuilt_on_its_trades_and_the_bars_before_them(monkeypatch, ib_tasks):
    recent = [{"ts": t("09:42:00") + k * 0.05, "price": 4.0, "exchange": "NASDAQ", "conditions": "",
               "sets_price": True} for k in range(1000)]
    minutes = [{"ts": t("09:33:00") + 60 * k, "average": 4.0, "count": 600} for k in range(9)]
    answer(monkeypatch, {"trades": recent, "since": t("09:42:00"), "complete": False, "pages": 5,
                         "minutes": minutes, "minutes_note": None})
    first_print()
    run(ib_tasks)
    v = live.view("FLYE", t("09:43:08"))
    assert (v["reference_source"], v["reference"]) == ("backfill", 4.0)
    assert v["reference_since"] < t("09:42:00")                            # seeded five minutes into the ten
    assert v["backfill"]["minutes"] == 9 and v["backfill"]["trades"] == 1000
    assert v["reference_words"].endswith("(its 1000 trades reach back only to 09:42:00 ET; IBKR's 1-minute bars "
                                         "before that)")
