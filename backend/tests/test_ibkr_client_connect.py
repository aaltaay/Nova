"""IBKR client connect hardening — hard wall + recreate on timeout."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from constants import IBKR_CLIENT_ID
from ibkr import client as ibkr_client
from metrics import op_metrics


def setup_function() -> None:
    op_metrics.reset_for_tests()


def test_default_client_id_avoids_one():
    """clientId 1 is commonly held by zombie uvicorn workers (Error 326)."""
    assert IBKR_CLIENT_ID != 1
    assert IBKR_CLIENT_ID == 17


def test_attempt_connect_hard_timeout_disconnects():
    ib = MagicMock()
    ib.isConnected.return_value = False

    async def _hang(*_a, **_k):
        await asyncio.sleep(60)

    ib.connectAsync = _hang

    async def _run():
        with patch.object(ibkr_client, "IBKR_CONNECT_TIMEOUT_SEC", 0.05):
            return await ibkr_client._attempt_connect(ib, "127.0.0.1", 4001, 17)

    ok, reason = asyncio.run(_run())
    assert ok is False
    assert reason == "timeout"
    ib.disconnect.assert_called()
    stats = op_metrics.snapshot()["operations"]["ibkr.connect"]
    assert stats["count"] == 1
    assert stats["error_count"] == 1


def test_attempt_connect_success():
    ib = MagicMock()
    ib.connectAsync = AsyncMock(return_value=None)

    async def _run():
        with patch.object(ibkr_client, "IBKR_CONNECT_TIMEOUT_SEC", 2.0):
            return await ibkr_client._attempt_connect(ib, "127.0.0.1", 4001, 17)

    ok, reason = asyncio.run(_run())
    assert ok is True
    assert reason == "ok"
    ib.disconnect.assert_not_called()
    stats = op_metrics.snapshot()["operations"]["ibkr.connect"]
    assert stats["count"] == 1
    assert stats["error_count"] == 0
    ib.connectAsync.assert_awaited_once()


def test_resolve_config_honors_env_client_id():
    with patch.dict("os.environ", {"IBKR_CLIENT_ID": "42"}, clear=False):
        _en, _h, _p, _m, client_id = ibkr_client._resolve_config()
    assert client_id == 42
