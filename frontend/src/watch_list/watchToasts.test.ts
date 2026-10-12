/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AlertObject } from '../hod_momo/types';
import { fakeHotList } from '../hot_list/hotListFake';
import type { HotListView } from '../hot_list';
import type { SetupState } from '../setups';
import type { WatchSetupClimb, WatchSetupStage } from './setupClimbs';
import { setupRow } from './setupFixtures';
import { getToastScores, resetToastScoresForTests } from './toastScores';
import { resetToastWindowForTests } from './toastWindow';
import { WATCH_TOAST_QUIET_MS } from './watchListConstants';
import { resetWatchListForTests } from './watchListStore';
import {
  dismissWatchToast,
  freshJoins,
  getWatchToasts,
  noteHotListJoins,
  noteWatchedHodAlert,
  noteWatchedSetupClimb,
  refreshWatchSetupLines,
  resetWatchToastsForTests,
  withSetupRows,
  withWatchAlert,
  withWatchJoin,
  withWatchSetup,
} from './watchToasts';

vi.mock('../hot_list', async () => (await import('../hot_list/hotListFake')).hotListFakeModule());

/** 2026-09-23 10:14:05 ET: inside the default 07:00-16:00 window. */
const IN_HOURS = Date.UTC(2026, 8, 23, 14, 14, 5);
/** 18:00 ET the same day: after it. */
const AFTER_HOURS = Date.UTC(2026, 8, 23, 22, 0, 0);

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

function reset(): void {
  localStorage.clear();
  resetWatchListForTests();
  resetWatchToastsForTests();
  resetToastScoresForTests();
  resetToastWindowForTests();
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

  it('in the quiet period only updates the toast on screen: its title, place and timer stay', () => {
    let toasts = withWatchSetup([], climb('GRML', 'armed', 'armed'), 1_000);
    toasts = withWatchAlert(toasts, hodAlert('ONCO'), 2_000);
    const quiet = withWatchAlert(toasts, hodAlert('GRML', 3, 'Squeeze'), 3_000, 4, false);
    expect(quiet.map(t => t.symbol)).toEqual(['ONCO', 'GRML']);
    const grml = quiet[1];
    expect([grml.head.kind, grml.lastAt, grml.count, grml.strategies]).toEqual(['setup', 1_000, 1, ['Squeeze']]);
    expect(withWatchAlert([], hodAlert('GRML'), 1, 4, false)).toEqual([]);   // nothing on screen: nothing to fold into
  });
});

