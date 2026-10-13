"""The desk's planned stop: keyed, logged, and out through uvicorn's own shutdown."""
from __future__ import annotations

import asyncio
import logging

import auth
from diagnostics import stop


def test_the_stop_route_always_needs_a_configured_key():
    assert auth.is_config_mutate("POST", "/api/diagnostics/stop")
    assert auth.is_config_mutate("POST", "/api/diagnostics/stop/")
    assert not auth.is_config_mutate("GET", "/api/diagnostics/stop")


def test_reason_is_one_short_line():
    assert stop.clean_reason("  update\n to  v1251 ") == "update to v1251"
    assert stop.clean_reason(None) == "unstated"
    assert len(stop.clean_reason("x" * 999)) == 200


def test_request_stop_logs_why_and_exits_like_ctrl_c(monkeypatch, caplog):
    raised: list[int] = []
    monkeypatch.setattr(stop.signal, "raise_signal", lambda sig: raised.append(sig))
    monkeypatch.setattr(stop, "DIAG_STOP_DELAY_SEC", 0.0)

    async def run() -> dict:
        out = stop.request_stop("the desk updated the backend to v1252")
        await asyncio.sleep(0.01)
        return out

    with caplog.at_level(logging.WARNING, logger="diagnostics.stop"):
        out = asyncio.run(run())
    assert out == {"ok": True, "stopping": True, "reason": "the desk updated the backend to v1252"}
    assert raised == [stop.signal.SIGINT]
    assert "stopping at the desk's request -- the desk updated the backend to v1252" in caplog.text
