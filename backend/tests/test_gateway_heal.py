"""Gateway paper/live port self-heal — persist + classify + alternate connect."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from ibkr import client as ibkr_client
from ibkr import gateway_heal as heal


def setup_function() -> None:
    heal.clear_heal_status_for_tests()


def test_alternate_mode_and_ports(monkeypatch):
    monkeypatch.setenv("IBKR_PAPER_PORT", "4002")
    monkeypatch.setenv("IBKR_LIVE_PORT", "4001")
    assert heal.alternate_mode("live") == "paper"
    assert heal.alternate_mode("paper") == "live"
    assert heal.port_for_mode("paper") == 4002
    assert heal.port_for_mode("live") == 4001


def test_classify_connect_failure():
    assert heal.classify_connect_failure(None, timed_out=True) == "timeout"
    assert (
        heal.classify_connect_failure(ConnectionRefusedError(), timed_out=False)
        == "refused"
    )
    assert (
        heal.classify_connect_failure(
            OSError(10061, "Connect call failed"),
            timed_out=False,
        )
        == "refused"
    )
    assert heal.classify_connect_failure(RuntimeError("boom"), timed_out=False) == "other"


def test_persist_gateway_mode_rewrites_env(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("IBKR_ENABLED=true\nIBKR_GATEWAY_MODE=live\nFOO=1\n", encoding="utf-8")
    assert heal.persist_gateway_mode("paper", env_path=env) is True
    text = env.read_text(encoding="utf-8")
    assert "IBKR_GATEWAY_MODE=paper" in text
    assert "IBKR_GATEWAY_MODE=live" not in text
    assert "IBKR_ENABLED=true" in text
    assert "FOO=1" in text


def test_persist_gateway_mode_appends_when_missing(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("IBKR_ENABLED=true\n", encoding="utf-8")
    assert heal.persist_gateway_mode("paper", env_path=env) is True
    assert "IBKR_GATEWAY_MODE=paper" in env.read_text(encoding="utf-8")


def test_try_connect_alternate_port_heals_on_refused(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("IBKR_GATEWAY_SELF_HEAL", "true")
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")
    monkeypatch.setenv("IBKR_LIVE_PORT", "4001")
    monkeypatch.setenv("IBKR_PAPER_PORT", "4002")
    env = tmp_path / ".env"
    env.write_text("IBKR_GATEWAY_MODE=live\n", encoding="utf-8")

    ib = MagicMock()
    calls: list[int] = []

    async def _connect(_host, port, clientId=0, timeout=1):  # noqa: N803
        calls.append(port)
        if port == 4002:
            return None
        raise ConnectionRefusedError(10061, "refused")

    ib.connectAsync = _connect
    ib.managedAccounts = lambda: ["DU1234567"]

    real_persist = heal.persist_gateway_mode

    def _persist(mode, env_path=None):
        return real_persist(mode, env_path=env)

    async def _run():
        with (
            patch.object(ibkr_client, "IBKR_CONNECT_TIMEOUT_SEC", 2.0),
            patch.object(heal, "persist_gateway_mode", side_effect=_persist),
        ):
            return await ibkr_client._try_connect_alternate_port(
                ib, "127.0.0.1", "live", 17, "refused",
            )

    healed = asyncio.run(_run())
    assert healed == "paper"
    assert calls == [4002]
    assert heal.heal_status()["gateway_self_heal"]["to_mode"] == "paper"
    assert "IBKR_GATEWAY_MODE=paper" in env.read_text(encoding="utf-8")
    assert os.environ.get("IBKR_GATEWAY_MODE") == "paper"


def test_try_connect_alternate_skips_when_disabled(monkeypatch):
    monkeypatch.setenv("IBKR_GATEWAY_SELF_HEAL", "false")
    ib = MagicMock()
    ib.connectAsync = AsyncMock()

    async def _run():
        return await ibkr_client._try_connect_alternate_port(
            ib, "127.0.0.1", "live", 17, "refused",
        )

    assert asyncio.run(_run()) is None
    ib.connectAsync.assert_not_called()


def test_heal_target_allowed_paper_only():
    assert heal.heal_target_allowed(from_mode="live", to_mode="paper") is True
    assert heal.heal_target_allowed(from_mode="paper", to_mode="live") is False
    assert heal.heal_target_allowed(from_mode="paper", to_mode="paper") is False
    assert heal.heal_target_allowed(from_mode="live", to_mode="live") is False


def test_intentional_mode_is_sticky_not_timed():
    """User intent must not expire after ~18s the way the old suppress timer did."""
    assert heal.self_heal_suppressed() is False
    heal.set_intentional_mode("live")
    assert heal.self_heal_suppressed() is True
    assert heal.intentional_mode() == "live"
    # Sticky — still suppressed (no sleep/expiry).
    assert heal.self_heal_suppressed() is True
    heal.clear_intentional_mode(reason="test")
    assert heal.self_heal_suppressed() is False


def test_try_connect_alternate_port_skips_when_intentional(monkeypatch):
    """Intentional live switch in progress: a refused live port must surface
    honestly, not silently self-heal back to paper mid-switch."""
    monkeypatch.setenv("IBKR_GATEWAY_SELF_HEAL", "true")
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")
    heal.set_intentional_mode("live")
    ib = MagicMock()
    ib.connectAsync = AsyncMock()

    async def _run():
        return await ibkr_client._try_connect_alternate_port(
            ib, "127.0.0.1", "live", 17, "refused",
        )

    assert asyncio.run(_run()) is None
    ib.connectAsync.assert_not_called()
    assert heal.heal_status()["gateway_self_heal"] is None


def test_try_connect_alternate_skips_timeout_not_refused(monkeypatch):
    """Timeout / Error 326 must not trigger live→paper heal."""
    monkeypatch.setenv("IBKR_GATEWAY_SELF_HEAL", "true")
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")
    ib = MagicMock()
    ib.connectAsync = AsyncMock()

    async def _run():
        return await ibkr_client._try_connect_alternate_port(
            ib, "127.0.0.1", "live", 17, "timeout",
        )

    assert asyncio.run(_run()) is None
    ib.connectAsync.assert_not_called()


def test_clear_last_heal_on_preferred_connect():
    heal.record_heal(
        from_mode="live",
        to_mode="paper",
        reason="refused",
        preferred_port=4001,
        healed_port=4002,
        persisted=True,
    )
    assert heal.heal_status()["gateway_self_heal"] is not None
    heal.record_connect_outcome("connected", reason="ok", mode="live")
    assert heal.heal_status()["gateway_self_heal"] is None


def test_try_connect_alternate_never_heals_paper_to_live(monkeypatch):
    """Paper pin: preferred paper down must NOT attach to live 4001."""
    monkeypatch.setenv("IBKR_GATEWAY_SELF_HEAL", "true")
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setenv("IBKR_LIVE_PORT", "4001")
    monkeypatch.setenv("IBKR_PAPER_PORT", "4002")
    ib = MagicMock()
    ib.connectAsync = AsyncMock()

    async def _run():
        return await ibkr_client._try_connect_alternate_port(
            ib, "127.0.0.1", "paper", 17, "refused",
        )

    assert asyncio.run(_run()) is None
    ib.connectAsync.assert_not_called()
    assert heal.heal_status()["gateway_self_heal"] is None
