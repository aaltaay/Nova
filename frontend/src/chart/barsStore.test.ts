import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  applyBarsPatch,
  clearBarsStoreForTests,
  ensureBars,
  ensureBarsBatch,
  getBarsEntry,
  invalidateBars,
  isBarsEntryFresh,
  parseBarsCoverage,
  setBars,
  subscribeBars,
  upsertTapePrint10SecBar,
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
    const networkSignal = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].signal as AbortSignal;
    expect(networkSignal).not.toBe(ac.signal);
    expect(networkSignal.aborted).toBe(false);
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

  it('merges live tape prints into the current 10Sec bucket', () => {
    expect(upsertTapePrint10SecBar('spci', {
      time: '2026-09-11T13:29:55.000Z',
      price: 150,
      size: 100,
    })).toBe(true);
    expect(upsertTapePrint10SecBar('SPCI', {
      time: '2026-09-11T13:29:58.000Z',
      price: 149.5,
      size: 40,
    })).toBe(true);

    expect(getBarsEntry('SPCI', '10Sec')?.bars).toEqual([
      {
        t: '2026-09-11T13:29:50.000Z',
        o: 150,
        h: 150,
        l: 149.5,
        c: 149.5,
        v: 140,
      },
    ]);
  });

  it('keeps a volume-only print (odd lot, average price) out of the 10Sec candle', () => {
    // PLTR 2026-09-23: a FINRA `4 W` print $2.40 under the market drew a wick.
    upsertTapePrint10SecBar('PLTR', { time: '2026-09-23T13:45:01.000Z', price: 192.75, size: 200 });
    expect(upsertTapePrint10SecBar('PLTR', {
      time: '2026-09-23T13:45:02.000Z',
      price: 190.38,
      size: 100,
      setsPrice: false,
    })).toBe(false);
    upsertTapePrint10SecBar('PLTR', {
      time: '2026-09-23T13:45:03.000Z', price: 192.8, size: 100, setsPrice: true,
    });

    expect(getBarsEntry('PLTR', '10Sec')?.bars).toEqual([
      { t: '2026-09-23T13:45:00.000Z', o: 192.75, h: 192.8, l: 192.75, c: 192.8, v: 300 },
    ]);
  });

  it('does not let a late empty HTTP response erase a live tape candle', async () => {
    let resolveFetch: (v: unknown) => void = () => {};
    (fetch as ReturnType<typeof vi.fn>).mockReturnValue(new Promise((resolve) => {
      resolveFetch = resolve;
    }));
    const request = ensureBars('SPCI', '10Sec', undefined, 1500);

    upsertTapePrint10SecBar('SPCI', {
      time: '2026-09-11T13:29:55.000Z',
      price: 150,
      size: 100,
    });
    resolveFetch({
      ok: true,
      json: async () => ({ bars: [], coverage: { filling: true } }),
    });

    await expect(request).resolves.toHaveLength(1);
    expect(getBarsEntry('SPCI', '10Sec')?.bars).toHaveLength(1);
  });

  it('does not let an empty bars_patch wipe a painted pane', () => {
    setBars('NNNN', '1Min', [bar(0), bar(1)], parseBarsCoverage({ filling: true }));

    applyBarsPatch('NNNN', '1Min', [], parseBarsCoverage({ filling: false }));

    const entry = getBarsEntry('NNNN', '1Min');
    expect(entry?.bars).toHaveLength(2);
    expect(entry?.coverage?.filling).toBe(true);
  });

  it('applies a bars_patch that carries bars, and an empty one to an empty pane', () => {
    applyBarsPatch('NNNN', '1Day', [], parseBarsCoverage({ filling: false }));
    expect(getBarsEntry('NNNN', '1Day')?.bars).toEqual([]);

    applyBarsPatch('NNNN', '5Min', [bar(2)], parseBarsCoverage({ filling: false }));
    expect(getBarsEntry('NNNN', '5Min')?.bars).toEqual([bar(2)]);
  });

  it('cancels the obsolete network on seek without losing its replacement', async () => {
    const requests: { signal: AbortSignal; resolve: (value: unknown) => void }[] = [];
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((_url: string, init: RequestInit) => new Promise((resolve, reject) => {
      const signal = init.signal as AbortSignal;
      requests.push({ signal, resolve });
      signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    }));
    const old = ensureBars('AAPL', '1Min');
    const oldRejected = expect(old).rejects.toMatchObject({ name: 'AbortError' });
    invalidateBars('AAPL', '1Min');
    const next = ensureBars('AAPL', '1Min');
    expect(requests[0].signal.aborted).toBe(true);
    expect(requests[1].signal.aborted).toBe(false);
    await oldRejected;
    // Completion of the canceled request must not remove the new in-flight entry.
    const shared = ensureBars('AAPL', '1Min');
    expect(fetch).toHaveBeenCalledTimes(2);
    requests[1].resolve({ ok: true, json: async () => ({ bars: [bar(1)] }) });
    await expect(next).resolves.toEqual([bar(1)]);
    await expect(shared).resolves.toEqual([bar(1)]);
  });

  it('fences an old response even if the transport ignores abort and generations reset', async () => {
    const requests: { signal: AbortSignal; resolve: (value: unknown) => void }[] = [];
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((_url: string, init: RequestInit) => new Promise(resolve => {
      requests.push({ signal: init.signal as AbortSignal, resolve });
    }));
    const old = ensureBars('AAPL', '1Min');
    clearBarsStoreForTests();
    expect(requests[0].signal.aborted).toBe(true);
    const next = ensureBars('AAPL', '1Min');
    requests[1].resolve({ ok: true, json: async () => ({ bars: [bar(1)] }) });
    await next;
    requests[0].resolve({ ok: true, json: async () => ({ bars: [bar(0)] }) });
    await expect(old).rejects.toMatchObject({ name: 'AbortError' });
    expect(getBarsEntry('AAPL', '1Min')?.bars).toEqual([bar(1)]);
  });

});
