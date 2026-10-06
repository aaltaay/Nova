"""GC policy (#619): the long-lived heap is frozen once, after startup settles."""
from __future__ import annotations

import asyncio
import gc
import logging

import pytest

from gc_policy import freeze


@pytest.fixture(autouse=True)
def _unfreeze():
    yield
    gc.unfreeze()                     # the rest of the suite keeps an ordinary collector


def test_freeze_moves_live_objects_out_of_full_collections(caplog):
    class ReleaseDuringLog(logging.Handler):
        def __init__(self):
            super().__init__()
            self.pending = [[], []]
            self.released = False

        def emit(self, _record):
            self.pending.clear()  # ordinary decref after the freeze-time snapshot
            self.released = True

    keep = [[i] for i in range(10_000)]
    keeper_ids = {id(keep)} | {id(obj) for obj in keep}
    handler = ReleaseDuringLog()
    with caplog.at_level(logging.INFO, logger=freeze.logger.name):
        freeze.logger.addHandler(handler)
        try:
            out = freeze.freeze_now()
            assert handler.released and handler.pending == []
            assert out["frozen"] >= 10_000
            active_ids = {id(obj) for obj in gc.get_objects()}
            assert keeper_ids.isdisjoint(active_ids)
            assert len(active_ids) < out["frozen"]
        finally:
            freeze.logger.removeHandler(handler)
            handler.close()
    del keep


def test_the_task_waits_then_freezes_once(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(freeze, "freeze_now", lambda: calls.append(1) or {"frozen": 1})
    asyncio.run(freeze.freeze_after_startup(delay_sec=0.01))
    assert calls == [1]


def test_switch_turns_it_off(monkeypatch):
    calls: list[int] = []
    monkeypatch.setenv("NOVA_GC_FREEZE", "0")
    monkeypatch.setattr(freeze, "freeze_now", lambda: calls.append(1) or {"frozen": 1})
    asyncio.run(freeze.freeze_after_startup(delay_sec=0.01))
    assert calls == []
    assert freeze.enabled() is False


def test_a_failed_freeze_is_logged_not_raised(monkeypatch, caplog):
    def _boom():
        raise RuntimeError("no")

    monkeypatch.setattr(freeze, "freeze_now", _boom)
    asyncio.run(freeze.freeze_after_startup(delay_sec=0.01))
    assert "gc policy: freeze failed" in caplog.text
