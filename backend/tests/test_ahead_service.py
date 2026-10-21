"""Ahead's service (ADR 065): the gates in order, one ask per minute, a short memory for failures, the breaker, its
own threads, and a replay that never sends a candle from after the playhead."""
from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import http_pool
from ahead import client, inputs, service
from ahead.client import ForecasterError
from tests.test_ahead_client import contract_forecast, contract_health

ET = ZoneInfo("America/New_York")
REAL_SESSION_BARS = inputs.session_bars
READY_ONLY = ("levels", "close", "volume", "paths", "volume_15", "range_15", "compute_ms", "issued_at",
              "exam_passed")


def at(h: int, m: int, s: int = 0) -> float:
    return datetime(2026, 10, 21, h, m, s, tzinfo=ET).timestamp()


def minutes(first: int, last: int, c: float = 4.6, hour: int = 9) -> list[dict]:
    return [{"t": at(hour, m), "o": c, "h": c, "l": c, "c": c, "v": 1000.0} for m in range(first, last + 1)]


def parsed(body: dict) -> dict:
    return client.parse_forecast(contract_forecast(sym=body["symbol"], as_of=body["as_of"]), body["symbol"],
                                 body["as_of"], 15)


@pytest.fixture
def desk(monkeypatch):
    service.reset_for_testing()
    state = SimpleNamespace(now=at(9, 40, 5), replay=False, venue="paper", bars=minutes(0, 39), prior=3.1,
                            forecasts=[], healths=0, forecast=parsed, health=lambda: client.parse_health(
                                contract_health()), threads={})
    monkeypatch.setenv("NOVA_AHEAD_URL", "http://127.0.0.1:8791")
    monkeypatch.setenv("NOVA_AHEAD_TOKEN", "tok-service-test")
    monkeypatch.setattr(inputs, "desk_now", lambda: (state.now, state.replay))
    monkeypatch.setattr(inputs, "venue", lambda: state.venue)

    def bars(sym, now, replay):
        state.threads["read"] = threading.current_thread().name
        return list(state.bars)

    def fake_forecast(body):
        state.threads["ask"] = threading.current_thread().name
        state.forecasts.append(body)
        return state.forecast(body)

    def fake_health():
        state.healths += 1
        return state.health()

    monkeypatch.setattr(inputs, "session_bars", bars)
    monkeypatch.setattr(inputs, "prior_close", lambda sym, replay: state.prior)
    monkeypatch.setattr(client, "forecast", fake_forecast)
    monkeypatch.setattr(client, "health", fake_health)
    monkeypatch.setattr(http_pool, "session", lambda name: pytest.fail("no real request in these tests"))
    yield state
    service.reset_for_testing()


async def drain() -> None:
    for _ in range(50):
        entry = next(iter(service._inflight.values()), None)
        if entry is None:
            return
        await asyncio.wait([entry[1]])
        await asyncio.sleep(0)


def ask(*polls: str) -> list[dict]:
    """Run ``ahead("XYZ")`` per poll; ``"drain"`` waits for the ask in flight."""
    async def run():
        out = []
        for p in polls:
            if p == "drain":
                await drain()
            else:
                out.append(await service.ahead(p))
        await drain()
        return out
    return asyncio.run(run())


def assert_no_ai_numbers(answer: dict) -> None:
    assert answer["ai"]["state"] != "ready"
    for field in READY_ONLY:
        assert answer["ai"][field] is None, field
    assert answer["ai"]["reason"]


def test_unset_answers_not_set_up_and_asks_nothing(desk, monkeypatch):
    monkeypatch.delenv("NOVA_AHEAD_URL")
    (out,) = ask("XYZ")
    assert out["ai"]["state"] == "not_set_up"
    assert out["ai"]["reason"] == "NOVA_AHEAD_URL is not set"
    assert out["bar_t"] == at(9, 39) and out["price"] == 4.6     # Nova's facts are still there
    assert desk.forecasts == [] and desk.healths == 0
    assert_no_ai_numbers(out)


def test_a_non_loopback_address_is_refused(desk, monkeypatch):
    monkeypatch.setenv("NOVA_AHEAD_URL", "http://192.168.1.20:8791")
    (out,) = ask("XYZ")
    assert out["ai"]["state"] == "not_set_up"
    assert desk.forecasts == [] and desk.healths == 0


def test_no_candles_comes_first(desk, monkeypatch):
    monkeypatch.delenv("NOVA_AHEAD_URL")
    desk.bars = []
    (out,) = ask("XYZ")
    assert out["ai"]["state"] == "not_enough_bars"
    assert (out["ai"]["need"], out["ai"]["have"]) == (30, 0)
    assert out["bar_t"] is None and out["as_of"] is None and out["bars"]["tail_gap_sec"] is None
    assert out["prior_close"] == 3.1


def test_under_30_candles_is_not_asked(desk):
    desk.bars = minutes(20, 39)
    (out,) = ask("XYZ")
    assert out["ai"]["state"] == "not_enough_bars"
    assert (out["ai"]["need"], out["ai"]["have"]) == (30, 20)
    assert desk.forecasts == []
    assert_no_ai_numbers(out)


