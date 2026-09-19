import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { clearBarsStoreForTests, ensureBars, getBarsEntry, invalidateBars, setBars, upsertTapePrint10SecBar } from './barsStore';

vi.mock('../ibkr/ibkrStatusPoller', () => ({ getIbkrStatusSnapshot: () => ({ mode: 'sim' }) }));
const future = { t: '2026-09-18T19:00:00Z', o: 10, h: 99, l: 1, c: 50, v: 900 };
const coverage = { asOf: null, completeThrough: null, filling: false, replay: true };
const response = (bars: typeof future[]) => ({ ok: true, json: async () => ({ bars, coverage: { replay: true, replay_mode: 'completed_bars' } }) });

beforeEach(() => { clearBarsStoreForTests(); vi.stubGlobal('fetch', vi.fn()); });
afterEach(() => { vi.unstubAllGlobals(); clearBarsStoreForTests(); });

it('does not restore stale future data when a rewind response arrives last', async () => {
  let resolveOld!: (value: unknown) => void;
  vi.mocked(fetch).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }));
  const old = ensureBars('IMCC', '1Min');
  const rejected = expect(old).rejects.toMatchObject({ name: 'AbortError' });
  invalidateBars('IMCC', '1Min');
  vi.mocked(fetch).mockResolvedValueOnce(response([]) as unknown as Response);
  await ensureBars('IMCC', '1Min');
  resolveOld(response([future]));
  await rejected;
  expect(getBarsEntry('IMCC', '1Min')?.bars).toEqual([]);
});

it('accepts an empty replay result instead of retaining future candles', async () => {
  setBars('IMCC', '1Min', [future], coverage);
  vi.mocked(fetch).mockResolvedValueOnce(response([]) as unknown as Response);
  expect(await ensureBars('IMCC', '1Min')).toEqual([]);
  expect(getBarsEntry('IMCC', '1Min')?.bars).toEqual([]);
});

it('rejects unbounded broker patches and tape changes on a replay-owned chart', () => {
  setBars('IMCC', '10Sec', [], coverage);
  setBars('IMCC', '10Sec', [future]);
  expect(upsertTapePrint10SecBar('IMCC', { time: future.t, price: 99, size: 100 })).toBe(false);
  expect(getBarsEntry('IMCC', '10Sec')?.bars).toEqual([]);
});

it('does not accept a live response after switching into SIM', async () => {
  vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => ({ bars: [future] }) } as Response);
  await expect(ensureBars('IMCC', '1Min')).rejects.toMatchObject({ name: 'AbortError' });
  expect(getBarsEntry('IMCC', '1Min')).toBeNull();
});
