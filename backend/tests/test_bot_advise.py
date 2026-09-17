"""Advise spend guards -- never places."""
from __future__ import annotations

import pytest

from bot.advise_guard import assert_advise_allowed, latest, start
from bot.autonomy import apply_patch
from bot.errors import BotError
from bot.persist import load_session
from constants_bot import BOT_REASON_ADVISE_CAP, BOT_REASON_ADVISE_OFF, BOT_REASON_L0_DARK


def test_advise_off_by_default():
    with pytest.raises(BotError) as exc:
        assert_advise_allowed()
    assert exc.value.reason in (BOT_REASON_L0_DARK, BOT_REASON_ADVISE_OFF)


def test_advise_off_at_l1():
    apply_patch({"level": 1}, desk=True)
    with pytest.raises(BotError) as exc:
        assert_advise_allowed()
    assert exc.value.reason == BOT_REASON_ADVISE_OFF


@pytest.mark.asyncio
async def test_advise_book_hit_does_not_charge(monkeypatch):
    apply_patch({"level": 1, "advise": {"enabled": True}}, desk=True)
    monkeypatch.setattr(
        "advise.service.estimate",
        lambda *_a, **_k: {"est_usd": 0.4},
    )
    monkeypatch.setattr(
        "advise.service.latest",
        lambda *_a, **_k: {"status": "complete", "from_book": True, "id": 9},
    )

    async def boom(*_a, **_k):
        raise AssertionError("start_run must not run on book hit")

    monkeypatch.setattr("advise.service.start_run", boom)
    out = await start("AAPL", 2)
    assert out["places"] is False
    assert out["advise_spend"] == 0.0
    assert load_session()["advise"]["calls_used"] == 0


@pytest.mark.asyncio
async def test_advise_charges_and_caps(monkeypatch):
    apply_patch(
        {"level": 1, "advise": {"enabled": True, "usd_cap": 0.5, "call_cap": 2}},
        desk=True,
    )
    monkeypatch.setattr("advise.service.estimate", lambda *_a, **_k: {"est_usd": 0.4})
    monkeypatch.setattr("advise.service.latest", lambda *_a, **_k: None)

    async def fake_start(*_a, **_k):
        return {"id": 1, "status": "running"}

    monkeypatch.setattr("advise.service.start_run", fake_start)
    out = await start("AAPL", 2, force_refresh=True)
    assert out["places"] is False
    assert out["advise_spend"] == 0.4
    assert load_session()["advise"]["calls_used"] == 1
    with pytest.raises(BotError) as exc:
        await start("AAPL", 2, force_refresh=True)
    assert exc.value.reason == BOT_REASON_ADVISE_CAP


def test_latest_never_places(monkeypatch):
    apply_patch({"level": 1, "advise": {"enabled": True}}, desk=True)
    monkeypatch.setattr("advise.service.latest", lambda *_a, **_k: {"id": 3})
    row = latest("AAPL", 2)
    assert row["places"] is False
