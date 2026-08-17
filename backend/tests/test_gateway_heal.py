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
            patch("ibkr.client_connect.IBKR_CONNECT_TIMEOUT_SEC", 2.0),
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


def test_heal_target_allowed_bidirectional():
    assert heal.heal_target_allowed(from_mode="live", to_mode="paper") is True
    assert heal.heal_target_allowed(from_mode="paper", to_mode="live") is True
    assert heal.heal_target_allowed(from_mode="paper", to_mode="paper") is False
    assert heal.heal_target_allowed(from_mode="live", to_mode="live") is False


def test_intentional_mode_is_sticky_through_mid_switch_grace(monkeypatch):
    """User intent must not expire after ~18s the way the old suppress timer did."""
    monkeypatch.setattr(heal, "IBKR_INTENTIONAL_FOLLOW_GRACE_SEC", 120.0)
    assert heal.self_heal_suppressed() is False
    heal.set_intentional_mode("live")
    assert heal.self_heal_suppressed() is True
    assert heal.intentional_mode() == "live"
    t0 = heal.heal_status()["intentional_gateway_mode_at"]
    monkeypatch.setattr(heal.time, "time", lambda: t0 + 18)
    assert heal.self_heal_suppressed(
        preferred_reachable=False,
        alternate_reachable=True,
    ) is True
    heal.clear_intentional_mode(reason="test")
    assert heal.self_heal_suppressed() is False


def test_intentional_expires_when_only_alternate_listens(monkeypatch):
    """Overnight IBC restart as the other mode: follow after grace."""
    monkeypatch.setattr(heal, "IBKR_INTENTIONAL_FOLLOW_GRACE_SEC", 120.0)
    heal.set_intentional_mode("live")
    t0 = heal.heal_status()["intentional_gateway_mode_at"]
    monkeypatch.setattr(heal.time, "time", lambda: t0 + 121)
    assert heal.self_heal_suppressed(
        preferred_reachable=False,
        alternate_reachable=True,
    ) is False
    assert heal.self_heal_suppressed(
        preferred_reachable=False,
        alternate_reachable=False,
    ) is True
    assert heal.self_heal_suppressed(
        preferred_reachable=True,
        alternate_reachable=True,
    ) is True


def test_try_connect_alternate_heals_after_intentional_grace(
    tmp_path: Path, monkeypatch,
):
    """Past grace + live dark + paper up → follow paper even if user last clicked Live."""
    monkeypatch.setenv("IBKR_GATEWAY_SELF_HEAL", "true")
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")
    monkeypatch.setenv("IBKR_LIVE_PORT", "4001")
    monkeypatch.setenv("IBKR_PAPER_PORT", "4002")
    monkeypatch.setattr(heal, "IBKR_INTENTIONAL_FOLLOW_GRACE_SEC", 120.0)
    env = tmp_path / ".env"
    env.write_text("IBKR_GATEWAY_MODE=live\n", encoding="utf-8")
    heal.set_intentional_mode("live")
    t0 = heal.heal_status()["intentional_gateway_mode_at"]
    monkeypatch.setattr(heal.time, "time", lambda: t0 + 121)

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
            patch("ibkr.client_connect.IBKR_CONNECT_TIMEOUT_SEC", 2.0),
            patch.object(heal, "persist_gateway_mode", side_effect=_persist),
            patch(
                "ibkr.client_connect.probe_port",
                side_effect=lambda _h, p, **_k: p == 4002,
            ),
        ):
            return await ibkr_client._try_connect_alternate_port(
                ib, "127.0.0.1", "live", 17, "refused",
            )

    healed = asyncio.run(_run())
    assert healed == "paper"
    assert calls == [4002]


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