def test_a_quiet_stock_is_not_asked(desk):
    desk.bars = minutes(0, 35)
    (out,) = ask("XYZ")
    assert out["ai"]["state"] == "quiet"
    assert out["ai"]["reason"] == "No trade in the last 4 minutes."
    assert out["bars"]["tail_gap_sec"] == 240
    assert desk.forecasts == []


def test_pending_then_ready_with_one_post_per_minute(desk):
    first, second, third = ask("XYZ", "drain", "XYZ", "XYZ")
    assert first["ai"]["state"] == "pending" and first["ai"]["retry_ms"] == 1000
    assert_no_ai_numbers(first)
    assert second["ai"]["state"] == third["ai"]["state"] == "ready"
    assert len(desk.forecasts) == 1 and desk.healths == 1
    body = desk.forecasts[0]
    assert body["as_of"] == "2026-10-21T09:40:00-04:00" and body["prior_close"] == 3.1 and body["venue"] == "paper"
    assert len(body["bars"]) == 40
    ai = second["ai"]
    assert ai["model"] == {"name": "model-a", "version": "1.0"} and ai["exam"]["scope"]
    assert ai["exam_passed"] is False and ai["reason"] is None
    assert len(ai["paths"]["close"]) == 16 and ai["levels"] == [0.1, 0.25, 0.5, 0.75, 0.9]
    assert second["as_of"] <= ai["issued_at"] and second["as_of"] <= second["generated_at"]


def test_a_failure_is_remembered_briefly_then_asked_again(desk, monkeypatch):
    def refuse(body):
        raise ForecasterError("error", "the forecaster answered HTTP 500")

    desk.forecast = refuse
    first, second = ask("XYZ", "drain", "XYZ")
    assert second["ai"]["state"] == "error" and second["ai"]["reason"] == "the forecaster answered HTTP 500"
    assert_no_ai_numbers(second)
    (third,) = ask("XYZ")
    assert len(desk.forecasts) == 1                      # inside the negative TTL: the same minute is not asked again
    assert third["ai"]["state"] == "error"
    monkeypatch.setattr(service, "AHEAD_NEGATIVE_TTL_SEC", 0.0)
    desk.forecast = parsed
    pending, ready = ask("XYZ", "drain", "XYZ")
    assert pending["ai"]["state"] == "pending" and ready["ai"]["state"] == "ready"
    assert len(desk.forecasts) == 2


def test_an_older_minute_in_flight_blocks_a_newer_start_and_nothing_is_queued(desk):
    gate = threading.Event()

    def slow(body):
        assert gate.wait(5)
        return parsed(body)

    desk.forecast = slow

    async def run():
        a = await service.ahead("XYZ")                       # asks 09:40
        desk.bars = minutes(0, 40)
        desk.now = at(9, 41, 5)
        b = await service.ahead("XYZ")                       # 09:41 waits: one ask per symbol
        gate.set()
        await drain()
        c = await service.ahead("XYZ")                       # now 09:41 is asked, never 09:40 again
        await drain()
        d = await service.ahead("XYZ")
        return a, b, c, d

    a, b, c, d = asyncio.run(run())
    assert [x["ai"]["state"] for x in (a, b, c, d)] == ["pending", "pending", "pending", "ready"]
    assert [f["as_of"] for f in desk.forecasts] == ["2026-10-21T09:40:00-04:00", "2026-10-21T09:41:00-04:00"]
    assert d["as_of"] == at(9, 41)


def test_the_breaker_opens_after_three_misses_and_a_success_clears_it(desk, monkeypatch):
    monkeypatch.setattr(service, "AHEAD_NEGATIVE_TTL_SEC", 0.0)

    def miss(body):
        raise ForecasterError("offline", "no answer in 3 s", transport=True)

    desk.forecast = miss
    answers = ask("XYZ", "drain", "XYZ", "drain", "XYZ", "drain", "XYZ")
    assert [a["ai"]["state"] for a in answers] == ["pending", "pending", "pending", "offline"]
    last = answers[-1]["ai"]
    assert last["reason"] == "missed 3 answers in a row; asks again in 30 s"
    # Wall-clock seconds, never the desk clock: on a paused replay the playhead would never reach it.
    assert last["retry_at"] == pytest.approx(time.time() + 30, abs=2)
    assert abs(last["retry_at"] - (desk.now + 30)) > 60
    assert len(desk.forecasts) == 3
    (still,) = ask("XYZ")
    assert still["ai"]["state"] == "offline" and len(desk.forecasts) == 3     # open: nothing is asked
    service._breaker["open_until"] = 0.0
    desk.forecast = parsed
    _, ready = ask("XYZ", "drain", "XYZ")
    assert ready["ai"]["state"] == "ready" and service._breaker["fails"] == 0


def test_the_done_callback_clears_the_ask_when_it_raises(desk, caplog):
    def broken(body):
        raise RuntimeError("bug")

    desk.forecast = broken
    first, second = ask("XYZ", "drain", "XYZ")
    assert service._inflight == {}
    assert second["ai"]["state"] == "error" and second["ai"]["reason"] == "Nova could not ask the forecaster"
    assert "asking the forecaster for XYZ failed" in caplog.text


