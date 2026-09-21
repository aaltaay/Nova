import { describe, expect, it } from 'vitest';
import { shouldRefreshSelection } from './simProgressiveReplay';
import type { HistoricalJob, HistoricalSelection } from './historicalTypes';

const W = { symbol: 'IMCC', date: '2026-09-18', start: '09:15', end: '11:30' };
const selection = (coverage: number): HistoricalSelection => ({ ...W, coverage_through: coverage });
const job = (over: Partial<HistoricalJob> = {}): HistoricalJob => ({
  id: 'j', kind: 'trades', status: 'running', count: 1000, pages: 1, error: null, cursor: 200, ...W, ...over,
});
const at = (sel: HistoricalSelection | null, jobs: HistoricalJob[], last = 0, now = 60_000) =>
  shouldRefreshSelection(sel, jobs, last, now, 10_000);

describe('shouldRefreshSelection', () => {
  it('folds in prints committed past what was loaded', () => {
    expect(at(selection(100), [job()])).toBe(true);
  });

  it('does nothing when the loaded coverage is already current', () => {
    expect(at(selection(200), [job()])).toBe(false);
  });

  it('throttles while the download runs, so a busy tape does not reload every poll', () => {
    expect(at(selection(100), [job()], 55_000, 60_000)).toBe(false);
  });

  it('takes the finished tail immediately, throttle or not', () => {
    expect(at(selection(100), [job({ status: 'complete' })], 59_000, 60_000)).toBe(true);
  });

  it("ignores another window's job, a bars job, and a stalled run", () => {
    expect(at(selection(100), [job({ date: '2026-09-17' })])).toBe(false);
    expect(at(selection(100), [job({ kind: 'bars' })])).toBe(false);
    expect(at(selection(100), [job({ stale: true })])).toBe(false);
    expect(at(selection(100), [job({ status: 'failed' })])).toBe(false);
  });

  it('does nothing with no selection', () => {
    expect(at(null, [job()])).toBe(false);
  });
});
