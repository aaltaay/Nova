/**
 * @vitest-environment jsdom
 *
 * The page's memory (ADR 053 amendment 2026-10-13 evening; operator: "when you close, it's pretty slow to load"):
 * the hook keeps its last answers for the life of the window, so the page opens again on the board it last showed
 * at once, then the next answer replaces it. Memory only: nothing is written to storage.
 */
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MARKET_KEPT_BOARDS } from './constants';
import { DEFAULT_PERIODS } from './periods';
import { sampleMarketBoard } from './sampleMarket';
import type { BlockPeriods, MarketBoard } from './types';
import { boardUrl, keptBoard, resetKeptBoardsForTests, useMarketBoard } from './useMarketBoard';

vi.mock('../sample_data/useSampleRoute', () => ({ useSampleRoute: () => false }));

function board(at: number, p: BlockPeriods = DEFAULT_PERIODS): MarketBoard {
  return { ...sampleMarketBoard(p), generated_at: at };
}

function respond(body: unknown, status = 200) {
  return Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) });
}

/** A fetch that answers when the test says so. */
function held() {
  const waiting: ((v: unknown) => void)[] = [];
  const fetchMock = vi.fn(() => new Promise((resolve) => { waiting.push(resolve); }));
  return { fetchMock, answer: (body: unknown, status = 200) => waiting.shift()?.(respond(body, status)) };
}

beforeEach(() => {
  resetKeptBoardsForTests();
  window.localStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('the Market page’s memory', () => {
  it('opens on nothing the first time, then the answer', async () => {
    vi.stubGlobal('fetch', vi.fn(() => respond(board(100))));
    const { result } = renderHook(() => useMarketBoard(DEFAULT_PERIODS));
    expect(result.current.data).toBeNull();
    await act(async () => {});
    expect(result.current.data?.generated_at).toBe(100);
  });

  it('opens again at once on the last answer, before the backend replies', async () => {
    vi.stubGlobal('fetch', vi.fn(() => respond(board(100))));
    const first = renderHook(() => useMarketBoard(DEFAULT_PERIODS));
    await act(async () => {});
    first.unmount();

    const { fetchMock, answer } = held();
    vi.stubGlobal('fetch', fetchMock);
    const again = renderHook(() => useMarketBoard(DEFAULT_PERIODS));
    expect(again.result.current.data?.generated_at).toBe(100);      // no "Reading the market" on the way back
    expect(fetchMock).toHaveBeenCalledTimes(1);                     // and it still asks
    await act(async () => { answer(board(200)); });
    expect(again.result.current.data?.generated_at).toBe(200);
  });

  it('shows a switch’s own last answer at once when the switch changes back', async () => {
    const weekly: BlockPeriods = { ...DEFAULT_PERIODS, climate: '7D' };
    vi.stubGlobal('fetch', vi.fn((url: string) => respond(board(url.includes('climate=7D') ? 70 : 10))));
    const { result, rerender } = renderHook(({ p }) => useMarketBoard(p), { initialProps: { p: DEFAULT_PERIODS } });
    await act(async () => {});
    rerender({ p: weekly });
    await act(async () => {});
    expect(result.current.data?.generated_at).toBe(70);

    const { fetchMock } = held();
    vi.stubGlobal('fetch', fetchMock);
    rerender({ p: DEFAULT_PERIODS });
    expect(result.current.data?.generated_at).toBe(10);           // the 1 D answer it had, not the 7 D one
  });

  it('keeps the newest answer for a switch it never saw', () => {
    expect(keptBoard(boardUrl(DEFAULT_PERIODS))).toBeNull();
    expect(keptBoard(null)).toBeNull();
  });

  it('keeps the last good answer and says so when a read fails', async () => {
    const fetchMock = vi.fn(() => respond(board(100)));
    vi.stubGlobal('fetch', fetchMock);
    const first = renderHook(() => useMarketBoard(DEFAULT_PERIODS));
    await act(async () => {});
    first.unmount();
    vi.stubGlobal('fetch', vi.fn(() => respond({}, 500)));
    const { result } = renderHook(() => useMarketBoard(DEFAULT_PERIODS));
    await act(async () => {});
    expect(result.current.data?.generated_at).toBe(100);
    expect(result.current.error).toContain('HTTP 500');
  });

  it('holds at most a bounded number of answers, the oldest let go first', async () => {
    let n = 0;
    vi.stubGlobal('fetch', vi.fn(() => { n += 1; return respond(board(n)); }));
    const periods = ['1D', '7D', '30D'] as const;
    const combos: BlockPeriods[] = [];
    for (const a of periods) for (const b of periods) {
      combos.push({ sectors: a, industries: b, climate: '1D', top: { kind: 'movers', period: '1D' } });
    }
    combos.push({ ...combos[0], climate: '7D' }, { ...combos[0], climate: '30D' }, { ...combos[0], top: { kind: 'biggest', period: '1D' } },
      { ...combos[0], top: { kind: 'runners', period: '7D' } });
    expect(combos.length).toBeGreaterThan(MARKET_KEPT_BOARDS);
    for (const p of combos) {
      const h = renderHook(() => useMarketBoard(p));
      await act(async () => {});
      h.unmount();
    }
    const newest = combos.length;
    // The first switches were let go: asking for them falls back to the newest answer, not their own.
    expect(keptBoard(boardUrl(combos[0]))?.generated_at).toBe(newest);
    // The last MARKET_KEPT_BOARDS are each still their own.
    combos.slice(-MARKET_KEPT_BOARDS).forEach((p, i) => {
      expect(keptBoard(boardUrl(p))?.generated_at).toBe(newest - MARKET_KEPT_BOARDS + 1 + i);
    });
  });

  it('never writes the board to storage', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    vi.stubGlobal('fetch', vi.fn(() => respond(board(100))));
    renderHook(() => useMarketBoard(DEFAULT_PERIODS));
    await act(async () => {});
    expect(setItem).not.toHaveBeenCalled();
    setItem.mockRestore();
  });
});