def test_reads_and_asks_run_on_separate_threads(desk):
    ask("XYZ", "drain")
    assert desk.threads["read"].startswith("ahead-read")
    assert desk.threads["ask"].startswith("ahead-ask")


def test_a_replay_never_sends_a_candle_from_after_the_playhead(desk, monkeypatch, caplog):
    from stock_read import replay_read

    monkeypatch.setattr(inputs, "session_bars", REAL_SESSION_BARS)      # the real reader, over a faked replay
    desk.replay, desk.venue, desk.now = True, "sim", at(9, 40, 5)
    leaked = minutes(0, 40)                                  # 09:40 has not closed at 09:40:05
    monkeypatch.setattr(replay_read, "bars", lambda sym, tf, limit, now: leaked)
    (out,) = ask("XYZ")
    assert out["ai"]["state"] == "error"
    assert out["ai"]["reason"] == "a candle ends after the forecast time, so nothing was asked"
    assert desk.forecasts == []
    monkeypatch.setattr(replay_read, "bars", lambda sym, tf, limit, now: minutes(0, 39))
    _, ready = ask("XYZ", "drain", "XYZ")
    assert ready["replay"] is True and ready["venue"] == "sim"
    assert ready["generated_at"] == at(9, 40, 5) and ready["as_of"] == at(9, 40)
    assert desk.forecasts[0]["venue"] == "sim"



def test_a_rewind_serves_the_older_minute_it_kept(desk):
    ask("XYZ", "drain")
    desk.bars, desk.now = minutes(0, 40), at(9, 41, 5)
    ask("XYZ", "drain")
    desk.bars, desk.now = minutes(0, 39), at(9, 40, 5)
    (back,) = ask("XYZ")
    assert back["ai"]["state"] == "ready" and back["as_of"] == at(9, 40)
    assert len(desk.forecasts) == 2


def test_another_feeds_minute_is_another_ask(desk):
    ask("XYZ", "drain")
    desk.bars = desk.bars[:-1] + [{**desk.bars[-1], "c": 4.7}]
    (out,) = ask("XYZ")
    assert out["ai"]["state"] == "pending" and len(desk.forecasts) == 2


@pytest.mark.parametrize("health, state, words", [
    ({"state": "warming", "detail": None}, "warming", "The forecaster is starting up."),
    ({"state": "error", "detail": "weights missing"}, "error", "weights missing"),
])
def test_a_not_ready_health_is_its_state(desk, health, state, words):
    desk.health = lambda: client.parse_health(contract_health(**health))
    _, out = ask("XYZ", "drain", "XYZ")
    assert (out["ai"]["state"], out["ai"]["reason"]) == (state, words)
    assert out["ai"]["model"] == {"name": "model-a", "version": "1.0"}
    assert desk.forecasts == []
    assert_no_ai_numbers(out)


def test_status_shapes(desk, monkeypatch):
    out = asyncio.run(service.status())
    assert out["configured"] is True and out["reason"] is None
    assert out["health"]["state"] == "ready" and out["health"]["contract_ok"] is True
    assert out["health"]["live"]["range_spearman"] is None
    service.reset_for_testing()

    def down():
        raise ForecasterError("offline", "could not connect to the forecaster", transport=True)

    desk.health = down
    out = asyncio.run(service.status())
    assert out["health"] is None and out["reason"] == "could not connect to the forecaster"
    monkeypatch.delenv("NOVA_AHEAD_TOKEN")
    out = asyncio.run(service.status())
    assert out == {"schema_version": 1, "configured": False, "reason": "NOVA_AHEAD_TOKEN is not set",
                   "checked_at": out["checked_at"], "health": None}


def test_a_ready_health_is_asked_at_most_every_15_seconds(desk):
    ask("XYZ", "drain")
    desk.bars, desk.now = minutes(0, 40), at(9, 41, 5)
    ask("XYZ", "drain")
    asyncio.run(service.status())
    assert desk.healths == 1



def test_a_changed_prior_close_or_earlier_candle_is_asked_again(desk):
    """The memory keys on the whole request: a prior close that arrives later, or a corrected earlier candle, in the
    same minute is a new ask; the same request is never asked twice."""
    ask("XYZ", "drain", "XYZ")
    assert len(desk.forecasts) == 1
    desk.prior = 3.2
    ask("XYZ", "drain", "XYZ")
    assert len(desk.forecasts) == 2 and desk.forecasts[-1]["prior_close"] == 3.2
    fixed = [dict(b) for b in desk.bars]
    fixed[3]["h"] = fixed[3]["h"] + 0.01
    desk.bars = fixed
    ask("XYZ", "drain", "XYZ")
    assert len(desk.forecasts) == 3


def test_a_health_answer_ends_a_run_of_misses(desk):
    """Two misses, then the forecaster answers its health (even "warming"): the run is over, so one more miss cannot
    open the breaker as if three came in a row."""
    service._breaker["fails"] = 2
    desk.health = lambda: client.parse_health(contract_health(state="warming", detail=None))
    ask("XYZ", "drain")
    assert service._breaker["fails"] == 0
