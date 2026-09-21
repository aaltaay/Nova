import { describe, expect, it } from 'vitest';
import { buildPracticeAccountView, dayPnlOf, isPracticeVenue, pnlTone, signedMoney } from './practiceAccountModel';
import { PAPER_ACCOUNT as PAPER } from './practiceFixtures';


describe('isPracticeVenue', () => {
  it('is true only for paper and sim', () => {
    expect(isPracticeVenue('paper')).toBe(true);
    expect(isPracticeVenue('sim')).toBe(true);
    expect(isPracticeVenue('live')).toBe(false);
    expect(isPracticeVenue('disconnected')).toBe(false);
    expect(isPracticeVenue(null)).toBe(false);
    expect(isPracticeVenue(undefined)).toBe(false);
  });
});

describe('buildPracticeAccountView', () => {
  it('formats the Paper strip with the account id, money and tooltips that name the venue', () => {
    const view = buildPracticeAccountView(PAPER);
    expect(view.accountId).toBe('NOVA-PAPER');
    expect(view.accountTitle).toMatch(/Paper practice account/);
    expect(view.accountTitle).toContain('$100,000.00');
    expect(view.cash.value).toBe('$98,750.50');
    expect(view.cash.title).toContain('$101,200.25');
    expect(view.buyingPower.value).toBe('$395,002.00');
    expect(view.buyingPower.title).toContain('$2,449.75');
    expect(view.dayPnl.value).toBe('+$250.25');
    expect(view.dayPnl.tone).toBe('global-app-bar__tone--up');
    expect(view.dayPnl.title).toContain('+$350.25');
    expect(view.dayPnl.title).toContain('-$100.00');
    expect(view.dayPnl.title).toContain('2026-09-21T04:00:00-04:00');
    expect(view.fees.value).toBe('$3.50');
    expect(view.fees.title).toContain('3 fills');
    expect(view.replay).toBeNull();
  });

  it('shows the replay key on Sim and states its absence rather than inventing one', () => {
    const loaded = buildPracticeAccountView({
      ...PAPER, venue: 'sim', account_id: 'NOVA-SIM', replay_key: 'capture:AAPL:2026-09-19',
    });
    expect(loaded.replay).toEqual(expect.objectContaining({ value: 'capture:AAPL:2026-09-19', loaded: true }));
    expect(loaded.accountTitle).toMatch(/Sim practice account/);
    const empty = buildPracticeAccountView({ ...PAPER, venue: 'sim', account_id: 'NOVA-SIM', replay_key: null });
    expect(empty.replay?.loaded).toBe(false);
    expect(empty.replay?.value).toBe('No replay loaded');
  });

  it('never fabricates a number: missing values render as the placeholder', () => {
    const view = buildPracticeAccountView({
      ...PAPER, cash: Number.NaN, buying_power: undefined as unknown as number,
      day_pnl: Number.NaN, realized_pnl: Number.NaN, unrealized_pnl: Number.NaN, fills_today: Number.NaN,
    });
    expect(view.cash.value).toBe('--');
    expect(view.buyingPower.value).toBe('--');
    expect(view.dayPnl.value).toBe('--');
    expect(view.dayPnl.tone).toBe('global-app-bar__tone--flat');
    expect(view.fees.title).toContain('0 fills');
  });
});

describe('dayPnlOf / signedMoney / pnlTone', () => {
  it('prefers the wire day_pnl and falls back to realized + unrealized', () => {
    expect(dayPnlOf({ day_pnl: 5, realized_pnl: 1, unrealized_pnl: 1 })).toBe(5);
    expect(dayPnlOf({ day_pnl: Number.NaN, realized_pnl: 2, unrealized_pnl: -0.5 })).toBe(1.5);
    expect(dayPnlOf({ day_pnl: Number.NaN, realized_pnl: Number.NaN, unrealized_pnl: 4 })).toBe(4);
    expect(dayPnlOf({ day_pnl: Number.NaN, realized_pnl: Number.NaN, unrealized_pnl: Number.NaN })).toBeNull();
  });
  it('signs and tones', () => {
    expect(signedMoney(-12.5)).toBe('-$12.50');
    expect(signedMoney(0)).toBe('$0.00');
    expect(signedMoney(null)).toBe('--');
    expect(pnlTone(-1)).toBe('global-app-bar__tone--down');
    expect(pnlTone(0)).toBe('global-app-bar__tone--flat');
  });
});
