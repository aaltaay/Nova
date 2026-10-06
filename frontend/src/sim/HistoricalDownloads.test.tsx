/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { HistoricalDownloads } from './HistoricalDownloads';
import { currentJob, jobSummary } from './historicalProgress';
import type { HistoricalJob } from './historicalTypes';

const START = Date.parse('2026-09-21T13:15:00Z') / 1000;
const job = (over: Partial<HistoricalJob> = {}): HistoricalJob => ({
  id: 'j', kind: 'trades', status: 'running', count: 10, pages: 1, error: null,
  symbol: 'GRML', date: '2026-09-21', start: '09:15', end: '11:30', start_ts: START, end_ts: START + 8100,
  progress_pct: 10, downloaded_through: START + 810, covered_seconds: 810, ...over,
});

afterEach(cleanup);

describe('HistoricalDownloads', () => {
  it('a job without a count reads "--", never a crash that replaces the desk (C7)', () => {
    render(<HistoricalDownloads jobs={[job({ count: null, pages: null })]} busy={new Set()} onPick={() => {}} onAction={() => {}} />);
    expect(screen.getByRole('status').textContent).toMatch(/trades: -- prints {2}- {2}-- pages/);
  });

  it('a failed or empty job says nothing was downloaded, not "through 09:15" (C45)', () => {
    render(<HistoricalDownloads
      jobs={[job({ status: 'failed', error: 'IBKR did not answer', progress_pct: 0, downloaded_through: START, covered_seconds: 0 })]}
      busy={new Set()} onPick={() => {}} onAction={() => {}} />);
    const item = screen.getByRole('listitem');
    expect(item.textContent).toMatch(/Nothing downloaded yet\./);
    expect(item.textContent).not.toMatch(/Downloaded through/);
    expect(screen.getByRole('status').textContent).toMatch(/GRML failed · nothing downloaded/);
  });

  it('a failed job offers a retry, never a "resume" of nothing (R28)', () => {
    render(<HistoricalDownloads jobs={[job({ status: 'failed', error: 'Ticker could not be uniquely qualified by IBKR' })]}
      busy={new Set()} onPick={() => {}} onAction={() => {}} />);
    expect(screen.getByRole('button', { name: /^Retry download:/ }).textContent).toBe('Retry download');
    expect(screen.queryByRole('button', { name: /^Resume download:/ })).toBeNull();
  });

  it('a finished candle download reads complete at 100%, through the window end (C40)', () => {
    render(<HistoricalDownloads
      jobs={[job({ kind: 'bars', status: 'complete', progress_pct: 100, downloaded_through: START + 8100, covered_seconds: 8100 })]}
      busy={new Set()} onPick={() => {}} onAction={() => {}} />);
    expect(screen.getByRole('status').textContent).toMatch(/GRML complete 100%/);
    expect(screen.getByRole('listitem').textContent).toMatch(/Downloaded through 11:30:00 ET/);
  });
});

describe('currentJob -- the Sim bar summary states the current download only (V41)', () => {
  it('prefers the job a worker is advancing', () => {
    const running = job({ id: 'run' });
    expect(currentJob([job({ id: 'old', status: 'failed', age_seconds: 99 }), running])).toBe(running);
  });

  it('names a stopped, failed or finished job only while it is recent', () => {
    const fresh = job({ id: 'f', status: 'failed', error: 'x', age_seconds: 60 });
    expect(currentJob([fresh])).toBe(fresh);
    const stale = job({ id: 's', status: 'failed', error: 'x', age_seconds: 3 * 3600 });
    expect(currentJob([stale])).toBeNull();
    expect(currentJob([job({ status: 'complete', age_seconds: 3 * 3600 })])).toBeNull();
    // An older API without an age keeps naming it.
    expect(currentJob([job({ status: 'complete', age_seconds: undefined })])?.status).toBe('complete');
    expect(currentJob([])).toBeNull();
  });

  it('jobSummary keeps its percent while a job runs, even at 0%', () => {
    expect(jobSummary(job({ progress_pct: 0, covered_seconds: 0 }))).toBe('GRML running 0%');
  });
});

describe('an import from the Massive files (ADR 046)', () => {
  const imported = (over: Partial<HistoricalJob> = {}) => job({
    source: 'massive', pages: 0, count: 0, progress_pct: 42, stage: 'reading',
    stages: { trades_v1: 64, minute_aggs_v1: 100, quotes_v1: 12 }, ...over,
  });

  it('reads each file while it runs, with no pages and no "downloaded through"', () => {
    render(<HistoricalDownloads jobs={[imported()]} busy={new Set()} onPick={() => {}} onAction={() => {}} />);
    expect(screen.getByRole('status').textContent).toBe('GRML importing 42%  -  Massive files');
    const item = screen.getByRole('listitem');
    expect(item.textContent).toMatch(/Reading trades 64% · bars 100% · bid\/ask 12%\./);
    expect(item.textContent).not.toMatch(/pages|Downloaded through/);
    expect(screen.getByRole('button', { name: /^Stop import:/ })).toBeTruthy();
  });

  it('says what a finished import holds, and offers to import a stopped one again', () => {
    render(<HistoricalDownloads busy={new Set()} onPick={() => {}} onAction={() => {}} jobs={[
      imported({ status: 'complete', count: 5120, bar_count: 135, quote_status: 'not_downloaded', progress_pct: 100 }),
      imported({ id: 'k', status: 'failed', error: 'disk read failed' }),
    ]} />);
    const [done, failed] = screen.getAllByRole('status');
    expect(done.textContent).toBe('GRML imported  -  Massive files: 5,120 prints · 135 bars · bid/ask not downloaded yet');
    expect(failed.textContent).toBe('GRML failed  -  Massive files');
    expect(screen.getAllByRole('button', { name: /^Import again:/ })).toHaveLength(1);
    expect(jobSummary(imported({ status: 'running', stale: true }))).toBe('GRML stopped by a restart');
  });
});
