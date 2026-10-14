/** @vitest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SimClockState } from '../sim/simClockTypes';
import { withGappersBySecond } from './gappersBySecond';
import { replayFromAnswer } from './leaderboardRows';
import type { ScannerReplay } from './leaderboardTypes';
import { useGappersBySecond } from './useGappersBySecond';

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));

let clockState: { data: SimClockState | null; error: string | null } = { data: null, error: null };
const listeners = new Set<() => void>();
vi.mock('../sim/simClockResource', () => ({
  simClockResource: {
    subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); },
    getSnapshot: () => clockState,
  },
}));
const setClock = (time: string) => {
  clockState = {
    data: { sim: true, live_edge: false, paused: false, scrubbed: true, session_date: '2026-09-01',
      sim_time_et: `2026-09-01T${time}-04:00` } as SimClockState,
    error: null,
  };
  listeners.forEach(listener => listener());
};
const epoch = (time: string) => Date.parse(`2026-09-01T${time}-04:00`) / 1000;

const board = (source: 'reconstructed' | 'recorded'): ScannerReplay => replayFromAnswer('2026-09-01', epoch('07:45:00'), {
  date: '2026-09-01', at: epoch('07:45:00'), source, minute_ts: epoch('07:45:00'), covered: true, gap: null,
  boards: { gappers: { state: 'rebuilt', rows: [] } }, leaders: [], catalyst_symbols: 0,
});

let postAnswer: Record<string, unknown> = { status: 'queued' };
let readStatus = 'ready';
const calls = () => mocks.fetch.mock.calls.map(([url, init]) => `${(init as RequestInit | undefined)?.method ?? 'GET'} ${String(url)}`)
  .filter(call => call.includes('/seconds'));

beforeEach(() => {
  listeners.clear();
  postAnswer = { status: 'queued' };
  readStatus = 'ready';
  mocks.fetch.mockReset().mockImplementation(async (url: string, init?: RequestInit) => {
    const at = Number(new URL(url, 'http://x').searchParams.get('at'));
    const body = init?.method === 'POST' ? postAnswer : {
      date: '2026-09-01', status: readStatus, second_ts: at, minute_ts: at - (at % 60), state: 'rebuilt',
      rows: [{ symbol: 'KALA', rank: 1, price: 0.82, prev_close: 0.6727, change_pct: 0.219 }],
    };
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  });
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe('useGappersBySecond', () => {
  it('a recorded day asks nothing', async () => {
    setClock('07:45:58');
    const { result } = renderHook(() => useGappersBySecond(board('recorded')));
    await act(async () => {});
    expect(result.current.latest).toBeNull();
    expect(calls()).toEqual([]);
  });

  it('asks for the build once, then reads the list at each playhead second', async () => {
    setClock('07:45:58');
    const replay = board('reconstructed');
    const { result } = renderHook(() => useGappersBySecond(replay));
    await waitFor(() => expect(result.current.latest?.answer?.secondTs).toBe(epoch('07:45:58')));
    await act(async () => { setClock('07:45:59'); });
    await waitFor(() => expect(result.current.latest?.answer?.secondTs).toBe(epoch('07:45:59')));
    const posts = calls().filter(call => call.startsWith('POST'));
    expect(posts).toHaveLength(1);
    expect(posts[0]).toMatch(/^POST .*\/api\/leaderboard\/2026-09-01\/seconds$/);
    expect(calls().some(call => call.endsWith(`/seconds?at=${epoch('07:45:59')}`))).toBe(true);
    const shown = withGappersBySecond(replay, result.current.latest, result.current.second);
    expect(shown?.tables.gappers.map(r => r.symbol)).toEqual(['KALA']);
  });

  it('a day the backend cannot build keeps its reason and is not read', async () => {
    postAnswer = { status: 'unavailable', reason: 'The day\'s Massive trades file is not on disk' };
    setClock('07:45:58');
    const { result } = renderHook(() => useGappersBySecond(board('reconstructed')));
    await waitFor(() => expect(result.current.latest?.answer?.status).toBe('unavailable'));
    await act(async () => { setClock('07:46:10'); });
    expect(result.current.latest?.answer?.reason).toBe('The day\'s Massive trades file is not on disk');
    expect(calls().filter(call => call.startsWith('GET') && call.includes('/seconds?at=')).length).toBeLessThanOrEqual(1);
  });

  it('a build request that failed is asked again; only the backend refusing the day is final', async () => {
    let posts = 0;
    const answer = mocks.fetch.getMockImplementation();
    mocks.fetch.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && posts++ === 0) throw new TypeError('Failed to fetch');
      return answer?.(url, init);
    });
    setClock('07:45:58');
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { result } = renderHook(() => useGappersBySecond(board('reconstructed')));
    await waitFor(() => expect(result.current.latest?.error).toMatch(/Could not reach Nova/));
    await act(async () => { vi.advanceTimersByTime(2_100); });
    await waitFor(() => expect(posts).toBe(2));
    await waitFor(() => expect(result.current.latest?.error).toBeNull());
    expect(result.current.latest?.answer?.secondTs).toBe(epoch('07:45:58'));
  });

  it('while the build runs it reads again with the playhead paused', async () => {
    readStatus = 'building';
    setClock('07:45:58');
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { result } = renderHook(() => useGappersBySecond(board('reconstructed')));
    await waitFor(() => expect(result.current.latest?.answer?.status).toBe('building'));
    const before = calls().length;
    await act(async () => { vi.advanceTimersByTime(4_100); });
    await waitFor(() => expect(calls().length).toBeGreaterThan(before));
  });
});
