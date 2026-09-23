"""Who may arm the desk (ADR 018 amendment, operator decision 2026-09-23).

"I want the bot to be able to unlock [Paper / Sim] themselves through an
endpoint, but I don't want the live trade to ever get unlocked without my
permission." One rule, one door (``ibkr.safety.arm`` behind
``POST /api/ibkr/arm``): Live arms only with the operator's PIN, checked by the
backend against a hash in ``.env``; Paper and Sim arm with no PIN, from the
padlock or a bot. The PIN used to be a constant in the public frontend source,
checked in the browser, while this endpoint armed Live for any local caller.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from constants_ibkr import ARM_PIN_HASH_ENV, ARM_PIN_MAX_FAILURES
from ibkr import arm_pin
from ibkr import safety as _safety
from routes.trading import router
from sim.mode import reset_for_tests as reset_venue, set_venue

PIN = "482915"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv(ARM_PIN_HASH_ENV, raising=False)
    reset_venue()
    arm_pin.reset_for_tests()
    yield
    reset_venue()
    arm_pin.reset_for_tests()


@pytest.fixture
def pin_set(monkeypatch):
    monkeypatch.setenv(ARM_PIN_HASH_ENV, arm_pin.hash_pin(PIN, iterations=1_000))


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ── Live: only with the operator's PIN ────────────────────────────────────────

def test_live_never_arms_without_a_pin_set() -> None:
    set_venue("live")
    for actor in ("operator", "bot"):
        code, reason = _safety.arm(True, pin="000000", actor=actor)
        assert code == "ARM_PIN_NOT_SET" and "set_live_arm_pin.py" in reason
    assert _safety.armed() is False


def test_live_arms_only_with_the_right_pin(pin_set) -> None:
    set_venue("live")
    assert _safety.arm(True, actor="bot")[0] == "ARM_PIN_REQUIRED"
    assert _safety.arm(True, pin="111111", actor="bot")[0] == "ARM_PIN_INVALID"
    assert _safety.armed() is False
    assert _safety.arm(True, pin=PIN) == (None, "")
    assert _safety.armed() is True and _safety.armed_by() == "operator"


def test_wrong_pins_lock_live_arming_out(pin_set) -> None:
    set_venue("live")
    codes = [_safety.arm(True, pin="999999")[0] for _ in range(ARM_PIN_MAX_FAILURES)]
    assert codes[-1] == "ARM_PIN_LOCKED"
    # Even the right PIN waits out the lockout: guessing six digits is not a door.
    assert _safety.arm(True, pin=PIN)[0] == "ARM_PIN_LOCKED"
    assert _safety.armed() is False


def test_the_pin_is_read_from_the_env_file_so_setting_it_needs_no_restart(tmp_path, monkeypatch) -> None:
    env = tmp_path / "desk.env"
    env.write_text(f"OTHER=1\n{ARM_PIN_HASH_ENV}={arm_pin.hash_pin(PIN, iterations=1_000)}\n", encoding="utf-8")
    monkeypatch.setenv("NOVA_ENV_PATH", str(env))
    set_venue("live")
    assert arm_pin.pin_is_set() is True
    assert _safety.arm(True, pin=PIN) == (None, "")


def test_an_unreadable_hash_is_not_a_pin() -> None:
    assert arm_pin._parse("plain-text-pin") is None
    assert arm_pin._parse("md5$1$aa$bb") is None


# ── Paper / Sim: no PIN, from the padlock or a bot ────────────────────────────

@pytest.mark.parametrize("venue", ["paper", "sim"])
def test_a_bot_arms_a_practice_venue_without_a_pin(venue: str) -> None:
    set_venue(venue)
    assert _safety.arm(True, actor="bot") == (None, "")
    assert _safety.armed() is True and _safety.armed_by() == "bot"
    assert _safety.arm_requires_pin() is False


def test_a_practice_arm_is_never_a_live_arm(pin_set, monkeypatch) -> None:
    """The latch carries its venue: even a path that skipped the venue change's
    disarm cannot hand Live an arm that was given on Paper."""
    set_venue("paper")
    _safety.arm(True, actor="bot")
    assert _safety.armed() is True
    monkeypatch.setattr("sim.mode.venue", lambda: "live")
    assert _safety.armed() is False
    assert _safety.assert_armed_for("manual")[0] is False


def test_an_unreadable_venue_answers_as_live(pin_set, monkeypatch) -> None:
    def broken() -> str:
        raise OSError("venue file unreadable")

    monkeypatch.setattr("sim.mode.venue", broken)
    assert _safety.arm_requires_pin() is True
    assert _safety.arm(True, actor="bot")[0] == "ARM_PIN_REQUIRED"


def test_anyone_may_disarm_any_venue(pin_set) -> None:
    set_venue("live")
    _safety.arm(True, pin=PIN)
    assert _safety.arm(False, actor="bot") == (None, "")
    assert _safety.armed() is False


# ── The route and the status ──────────────────────────────────────────────────

def test_the_route_answers_403_with_a_code_on_live(pin_set) -> None:
    client = _client()
    set_venue("live")
    res = client.post("/api/ibkr/arm", json={"armed": True, "actor": "bot"})
    assert res.status_code == 403 and res.json()["code"] == "ARM_PIN_REQUIRED"
    res = client.post("/api/ibkr/arm", json={"armed": True, "pin": PIN})
    assert res.status_code == 200 and res.json()["armed"] is True
    assert res.json()["armed_by"] == "operator" and res.json()["arm_requires_pin"] is True


def test_the_route_arms_paper_for_a_bot_and_says_who() -> None:
    client = _client()
    set_venue("paper")
    res = client.post("/api/ibkr/arm", json={"armed": True, "actor": "bot"})
    assert res.status_code == 200
    body = res.json()
    assert body["armed"] is True and body["armed_by"] == "bot"
    assert body["arm_requires_pin"] is False and body["live_arm_pin_set"] is False


def test_the_route_refuses_an_unknown_actor() -> None:
    res = _client().post("/api/ibkr/arm", json={"armed": True, "actor": "root"})
    assert res.status_code == 422
    assert _safety.armed() is False


def test_the_pin_tool_rewrites_only_its_own_line(tmp_path) -> None:
    import importlib.util
    from pathlib import Path

    tool = Path(__file__).resolve().parents[2] / "tools" / "set_live_arm_pin.py"
    spec = importlib.util.spec_from_file_location("set_live_arm_pin", tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    env = tmp_path / ".env"
    env.write_text(f"A=1\n{ARM_PIN_HASH_ENV}=old\nB=2\n", encoding="utf-8")
    module.write_hash(env, "new")
    assert env.read_text(encoding="utf-8").splitlines() == ["A=1", "B=2", f"{ARM_PIN_HASH_ENV}=new"]
