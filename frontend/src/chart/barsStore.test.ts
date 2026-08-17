import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { chartBarsFetchPriority } from '../constants';
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

  it('ranks 10Sec behind 1Min and daily behind 5Min', () => {
    expect(chartBarsFetchPriority('1Min')).toBeLessThan(chartBarsFetchPriority('10Sec'));
    expect(chartBarsFetchPriority('5Min')).toBeLessThan(chartBarsFetchPriority('1Day'));
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

  it('ensureBarsBatch writes each timeframe via sequential /bars calls', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      const tf = new URL(url, 'http://local').searchParams.get('timeframe');
      const v = tf === '5Min' ? 101 : 100;
      return Promise.resolve({
        ok: true,
        json: async () => ({ bars: [{ ...bar(0), v }] }),
      });
    });
    const out = await ensureBarsBatch('NUWE', ['1Min', '5Min']);
    expect(out.results['1Min']).toHaveLength(1);
    expect(getBarsEntry('NUWE', '5Min')?.bars[0].v).toBe(101);
    expect(fetch).toHaveBeenCalledTimes(2);
    const urls = (fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => String(c[0]));
    expect(urls[0]).toContain('timeframe=1Min');
    expect(urls[1]).toContain('timeframe=5Min');
    expect(urls.some((u) => u.includes('/bars/batch'))).toBe(false);
  });

  it('serializes different timeframes and prefers 1Min over 10Sec', async () => {
    let releaseFive: (v: unknown) => void = () => {};
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      const tf = new URL(url, 'http://local').searchParams.get('timeframe');
      if (tf === '5Min') {
        return new Promise((resolve) => {
          releaseFive = resolve;
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ bars: [bar(0)] }),
      });
    });

    const p5 = ensureBars('AAPL', '5Min');
    const p10 = ensureBars('AAPL', '10Sec', undefined, 1500);
    const p1 = ensureBars('AAPL', '1Min');
    await Promise.resolve();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(String((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0])).toContain('5Min');

    releaseFive({
      ok: true,
      json: async () => ({ bars: [bar(0)] }),
    });
    await Promise.all([p5, p10, p1]);
    const urls = (fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => String(c[0]));
    expect(urls).toHaveLength(3);
    expect(urls[1]).toContain('1Min');
    expect(urls[2]).toContain('10Sec');
  });

  it('does not start a queued fetch after abort', async () => {
    let releaseFive: (v: unknown) => void = () => {};
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      const tf = new URL(url, 'http://local').searchParams.get('timeframe');
      if (tf === '5Min') {
        return new Promise((resolve) => {
          releaseFive = resolve;
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ bars: [bar(0)] }),
      });
    });
    const ac = new AbortController();
    const first = ensureBars('IPST', '5Min');
    const second = ensureBars('IPST', '10Sec', ac.signal, 1500);
    await Promise.resolve();
    ac.abort();
    releaseFive({
      ok: true,
      json: async () => ({ bars: [bar(0)] }),
    });
    await first;
    await expect(second).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('does not arm the 25s abort until the queued fetch starts', async () => {
    const setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout');
    let releaseFive: (v: unknown) => void = () => {};
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      const tf = new URL(url, 'http://local').searchParams.get('timeframe');
      if (tf === '5Min') {
        return new Promise((resolve) => {
          releaseFive = resolve;
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ bars: [bar(0)] }),
      });
    });
    const p5 = ensureBars('AAPL', '5Min');
    const p10 = ensureBars('AAPL', '10Sec', undefined, 1500);
    await Promise.resolve();
    const armed = setTimeoutSpy.mock.calls.filter((c) => c[1] === 25_000);
    expect(armed).toHaveLength(1);
    releaseFive({
      ok: true,
      json: async () => ({ bars: [bar(0)] }),
    });
    await Promise.all([p5, p10]);
    expect(setTimeoutSpy.mock.calls.filter((c) => c[1] === 25_000)).toHaveLength(2);
    setTimeoutSpy.mockRestore();
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
