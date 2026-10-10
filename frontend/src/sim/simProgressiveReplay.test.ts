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

describe('shouldRefreshSelection with coverage ranges', () => {
  it('reloads when covered time grew, even though the cursor jumped backwards to backfill', () => {
    const sel = { ...selection(500), covered_seconds: 600 };
    expect(at(sel, [job({ cursor: 100, covered_seconds: 700 })])).toBe(true);
    expect(at(sel, [job({ cursor: 900, covered_seconds: 600 })])).toBe(false);
  });
});

describe('shouldRefreshSelection for a window from the Massive files (ADR 046)', () => {
  const massive = (over: Partial<HistoricalSelection> = {}): HistoricalSelection =>
    ({ ...W, coverage_through: 0, source: 'massive', covered_seconds: 0, trade_count: 0, quote_status: null, ...over });
  const imported = (over: Partial<HistoricalJob> = {}): HistoricalJob =>
    job({ source: 'massive', status: 'complete', count: 5, covered_seconds: 8100, quote_status: 'complete', quote_count: 4, ...over });

  it('reloads once the first import finishes, never while it runs', () => {
    expect(at(massive(), [imported({ status: 'running', covered_seconds: 0, count: 0 })])).toBe(false);
    expect(at(massive(), [imported()])).toBe(true);
  });

  it('reloads when an import added the bid/ask, and not again once loaded', () => {
    const loaded = massive({ covered_seconds: 8100, trade_count: 5, quote_status: 'not_downloaded', quote_count: 0 });
    expect(at(loaded, [imported({ status: 'running', quote_status: 'not_downloaded', quote_count: 0 })])).toBe(false);
    expect(at(loaded, [imported()])).toBe(true);
    expect(at({ ...loaded, quote_status: 'complete', quote_count: 4 }, [imported()])).toBe(false);
  });

  it('reloads when an import added the day around the window, and not again once loaded', () => {
    const loaded = massive({ covered_seconds: 8100, trade_count: 5, quote_status: 'complete', quote_count: 4, bar_count: 135 });
    expect(at(loaded, [imported({ bar_count: 135 })])).toBe(false);
    expect(at(loaded, [imported({ bar_count: 942 })])).toBe(true);
  });

  it("reads only its own source's job for the same hours", () => {
    expect(at(massive(), [job({ status: 'complete', covered_seconds: 8100 })])).toBe(false);
    expect(at(selection(100), [imported()])).toBe(false);
  });
});

describe('shouldRefreshSelection under a stock-day import (ADR 046 amendment, 2026-10-09)', () => {
  const DAY = { id: 'day', start: '04:00', end: '20:00', kept_start: '04:00', kept_end: '20:00' };
  const day = (over: Partial<HistoricalJob> = {}): HistoricalJob =>
    job({ ...DAY, source: 'massive', status: 'complete', count: 6, covered_seconds: 57_600, quote_status: 'complete',
      quote_count: 4, bar_count: 4, ...over });
  const loaded = (over: Partial<HistoricalSelection> = {}): HistoricalSelection =>
    ({ ...W, coverage_through: 0, source: 'massive', covered_seconds: 0, trade_count: 0, quote_status: null, ...over });

  it('a window loaded empty while the day imported moves onto the day once it holds it', () => {
    const empty = loaded({ job_id: 'day' });
    expect(at(empty, [day({ status: 'running', covered_seconds: 0, count: 0, kept_start: null, kept_end: null })])).toBe(false);
    expect(at(empty, [day()])).toBe(true);
  });

  it('an older import of the window moves onto the day, and the day loaded stays put', () => {
    const older = loaded({ job_id: 'old', covered_seconds: 8100, trade_count: 5, quote_status: 'complete', quote_count: 4 });
    const oldJob = job({ id: 'old', source: 'massive', status: 'complete', count: 5, covered_seconds: 8100,
      quote_status: 'complete', quote_count: 4 });
    expect(at(older, [oldJob])).toBe(false);
    expect(at(older, [day(), oldJob])).toBe(true);
    const whole = loaded({ ...DAY, job_id: 'day', covered_seconds: 57_600, trade_count: 6, quote_status: 'complete',
      quote_count: 4, bar_count: 4 });
    expect(at(whole, [day()])).toBe(false);
  });

  it('a capped day that kept another window does not move the loaded one', () => {
    const older = loaded({ job_id: 'old', covered_seconds: 8100, trade_count: 5 });
    const capped = day({ kept_start: '06:45', kept_end: '09:00', covered_seconds: 8100,
      capped: { what: 'prints', count: 812_345, limit: 500_000 } });
    expect(at(older, [capped])).toBe(false);
  });
});
