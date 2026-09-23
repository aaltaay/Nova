/** @vitest-environment jsdom */
import { act } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { resetNavRailStoreForTests, setNavPage } from '../workspace/navRailStore';
import { SimSessionHeader } from './SimSessionHeader';

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));
vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => ({ openStockView: vi.fn(), activeTraderSymbol: null, traderViewActive: false }),
}));

const epoch = (date: string, time: string) => Date.parse(`${date}T${time}:00-04:00`) / 1000;
const day = (date: string) => ({
  session_date: date, session_open_et: `${date}T04:00:00-04:00`, session_close_et: `${date}T20:00:00-04:00`,
});
const edge = { sim: true, replay_source: 'none', live_edge: true, minute_from_open: 854, minute_max: 960,
  sim_time_et: '2026-09-21T18:14:07-04:00', ...day('2026-09-21') };
const parked = { sim: true, replay_source: 'none', live_edge: false, paused: true, scrubbed: true, minute_from_open: 180,
  minute_max: 960, sim_time_et: '2026-09-18T07:00:00-04:00', ...day('2026-09-18') };

let clock: Record<string, unknown> = edge;
let sessions: Record<string, unknown> = { days: [], tickers_by_day: {} };
const DAYS = {
  schema_version: 1, store: { path: 'F:/Nova/leaderboard', ok: true, error: null },
  days: [
    { date: '2026-09-18', recorded: null, reconstructed: { minutes: 960, first_ts: 1, last_ts: 2 } },
  ],
};
const coverage = (date: string) => ({
  date, source: 'reconstructed', session_open: epoch(date, '04:00'), session_close: epoch(date, '20:00'),
  spans: [[epoch(date, '04:01'), epoch(date, '20:01')]],
  gaps: [{ start: epoch(date, '04:00'), end: epoch(date, '04:01'), reason: 'not_recorded' }],
});

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] });
  vi.setSystemTime(new Date('2026-09-21T22:14:07Z'));
  resetNavRailStoreForTests();
  setNavPage('dashboard');
  clock = edge;
  sessions = { days: [], tickers_by_day: {} };
  mocks.fetch.mockReset().mockImplementation(async (url: string, init?: RequestInit) => {
    const posted = init?.method === 'POST' ? JSON.parse(String(init.body)) : null;
    if (posted && 'session_date' in posted) clock = posted.session_date ? parked : edge;
    const body = url.endsWith('/api/leaderboard/days') ? DAYS
      : url.includes('/coverage') ? coverage(url.match(/leaderboard\/([\d-]+)\/coverage/)![1])
        : url.endsWith('/history') ? { jobs: [], selection: null }
          : url.endsWith('/sessions') ? sessions
            : clock;
    return { ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) };
  });
});
afterEach(() => { cleanup(); resetNavRailStoreForTests(); vi.useRealTimers(); });

const posts = () => mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'POST')
  .map(([url, init]) => ({ path: String(url).split('/api/sim')[1], body: JSON.parse(String(init.body)) }));

describe('Scanner Sim bar: watch a past day (ADR 023)', () => {
  it('offers the days with a board and moves Sim there with nothing loaded', async () => {
    await act(async () => { render(<SimSessionHeader active />); });
    await act(async () => { fireEvent.click(screen.getByTestId('sim-strip-day')); });
    const cell = screen.getByTestId('sim-day-cell-2026-09-18');
    expect(cell.dataset.rebuilt).toBe('1');
    await act(async () => { fireEvent.click(cell); });
    expect(posts().at(-1)).toEqual({ path: '/clock', body: { session_date: '2026-09-18' } });
  });

  it('marks the days the operator recorded a Session Record', async () => {
    sessions = { days: [{ date: '2026-09-18', ticker_count: 2 }], tickers_by_day: { '2026-09-18': [
      { symbol: 'GRML', prints: 10, l2: 5, usable: true, empty: false },
      { symbol: 'NULL', prints: 0, l2: 0, usable: false, empty: true },
    ] } };
    await act(async () => { render(<SimSessionHeader active />); });
    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    await act(async () => { fireEvent.click(screen.getByTestId('sim-strip-day')); });
    const cell = screen.getByTestId('sim-day-cell-2026-09-18');
    expect(cell.dataset.sessions).toBe('1');
    expect(cell.title).toContain('Your Session Records: GRML');
    expect(cell.title).not.toContain('NULL');
  });

  it('draws the board lane for the day under the scrubber', async () => {
    clock = parked;
    await act(async () => { render(<SimSessionHeader active />); });
    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    expect(screen.getAllByTestId('sim-scrubber-board-span')).toHaveLength(1);
    expect(screen.getByTestId('sim-scrubber-board-gap').title).toMatch(/04:00–04:01/);
  });
});
