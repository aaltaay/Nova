/** @vitest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SimClockState } from '../sim/simClockTypes';
import { withScannerReplay } from './scannerReplayFeed';
import { playheadMinuteKey } from './simPlayhead';
import { useLeaderboardPlayback } from './useLeaderboardPlayback';

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), mode: 'sim' as string }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));
vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => ({ mode: mocks.mode }) }));

// A STABLE snapshot between reads (useSyncExternalStore), replaced and announced on each "poll".
let clockState: { data: SimClockState | null; error: string | null } = { data: null, error: null };
const listeners = new Set<() => void>();
vi.mock('../sim/simClockResource', () => ({
  simClockResource: {
    subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); },
    getSnapshot: () => clockState,
  },
}));
const setClock = (clock: SimClockState | null) => {
  clockState = { data: clock, error: null };
  listeners.forEach(listener => listener());
};

const clock = (time: string, over: Partial<SimClockState> = {}): SimClockState => ({
  sim: true, live_edge: false, paused: true, scrubbed: true, session_date: '2026-09-21',
  session_open_et: '2026-09-21T04:00:00-04:00', session_close_et: '2026-09-21T20:00:00-04:00',
  sim_time_et: `2026-09-21T${time}-04:00`, ...over,
});
const epoch = (time: string) => Date.parse(`2026-09-21T${time}-04:00`) / 1000;

const board = (minute: string, symbols: string[]) => ({
  schema_version: 1, date: '2026-09-21', source: 'recorded', minute_ts: epoch(`${minute}:00`), covered: true, gap: null,
  boards: { gainers: { state: 'live', rows: symbols.map((symbol, i) => ({ symbol, rank: i + 1, price: 5, prev_close: 4 })) } },
  leaders: { board: 'gainers', symbols: [], rules: {} },
});
let answers: Record<string, unknown> = {};
const boardCalls = () => mocks.fetch.mock.calls.map(([url]) => String(url)).filter(url => url.includes('/api/leaderboard/'));

beforeEach(() => {
  mocks.mode = 'sim';
  answers = {};
  listeners.clear();
  clockState = { data: null, error: null };
  mocks.fetch.mockReset().mockImplementation(async (url: string) => {
    const at = Number(new URL(url, 'http://x').searchParams.get('at'));
    const minute = new Date((Math.floor((at - 1) / 60) * 60) * 1000)
      .toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false }).slice(0, 5);
    const body = answers[minute] ?? board(minute, ['GRML']);
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  });
});
afterEach(() => cleanup());

describe('useLeaderboardPlayback', () => {
  it('Live and Paper stay live: no board, no request', async () => {
    mocks.mode = 'paper';
    setClock(clock('07:42:10'));
    const { result } = renderHook(() => useLeaderboardPlayback());
    await act(async () => {});
    expect(result.current).toBeNull();
    expect(boardCalls()).toEqual([]);
  });

  it('the Sim live edge stays live too', async () => {
    setClock(clock('07:42:10', { live_edge: true, paused: false, scrubbed: false }));
    const { result } = renderHook(() => useLeaderboardPlayback());
    await act(async () => {});
    expect(result.current).toBeNull();
    expect(boardCalls()).toEqual([]);
  });

  it('follows the playhead minute and never asks twice inside one minute', async () => {
    setClock(clock('07:42:10'));
    const { result } = renderHook(() => useLeaderboardPlayback());
    await waitFor(() => expect(result.current?.status).toBe('ready'));
    expect(boardCalls()).toHaveLength(1);
    expect(boardCalls()[0]).toContain(`/api/leaderboard/2026-09-21?at=${epoch('07:42:10')}`);
    expect(result.current?.tables.gainers.map(r => r.symbol)).toEqual(['GRML']);
    expect(result.current?.minuteTs).toBe(epoch('07:42:00'));

    for (const second of ['07:42:20', '07:42:40', '07:42:59', '07:43:00']) {
      await act(async () => { setClock(clock(second)); });
    }
    expect(boardCalls()).toHaveLength(1);

    answers['07:43'] = board('07:43', ['QNME']);
    await act(async () => { setClock(clock('07:43:02')); });
    await waitFor(() => expect(result.current?.tables.gainers.map(r => r.symbol)).toEqual(['QNME']));
    expect(boardCalls()).toHaveLength(2);
    expect(boardCalls()[1]).toContain(`at=${epoch('07:43:02')}`);
  });

  it('a gap shows no rows -- the earlier board is never carried across it', async () => {
    setClock(clock('07:42:10'));
    const { result } = renderHook(() => useLeaderboardPlayback());
    await waitFor(() => expect(result.current?.tables.gainers).toHaveLength(1));
    answers['09:20'] = {
      ...board('09:20', []), covered: false, minute_ts: null,
      gap: { reason: 'not_running', start: epoch('09:12:00'), end: epoch('09:31:00'), stop: null },
    };
    await act(async () => { setClock(clock('09:20:30')); });
    // A jump is not the next minute: nothing from 07:42 is shown while 09:20 loads, nor after.
    expect(result.current?.tables.gainers).toEqual([]);
    await waitFor(() => expect(result.current?.gap?.reason).toBe('not_running'));
    expect(result.current?.tables.gainers).toEqual([]);
  });

  it('keys only on the replaying clock, and the feed swap leaves a live feed untouched', () => {
    expect(playheadMinuteKey(false, clock('07:42:10'))).toBe('');
    expect(playheadMinuteKey(true, clock('07:42:10', { live_edge: true }))).toBe('');
    expect(playheadMinuteKey(true, clock('07:42:10'))).toBe(`2026-09-21|${epoch('07:42:00')}`);
    // The first settle second still reads the minute before (a recorded board is visible from m + 1 s).
    expect(playheadMinuteKey(true, clock('07:42:00'))).toBe(`2026-09-21|${epoch('07:41:00')}`);
    const live = {
      gappers: [], gainers: [], losers: [], afterhours: [], largeCap: [], catalysts: [], flashSymbols: {}, rowQuoteTs: {},
    };
    expect(withScannerReplay(live, null)).toBe(live);
  });
});
