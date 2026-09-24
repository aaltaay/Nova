/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { AlertObject } from '../hod_momo/types';
import { addToWatchList, resetWatchListForTests } from './watchListStore';
import {
  dismissWatchToast,
  getWatchToasts,
  noteWatchedHodAlert,
  resetWatchToastsForTests,
  withWatchAlert,
} from './watchToasts';

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
    expect(toasts[0].alert.strategy_name).toBe('Squeeze');
  });

  it('keeps at most `max` toasts, dropping the oldest', () => {
    let toasts = withWatchAlert([], hodAlert('A'), 1, 2);
    toasts = withWatchAlert(toasts, hodAlert('B'), 2, 2);
    toasts = withWatchAlert(toasts, hodAlert('C'), 3, 2);
    expect(toasts.map(t => t.symbol)).toEqual(['C', 'B']);
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

  it('toasts a watched symbol only, never Running Up, and dismisses by symbol', () => {
    addToWatchList('GRML');
    expect(noteWatchedHodAlert(hodAlert('ONCO'))).toBe(false);
    expect(noteWatchedHodAlert(hodAlert('GRML', 12, 'Running Up'))).toBe(false);
    expect(getWatchToasts()).toEqual([]);
    expect(noteWatchedHodAlert(hodAlert('grml'))).toBe(true);
    expect(getWatchToasts().map(t => t.symbol)).toEqual(['GRML']);
    dismissWatchToast('GRML');
    expect(getWatchToasts()).toEqual([]);
  });
});
