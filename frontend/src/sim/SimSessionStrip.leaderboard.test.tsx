/** @vitest-environment jsdom */
import { act } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { leaderboardLane } from '../leaderboard/leaderboardLane';
import { SimSessionStrip } from './SimSessionStrip';
import type { SimClockState } from './simClockTypes';

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));
vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => ({ openStockView: vi.fn(), activeTraderSymbol: 'GRML' }),
}));
vi.mock('../workspace', () => ({
  useWorkspace: () => ({ openStockView: vi.fn(), activeTraderSymbol: 'GRML' }),
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
const DAYS = {
  schema_version: 1, store: { path: 'F:/Nova/leaderboard', ok: true, error: null },
  days: [
    { date: '2026-09-21', recorded: { minutes: 600, first_ts: 1, last_ts: 2, boards: ['gainers'] }, reconstructed: null },
    { date: '2026-09-18', recorded: { minutes: 900, first_ts: 1, last_ts: 2, boards: ['gainers'] },
      reconstructed: { minutes: 960, first_ts: 1, last_ts: 2 } },
    { date: '2026-09-17', recorded: null, reconstructed: { minutes: 960, first_ts: 1, last_ts: 2 } },
  ],
};
const coverage = (date: string) => ({
  date, source: 'recorded', session_open: epoch(date, '04:00'), session_close: epoch(date, '20:00'),
  spans: [[epoch(date, '04:00'), epoch(date, '09:12')], [epoch(date, '09:31'), epoch(date, '12:00')]],
  gaps: [{ start: epoch(date, '09:12'), end: epoch(date, '09:31'), reason: 'not_running' }],
});

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] });
  vi.setSystemTime(new Date('2026-09-21T22:14:07Z'));
  clock = edge;
  mocks.fetch.mockReset().mockImplementation(async (url: string, init?: RequestInit) => {
    const body = url.endsWith('/api/leaderboard/days') ? DAYS
      : url.includes('/coverage') ? coverage(url.match(/leaderboard\/([\d-]+)\/coverage/)![1])
        : url.endsWith('/history') ? { jobs: [], selection: null }
          : url.endsWith('/sessions') ? { days: [], tickers_by_day: {} }
            : init?.method === 'POST' && JSON.parse(String(init.body)).session_date ? parked
              : clock;
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  });
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

async function mount() { await act(async () => { render(<SimSessionStrip />); }); }
const posts = () => mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'POST')
  .map(([url, init]) => ({ path: String(url).split('/api/sim')[1], body: JSON.parse(String(init.body)) }));

describe('Sim strip: the Scanner board day and lane (ADR 022)', () => {
  it('lists days with a board, marked recorded / rebuilt, and posts session_date on a pick', async () => {
    await mount();
    const picker = screen.getByTestId('sim-strip-day') as HTMLSelectElement;
    const options = Array.from(picker.options).map(o => [o.value, o.textContent]);
    expect(options).toEqual([
      ['', 'Today'],
      ['2026-09-18', 'Sep 18 · rec + rebuilt'],
      ['2026-09-17', 'Sep 17 · rebuilt'],
    ]);
    await act(async () => { fireEvent.change(picker, { target: { value: '2026-09-18' } }); });
    expect(posts().at(-1)).toEqual({ path: '/clock', body: { session_date: '2026-09-18' } });
    expect((screen.getByTestId('sim-strip-day') as HTMLSelectElement).value).toBe('2026-09-18');
    await act(async () => { fireEvent.change(screen.getByTestId('sim-strip-day'), { target: { value: '' } }); });
    expect(posts().at(-1)).toEqual({ path: '/clock', body: { session_date: null } });
  });

  it('draws where the board was recorded and the gap as a gap, with its reason', async () => {
    clock = parked;
    await mount();
    expect(screen.getAllByTestId('sim-strip-leaderboard-span')).toHaveLength(2);
    const gap = screen.getByTestId('sim-strip-leaderboard-gap');
    expect(gap.title).toBe('Nova not running 09:12–09:31');
    // 09:12-09:31 of the 04:00-20:00 band.
    expect(parseFloat(gap.style.left)).toBeCloseTo((((9 * 60 + 12) - 240) / 960) * 100, 2);
    expect(parseFloat(gap.style.width)).toBeCloseTo((19 / 960) * 100, 2);
    expect(screen.getByTestId('sim-strip-leaderboard').closest('.sim-strip__track')?.getAttribute('title'))
      .toMatch(/Scanner board recorded 04:00–09:12, 09:31–12:00 ET\nNo board: Nova not running 09:12–09:31/);
    expect(mocks.fetch.mock.calls.some(([url]) => String(url).includes('/api/leaderboard/2026-09-18/coverage'))).toBe(true);
  });

  it('draws nothing for a day whose coverage has not answered, and nothing for another day', () => {
    const format = (ts: number) => new Date(ts * 1000).toISOString().slice(11, 16);
    expect(leaderboardLane(parked as SimClockState, null, format)).toBeNull();
    const other = { ...coverage('2026-09-17'), source: 'recorded' as const };
    expect(leaderboardLane(parked as SimClockState, other, format)).toBeNull();
  });
});
