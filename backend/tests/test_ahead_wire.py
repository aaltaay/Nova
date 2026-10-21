"""The desk wire (ADR 065): for every made-up fixture the desk's tests read (``frontend/src/ahead/__fixtures__``),
``ahead.view`` builds the same key tree with the same JSON types -- null exactly where the fixture is null."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ahead import client, view
from tests.test_ahead_client import contract_forecast, contract_health

FIXTURES = Path(__file__).resolve().parents[2] / "frontend" / "src" / "ahead" / "__fixtures__"
T0 = 1792500000.0           # the fixtures' newest candle (bar_t)
NOW = T0 + 65               # their generated_at


def shape(v: Any) -> Any:
    """The JSON type tree of ``v``: numbers are one type (JSON has no int), a list is the shape of its items."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        items = [shape(x) for x in v]
        assert all(i == items[0] for i in items), "a list mixes shapes"
        return ["list", items[0] if items else "empty"]
    if isinstance(v, dict):
        return {k: shape(x) for k, x in v.items()}
    raise TypeError(type(v))


def bars(n: int, *, gap_after: int | None = None) -> list[dict]:
    out, t = [], T0 - (n - 1) * 60
    for i in range(n):
        out.append({"t": t, "o": 4.6, "h": 4.62, "l": 4.58, "c": 4.62, "v": 500.0})
        t += 120 if gap_after is not None and i == gap_after else 60
    out[-1]["t"] = T0
    return out


def health(*, exam: bool = True) -> dict:
    h = client.parse_health(contract_health())
    return {**h, "exam": h["exam"] if exam else None}


def forecast() -> dict:
    as_of = "2026-10-21T09:01:00-04:00"
    return client.parse_forecast(contract_forecast(as_of=as_of), "XYZ", as_of, 15)


AI = {
    "ready": lambda: view.ai_block("ready", health=health(), forecast=forecast(), issued_at=NOW - 1),
    "pending": lambda: view.ai_block("pending", reason="Reading the minute that just closed.", retry_ms=1000,
                                     health=health()),
    "warming": lambda: view.ai_block("warming", reason="The forecaster is starting up.", health=health(exam=False)),
    "offline": lambda: view.ai_block("offline", reason="no answer in 3 s", retry_at=NOW + 30),
    "error": lambda: view.ai_block("error", reason="the forecaster's answer is missing close"),
    "not_set_up": lambda: view.ai_block("not_set_up", reason="NOVA_AHEAD_URL is not set"),
    "quiet": lambda: view.ai_block("quiet", reason="No trade in the last 4 minutes."),
    "not_enough_bars": lambda: view.ai_block("not_enough_bars", reason="Ahead needs 30 one-minute candles.",
                                             need=30, have=0),
}
BARS = {"not_enough_bars": [], "quiet": bars(120, gap_after=50)}


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_every_state_has_a_fixture():
    names = {p.name for p in FIXTURES.glob("answer_*.json")}
    assert names == {f"answer_{state}.json" for state in AI}


@pytest.mark.parametrize("state", sorted(AI))
def test_view_builds_each_fixtures_shape(state):
    want = _fixture(f"answer_{state}.json")
    got = view.answer(sym="XYZ", now=NOW, replay=False, venue="paper", bars=BARS.get(state, bars(240)),
                      prior_close=3.1, ai=AI[state]())
    assert shape(got) == shape(want)
    assert json.loads(json.dumps(got, allow_nan=False)) == got          # plain JSON, nothing non-finite
    assert got["ai"]["state"] == want["ai"]["state"]


def test_ready_rounds_like_the_fixture():
    got = view.answer(sym="XYZ", now=NOW, replay=False, venue="paper", bars=bars(240), prior_close=3.1,
                      ai=AI["ready"]())
    want = _fixture("answer_ready.json")
    assert got["ai"]["close"] == want["ai"]["close"]
    assert got["ai"]["paths"]["close"] == want["ai"]["paths"]["close"]
    assert all(isinstance(x, int) for row in got["ai"]["volume"] for x in row)
    assert got["as_of"] == want["as_of"] and got["bars"]["tail_gap_sec"] == 0


def test_a_sub_dollar_price_keeps_six_decimals():
    assert view.price(0.123456789) == 0.123457
    assert view.price(4.123456789) == 4.1235


@pytest.mark.parametrize("name, kwargs", [
    ("status_ready.json", {"configured": True, "reason": None, "health": "ready"}),
    ("status_not_configured.json", {"configured": False, "reason": "NOVA_AHEAD_URL is not set", "health": None}),
])
def test_view_builds_each_status_fixtures_shape(name, kwargs):
    h = health() if kwargs["health"] else None
    got = view.status(configured=kwargs["configured"], reason=kwargs["reason"], health=h, checked_at=NOW)
    assert shape(got) == shape(_fixture(name))


def test_a_forecast_goes_with_ready_only():
    with pytest.raises(ValueError):
        view.ai_block("pending", forecast=forecast())
    with pytest.raises(ValueError):
        view.ai_block("ready")
