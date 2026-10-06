"""Halt transitions reach served scanner rows without mutating their rosters (#571)."""
import asyncio
import copy
from dataclasses import asdict
import json
from types import SimpleNamespace

import pytest

import scanner_push
from ibkr import client, halt_status, nasdaq_halt_feed, ticks, ticks_handler
from runtime_state import get_runtime_state
from tests.test_scanner_row_halted import _item, _rss


class Socket:
    def __init__(self):
        self.frames = []

    async def send_text(self, text):
        self.frames.append(json.loads(text))


@pytest.fixture
def desk(monkeypatch):
    state = get_runtime_state()
    monkeypatch.setattr(state, 'gapper_cache', [{'symbol': 'HALT', 'price': 4.3}, {'symbol': 'UNKNOWN', 'price': 2.0}])
    monkeypatch.setattr(state, 'gainer_cache', [{'symbol': 'HALT', 'price': 4.4}, {'symbol': 'LINE', 'price': 3.0}])
    monkeypatch.setattr(state.gapper_table, 'state', 'frozen')
    sock = Socket()
    monkeypatch.setattr(scanner_push, '_clients', {sock})
    held = {}
    monkeypatch.setattr(client, 'is_ready', lambda: True)
    monkeypatch.setattr(ticks, 'get_ticker', lambda symbol: held.get(symbol))
    monkeypatch.setattr('leaderboard.halts.observe_ibkr', lambda *_a: None)
    halt_status.reset()
    nasdaq_halt_feed.reset()
    yield state, sock, held
    halt_status.reset()
    nasdaq_halt_feed.reset()


def test_tick49_transitions_and_first_clear_push_only_the_overlay(desk):
    state, sock, held = desk
    before = copy.deepcopy((state.gapper_cache, state.gainer_cache, asdict(state.gapper_table)))
    ticker = held['HALT'] = SimpleNamespace(halted=0)

    async def run():
        for code in (0, 2, 2, 0):
            ticker.halted = code
            ticks_handler._observe_halt('HALT', ticker)
            await asyncio.sleep(0)
    asyncio.run(run())
    assert [frame['rows'] for frame in sock.frames] == [
        [{'symbol': 'HALT', 'halted': False}],
        [{'symbol': 'HALT', 'halted': True}],
        [{'symbol': 'HALT', 'halted': False}],
    ]
    assert all(frame['type'] == 'halt_patch' and set(frame) == {'type', 'rows', 'ts'} for frame in sock.frames)
    assert (state.gapper_cache, state.gainer_cache, asdict(state.gapper_table)) == before


def test_rss_removal_failure_and_expiry_restate_every_current_symbol(desk, monkeypatch):
    _state, sock, held = desk
    held['LINE'] = SimpleNamespace(halted=0)
    now = 1_790_276_000.0
    monkeypatch.setattr('scanner_push.time_now', lambda: now)
    monkeypatch.setattr('ibkr.halt_status.time.time', lambda: now)
    nasdaq_halt_feed.refresh(now=now, xml_text=_rss(_item('HALT')))
    asyncio.run(halt_status.broadcast_live_halts())
    got = {row['symbol']: row['halted'] for row in sock.frames[-1]['rows']}
    assert got['HALT'] is True and got['UNKNOWN'] is False and got['LINE'] is False
    nasdaq_halt_feed.refresh(now=now + 1, xml_text=_rss())
    asyncio.run(halt_status.broadcast_live_halts())
    assert {r['symbol']: r['halted'] for r in sock.frames[-1]['rows']}['HALT'] is False
    nasdaq_halt_feed.refresh(now=now + 2, xml_text='not RSS')
    asyncio.run(halt_status.broadcast_live_halts())
    got = {r['symbol']: r['halted'] for r in sock.frames[-1]['rows']}
    assert got['HALT'] is None and got['UNKNOWN'] is None and got['LINE'] is False
    nasdaq_halt_feed.refresh(now=now - 10000, xml_text=_rss(_item('HALT')))
    asyncio.run(halt_status.broadcast_live_halts())
    assert {r['symbol']: r['halted'] for r in sock.frames[-1]['rows']}['HALT'] is None


def test_the_pinned_slotted_ticker_can_deliver_a_halt(desk):
    from ib_async import Ticker

    _state, sock, held = desk
    ticker = held['HALT'] = Ticker()
    # ib_async initializes its slots in __post_init__; incoming updates set them.
    ticker.halted = 2
    async def run():
        ticks_handler._observe_halt('HALT', ticker)
        await asyncio.sleep(0)
    asyncio.run(run())
    assert sock.frames[-1]['rows'] == [{'symbol': 'HALT', 'halted': True}]
