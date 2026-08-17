"""ADR 010 -- IB loop supervisor identity and HTTP isolation."""
from __future__ import annotations

import asyncio
import time

import pytest

from ibkr.loop_supervisor import (
    assert_ib_loop,
    is_ib_loop,
    on_ib,
    start,
    stop,
)


@pytest.fixture
def ib_loop():
    start()
    try:
        yield
    finally:
        stop()


def test_on_ib_asserts_ib_loop(ib_loop) -> None:
    async def _on_ib_side() -> bool:
        assert_ib_loop()
        return is_ib_loop()

    async def _http() -> None:
        assert is_ib_loop() is False
        assert await on_ib(_on_ib_side(), 2.0, label="id") is True

    asyncio.run(_http())


def test_ib_sleep_does_not_delay_http_await(ib_loop) -> None:
    async def _ib_sleep() -> str:
        await asyncio.sleep(2.0)
        return "ib"

    async def _http() -> None:
        t0 = time.monotonic()
        ib_task = asyncio.create_task(on_ib(_ib_sleep(), 5.0, label="sleep"))
        await asyncio.sleep(0.05)
        http_ms = (time.monotonic() - t0) * 1000.0
        assert http_ms < 200.0
        assert await ib_task == "ib"

    asyncio.run(_http())


def test_assert_ib_loop_fails_on_uvicorn_loop(ib_loop) -> None:
    async def _http() -> None:
        with pytest.raises(RuntimeError, match="connect-loop"):
            assert_ib_loop()

    asyncio.run(_http())
