/** @vitest-environment jsdom */
import { act } from 'react';
import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useProgressiveReplay } from './useProgressiveReplay';
import { historicalStatus } from './historicalStatusStore';
import { SIM_CLOCK_SCRUB_EVENT } from './simClockEvents';
import type { HistoricalJob } from './historicalTypes';

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));

const W = { symbol: 'IMCC', date: '2026-09-18', start: '09:15', end: '11:30' };
const running: HistoricalJob = {
  id: 'j', kind: 'trades', status: 'running', count: 3000, pages: 3, error: null, cursor: 500, ...W,
};
const response = (body: unknown) => ({ ok: true, json: async () => body });
let posts: string[] = [];

beforeEach(() => {
  posts = [];
  mocks.fetch.mockReset().mockImplementation(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      posts.push(url);
      return response({ ...W, coverage_through: 500, trade_count: 3000 });
    }
    return response({ jobs: [running], selection: { ...W, coverage_through: 100 } });
  });
});
afterEach(() => vi.restoreAllMocks());

describe('useProgressiveReplay', () => {
  it('re-selects quietly as prints land -- no scrub, so chart zoom survives', async () => {
    const scrubs = vi.fn();
    window.addEventListener(SIM_CLOCK_SCRUB_EVENT, scrubs);
    const { unmount } = renderHook(() => useProgressiveReplay(true));
    await act(async () => {
      historicalStatus.setData({ jobs: [running], selection: { ...W, coverage_through: 100 } });
    });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(posts.filter(url => url.endsWith('/history/select'))).toHaveLength(1);
    expect(scrubs).not.toHaveBeenCalled();
    expect(historicalStatus.getSnapshot().data?.selection?.coverage_through).toBe(500);
    window.removeEventListener(SIM_CLOCK_SCRUB_EVENT, scrubs);
    unmount();
  });

  it('stays idle outside Sim', async () => {
    const { unmount } = renderHook(() => useProgressiveReplay(false));
    await act(async () => { await Promise.resolve(); });
    expect(mocks.fetch).not.toHaveBeenCalled();
    unmount();
  });
});
