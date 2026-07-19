"""IBKR client connect hardening — hard wall + recreate on timeout."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from constants import IBKR_CLIENT_ID
from ibkr import client as ibkr_client


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


def test_resolve_config_honors_env_client_id():
    with patch.dict("os.environ", {"IBKR_CLIENT_ID": "42"}, clear=False):
        _en, _h, _p, _m, client_id = ibkr_client._resolve_config()
    assert client_id == 42