def test_alternate_heal_eligible_probe_rules():
    """Core law: refuse always; timeout only when preferred dark + alternate up."""
    assert heal.alternate_heal_eligible(
        "refused",
        preferred_reachable=True,
        alternate_reachable=False,
    ) is True
    assert heal.alternate_heal_eligible(
        "timeout",
        preferred_reachable=True,
        alternate_reachable=True,
    ) is False
    assert heal.alternate_heal_eligible(
        "timeout",
        preferred_reachable=False,
        alternate_reachable=True,
    ) is True
    assert heal.alternate_heal_eligible(
        "timeout",
        preferred_reachable=False,
        alternate_reachable=False,
    ) is False
    assert heal.alternate_heal_eligible(
        "preferred_dark",
        preferred_reachable=False,
        alternate_reachable=True,
    ) is True
    assert heal.alternate_heal_eligible(
        "other",
        preferred_reachable=False,
        alternate_reachable=True,
    ) is False


def test_try_connect_alternate_skips_timeout_when_preferred_listening(monkeypatch):
    """Timeout / Error 326 while preferred still listens must not heal."""
    monkeypatch.setenv("IBKR_GATEWAY_SELF_HEAL", "true")
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")
    monkeypatch.setenv("IBKR_LIVE_PORT", "4001")
    monkeypatch.setenv("IBKR_PAPER_PORT", "4002")
    ib = MagicMock()
    ib.connectAsync = AsyncMock()

    async def _run():
        with patch("ibkr.client_connect.probe_port", side_effect=lambda _h, p, **_k: p == 4001):
            return await ibkr_client._try_connect_alternate_port(
                ib, "127.0.0.1", "live", 17, "timeout",
            )

    assert asyncio.run(_run()) is None
    ib.connectAsync.assert_not_called()


def test_try_connect_alternate_heals_timeout_when_preferred_dark(
    tmp_path: Path, monkeypatch,
):
    """Windows often times out a dark preferred port — still follow the live Gateway."""
    monkeypatch.setenv("IBKR_GATEWAY_SELF_HEAL", "true")
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setenv("IBKR_LIVE_PORT", "4001")
    monkeypatch.setenv("IBKR_PAPER_PORT", "4002")
    env = tmp_path / ".env"
    env.write_text("IBKR_GATEWAY_MODE=paper\n", encoding="utf-8")

    ib = MagicMock()
    calls: list[int] = []

    async def _connect(_host, port, clientId=0, timeout=1):  # noqa: N803
        calls.append(port)
        if port == 4001:
            return None
        raise ConnectionRefusedError(10061, "refused")

    ib.connectAsync = _connect
    ib.managedAccounts = lambda: ["U5876610"]

    real_persist = heal.persist_gateway_mode

    def _persist(mode, env_path=None):
        return real_persist(mode, env_path=env)

    async def _run():
        with (
            patch("ibkr.client_connect.IBKR_CONNECT_TIMEOUT_SEC", 2.0),
            patch.object(heal, "persist_gateway_mode", side_effect=_persist),
            patch(
                "ibkr.client_connect.probe_port",
                side_effect=lambda _h, p, **_k: p == 4001,
            ),
        ):
            return await ibkr_client._try_connect_alternate_port(
                ib, "127.0.0.1", "paper", 17, "timeout",
            )

    healed = asyncio.run(_run())
    assert healed == "live"
    assert calls == [4001]
    assert heal.heal_status()["gateway_self_heal"]["to_mode"] == "live"
    assert heal.heal_status()["gateway_self_heal"]["reason"] == "timeout"
    assert "IBKR_GATEWAY_MODE=live" in env.read_text(encoding="utf-8")


def test_try_connect_alternate_heals_preferred_dark_probe(
    tmp_path: Path, monkeypatch,
):
    """TCP probe mismatch (preferred dark, alternate up) is enough to follow Gateway."""
    monkeypatch.setenv("IBKR_GATEWAY_SELF_HEAL", "true")
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setenv("IBKR_LIVE_PORT", "4001")
    monkeypatch.setenv("IBKR_PAPER_PORT", "4002")
    env = tmp_path / ".env"
    env.write_text("IBKR_GATEWAY_MODE=paper\n", encoding="utf-8")

    ib = MagicMock()
    calls: list[int] = []

    async def _connect(_host, port, clientId=0, timeout=1):  # noqa: N803
        calls.append(port)
        if port == 4001:
            return None
        raise ConnectionRefusedError(10061, "refused")

    ib.connectAsync = _connect
    ib.managedAccounts = lambda: ["U5876610"]

    real_persist = heal.persist_gateway_mode

    def _persist(mode, env_path=None):
        return real_persist(mode, env_path=env)

    async def _run():
        with (
            patch("ibkr.client_connect.IBKR_CONNECT_TIMEOUT_SEC", 2.0),
            patch.object(heal, "persist_gateway_mode", side_effect=_persist),
            patch(
                "ibkr.client_connect.probe_port",
                side_effect=lambda _h, p, **_k: p == 4001,
            ),
        ):
            return await ibkr_client._try_connect_alternate_port(
                ib, "127.0.0.1", "paper", 17, "preferred_dark",
            )

    healed = asyncio.run(_run())
    assert healed == "live"
    assert calls == [4001]
    assert os.environ.get("IBKR_GATEWAY_MODE") == "live"


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


