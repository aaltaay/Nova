import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearBarsStoreForTests,
  ensureBars,
  ensureBarsBatch,
  getBarsEntry,
  isBarsEntryFresh,
  setBars,
  subscribeBars,
} from './barsStore';
import type { RawBar } from '../tickerChartData';

function bar(i: number): RawBar {
  return {
    t: `2026-07-29T14:0${i}:00Z`,
    o: 1,
    h: 2,
    l: 0.5,
    c: 1.5,
    v: 100 + i,
  };
}

describe('barsStore', () => {
  beforeEach(() => {
    clearBarsStoreForTests();
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    clearBarsStoreForTests();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('notifies subscribers when bars are set', () => {
    const spy = vi.fn();
    const unsub = subscribeBars('aapl', '1Min', spy);
    setBars('AAPL', '1Min', [bar(0)]);
    expect(spy).toHaveBeenCalledTimes(1);
    expect(getBarsEntry('AAPL', '1Min')?.bars).toHaveLength(1);
    unsub();
  });

  it('treats recent entries as fresh', () => {
    const entry = setBars('AAPL', '1Min', [bar(0)]);
    expect(isBarsEntryFresh(entry, 15_000)).toBe(true);
    expect(isBarsEntryFresh(entry, -1)).toBe(false);
  });

  it('dedupes in-flight ensureBars calls', async () => {
    let resolveFetch: (v: unknown) => void = () => {};
    const fetchPromise = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    (fetch as ReturnType<typeof vi.fn>).mockReturnValue(fetchPromise);

    const a = ensureBars('AAPL', '1Min');
    const b = ensureBars('AAPL', '1Min');
    expect(fetch).toHaveBeenCalledTimes(1);

    resolveFetch({
      ok: true,
      json: async () => ({ bars: [bar(0), bar(1)] }),
    });
    const [ra, rb] = await Promise.all([a, b]);
    expect(ra).toHaveLength(2);
    expect(rb).toHaveLength(2);
    expect(getBarsEntry('AAPL', '1Min')?.revision).toBe(1);
  });

  it('ensureBarsBatch writes each timeframe into the store', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({
        results: {
          '1Min': { bars: [bar(0)] },
          '5Min': { bars: [bar(1)] },
        },
        errors: {},
      }),
    });
    const out = await ensureBarsBatch('NUWE', ['1Min', '5Min']);
    expect(out.results['1Min']).toHaveLength(1);
    expect(getBarsEntry('NUWE', '5Min')?.bars[0].v).toBe(101);
  });

  it('ensureBars appends limit query param when provided', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ bars: [bar(0)] }),
    });
    await ensureBars('AAPL', '10Sec', undefined, 1500);
    const url = String((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]);
    expect(url).toContain('timeframe=10Sec');
    expect(url).toContain('limit=1500');
  });
});
