import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearBarsStoreForTests,
  ensureBars,
  ensureBarsBatch,
  getBarsEntry,
  isBarsEntryFresh,
  parseBarsCoverage,
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

  it('parses coverage metadata from the API shape', () => {
    const cov = parseBarsCoverage({
      as_of: '2026-08-18T15:03:00Z',
      complete_through: '2026-08-18T15:03:00Z',
      filling: true,
      derived_from: '1Min',
    });
    expect(cov).toEqual({
      asOf: '2026-08-18T15:03:00Z',
      completeThrough: '2026-08-18T15:03:00Z',
      filling: true,
      derivedFrom: '1Min',
    });
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

  it('starts different timeframes in parallel', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      const tf = new URL(url, 'http://local').searchParams.get('timeframe');
      return Promise.resolve({
        ok: true,
        json: async () => ({
          bars: [bar(0)],
          coverage: { filling: tf === '5Min', as_of: '2026-08-18T14:00:00Z' },
        }),
      });
    });
    const p5 = ensureBars('AAPL', '5Min');
    const p1 = ensureBars('AAPL', '1Min');
    const p10 = ensureBars('AAPL', '10Sec', undefined, 1500);
    await Promise.resolve();
    expect(fetch).toHaveBeenCalledTimes(3);
    await Promise.all([p5, p1, p10]);
    expect(getBarsEntry('AAPL', '5Min')?.coverage?.filling).toBe(true);
    expect(getBarsEntry('AAPL', '1Min')?.coverage?.filling).toBe(false);
  });

  it('keeps the shared HTTP alive when one caller aborts', async () => {
    let resolveFetch: (v: unknown) => void = () => {};
    const fetchPromise = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    (fetch as ReturnType<typeof vi.fn>).mockReturnValue(fetchPromise);
    const ac = new AbortController();
    const aborted = ensureBars('AAPL', '1Min', ac.signal);
    const kept = ensureBars('AAPL', '1Min');
    ac.abort();
    resolveFetch({
      ok: true,
      json: async () => ({ bars: [bar(0), bar(1)] }),
    });
    await expect(aborted).rejects.toMatchObject({ name: 'AbortError' });
    await expect(kept).resolves.toHaveLength(2);
    expect(getBarsEntry('AAPL', '1Min')?.bars).toHaveLength(2);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('does not start a fetch after abort', async () => {
    const ac = new AbortController();
    ac.abort();
    await expect(ensureBars('IPST', '10Sec', ac.signal, 1500)).rejects.toMatchObject({
      name: 'AbortError',
    });
    expect(fetch).not.toHaveBeenCalled();
  });

  it('ensureBarsBatch writes each timeframe via /bars (not /bars/batch)', async () => {
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
    expect(urls.some((u) => u.includes('/bars/batch'))).toBe(false);
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