def test_try_connect_alternate_heals_paper_to_live(tmp_path: Path, monkeypatch):
    """Preferred paper refused + live port up → self-heal to live when account is live."""
    monkeypatch.setenv("IBKR_GATEWAY_SELF_HEAL", "true")
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setenv("IBKR_LIVE_PORT", "4001")
    monkeypatch.setenv("IBKR_PAPER_PORT", "4002")
    env = tmp_path / ".env"
    env.write_text("IBKR_GATEWAY_MODE=paper\n", encoding="utf-8")

    ib = MagicMock()
    calls: list[int] = []

    async def _connect(_host, port, clientId=0, timeout=1):  # noqa: N803
        calls.append(port)
        if port == 4001:
            return None
        raise ConnectionRefusedError(10061, "refused")

    ib.connectAsync = _connect
    ib.managedAccounts = lambda: ["U5876610"]

    real_persist = heal.persist_gateway_mode

    def _persist(mode, env_path=None):
        return real_persist(mode, env_path=env)

    async def _run():
        with (
            patch("ibkr.client_connect.IBKR_CONNECT_TIMEOUT_SEC", 2.0),
            patch.object(heal, "persist_gateway_mode", side_effect=_persist),
        ):
            return await ibkr_client._try_connect_alternate_port(
                ib, "127.0.0.1", "paper", 17, "refused",
            )

    healed = asyncio.run(_run())
    assert healed == "live"
    assert calls == [4001]
    assert heal.heal_status()["gateway_self_heal"]["to_mode"] == "live"
    assert "IBKR_GATEWAY_MODE=live" in env.read_text(encoding="utf-8")
    assert os.environ.get("IBKR_GATEWAY_MODE") == "live"


def test_try_connect_alternate_refuses_kind_mismatch(tmp_path: Path, monkeypatch):
    """Alternate port up but account kind does not match → no heal."""
    monkeypatch.setenv("IBKR_GATEWAY_SELF_HEAL", "true")
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setenv("IBKR_LIVE_PORT", "4001")
    monkeypatch.setenv("IBKR_PAPER_PORT", "4002")
    env = tmp_path / ".env"
    env.write_text("IBKR_GATEWAY_MODE=paper\n", encoding="utf-8")

    ib = MagicMock()

    async def _connect(_host, port, clientId=0, timeout=1):  # noqa: N803
        if port == 4001:
            return None
        raise ConnectionRefusedError(10061, "refused")

    ib.connectAsync = _connect
    # Live port answers but reports mixed accounts — must refuse.
    ib.managedAccounts = lambda: ["DU111", "U111"]

    real_persist = heal.persist_gateway_mode

    def _persist(mode, env_path=None):
        return real_persist(mode, env_path=env)

    async def _run():
        with (
            patch("ibkr.client_connect.IBKR_CONNECT_TIMEOUT_SEC", 2.0),
            patch.object(heal, "persist_gateway_mode", side_effect=_persist),
        ):
            return await ibkr_client._try_connect_alternate_port(
                ib, "127.0.0.1", "paper", 17, "refused",
            )

    assert asyncio.run(_run()) is None
    assert heal.heal_status()["gateway_self_heal"] is None
    assert "IBKR_GATEWAY_MODE=paper" in env.read_text(encoding="utf-8")