describe('withWatchSetup and withWatchJoin', () => {
  it('folds setups and HOD alerts into one toast per symbol; the title follows the newest event', () => {
    let toasts = withWatchAlert([], hodAlert('GRML'), 1_000);
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
    expect([toast.alert?.strategy_name, toast.count, toast.lastAt]).toEqual(['New High of Day', 1, 4_000]);

    const back = withWatchAlert(toasts, hodAlert('GRML', 2, 'Squeeze'), 5_000);
    expect(back[0].head).toEqual({ kind: 'hod' });
    expect(back[0].setups).toHaveLength(2);
  });

  it('starts a setup-only toast with no alert, and a join toast with its rank', () => {
    const [toast] = withWatchSetup([], climb('PFSA', 'armed', 'armed'), 1);
    expect([toast.alert, toast.strategies, toast.count, toast.join]).toEqual([null, [], 0, null]);
    const [joined] = withWatchJoin([], 'gixi', { rank: 1, n: 3, changePct: 0.72, at: 1_790_000_000 }, 2);
    expect([joined.symbol, joined.head, joined.join?.rank, joined.lastAt]).toEqual(['GIXI', { kind: 'join' }, 1, 2]);
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

describe('freshJoins', () => {
  const view = (entries: HotListView['entries']): HotListView => ({
    schema_version: 1, date: '2026-09-23', cap: 20, auto_cap: 20,
    auto: { n: 3, start: '07:00', end: '16:00', rule: null, error: null }, entries, yesterday: [], error: null,
  });
  const at = (ms: number) => ms / 1000;
  const entry = (symbol: string, how: 'auto' | 'star', atS: number) => ({
    symbol, how, at: atS, board: how === 'auto' ? 'gainers' : null, rank: 2, change_pct: 0.4, followed: true,
    why_not_followed: null,
  });

  it('is the auto stars that joined in the last two minutes, with the board they came from', () => {
    const v = view([
      entry('NEW', 'auto', at(IN_HOURS - 30_000)),
      entry('OLD', 'auto', at(IN_HOURS - 10 * 60_000)),
      entry('MINE', 'star', at(IN_HOURS - 10_000)),
    ]);
    expect(freshJoins(v, IN_HOURS)).toEqual([{ symbol: 'NEW', join: { rank: 2, n: 3, changePct: 0.4, at: at(IN_HOURS - 30_000) } }]);
    expect(freshJoins(null, IN_HOURS)).toEqual([]);
  });
});

describe('which events toast (ADR 044 amendment, 2026-10-12)', () => {
  beforeEach(() => {
    reset();
    // The day's record is today's: the desk's clock on the events' day.
    vi.useFakeTimers({ now: IN_HOURS, toFake: ['Date'] });
  });
  afterEach(() => {
    vi.useRealTimers();
    reset();
  });

  it('a star toasts on HOD Momo; Running Up, an auto star and an unlisted name do not', () => {
    fakeHotList.set(['GRML', { symbol: 'AUTO', how: 'auto' }]);
    expect(noteWatchedHodAlert(hodAlert('ONCO'), IN_HOURS)).toBe(false);
    expect(noteWatchedHodAlert(hodAlert('grml', 12, 'Running Up Alert'), IN_HOURS)).toBe(false);
    expect(noteWatchedHodAlert(hodAlert('AUTO'), IN_HOURS)).toBe(false);
    expect(getWatchToasts()).toEqual([]);
    expect(noteWatchedHodAlert(hodAlert('GRML'), IN_HOURS)).toBe(true);
    expect(getWatchToasts().map(t => [t.symbol, t.head.kind])).toEqual([['GRML', 'hod']]);
    const day = getToastScores();
    expect(day.toasts.map(t => [t.symbol, t.kind, t.price])).toEqual([['GRML', 'hod', 4.52]]);
    expect(day.held).toEqual({ running_up: 1, auto_star: 1 });         // an unlisted name is not counted
  });

  it('keeps a stock quiet after its toast: folds while it shows, holds after, toasts again 15 minutes on', () => {
    fakeHotList.set(['GRML']);
    expect(noteWatchedHodAlert(hodAlert('GRML'), IN_HOURS)).toBe(true);
    expect(noteWatchedHodAlert(hodAlert('GRML', 3, 'Squeeze'), IN_HOURS + 5_000)).toBe(true);
    expect(getWatchToasts().map(t => [t.count, t.lastAt])).toEqual([[2, IN_HOURS]]);   // folded: the timer stays
    dismissWatchToast('GRML');
    expect(noteWatchedHodAlert(hodAlert('GRML'), IN_HOURS + 60_000)).toBe(false);
    expect(getToastScores().held).toEqual({ quiet: 1 });
    expect(noteWatchedHodAlert(hodAlert('GRML'), IN_HOURS + WATCH_TOAST_QUIET_MS)).toBe(true);
    expect(getToastScores().toasts).toHaveLength(2);
  });

  it('a setup toasts from armed up, through the quiet period; forming never toasts', () => {
    fakeHotList.set(['GRML']);
    expect(noteWatchedSetupClimb(climb('GRML', 'leg', 'forming'), IN_HOURS)).toBe(false);
    expect(noteWatchedSetupClimb(climb('GRML', 'armed', 'armed'), IN_HOURS)).toBe(true);
    expect(noteWatchedSetupClimb(climb('GRML', 'near', 'near'), IN_HOURS + 30_000)).toBe(true);
    expect(getToastScores().toasts.map(t => [t.kind, t.price])).toEqual([['armed', 4.35], ['near', 4.35]]);
    expect(getToastScores().held).toEqual({ forming: 1 });
    const before = getWatchToasts();
    refreshWatchSetupLines([setupRow('GRML', 'triggered')]);
    expect(getWatchToasts()).not.toBe(before);
    expect(getWatchToasts()[0].setups[0].row.state).toBe('triggered');
  });

  it('nothing toasts outside the trading window', () => {
    fakeHotList.set(['GRML']);
    expect(noteWatchedHodAlert(hodAlert('GRML'), AFTER_HOURS)).toBe(false);
    expect(noteWatchedSetupClimb(climb('GRML', 'armed', 'armed'), AFTER_HOURS)).toBe(false);
    expect(getToastScores().held).toEqual({ outside_window: 2 });
  });

  it('an auto star toasts once, when it joins', () => {
    fakeHotList.set([{ symbol: 'GIXI', how: 'auto' }, 'MINE']);
    const view: HotListView = {
      schema_version: 1, date: '2026-09-23', cap: 20, auto_cap: 20,
      auto: { n: 3, start: '07:00', end: '16:00', rule: null, error: null },
      entries: [
        { symbol: 'GIXI', how: 'auto', at: (IN_HOURS - 20_000) / 1000, board: 'gainers', rank: 1, change_pct: 0.72,
          followed: true, why_not_followed: null },
        { symbol: 'MINE', how: 'star', at: (IN_HOURS - 20_000) / 1000, board: null, rank: null, change_pct: null,
          followed: true, why_not_followed: null },
      ],
      yesterday: [], error: null,
    };
    expect(noteHotListJoins(view, IN_HOURS)).toEqual(['GIXI']);
    expect(noteHotListJoins(view, IN_HOURS + 10_000)).toEqual([]);              // once a day
    expect(getWatchToasts().map(t => [t.symbol, t.head.kind, t.join?.n])).toEqual([['GIXI', 'join', 3]]);
    expect(getToastScores().toasts.map(t => [t.symbol, t.kind, t.price])).toEqual([['GIXI', 'join', null]]);
  });
});
