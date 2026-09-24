/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { AlertObject } from '../hod_momo/types';
import type { SetupState } from '../setups';
import type { WatchSetupClimb, WatchSetupStage } from './setupClimbs';
import { setupRow } from './setupFixtures';
import { addToWatchList, resetWatchListForTests } from './watchListStore';
import {
  dismissWatchToast,
  getWatchToasts,
  noteWatchedHodAlert,
  noteWatchedSetupClimb,
  refreshWatchSetupLines,
  resetWatchToastsForTests,
  withSetupRows,
  withWatchAlert,
  withWatchSetup,
} from './watchToasts';

function climb(symbol: string, state: SetupState, stage: WatchSetupStage, setupType = 'first_pullback'): WatchSetupClimb {
  const row = setupRow(symbol, state, { setup_type: setupType, kind: setupType });
  return { symbol, setupType, stage, row, at: 1_790_000_900 };
}

function hodAlert(ticker: string, strategy_id = 1, strategy_name = 'New High of Day', id = `${ticker}-${strategy_id}`): AlertObject {
  return {
    id,
    timestamp: '2026-09-23T14:14:05Z',
    ticker,
    strategy_id,
    strategy_name,
    price: 4.52,
    change_pct: 38.2,
    rvol: 5.2,
    float_shares: 3_000_000,
    gap_pct: 20,
    volume: 2_100_000,
    momentum_pct: null,
    rvol_source: 'alpaca',
    consolidation_count: 1,
    consolidated_ids: [],
  };
}

describe('withWatchAlert', () => {
  it('folds a second alert for the same symbol into one toast and moves it to the top', () => {
    let toasts = withWatchAlert([], hodAlert('AAA'), 1_000);
    toasts = withWatchAlert(toasts, hodAlert('BBB'), 2_000);
    toasts = withWatchAlert(toasts, hodAlert('AAA', 3, 'Squeeze'), 3_000);
    expect(toasts.map(t => t.symbol)).toEqual(['AAA', 'BBB']);
    expect(toasts[0]).toEqual(expect.objectContaining({
      count: 2,
      lastAt: 3_000,
      strategies: ['Squeeze', 'New High of Day'],
    }));
    expect(toasts[0].alert?.strategy_name).toBe('Squeeze');
  });

  it('keeps at most `max` toasts, dropping the oldest', () => {
    let toasts = withWatchAlert([], hodAlert('A'), 1, 2);
    toasts = withWatchAlert(toasts, hodAlert('B'), 2, 2);
    toasts = withWatchAlert(toasts, hodAlert('C'), 3, 2);
    expect(toasts.map(t => t.symbol)).toEqual(['C', 'B']);
  });
});

describe('withWatchSetup', () => {
  it('folds setups and HOD alerts into one toast per symbol; the title follows the newest event', () => {
    let toasts = withWatchAlert([], hodAlert('GRML', 12, 'Running Up Alert'), 1_000);
    toasts = withWatchSetup(toasts, climb('GRML', 'leg', 'forming', 'bull_flag'), 2_000);
    toasts = withWatchSetup(toasts, climb('GRML', 'armed', 'armed'), 3_000);
    toasts = withWatchSetup(toasts, climb('GRML', 'near', 'near', 'bull_flag'), 4_000);
    expect(toasts).toHaveLength(1);
    const [toast] = toasts;
    expect(toast.head).toEqual({ kind: 'setup', setupType: 'bull_flag', stage: 'near', setupKind: 'bull_flag', at: 1_790_000_900 });
    // One line per setup, newest first; the HOD alert and its count stay.
    expect(toast.setups.map(l => [l.setupType, l.stage, l.row.state])).toEqual([
      ['bull_flag', 'near', 'near'],
      ['first_pullback', 'armed', 'armed'],
    ]);
    expect([toast.alert?.strategy_name, toast.count, toast.lastAt]).toEqual(['Running Up Alert', 1, 4_000]);

    const back = withWatchAlert(toasts, hodAlert('GRML'), 5_000);
    expect(back[0].head).toEqual({ kind: 'hod' });
    expect(back[0].setups).toHaveLength(2);
  });

  it('starts a setup-only toast with no alert', () => {
    const [toast] = withWatchSetup([], climb('PFSA', 'armed', 'armed'), 1);
    expect([toast.alert, toast.strategies, toast.count, toast.hod]).toEqual([null, [], 0, false]);
  });
});

describe('withSetupRows', () => {
  it('moves each line to the row the board lists now, and marks a line the board dropped', () => {
    const toasts = withWatchSetup(withWatchSetup([], climb('GRML', 'armed', 'armed'), 1), climb('ONCO', 'near', 'near'), 2);
    const next = withSetupRows(toasts, [setupRow('GRML', 'failed', { reason: 'gave back half the leg' })]);
    const grml = next.find(t => t.symbol === 'GRML')!;
    const onco = next.find(t => t.symbol === 'ONCO')!;
    expect([grml.setups[0].row.state, grml.setups[0].row.reason, grml.setups[0].listed])
      .toEqual(['failed', 'gave back half the leg', true]);
    expect([onco.setups[0].row.state, onco.setups[0].listed]).toEqual(['near', false]);
    // The climb that raised it and the timer are the toast's own.
    expect([grml.setups[0].stage, grml.lastAt, onco.lastAt]).toEqual(['armed', 1, 2]);
  });

  it('leaves toasts with no setup line alone', () => {
    const toasts = withWatchAlert([], hodAlert('GRML'), 1);
    expect(withSetupRows(toasts, [setupRow('GRML', 'armed')])).toBe(toasts);
  });
});

describe('noteWatchedHodAlert', () => {
  beforeEach(() => {
    localStorage.clear();
    resetWatchListForTests();
    resetWatchToastsForTests();
  });
  afterEach(() => {
    localStorage.clear();
    resetWatchListForTests();
    resetWatchToastsForTests();
  });

  it('toasts a watched symbol only -- Running Up included -- and dismisses by symbol', () => {
    addToWatchList('GRML');
    expect(noteWatchedHodAlert(hodAlert('ONCO'))).toBe(false);
    expect(getWatchToasts()).toEqual([]);
    expect(noteWatchedHodAlert(hodAlert('grml', 12, 'Running Up Alert'))).toBe(true);
    expect(getWatchToasts().map(t => [t.symbol, t.hod])).toEqual([['GRML', false]]);
    // A HOD Momo strategy folded in makes it a HOD toast, and it stays one.
    expect(noteWatchedHodAlert(hodAlert('GRML'))).toBe(true);
    expect(noteWatchedHodAlert(hodAlert('GRML', 12, 'Running Up Alert', 'again'))).toBe(true);
    expect(getWatchToasts().map(t => [t.symbol, t.hod, t.count])).toEqual([['GRML', true, 3]]);
    dismissWatchToast('GRML');
    expect(getWatchToasts()).toEqual([]);
  });

  it('toasts a watched symbol\'s setup climb only, and refreshes the lines on screen', () => {
    addToWatchList('GRML');
    expect(noteWatchedSetupClimb(climb('ONCO', 'armed', 'armed'))).toBe(false);
    expect(noteWatchedSetupClimb(climb('GRML', 'armed', 'armed'))).toBe(true);
    const before = getWatchToasts();
    refreshWatchSetupLines([setupRow('GRML', 'near')]);
    expect(getWatchToasts()).not.toBe(before);
    expect(getWatchToasts()[0].setups[0].row.state).toBe('near');
  });
});
