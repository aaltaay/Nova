"""The breaker chooses today's broker P&L and states any fallback (#664)."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from bot import day_pnl
from sim.mode import reset_for_tests, set_venue


@pytest.fixture
def live(monkeypatch):
    import ibkr
    reset_for_tests()
    set_venue('live', persist=False)
    day_pnl.reset_for_tests()
    daily = {'daily_pnl': 0.0, 'updated_at': 12.0, 'error': None}
    fake = SimpleNamespace(read=lambda: dict(daily))
    monkeypatch.setitem(sys.modules, 'ibkr.day_pnl', fake)
    monkeypatch.setattr(ibkr, 'day_pnl', fake, raising=False)
    monkeypatch.setattr('ibkr.account.get_account_summary',
                        lambda: {'connected': True, 'RealizedPnL': 0, 'UnrealizedPnL': -250})
    monkeypatch.setattr('execution.store_facts.session_commission_by_symbol', lambda **kw: {'TEST': 2})
    yield daily
    reset_for_tests()
    day_pnl.reset_for_tests()


@pytest.mark.parametrize('lifetime', [-250, 300])
def test_an_overnight_lifetime_move_is_not_today(live, monkeypatch, lifetime):
    monkeypatch.setattr('ibkr.account.get_account_summary',
                        lambda: {'connected': True, 'RealizedPnL': 0, 'UnrealizedPnL': lifetime})
    pnl, meter = day_pnl.read_account_day_pnl()
    assert pnl == 0.0
    assert meter['source'] == 'ibkr_daily_pnl' and meter['fallback'] is False
    assert meter['daily_pnl_updated_at'] == 12
    assert meter['reset_time'] is None and 'IBKR' in meter['reset_semantics']
    assert meter['commissions'] == 2 and meter['commissions_in_figure'] is True


def test_unavailable_daily_pnl_has_an_explicit_lifetime_summary_fallback(live):
    live.update(daily_pnl=None, updated_at=None, error='daily subscription pending')
    pnl, meter = day_pnl.read_account_day_pnl()
    assert pnl == -250
    assert meter['source'] == 'account_summary' and meter['fallback'] is True
    assert meter['fallback_reason'] == 'daily subscription pending'
    assert 'lifetime' in meter['compares']
    assert meter['reset_time'] is None


@pytest.mark.parametrize('invalid', [float('nan'), float('inf'), -float('inf')])
def test_neither_an_invalid_daily_nor_invalid_summary_is_a_usable_figure(live, monkeypatch, invalid):
    live.update(daily_pnl=invalid, error=None)
    monkeypatch.setattr('ibkr.account.get_account_summary',
                        lambda: {'connected': True, 'RealizedPnL': invalid, 'UnrealizedPnL': invalid})
    pnl, meter = day_pnl.read_account_day_pnl()
    assert pnl is None and meter['error']


def test_known_daily_pnl_survives_a_failed_summary_read(live, monkeypatch):
    live['daily_pnl'] = -12
    def failed():
        raise RuntimeError('accountValues failed')
    monkeypatch.setattr('ibkr.account.get_account_summary', failed)
    pnl, meter = day_pnl.read_account_day_pnl()
    assert pnl == -12 and meter['source'] == 'ibkr_daily_pnl' and meter['error'] is None
    assert 'accountValues failed' in meter['summary_error']


def test_unknown_commissions_preserve_pnl_and_the_existing_live_entry_hold(live, monkeypatch):
    live['daily_pnl'] = -40
    def failed(**kw):
        raise OSError('ledger unreadable')
    monkeypatch.setattr('execution.store_facts.session_commission_by_symbol', failed)
    pnl, meter = day_pnl.read_account_day_pnl()
    assert pnl == -40 and meter['commissions_unknown'] is True
    assert day_pnl.commission_hold('live') is not None
    assert day_pnl.commission_hold('paper') is None


def test_practice_reads_no_ibkr_daily_subscription(live, monkeypatch):
    import ibkr
    set_venue('paper', persist=False)
    monkeypatch.setattr(ibkr.day_pnl, 'read', lambda: pytest.fail('practice touched IBKR daily P&L'))
    monkeypatch.setattr('ibkr.account.get_account_summary', lambda: {'practice': True, 'DayPnL': -9})
    pnl, meter = day_pnl.read_account_day_pnl()
    assert pnl == -9 and meter['source'] == 'practice_ledger_day_pnl'


def test_overflowing_summary_sum_is_unknown(live, monkeypatch):
    live.update(daily_pnl=None, error='daily unavailable')
    monkeypatch.setattr('ibkr.account.get_account_summary',
                        lambda: {'RealizedPnL': 1e308, 'UnrealizedPnL': 1e308})
    assert day_pnl.read_account_day_pnl()[0] is None


def test_malformed_practice_summary_cannot_fall_through_to_live_pnl(live, monkeypatch):
    import ibkr
    set_venue('paper', persist=False)
    monkeypatch.setattr('ibkr.account.get_account_summary', lambda: {})
    monkeypatch.setattr(ibkr.day_pnl, 'read', lambda: pytest.fail('practice touched Live P&L'))
    pnl, meter = day_pnl.read_account_day_pnl()
    assert pnl is None and meter['source'] == 'practice_ledger_day_pnl'
