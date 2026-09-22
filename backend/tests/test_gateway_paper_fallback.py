"""The legacy paper Gateway is never an automatic fallback (ADR 020, second pass).

Follow-Gateway still heals paper -> live. live -> paper needs the explicit
``IBKR_PAPER_GATEWAY_FALLBACK`` opt-in (default off: with market-data sharing
on, a paper login beside a live session is read-only and carries no tape, so a
desk that silently followed it would look connected while every scanner and
Level 2 stayed dark). ``POST /api/ibkr/gateway-mode {mode: "paper"}`` remains
the by-hand door and is covered in ``test_gateway_mode_switch.py``.
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

from constants import IBKR_PAPER_GATEWAY_FALLBACK
from ibkr import client as ibkr_client
from ibkr import client_connect
from ibkr import gateway_heal as heal


def setup_function() -> None:
    heal.clear_heal_status_for_tests()


def test_the_constant_defaults_off() -> None:
    assert IBKR_PAPER_GATEWAY_FALLBACK is False


def test_heal_target_never_paper_by_default(monkeypatch):
    """paper -> live heals; live -> paper does not."""
    monkeypatch.delenv("IBKR_PAPER_GATEWAY_FALLBACK", raising=False)
    assert heal.paper_fallback_enabled() is False
    assert heal.heal_target_allowed(from_mode="paper", to_mode="live") is True
    assert heal.heal_target_allowed(from_mode="live", to_mode="paper") is False
    assert heal.heal_target_allowed(from_mode="paper", to_mode="paper") is False
    assert heal.heal_target_allowed(from_mode="live", to_mode="live") is False
    assert heal.heal_status()["paper_gateway_fallback_enabled"] is False


def test_heal_target_paper_only_with_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("IBKR_PAPER_GATEWAY_FALLBACK", "true")
    assert heal.paper_fallback_enabled() is True
    assert heal.heal_target_allowed(from_mode="live", to_mode="paper") is True
    assert heal.heal_target_allowed(from_mode="paper", to_mode="live") is True
    assert heal.heal_status()["paper_gateway_fallback_enabled"] is True
    monkeypatch.setenv("IBKR_PAPER_GATEWAY_FALLBACK", "false")
    assert heal.heal_target_allowed(from_mode="live", to_mode="paper") is False


def test_try_connect_alternate_never_dials_paper_by_default(monkeypatch):
    """Live refused, paper listening: stay disconnected -- no dial, no heal record, .env untouched."""
    monkeypatch.setenv("IBKR_GATEWAY_SELF_HEAL", "true")
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")
    monkeypatch.setenv("IBKR_LIVE_PORT", "4001")
    monkeypatch.setenv("IBKR_PAPER_PORT", "4002")
    monkeypatch.delenv("IBKR_PAPER_GATEWAY_FALLBACK", raising=False)
    ib = MagicMock()
    ib.connectAsync = AsyncMock()

    async def _run():
        with (
            patch("ibkr.client_connect.probe_port", side_effect=lambda _h, p, **_k: p == 4002),
            patch.object(heal, "persist_gateway_mode") as persist,
        ):
            result = await ibkr_client._try_connect_alternate_port(
                ib, "127.0.0.1", "live", 17, "refused",
            )
            persist.assert_not_called()
            return result

    assert asyncio.run(_run()) is None
    ib.connectAsync.assert_not_called()
    assert heal.heal_status()["gateway_self_heal"] is None
    assert os.environ.get("IBKR_GATEWAY_MODE") == "live"


def test_port_probe_fast_path_never_heals_toward_paper_by_default(monkeypatch):
    """The pre-dial probe path refuses the same target and does not even probe."""
    monkeypatch.setenv("IBKR_GATEWAY_SELF_HEAL", "true")
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")
    monkeypatch.delenv("IBKR_PAPER_GATEWAY_FALLBACK", raising=False)
    probes: list[int] = []
    ib = MagicMock()
    ib.connectAsync = AsyncMock()

    def _probe(_h, p, **_k):
        probes.append(p)
        return p == 4002

    async def _run():
        with patch("ibkr.client_connect.probe_port", side_effect=_probe):
            return await client_connect.maybe_heal_from_port_probes(
                ib, "127.0.0.1", "live", 17, accept_session=lambda *_a: (True, "ok"),
            )

    assert asyncio.run(_run()) is None
    assert probes == []
    ib.connectAsync.assert_not_called()


def test_port_probe_fast_path_still_follows_live_from_paper(monkeypatch):
    """The by-hand paper door dark and live up: follow-Gateway still walks to live."""
    monkeypatch.setenv("IBKR_GATEWAY_SELF_HEAL", "true")
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setenv("IBKR_LIVE_PORT", "4001")
    monkeypatch.setenv("IBKR_PAPER_PORT", "4002")
    monkeypatch.delenv("IBKR_PAPER_GATEWAY_FALLBACK", raising=False)
    probes: list[int] = []
    ib = MagicMock()

    def _probe(_h, p, **_k):
        probes.append(p)
        return p == 4001

    async def _run():
        with (
            patch("ibkr.client_connect.probe_port", side_effect=_probe),
            patch.object(client_connect, "try_connect_alternate_port", new=AsyncMock(return_value="live")) as walk,
        ):
            result = await client_connect.maybe_heal_from_port_probes(
                ib, "127.0.0.1", "paper", 17, accept_session=lambda *_a: (True, "ok"),
            )
            walk.assert_awaited_once()
            return result

    assert asyncio.run(_run()) == "live"
    assert sorted(probes) == [4001, 4002]
